import unittest
from unittest.mock import MagicMock, patch

import fetch_apac as feed


class FeedFallbackTests(unittest.TestCase):
    def test_collect_rows_uses_public_sources_when_primary_api_is_unavailable(self):
        def add_public_row(rows):
            feed.add_row(rows, "198.51.100.10", "443", "HK")

        with (
            patch.object(feed, "EXCLUDE_CLOUDFLARE_IPS", False),
            patch.object(feed, "request_json", side_effect=RuntimeError("DNS lookup failed")),
            patch.object(feed, "add_extra_source_rows", side_effect=add_public_row),
        ):
            rows, total_hint = feed.collect_rows()

        self.assertIsNone(total_hint)
        self.assertEqual(rows, {feed.ProxyRow("198.51.100.10", 443, "HK")})

    def test_collect_rows_uses_cached_candidates_when_all_remote_sources_fail(self):
        cache_path = MagicMock()
        cache_path.exists.return_value = True
        cache_path.read_text.return_value = "198.51.100.20:443#JP\n"

        with (
            patch.object(feed, "OUTPUT_PATH", cache_path),
            patch.object(feed, "EXCLUDE_CLOUDFLARE_IPS", False),
            patch.object(feed, "request_json", side_effect=RuntimeError("DNS lookup failed")),
            patch.object(feed, "add_extra_source_rows"),
        ):
            rows, total_hint = feed.collect_rows()

        self.assertIsNone(total_hint)
        self.assertEqual(rows, {feed.ProxyRow("198.51.100.20", 443, "JP")})

    def test_main_preserves_existing_files_when_no_final_rows_are_available(self):
        with (
            patch.object(
                feed,
                "collect_rows",
                return_value=({feed.ProxyRow("198.51.100.30", 443, "HK")}, None),
            ),
            patch.object(feed, "probe_candidates", return_value=[]),
            patch.object(feed, "enrich_cn_api_latencies", side_effect=lambda results: results),
            patch.object(feed, "write_lines") as write_lines,
            patch.object(feed, "write_json") as write_json,
        ):
            feed.main()

        write_lines.assert_not_called()
        write_json.assert_not_called()

    def test_main_preserves_published_country_coverage(self):
        result = feed.ProbeResult(
            ip="198.51.100.30",
            port=443,
            country="HK",
            cf_latency_ms=10,
            score=10,
            exit_country="HK",
            cn_api_latency_ms=10,
        )
        with (
            patch.object(
                feed,
                "collect_rows",
                return_value=({feed.ProxyRow("198.51.100.30", 443, "HK")}, None),
            ),
            patch.object(feed, "probe_candidates", return_value=[result]),
            patch.object(feed, "enrich_cn_api_latencies", side_effect=lambda results: results),
            patch.object(feed, "output_countries", return_value={"HK", "JP"}),
            patch.object(feed, "write_lines") as write_lines,
            patch.object(feed, "write_json") as write_json,
        ):
            feed.main()

        write_lines.assert_not_called()
        write_json.assert_not_called()


class ExtraSourceTests(unittest.TestCase):
    def test_bestcf_page_sources_are_present_without_duplicate_urls(self):
        expected = {
            "https://bestcf.pages.dev/cmliu2/all.txt",
            "https://cf.junzhen.qzz.io/best_ips_bj.txt",
            "https://raw.githubusercontent.com/svip-s/cloudflare_ip/refs/heads/main/best_ips.txt",
            "https://raw.githubusercontent.com/love-ztm/cfip/refs/heads/main/best_ips.txt",
            "https://raw.githubusercontent.com/love-ztm/cfip/refs/heads/main/ubest_ips.txt",
            "https://raw.githubusercontent.com/cmliu/WorkerVless2sub/refs/heads/main/addressesapi.txt",
            "https://bestcf.pages.dev/tiancheng2/all.txt",
            "https://bestcf.pages.dev/tiancheng3/all.txt",
            "https://raw.githubusercontent.com/Fiatnorm/OptiDomain-Pages/refs/heads/main/optimized_cf_ips.txt",
        }

        self.assertTrue(expected.issubset(set(feed.DEFAULT_EXTRA_SOURCES)))
        self.assertEqual(len(feed.DEFAULT_EXTRA_SOURCES), len(set(feed.DEFAULT_EXTRA_SOURCES)))

    def test_bestcf_country_tagged_line_keeps_region_code(self):
        parsed = feed.parse_extra_source_line(
            "198.51.100.10:443#CM preferred | Hong Kong HK"
        )

        self.assertEqual(parsed, ("198.51.100.10", "443", "HK"))

    def test_extra_sources_skip_non_public_and_duplicate_rows(self):
        source = "https://example.invalid/cmliu2/all.txt"
        text = "\n".join(
            (
                "127.0.0.1:1234#HK",
                "10.0.0.1:443#HK",
                "8.8.8.8:443#HK",
                "8.8.8.8:443#HK",
                "not-an-ip:443#HK",
            )
        )
        rows = set()

        with (
            patch.object(feed, "EXTRA_SOURCES", [source, source]),
            patch.object(feed, "fetch_text", return_value=text),
            patch.object(feed, "is_cloudflare_ip", return_value=False),
        ):
            feed.add_extra_source_rows(rows)

        self.assertEqual(rows, {feed.ProxyRow("8.8.8.8", 443, "HK")})


class LatencyModeTests(unittest.TestCase):
    def test_external_latency_enrichment_is_enabled_by_default(self):
        self.assertTrue(feed.ENABLE_CN_API_LATENCY)

    def test_explicitly_disabled_external_latency_keeps_cloudflare_measurements(self):
        rows = [feed.ProbeResult("198.51.100.39", 443, "HK", 12, 999999)]
        with (
            patch.object(feed, "ENABLE_CN_API_LATENCY", False),
            patch.object(feed, "test_latency_api") as test_latency_api,
        ):
            enriched = feed.enrich_cn_api_latencies(rows)

        self.assertIs(enriched, rows)
        test_latency_api.assert_not_called()

    def test_request_start_limiter_spaces_requests(self):
        limiter = feed.RequestStartLimiter(4)
        with (
            patch.object(feed.time, "monotonic", side_effect=[10.0, 10.0]),
            patch.object(feed.time, "sleep") as sleep,
        ):
            limiter.wait()
            limiter.wait()

        sleep.assert_called_once_with(0.25)

    def test_single_mode_uses_only_the_primary_latency_api(self):
        rows = [
            feed.ProbeResult("198.51.100.40", 443, "HK", 10, 999999),
            feed.ProbeResult("198.51.100.41", 443, "JP", 20, 999999),
        ]
        calls = []

        def fake_latency(row, api_name, api_url, timeout):
            calls.append((api_name, api_url))
            return feed.ProbeResult(
                row.ip,
                row.port,
                row.country,
                None,
                5,
                cn_api_latency_ms=5,
                cn_api_source=api_url,
            )

        with (
            patch.object(feed, "ENABLE_CN_API_LATENCY", True),
            patch.object(feed, "LATENCY_GROUP_MODE", "single"),
            patch.object(feed, "CN_TCPING_API", "https://latency.example/api"),
            patch.object(feed, "test_latency_api", side_effect=fake_latency),
        ):
            enriched = feed.enrich_cn_api_latencies(rows)

        self.assertEqual(len(enriched), len(rows))
        self.assertEqual(calls, [("A", "https://latency.example/api")] * len(rows))

    def test_single_mode_sends_every_available_row_to_domestic_tcping(self):
        rows = [
            feed.ProbeResult(f"198.51.100.{index}", 443, "HK", index, 999999)
            for index in range(1, 13)
        ]
        calls = []

        def fake_latency(row, api_name, api_url, timeout):
            calls.append((row.ip, row.port, api_name, api_url))
            return feed.ProbeResult(
                row.ip,
                row.port,
                row.country,
                None,
                1,
                cn_api_latency_ms=1,
                cn_api_source=api_url,
            )

        with (
            patch.object(feed, "ENABLE_CN_API_LATENCY", True),
            patch.object(feed, "LATENCY_GROUP_MODE", "single"),
            patch.object(feed, "CN_TCPING_API", "https://latency.example/api"),
            patch.object(feed, "CN_TCPING_MAX_QPS", 0),
            patch.object(feed, "test_latency_api", side_effect=fake_latency),
        ):
            enriched = feed.enrich_cn_api_latencies(rows)

        self.assertEqual(len(enriched), len(rows))
        self.assertEqual(
            {(ip, port) for ip, port, _, _ in calls},
            {(row.ip, row.port) for row in rows},
        )

    def test_select_top_results_keeps_ten_lowest_domestic_latencies_per_region(self):
        results = []
        for country, third_octet in (("HK", 100), ("JP", 101)):
            for latency in range(12):
                results.append(
                    feed.ProbeResult(
                        ip=f"198.51.{third_octet}.{latency + 1}",
                        port=443,
                        country=country,
                        cf_latency_ms=999,
                        score=latency,
                        exit_country=country,
                        cn_api_latency_ms=latency,
                    )
                )

        selected = feed.select_top_results(results)

        self.assertEqual(len(selected), 20)
        for country in ("HK", "JP"):
            latencies = [
                item.cn_api_latency_ms
                for item in selected
                if item.output_country == country
            ]
            self.assertEqual(latencies, list(range(10)))

    def test_two_mode_requires_an_explicit_second_latency_api(self):
        row = feed.ProbeResult("198.51.100.42", 443, "HK", 10, 999999)
        with (
            patch.object(feed, "ENABLE_CN_API_LATENCY", True),
            patch.object(feed, "LATENCY_GROUP_MODE", "two"),
            patch.object(feed, "LATENCY_API_B", ""),
        ):
            with self.assertRaisesRegex(RuntimeError, "LATENCY_API_B"):
                feed.enrich_cn_api_latencies([row])
