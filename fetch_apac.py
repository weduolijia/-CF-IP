import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = os.environ.get("CFIP_BASE_URL", "https://cfip.wxgqlfx.fun")
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "all.txt"))
LIMIT = int(os.environ.get("CFIP_LIMIT", "10000"))

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


def add_proxy(rows, proxy, fallback_country):
    ip = str(proxy.get("ip", "")).strip()
    port = str(proxy.get("port", "")).strip()
    country = str(proxy.get("country", fallback_country)).strip() or fallback_country
    if ip and port:
        rows.add(f"{ip}:{port}#{country}")


def sort_key(line):
    host, _, country = line.partition("#")
    ip, _, port = host.partition(":")
    ip_parts = tuple(int(part) if part.isdigit() else 999 for part in ip.split("."))
    port_key = int(port) if port.isdigit() else 999999
    return ip_parts, port_key, country


def main():
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

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(sorted(rows, key=sort_key)) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} unique rows to {OUTPUT_PATH}")
    if total_hint is not None:
        print(f"api totalProxies hint: {total_hint}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
