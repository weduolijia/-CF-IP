import csv
import json
import ipaddress
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
LATENCY_API_A = os.environ.get("LATENCY_API_A", "https://v2.xxapi.cn/api/tcping")
LATENCY_API_B = os.environ.get("LATENCY_API_B", "https://api.jaxing.cc/v2/Tcping")
LATENCY_API_C = os.environ.get("LATENCY_API_C", "https://jkapi.com/api/zz_tcping")
LATENCY_WORKERS_A = int(os.environ.get("LATENCY_WORKERS_A", "8"))
LATENCY_WORKERS_B = int(os.environ.get("LATENCY_WORKERS_B", "8"))
LATENCY_WORKERS_C = int(os.environ.get("LATENCY_WORKERS_C", "8"))
LATENCY_TIMEOUT_A = float(os.environ.get("LATENCY_TIMEOUT_A", str(CN_TCPING_TIMEOUT)))
LATENCY_TIMEOUT_B = float(os.environ.get("LATENCY_TIMEOUT_B", str(CN_TCPING_TIMEOUT)))
LATENCY_TIMEOUT_C = float(os.environ.get("LATENCY_TIMEOUT_C", str(CN_TCPING_TIMEOUT)))
CF_IPS_V4_URL = os.environ.get("CF_IPS_V4_URL", "https://www.cloudflare.com/ips-v4")
CF_IPS_V6_URL = os.environ.get("CF_IPS_V6_URL", "https://www.cloudflare.com/ips-v6")
EXCLUDE_CLOUDFLARE_IPS = os.environ.get("EXCLUDE_CLOUDFLARE_IPS", "1") != "0"
ALLOW_UNKNOWN_EXTRA_SOURCE_COUNTRY = os.environ.get("ALLOW_UNKNOWN_EXTRA_SOURCE_COUNTRY", "0") == "1"
DEFAULT_EXTRA_SOURCES = [
    "https://zip.cm.edu.kg/all.txt",
    "https://bestcf.pages.dev/cmliu/all.txt",
    "https://bestcf.pages.dev/luoli/all.txt",
    "https://bestcf.pages.dev/s5gy/all.txt",
    "https://bestcf.pages.dev/lzj/all.txt",
    "https://bestcf.pages.dev/tiancheng/all.txt",
    "https://bestcf.pages.dev/tiancheng/hk.txt",
    "https://bestcf.pages.dev/tiancheng/sg.txt",
    "https://bestcf.pages.dev/tiancheng/jp.txt",
    "https://bestcf.pages.dev/tiancheng/kr.txt",
    "https://bestcf.pages.dev/tiancheng/us.txt",
    "https://bestcf.pages.dev/moistr/all.txt",
    # BestIP feeds from bestcf.pages.dev and Junzhen's mirror.
    "https://bestcf.pages.dev/wetest/ipv4.txt",
    "https://bestcf.pages.dev/uouin/all.txt",
    "https://bestcf.pages.dev/xinyitang3/ipv4.txt",
    "https://bestcf.pages.dev/cfyes/ipv4.txt",
    "https://bestcf.pages.dev/gslege/Cfxyz.txt",
    "https://cf.junzhen.qzz.io/best_ips.txt",
    "https://bestcf.pages.dev/zhixuanwang/ipv4-onlyip.txt",
    # Additional BestIP feeds supplied by the user.
    "https://bestcf.pages.dev/vvhan/ipv4.txt",
    "https://bestcf.pages.dev/nirevil/ipv4.txt",
    "https://raw.githubusercontent.com/ymyuuu/IPDB/main/BestCF/bestcfv4.txt",
    "https://raw.githubusercontent.com/yuanxiawan/cfipv4db/main/cfip.txt",
    "https://bestcf.pages.dev/lajiao/all.txt",
    "https://bestcf.pages.dev/kristi/all.txt",
    "https://raw.githubusercontent.com/joname1/BestCFip/main/ipv4.txt",
    "https://raw.githubusercontent.com/LancelotRar/best-cf-ips/main/best-cf-ipv4.txt",
    "https://raw.githubusercontent.com/Senflare/Senflare-IP/main/IPlist-Pro.txt",
    "https://raw.githubusercontent.com/Senflare/Senflare-IP/main/Senflare-Pro.txt",
    "https://raw.githubusercontent.com/JieChaoCC/cf-ip-auto/main/data/ipapi.txt",
    "https://raw.githubusercontent.com/ahang39/router/main/all.txt",
    "https://bestcf.pages.dev/ircf/ipv4.txt",
    "https://raw.githubusercontent.com/einsitang/my-fast-cf-ip/master/fastips.txt",
    "https://raw.githubusercontent.com/hubbylei/bestcf/main/bestcf.txt",
    "https://bestcf.pages.dev/yutian/all.txt",
    "https://raw.githubusercontent.com/gshtwy/CF-DNS-Clone/main/wetest-cloudflare-v4.txt",
    # Additional public feeds: country-tagged ProxyIP lists, CSV results,
    # and IPDB's country-aware proxy list.
    "https://raw.githubusercontent.com/wanwushequ/ProxyIP/main/HK-TOP10.txt",
    "https://raw.githubusercontent.com/wanwushequ/ProxyIP/main/JP-TOP10.txt",
    "https://raw.githubusercontent.com/wanwushequ/ProxyIP/main/KR-TOP10.txt",
    "https://raw.githubusercontent.com/wanwushequ/ProxyIP/main/SG-TOP10.txt",
    "https://raw.githubusercontent.com/wanwushequ/ProxyIP/main/TW-TOP10.txt",
    "https://raw.githubusercontent.com/wanwushequ/ProxyIP/main/US-TOP10.txt",
    "https://raw.githubusercontent.com/xgonce/Cloudflare_IP/main/result.csv",
    "https://raw.githubusercontent.com/ymyuuu/IPDB/main/BestProxy/bestproxy%26country.txt",
]
ALLOW_UNKNOWN_SOURCE_HINTS = (
    "bestcf.pages.dev/wetest/",
    "bestcf.pages.dev/uouin/",
    "bestcf.pages.dev/xinyitang3/",
    "bestcf.pages.dev/cfyes/",
    "bestcf.pages.dev/gslege/",
    "cf.junzhen.qzz.io/",
    "bestcf.pages.dev/zhixuanwang/",
    "bestcf.pages.dev/vvhan/",
    "bestcf.pages.dev/nirevil/",
    "bestcf.pages.dev/lajiao/",
    "bestcf.pages.dev/kristi/",
    "bestcf.pages.dev/ircf/",
    "bestcf.pages.dev/yutian/",
    "raw.githubusercontent.com/ymyuuu/IPDB/",
    "raw.githubusercontent.com/yuanxiawan/cfipv4db/",
    "raw.githubusercontent.com/joname1/BestCFip/",
    "raw.githubusercontent.com/LancelotRar/best-cf-ips/",
    "raw.githubusercontent.com/Senflare/Senflare-IP/",
    "raw.githubusercontent.com/JieChaoCC/cf-ip-auto/",
    "raw.githubusercontent.com/ahang39/router/",
    "raw.githubusercontent.com/einsitang/my-fast-cf-ip/",
    "raw.githubusercontent.com/hubbylei/bestcf/",
    "raw.githubusercontent.com/gshtwy/CF-DNS-Clone/",
)
EXTRA_SOURCES = [
    source.strip()
    for source in os.environ.get("EXTRA_SOURCES", ",".join(DEFAULT_EXTRA_SOURCES)).split(",")
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

IP_PORT_RE = re.compile(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(?::(\d{1,5}))?(?![\d.])")
COUNTRY_CODE_RE = re.compile(r"(?<![A-Z])(?:TW|HK|MO|SG|MY|KR|JP|US)(?![A-Z])")
HASH_COUNTRY_CODE_RE = re.compile(r"#\s*([A-Za-z]{2})(?=\s*(?:$|\||,))")
PIPE_COUNTRY_CODE_RE = re.compile(r"(?:^|\|)\s*([A-Z]{2})(?=\s*(?:\||$))")

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

COUNTRY_HINTS = {
    "香港": "HK",
    "港岛": "HK",
    "港島": "HK",
    "澳门": "MO",
    "澳門": "MO",
    "台湾": "TW",
    "台灣": "TW",
    "新加坡": "SG",
    "马来西亚": "MY",
    "馬來西亞": "MY",
    "韩国": "KR",
    "韓國": "KR",
    "日本": "JP",
    "美国": "US",
    "美國": "US",
}

CF_IP_NETWORKS = None


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


def fetch_cloudflare_networks():
    networks = []
    for url in (CF_IPS_V4_URL, CF_IPS_V6_URL):
        try:
            text = fetch_text(url)
        except RuntimeError as exc:
            print(f"warning: failed to fetch Cloudflare IP ranges from {url}: {exc}", flush=True)
            continue
        for line in text.splitlines():
            value = line.strip()
            if not value:
                continue
            try:
                networks.append(ipaddress.ip_network(value, strict=False))
            except ValueError:
                print(f"warning: ignored invalid Cloudflare range: {value}", flush=True)
    return networks


def get_cloudflare_networks():
    global CF_IP_NETWORKS
    if not EXCLUDE_CLOUDFLARE_IPS:
        return []
    if CF_IP_NETWORKS is None:
        CF_IP_NETWORKS = fetch_cloudflare_networks()
        print(f"loaded {len(CF_IP_NETWORKS)} Cloudflare IP ranges", flush=True)
    return CF_IP_NETWORKS


def is_cloudflare_ip(ip):
    if not EXCLUDE_CLOUDFLARE_IPS:
        return False
    networks = get_cloudflare_networks()
    if not networks:
        return False
    try:
        address = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return False
    return any(address in network for network in networks)


def add_row(rows, ip, port, country):
    try:
        port_number = int(str(port).strip())
    except ValueError:
        return
    if not (1 <= port_number <= 65535):
        return

    ip = str(ip).strip()
    country = str(country).strip().upper()
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return
    if ip and country and not is_cloudflare_ip(ip):
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


def infer_country_from_text(text):
    upper = str(text or "").upper().replace("_", " ").replace("-", " ")
    match = HASH_COUNTRY_CODE_RE.search(upper)
    if match:
        return match.group(1)
    match = COUNTRY_CODE_RE.search(upper)
    if match:
        return match.group(0)
    for name, code in COUNTRY_NAME_TO_CODE.items():
        if name in upper:
            return code
    for hint, code in COUNTRY_HINTS.items():
        if hint in text:
            return code
    match = PIPE_COUNTRY_CODE_RE.search(upper)
    if match:
        return match.group(1)
    return ""


def parse_extra_source_line(line, fallback_country=""):
    match = IP_PORT_RE.search(line)
    if not match:
        return None
    ip, port = match.groups()
    port = port or "443"
    country = infer_country_from_text(line) or normalize_country_code(fallback_country) or "ZZ"
    return ip, port, country


def parse_csv_source(text):
    """Parse xgonce/Cloudflare_IP's CSV while tolerating UTF-8 BOM and headers."""
    text = text.lstrip("\ufeff")
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if "IP" not in first_line or "端口" not in first_line:
        return []
    rows = []
    reader = csv.DictReader(text.splitlines())
    for item in reader:
        ip = str(item.get("IP", "")).strip()
        port = str(item.get("端口", "")).strip() or "443"
        country = normalize_country_code(item.get("CF归属国", "")) or "ZZ"
        if ip:
            rows.append((ip, port, country))
    return rows


def source_country_hint(source):
    name = urllib.parse.unquote(urllib.parse.urlparse(source).path)
    return infer_country_from_text(name)


def add_extra_source_rows(rows):
    for source in EXTRA_SOURCES:
        before = len(rows)
        skipped_cf = 0
        skipped_region = 0
        try:
            text = fetch_text(source)
        except RuntimeError as exc:
            print(f"warning: failed to fetch extra source {source}: {exc}", flush=True)
            continue

        parsed_rows = parse_csv_source(text)
        if not parsed_rows:
            fallback_country = source_country_hint(source)
            parsed_rows = [
                parsed
                for line in text.splitlines()
                if (parsed := parse_extra_source_line(line, fallback_country))
            ]

        allow_unknown = ALLOW_UNKNOWN_EXTRA_SOURCE_COUNTRY or any(
            hint in source for hint in ALLOW_UNKNOWN_SOURCE_HINTS
        )
        for parsed in parsed_rows:
            if not parsed:
                continue
            ip, port, country = parsed
            if is_cloudflare_ip(ip):
                skipped_cf += 1
                continue
            if country == "ZZ" and not allow_unknown:
                skipped_region += 1
                continue
            if country != "ZZ" and country not in APAC_CODES:
                skipped_region += 1
                continue
            add_row(rows, ip, port, country)
        print(
            f"extra source {source}: +{len(rows) - before} target rows "
            f"(skipped_cf={skipped_cf}, skipped_region={skipped_region})",
            flush=True,
        )


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


def parse_latency_payload(payload):
    if isinstance(payload, dict):
        data = payload.get("data") or {}
        if payload.get("code") not in (None, 200, "200", "ok", "OK"):
            return None
        values = [data.get("ping"), data.get("平均延迟"), payload.get("ping")]
        for value in values:
            latency = parse_latency_ms(value)
            if latency is not None:
                return latency
    return parse_latency_ms(payload)


def test_latency_api(row, api_name, api_url, timeout):
    if api_name == "A":
        params = {"address": row.ip, "port": str(row.port)}
    else:
        params = {"host": row.ip, "port": str(row.port)}
    url = f"{api_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "cfip-apac-feed/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw
    latency = parse_latency_payload(payload)
    if latency is None:
        return None

    return ProbeResult(
        ip=row.ip,
        port=row.port,
        country=row.country,
        cf_latency_ms=None,
        score=score_result(latency),
        cn_api_latency_ms=latency,
        cn_api_source=api_url,
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
        return results

    print(
        f"three independent latency groups for {len(results)} available rows",
        flush=True,
    )
    configs = [
        ("A", LATENCY_API_A, LATENCY_WORKERS_A, LATENCY_TIMEOUT_A),
        ("B", LATENCY_API_B, LATENCY_WORKERS_B, LATENCY_TIMEOUT_B),
        ("C", LATENCY_API_C, LATENCY_WORKERS_C, LATENCY_TIMEOUT_C),
    ]
    # Sort before round-robin splitting so the same IP:port stays in the same
    # independent API group across runs.
    ordered_results = sorted(results, key=lambda item: (item.ip, item.port, item.country))
    groups = [ordered_results[index::3] for index in range(3)]

    def run_group(group, config):
        api_name, api_url, workers, timeout = config
        print(
            f"  group {api_name}: {len(group)} rows -> {api_url} "
            f"(workers={workers}, timeout={timeout}s)",
            flush=True,
        )
        output = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    test_latency_api,
                    ProxyRow(result.ip, result.port, result.country),
                    api_name,
                    api_url,
                    timeout,
                ): result
                for result in group
            }
            completed = 0
            for future in as_completed(future_map):
                completed += 1
                measured = future.result()
                if measured is not None:
                    original = future_map[future]
                    output.append(
                        replace(
                            original,
                            cn_api_latency_ms=measured.cn_api_latency_ms,
                            cn_api_source=f"group-{api_name}:{api_url}",
                            score=score_result(measured.cn_api_latency_ms),
                        )
                    )
                if completed % 100 == 0 or completed == len(future_map):
                    print(
                        f"    group {api_name}: tested {completed}/{len(future_map)}, "
                        f"updated={len(output)}",
                        flush=True,
                    )
        return output

    merged = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_group, group, config) for group, config in zip(groups, configs)]
        for future in as_completed(futures):
            merged.extend(future.result())
    print(f"merged latency results: {len(merged)} rows from 3 independent groups", flush=True)
    return merged


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
