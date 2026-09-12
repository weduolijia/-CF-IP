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
