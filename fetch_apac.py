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
from dataclasses import dataclass
from pathlib import Path


BASE_URL = os.environ.get("CFIP_BASE_URL", "https://cfip.wxgqlfx.fun")
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "all.txt"))
TOP_OUTPUT_PATH = Path(os.environ.get("TOP_OUTPUT_PATH", "top10.txt"))
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
    latency_ms: int | None = None

    @property
    def line(self):
        return f"{self.ip}:{self.port}#{self.country}"

    @property
    def latency_line(self):
        if self.latency_ms is None:
            return self.line
        return f"{self.line}#{self.latency_ms}ms"


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


def sort_key(row):
    return row.country, ip_sort_parts(row.ip), row.port


def latency_sort_key(row):
    latency = row.latency_ms if row.latency_ms is not None else 999999
    return row.country, latency, ip_sort_parts(row.ip), row.port


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


def test_tcp_latency(row):
    start = time.perf_counter()
    try:
        with socket.create_connection((row.ip, row.port), timeout=SPEED_TEST_TIMEOUT):
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ProxyRow(row.ip, row.port, row.country, latency_ms)
    except OSError:
        return None


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
        latency_ms = int(float(payload.get("responseTime")))
    except (TypeError, ValueError):
        return None
    return ProxyRow(row.ip, row.port, row.country, latency_ms)


def test_latency(row):
    if SPEED_TEST_MODE == "tcp":
        return test_tcp_latency(row)
    return test_proxyip_api_latency(row)


def select_top_rows(rows):
    if not ENABLE_SPEED_TEST:
        print("speed test disabled; top file will use sorted first rows", flush=True)
        by_country = {}
        for row in sorted(rows, key=sort_key):
            by_country.setdefault(row.country, []).append(row)
        return [
            row
            for country in sorted(by_country)
            for row in by_country[country][:TOP_PER_COUNTRY]
        ]

    print(
        f"speed testing {len(rows)} rows with {SPEED_TEST_MODE} "
        f"(workers={SPEED_TEST_WORKERS}, timeout={SPEED_TEST_TIMEOUT}s)",
        flush=True,
    )
    tested = []
    with ThreadPoolExecutor(max_workers=SPEED_TEST_WORKERS) as executor:
        future_map = {executor.submit(test_latency, row): row for row in rows}
        completed = 0
        for future in as_completed(future_map):
            completed += 1
            result = future.result()
            if result is not None:
                tested.append(result)
            if completed % 100 == 0 or completed == len(future_map):
                print(f"  tested {completed}/{len(future_map)}, alive={len(tested)}", flush=True)

    by_country = {}
    for row in sorted(tested, key=latency_sort_key):
        by_country.setdefault(row.country, []).append(row)

    top_rows = [
        row
        for country in sorted(by_country)
        for row in by_country[country][:TOP_PER_COUNTRY]
    ]
    print(f"selected {len(top_rows)} top rows from {len(tested)} reachable rows", flush=True)
    return top_rows


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


def main():
    rows, total_hint = collect_rows()

    write_lines(OUTPUT_PATH, [row.line for row in sorted(rows, key=sort_key)])
    print(f"wrote {len(rows)} unique rows to {OUTPUT_PATH}")

    top_rows = select_top_rows(rows)
    write_lines(TOP_OUTPUT_PATH, [row.latency_line for row in sorted(top_rows, key=latency_sort_key)])
    print(f"wrote {len(top_rows)} top rows to {TOP_OUTPUT_PATH}")

    if total_hint is not None:
        print(f"api totalProxies hint: {total_hint}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
