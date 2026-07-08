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
from dataclasses import asdict, dataclass, replace
from pathlib import Path


BASE_URL = os.environ.get("CFIP_BASE_URL", "https://cfip.wxgqlfx.fun")
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "all.txt"))
RAW_OUTPUT_PATH = Path(os.environ.get("RAW_OUTPUT_PATH", "raw.all"))
TOP_OUTPUT_PATH = Path(os.environ.get("TOP_OUTPUT_PATH", "top10.txt"))
TOP_JSON_PATH = Path(os.environ.get("TOP_JSON_PATH", "top10.json"))
LIMIT = int(os.environ.get("CFIP_LIMIT", "10000"))
TOP_PER_COUNTRY = int(os.environ.get("TOP_PER_COUNTRY", "10"))
ENABLE_SPEED_TEST = os.environ.get("ENABLE_SPEED_TEST", "1") != "0"
SPEED_TEST_MODE = os.environ.get("SPEED_TEST_MODE", "proxyip_api")
SPEED_TEST_TIMEOUT = float(os.environ.get("SPEED_TEST_TIMEOUT", "30"))
SPEED_TEST_WORKERS = int(os.environ.get("SPEED_TEST_WORKERS", "20"))
PROXYIP_CHECK_API = os.environ.get("PROXYIP_CHECK_API", "https://api.090227.xyz/check")
ENABLE_CN_API_LATENCY = os.environ.get("ENABLE_CN_API_LATENCY", "1") != "0"
CN_TCPING_API = os.environ.get("CN_TCPING_API", "https://v2.xxapi.cn/api/tcping")
CN_TCPING_WORKERS = int(os.environ.get("CN_TCPING_WORKERS", "8"))
CN_TCPING_TIMEOUT = float(os.environ.get("CN_TCPING_TIMEOUT", "15"))
EXTRA_SOURCES = [
    source.strip()
    for source in os.environ.get("EXTRA_SOURCES", "https://zip.cm.edu.kg/all.txt").split(",")
    if source.strip()
]

# Target scope. Final output is also filtered by checked exit country.
APAC_CODES = {
    "HK",
    "JP",
    "KR",
    "MO",
    "MY",
    "SG",
    "TW",
    "US",
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

COUNTRY_NAME_TO_CODE = {
    "AUSTRALIA": "AU",
    "BANGLADESH": "BD",
    "CHINA": "CN",
    "GERMANY": "DE",
    "HONG KONG": "HK",
    "INDIA": "IN",
    "INDONESIA": "ID",
    "JAPAN": "JP",
    "KAZAKHSTAN": "KZ",
    "KYRGYZSTAN": "KG",
    "MACAO": "MO",
    "MACAU": "MO",
    "MALAYSIA": "MY",
    "PHILIPPINES": "PH",
    "SINGAPORE": "SG",
    "SOUTH KOREA": "KR",
    "TAIWAN": "TW",
    "THAILAND": "TH",
    "UNITED STATES": "US",
    "UZBEKISTAN": "UZ",
    "VIETNAM": "VN",
}


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
    cn_api_latency_ms: int | None = None
    cn_api_source: str = ""

    @property
    def output_country(self):
        return normalize_country_code(self.exit_country) or self.country

    @property
    def line(self):
        latency = f"{self.cn_api_latency_ms}ms" if self.cn_api_latency_ms is not None else ""
        return "#".join([f"{self.ip}:{self.port}", self.output_country, latency]).rstrip("#")


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
    return (
        result.output_country,
        result.cn_api_latency_ms if result.cn_api_latency_ms is not None else 999999,
        result.cf_latency_ms if result.cf_latency_ms is not None else 999999,
        ip_sort_parts(result.ip),
        result.port,
    )


def normalize_country_code(value):
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper().replace("_", " ").replace("-", " ")
    if len(upper) == 2 and upper.isalpha():
        return upper
    return COUNTRY_NAME_TO_CODE.get(upper, upper)


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
        print(f"extra source {source}: +{len(rows) - before} target rows", flush=True)


def score_result(cn_api_latency):
    return cn_api_latency if cn_api_latency is not None else 999999


def parse_latency_ms(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*ms", text)
    if match:
        return int(float(match.group(1)))
    try:
        return int(float(text))
    except ValueError:
        return None


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
        score=999999,
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
        score=999999,
        colo=str(payload.get("colo", "")).strip(),
        exit_ip=str(exit_data.get("ip", "")).strip(),
        exit_country=str(exit_data.get("country", "")).strip(),
        exit_asn=exit_asn,
        exit_org=exit_org,
    )


def test_cn_tcping_api(row):
    query = urllib.parse.urlencode({"address": row.ip, "port": str(row.port)})
    url = f"{CN_TCPING_API}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "cfip-apac-feed/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=CN_TCPING_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    if int(payload.get("code", 0) or 0) != 200:
        return None
    latency = parse_latency_ms((payload.get("data") or {}).get("ping"))
    if latency is None:
        return None

    return ProbeResult(
        ip=row.ip,
        port=row.port,
        country=row.country,
        cf_latency_ms=None,
        score=score_result(latency),
        cn_api_latency_ms=latency,
        cn_api_source=CN_TCPING_API,
    )


def test_candidate(row):
    if SPEED_TEST_MODE == "tcp":
        return test_tcp_latency(row)
    if SPEED_TEST_MODE == "cn_tcping_api":
        return test_cn_tcping_api(row)
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


def enrich_cn_api_latencies(results):
    if not ENABLE_CN_API_LATENCY or not results:
        return []

    print(
        f"CN API tcping latency testing {len(results)} available rows "
        f"(workers={CN_TCPING_WORKERS}, timeout={CN_TCPING_TIMEOUT}s)",
        flush=True,
    )
    by_key = {(result.ip, result.port, result.country): result for result in results}
    enriched = []
    rows = [
        ProxyRow(ip=result.ip, port=result.port, country=result.country)
        for result in results
    ]

    completed = 0
    updated = 0
    with ThreadPoolExecutor(max_workers=CN_TCPING_WORKERS) as executor:
        future_map = {executor.submit(test_cn_tcping_api, row): row for row in rows}
        for future in as_completed(future_map):
            completed += 1
            cn_result = future.result()
            if cn_result is not None:
                key = (cn_result.ip, cn_result.port, cn_result.country)
                current = by_key[key]
                by_key[key] = replace(
                    current,
                    cn_api_latency_ms=cn_result.cn_api_latency_ms,
                    cn_api_source=cn_result.cn_api_source,
                    score=score_result(cn_result.cn_api_latency_ms),
                )
                enriched.append(by_key[key])
                updated += 1
            if completed % 100 == 0 or completed == len(future_map):
                print(f"  CN API tested {completed}/{len(future_map)}, updated={updated}", flush=True)

    return enriched


def select_top_results(results):
    by_country = {}
    for result in sorted(results, key=result_sort_key):
        if result.output_country not in APAC_CODES:
            continue
        by_country.setdefault(result.output_country, []).append(result)

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
    print("stage 2/5: merge and filter target rows")
    rows, total_hint = collect_rows()

    write_lines(OUTPUT_PATH, [row.line for row in sorted(rows, key=row_sort_key)])
    print(f"wrote {len(rows)} unique rows to {OUTPUT_PATH}")

    print("stage 3/5: availability check")
    print("stage 4/5: latency test")
    results = probe_candidates(rows)
    results = enrich_cn_api_latencies(results)

    print("stage 5/5: score and keep top entries per country/region")
    top_results = select_top_results(results)
    write_lines(RAW_OUTPUT_PATH, [result.line for result in sorted(top_results, key=result_sort_key)])
    write_lines(TOP_OUTPUT_PATH, [result.line for result in sorted(top_results, key=result_sort_key)])
    write_json(TOP_JSON_PATH, [asdict(result) for result in sorted(top_results, key=result_sort_key)])
    print(f"wrote {len(top_results)} final rows to {RAW_OUTPUT_PATH}")
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
