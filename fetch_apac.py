import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path


BASE_URL = os.environ.get("CFIP_BASE_URL", "https://cfip.wxgqlfx.fun")
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "all.txt"))
TOP_OUTPUT_PATH = Path(os.environ.get("TOP_OUTPUT_PATH", "top10.txt"))
TOP_JSON_PATH = Path(os.environ.get("TOP_JSON_PATH", "top10.json"))
LIMIT = int(os.environ.get("CFIP_LIMIT", "10000"))
TOP_PER_COUNTRY = int(os.environ.get("TOP_PER_COUNTRY", "10"))
ENABLE_SPEED_TEST = os.environ.get("ENABLE_SPEED_TEST", "1") != "0"
SPEED_TEST_MODE = os.environ.get("SPEED_TEST_MODE", "proxyip_api")
SPEED_TEST_TIMEOUT = float(os.environ.get("SPEED_TEST_TIMEOUT", "30"))
SPEED_TEST_WORKERS = int(os.environ.get("SPEED_TEST_WORKERS", "20"))
PROXYIP_CHECK_API = os.environ.get("PROXYIP_CHECK_API", "https://api.090227.xyz/check")
EXTRA_SOURCES = [
    source.strip()
    for source in os.environ.get("EXTRA_SOURCES", "https://zip.cm.edu.kg/all.txt").split(",")
    if source.strip()
]

# Asia-Pacific-ish scope based on what /api/countries currently exposes.
# Edit this set if you want a narrower or wider feed.
APAC_CODES = {
    "AU",
    "BD",
    "CN",
    "HK",
    "ID",
    "IN",
    "JP",
    "KG",
    "KR",
    "KZ",
    "MY",
    "PH",
    "SG",
    "TH",
    "UZ",
    "VN",
}

COMMON_CF_PORTS = {
    "80",
    "443",
    "2052",
    "2053",
    "2082",
    "2083",
    "2086",
    "2087",
    "2095",
    "2096",
    "8080",
    "8443",
    "8880",
}

APAC_LINE_RE = re.compile(r"^\s*([0-9A-Fa-f:.]+):(\d{1,5})#([A-Za-z0-9/_-]+)")


@dataclass(frozen=True)
class ProxyRow:
    ip: str
    port: int
    country: str

    @property
    def line(self):
        return f"{self.ip}:{self.port}#{self.country}"


@dataclass(frozen=True)
class ProbeResult:
    ip: str
    port: int
    country: str
    cf_latency_ms: int | None
    score: int
    colo: str = ""
    exit_ip: str = ""
    exit_country: str = ""
    exit_asn: str = ""
    exit_org: str = ""
    ct_latency_ms: int | None = None
    cu_latency_ms: int | None = None
    cm_latency_ms: int | None = None

    @property
    def line(self):
        parts = [f"{self.ip}:{self.port}", self.country]
        if self.cf_latency_ms is not None:
            parts.append(f"cf={self.cf_latency_ms}ms")
        if self.ct_latency_ms is not None:
            parts.append(f"ct={self.ct_latency_ms}ms")
        if self.cu_latency_ms is not None:
            parts.append(f"cu={self.cu_latency_ms}ms")
        if self.cm_latency_ms is not None:
            parts.append(f"cm={self.cm_latency_ms}ms")
        parts.append(f"score={self.score}")
        return "#".join(parts)


def request_json(path, method="GET", body=None, retries=3):
    data = None
    headers = {"User-Agent": "cfip-apac-feed/1.0"}
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"request failed for {path}: {last_error}")


def fetch_text(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "cfip-apac-feed/1.0"})
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"request failed for {url}: {last_error}")


def add_row(rows, ip, port, country):
    try:
        port_number = int(str(port).strip())
    except ValueError:
        return
    if not (1 <= port_number <= 65535):
        return

    ip = str(ip).strip()
    country = str(country).strip().upper()
    if ip and country:
        rows.add(ProxyRow(ip=ip, port=port_number, country=country))


def add_proxy(rows, proxy, fallback_country):
    ip = str(proxy.get("ip", "")).strip()
    port = str(proxy.get("port", "")).strip()
    country = str(proxy.get("country", fallback_country)).strip() or fallback_country
    if ip and port:
        add_row(rows, ip, port, country)


def ip_sort_parts(ip):
    return tuple(int(part) if part.isdigit() else 999 for part in ip.split("."))


def row_sort_key(row):
    return row.country, ip_sort_parts(row.ip), row.port


def result_sort_key(result):
    return result.country, result.score, result.cf_latency_ms or 999999, ip_sort_parts(result.ip), result.port


def add_extra_source_rows(rows):
    for source in EXTRA_SOURCES:
        before = len(rows)
        text = fetch_text(source)
        for line in text.splitlines():
            match = APAC_LINE_RE.match(line)
            if not match:
                continue
            ip, port, country = match.groups()
            country = country.upper()
            if country in APAC_CODES:
                add_row(rows, ip, port, country)
        print(f"extra source {source}: +{len(rows) - before} APAC rows", flush=True)


def score_result(cf_latency, ct_latency=None, cu_latency=None, cm_latency=None):
    # Lower is better. CF latency is the baseline because it is always available
    # after ProxyIP validation. Three-network latencies can be added later.
    score = cf_latency if cf_latency is not None else 999999
    for latency in (ct_latency, cu_latency, cm_latency):
        if latency is not None:
            score += latency
    return int(score)


def first_exit(payload):
    probe_results = payload.get("probe_results") or {}
    for stack in ("ipv4", "ipv6"):
        probe = probe_results.get(stack) or {}
        if probe.get("ok") and probe.get("exit"):
            return probe["exit"]
    return {}


def test_tcp_latency(row):
    start = time.perf_counter()
    try:
        with socket.create_connection((row.ip, row.port), timeout=SPEED_TEST_TIMEOUT):
            latency_ms = int((time.perf_counter() - start) * 1000)
    except OSError:
        return None

    return ProbeResult(
        ip=row.ip,
        port=row.port,
        country=row.country,
        cf_latency_ms=latency_ms,
        score=score_result(latency_ms),
    )


def test_proxyip_api_latency(row):
    query = urllib.parse.urlencode({"proxyip": f"{row.ip}:{row.port}"})
    url = f"{PROXYIP_CHECK_API}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "cfip-apac-feed/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=SPEED_TEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    if not payload.get("success"):
        return None
    try:
        cf_latency = int(float(payload.get("responseTime")))
    except (TypeError, ValueError):
        return None

    exit_data = first_exit(payload)
    exit_asn = str(exit_data.get("asn", "")).strip()
    exit_org = str(exit_data.get("asOrganization") or exit_data.get("org") or "").strip()

    return ProbeResult(
        ip=row.ip,
        port=row.port,
        country=row.country,
        cf_latency_ms=cf_latency,
        score=score_result(cf_latency),
        colo=str(payload.get("colo", "")).strip(),
        exit_ip=str(exit_data.get("ip", "")).strip(),
        exit_country=str(exit_data.get("country", "")).strip(),
        exit_asn=exit_asn,
        exit_org=exit_org,
    )


def test_candidate(row):
    if SPEED_TEST_MODE == "tcp":
        return test_tcp_latency(row)
    return test_proxyip_api_latency(row)


def probe_candidates(rows):
    if not ENABLE_SPEED_TEST:
        print("speed test disabled; treating sorted rows as available", flush=True)
        return [
            ProbeResult(row.ip, row.port, row.country, None, 999999)
            for row in sorted(rows, key=row_sort_key)
        ]

    print(
        f"availability + latency testing {len(rows)} rows with {SPEED_TEST_MODE} "
        f"(workers={SPEED_TEST_WORKERS}, timeout={SPEED_TEST_TIMEOUT}s)",
        flush=True,
    )
    results = []
    with ThreadPoolExecutor(max_workers=SPEED_TEST_WORKERS) as executor:
        future_map = {executor.submit(test_candidate, row): row for row in rows}
        completed = 0
        for future in as_completed(future_map):
            completed += 1
            result = future.result()
            if result is not None:
                results.append(result)
            if completed % 100 == 0 or completed == len(future_map):
                print(f"  tested {completed}/{len(future_map)}, available={len(results)}", flush=True)
    return results


def select_top_results(results):
    by_country = {}
    for result in sorted(results, key=result_sort_key):
        by_country.setdefault(result.country, []).append(result)

    top_results = [
        result
        for country in sorted(by_country)
        for result in by_country[country][:TOP_PER_COUNTRY]
    ]
    print(f"selected {len(top_results)} top rows from {len(results)} available rows", flush=True)
    return top_results


def collect_rows():
    countries = request_json("/api/countries")
    available = {country["code"] for country in countries}
    selected = sorted(APAC_CODES & available)
    missing = sorted(APAC_CODES - available)

    rows = set()
    ports_by_country = {}
    capped_countries = []
    total_hint = None

    print(f"selected countries: {', '.join(selected)}")
    if missing:
        print(f"missing from API: {', '.join(missing)}")

    for index, code in enumerate(selected, 1):
        payload = {"country": code, "port": "", "limit": LIMIT}
        data = request_json("/api/query", method="POST", body=payload)
        proxies = data.get("proxies", [])
        total_hint = data.get("totalProxies", total_hint)

        if len(proxies) >= 250:
            capped_countries.append(code)

        for proxy in proxies:
            add_proxy(rows, proxy, code)
            port = str(proxy.get("port", "")).strip()
            if port:
                ports_by_country.setdefault(code, set()).add(port)

        print(f"[{index:02d}/{len(selected)}] {code}: {len(proxies)} rows", flush=True)
        time.sleep(0.05)

    for code in capped_countries:
        ports = sorted(
            ports_by_country.get(code, set()) | COMMON_CF_PORTS,
            key=lambda value: int(value) if value.isdigit() else 999999,
        )
        before = len(rows)
        print(f"{code}: port backfill candidates: {len(ports)}", flush=True)
        for port in ports:
            payload = {"country": code, "port": port, "limit": LIMIT}
            data = request_json("/api/query", method="POST", body=payload)
            for proxy in data.get("proxies", []):
                add_proxy(rows, proxy, code)
            time.sleep(0.03)
        print(f"{code}: +{len(rows) - before} rows after backfill", flush=True)

    add_extra_source_rows(rows)
    return rows, total_hint


def write_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    print("stage 1/5: pull IP sources")
    print("stage 2/5: merge and filter APAC rows")
    rows, total_hint = collect_rows()

    write_lines(OUTPUT_PATH, [row.line for row in sorted(rows, key=row_sort_key)])
    print(f"wrote {len(rows)} unique rows to {OUTPUT_PATH}")

    print("stage 3/5: availability check")
    print("stage 4/5: latency test")
    results = probe_candidates(rows)

    print("stage 5/5: score and keep top entries per country/region")
    top_results = select_top_results(results)
    write_lines(TOP_OUTPUT_PATH, [result.line for result in sorted(top_results, key=result_sort_key)])
    write_json(TOP_JSON_PATH, [asdict(result) for result in sorted(top_results, key=result_sort_key)])
    print(f"wrote {len(top_results)} top rows to {TOP_OUTPUT_PATH}")
    print(f"wrote {len(top_results)} top JSON rows to {TOP_JSON_PATH}")

    if total_hint is not None:
        print(f"api totalProxies hint: {total_hint}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
