import csv
import json
import ipaddress
impor t os
import re
import socket
import sys
impor t time
import urllib.error
import urllib.pars e
import urllib.request
from concurrent.futur es import ThreadPoolExecutor, as_completed
fr om dataclasses import asdict, dataclass, repl ace
from pathlib import Path


BASE_URL = os. environ.get("CFIP_BASE_URL", "https://cfip.wx gqlfx.fun")
OUTPUT_PATH = Path(os.environ.get ("OUTPUT_PATH", "all.txt"))
RAW_OUTPUT_PATH =  Path(os.environ.get("RAW_OUTPUT_PATH", "raw. all"))
TOP_OUTPUT_PATH = Path(os.environ.get( "TOP_OUTPUT_PATH", "top10.txt"))
TOP_JSON_PAT H = Path(os.environ.get("TOP_JSON_PATH", "top 10.json"))
LIMIT = int(os.environ.get("CFIP_L IMIT", "10000"))
TOP_PER_COUNTRY = int(os.env iron.get("TOP_PER_COUNTRY", "10"))
ENABLE_SPE ED_TEST = os.environ.get("ENABLE_SPEED_TEST",  "1") != "0"
SPEED_TEST_MODE = os.environ.get ("SPEED_TEST_MODE", "proxyip_api")
SPEED_TEST _TIMEOUT = float(os.environ.get("SPEED_TEST_T IMEOUT", "30"))
SPEED_TEST_WORKERS = int(os.e nviron.get("SPEED_TEST_WORKERS", "20"))
PROXY IP_CHECK_API = os.environ.get("PROXYIP_CHECK_ API", "https://api.090227.xyz/check")
ENABLE_ CN_API_LATENCY = os.environ.get("ENABLE_CN_AP I_LATENCY", "1") != "0"
CN_TCPING_API = os.en viron.get("CN_TCPING_API", "https://v2.xxapi. cn/api/tcping")
CN_TCPING_WORKERS = int(os.en viron.get("CN_TCPING_WORKERS", "8"))
CN_TCPIN G_TIMEOUT = float(os.environ.get("CN_TCPING_T IMEOUT", "15"))
CF_IPS_V4_URL = os.environ.ge t("CF_IPS_V4_URL", "https://www.cloudflare.co m/ips-v4")
CF_IPS_V6_URL = os.environ.get("CF _IPS_V6_URL", "https://www.cloudflare.com/ips -v6")
EXCLUDE_CLOUDFLARE_IPS = os.environ.get ("EXCLUDE_CLOUDFLARE_IPS", "1") != "0"
ALLOW_ UNKNOWN_EXTRA_SOURCE_COUNTRY = os.environ.get ("ALLOW_UNKNOWN_EXTRA_SOURCE_COUNTRY", "0") = = "1"
DEFAULT_EXTRA_SOURCES = [
    "https:// zip.cm.edu.kg/all.txt",
    "https://bestcf.p ages.dev/cmliu/all.txt",
    "https://bestcf. pages.dev/luoli/all.txt",
    "https://bestcf .pages.dev/s5gy/all.txt",
    "https://bestcf .pages.dev/lzj/all.txt",
    "https://bestcf. pages.dev/tiancheng/all.txt",
    "https://be stcf.pages.dev/tiancheng/hk.txt",
    "https: //bestcf.pages.dev/tiancheng/sg.txt",
    "ht tps://bestcf.pages.dev/tiancheng/jp.txt",
     "https://bestcf.pages.dev/tiancheng/kr.txt", 
    "https://bestcf.pages.dev/tiancheng/us.t xt",
    "https://bestcf.pages.dev/moistr/all .txt",
    # Additional public feeds: country -tagged ProxyIP lists, CSV results,
    # and  IPDB's country-aware proxy list.
    "https: //raw.githubusercontent.com/wanwushequ/ProxyI P/main/HK-TOP10.txt",
    "https://raw.github usercontent.com/wanwushequ/ProxyIP/main/JP-TO P10.txt",
    "https://raw.githubusercontent. com/wanwushequ/ProxyIP/main/KR-TOP10.txt",
     "https://raw.githubusercontent.com/wanwushe qu/ProxyIP/main/SG-TOP10.txt",
    "https://r aw.githubusercontent.com/wanwushequ/ProxyIP/m ain/TW-TOP10.txt",
    "https://raw.githubuse rcontent.com/wanwushequ/ProxyIP/main/US-TOP10 .txt",
    "https://raw.githubusercontent.com /xgonce/Cloudflare_IP/main/result.csv",
    " https://raw.githubusercontent.com/ymyuuu/IPDB /main/BestProxy/bestproxy%26country.txt",
     "https://raw.githubusercontent.com/weduoliji a/cf-subscription-parser/main/proxyip.txt",
] 
EXTRA_SOURCES = [
    source.strip()
    for  source in os.environ.get("EXTRA_SOURCES", ", ".join(DEFAULT_EXTRA_SOURCES)).split(",")
     if source.strip()
]

# Target scope. Final o utput is also filtered by checked exit countr y.
APAC_CODES = {
    "HK",
    "JP",
    "KR ",
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
    "888 0",
}

IP_PORT_RE = re.compile(r"(?<![\d.])(( ?:\d{1,3}\.){3}\d{1,3})(?::(\d{1,5}))?(?![\d. ])")
COUNTRY_CODE_RE = re.compile(r"(?<![A-Z] )(?:TW|HK|MO|SG|MY|KR|JP|US)(?![A-Z])")
HASH_ COUNTRY_CODE_RE = re.compile(r"#\s*([A-Za-z]{ 2})(?=\s*(?:$|\||,))")
PIPE_COUNTRY_CODE_RE =  re.compile(r"(?:^|\|)\s*([A-Z]{2})(?=\s*(?:\ ||$))")

COUNTRY_NAME_TO_CODE = {
    "AUSTRA LIA": "AU",
    "BANGLADESH": "BD",
    "CHIN A": "CN",
    "GERMANY": "DE",
    "HONG KONG ": "HK",
    "INDIA": "IN",
    "INDONESIA":  "ID",
    "JAPAN": "JP",
    "KAZAKHSTAN": "K Z",
    "KYRGYZSTAN": "KG",
    "MACAO": "MO" ,
    "MACAU": "MO",
    "MALAYSIA": "MY",
     "PHILIPPINES": "PH",
    "SINGAPORE": "SG", 
    "SOUTH KOREA": "KR",
    "TAIWAN": "TW", 
    "THAILAND": "TH",
    "UNITED STATES": " US",
    "UZBEKISTAN": "UZ",
    "VIETNAM": " VN",
}

COUNTRY_HINTS = {
    "香港": "HK", 
    "港岛": "HK",
    "港島": "HK",
     "澳门": "MO",
    "澳門": "MO",
    "台� ��": "TW",
    "台灣": "TW",
    "新加坡 ": "SG",
    "马来西亚": "MY",
    "馬� �西亞": "MY",
    "韩国": "KR",
    "韓� ��": "KR",
    "日本": "JP",
    "美国":  "US",
    "美國": "US",
}

CF_IP_NETWORKS =  None


@dataclass(frozen=True)
class ProxyRo w:
    ip: str
    port: int
    country: str 

    @property
    def line(self):
        r eturn f"{self.ip}:{self.port}#{self.country}" 


@dataclass(frozen=True)
class ProbeResult: 
    ip: str
    port: int
    country: str
     cf_latency_ms: int | None
    score: int
     colo: str = ""
    exit_ip: str = ""
    e xit_country: str = ""
    exit_asn: str = ""
     exit_org: str = ""
    ct_latency_ms: int  | None = None
    cu_latency_ms: int | None  = None
    cm_latency_ms: int | None = None
     cn_api_latency_ms: int | None = None
    c n_api_source: str = ""

    @property
    def  output_country(self):
        return normali ze_country_code(self.exit_country) or self.co untry

    @property
    def line(self):
         latency = f"{self.cn_api_latency_ms}ms" i f self.cn_api_latency_ms is not None else ""
         return "#".join([f"{self.ip}:{self.po rt}", self.output_country, latency]).rstrip(" #")


def request_json(path, method="GET", bo dy=None, retries=3):
    data = None
    head ers = {"User-Agent": "cfip-apac-feed/1.0"}
     if body is not None:
        data = json.du mps(body, separators=(",", ":")).encode("utf- 8")
        headers["Content-Type"] = "applic ation/json"

    req = urllib.request.Request (BASE_URL + path, data=data, headers=headers,  method=method)
    last_error = None
    for  attempt in range(retries):
        try:
             with urllib.request.urlopen(req, time out=25) as response:
                return j son.loads(response.read().decode("utf-8"))
         except (urllib.error.URLError, TimeoutE rror, json.JSONDecodeError) as exc:
             last_error = exc
            time.sleep(0. 8 * (attempt + 1))
    raise RuntimeError(f"r equest failed for {path}: {last_error}")


de f fetch_text(url, retries=3):
    req = urlli b.request.Request(url, headers={"User-Agent":  "cfip-apac-feed/1.0"})
    last_error = None 
    for attempt in range(retries):
        t ry:
            with urllib.request.urlopen(r eq, timeout=30) as response:
                 return response.read().decode("utf-8", errors ="replace")
        except (urllib.error.URLE rror, TimeoutError) as exc:
            last_ error = exc
            time.sleep(0.8 * (att empt + 1))
    raise RuntimeError(f"request f ailed for {url}: {last_error}")


def fetch_c loudflare_networks():
    networks = []
    f or url in (CF_IPS_V4_URL, CF_IPS_V6_URL):
         try:
            text = fetch_text(url)
         except RuntimeError as exc:
             print(f"warning: failed to fetch Cloudflar e IP ranges from {url}: {exc}", flush=True)
             continue
        for line in text. splitlines():
            value = line.strip( )
            if not value:
                c ontinue
            try:
                netw orks.append(ipaddress.ip_network(value, stric t=False))
            except ValueError:
                 print(f"warning: ignored invalid  Cloudflare range: {value}", flush=True)
    r eturn networks


def get_cloudflare_networks( ):
    global CF_IP_NETWORKS
    if not EXCLU DE_CLOUDFLARE_IPS:
        return []
    if C F_IP_NETWORKS is None:
        CF_IP_NETWORKS  = fetch_cloudflare_networks()
        print( f"loaded {len(CF_IP_NETWORKS)} Cloudflare IP  ranges", flush=True)
    return CF_IP_NETWORK S


def is_cloudflare_ip(ip):
    if not EXCL UDE_CLOUDFLARE_IPS:
        return False
     networks = get_cloudflare_networks()
    if n ot networks:
        return False
    try:
         address = ipaddress.ip_address(str(ip). strip())
    except ValueError:
        retur n False
    return any(address in network for  network in networks)


def add_row(rows, ip,  port, country):
    try:
        port_number  = int(str(port).strip())
    except ValueErr or:
        return
    if not (1 <= port_numb er <= 65535):
        return

    ip = str(ip ).strip()
    country = str(country).strip(). upper()
    try:
        ipaddress.ip_address (ip)
    except ValueError:
        return
     if ip and country and not is_cloudflare_ip( ip):
        rows.add(ProxyRow(ip=ip, port=po rt_number, country=country))


def add_proxy( rows, proxy, fallback_country):
    ip = str( proxy.get("ip", "")).strip()
    port = str(p roxy.get("port", "")).strip()
    country = s tr(proxy.get("country", fallback_country)).st rip() or fallback_country
    if ip and port: 
        add_row(rows, ip, port, country)


d ef ip_sort_parts(ip):
    return tuple(int(pa rt) if part.isdigit() else 999 for part in ip .split("."))


def row_sort_key(row):
    ret urn row.country, ip_sort_parts(row.ip), row.p ort


def result_sort_key(result):
    return  (
        result.output_country,
        res ult.cn_api_latency_ms if result.cn_api_latenc y_ms is not None else 999999,
        result. cf_latency_ms if result.cf_latency_ms is not  None else 999999,
        ip_sort_parts(resul t.ip),
        result.port,
    )


def norma lize_country_code(value):
    text = str(valu e or "").strip()
    if not text:
        ret urn ""
    upper = text.upper().replace("_",  " ").replace("-", " ")
    if len(upper) == 2  and upper.isalpha():
        return upper
     return COUNTRY_NAME_TO_CODE.get(upper, uppe r)


def infer_country_from_text(text):
    u pper = str(text or "").upper().replace("_", "  ").replace("-", " ")
    match = HASH_COUNTR Y_CODE_RE.search(upper)
    if match:
         return match.group(1)
    match = COUNTRY_CO DE_RE.search(upper)
    if match:
        ret urn match.group(0)
    for name, code in COUN TRY_NAME_TO_CODE.items():
        if name in  upper:
            return code
    for hint,  code in COUNTRY_HINTS.items():
        if hin t in text:
            return code
    match  = PIPE_COUNTRY_CODE_RE.search(upper)
    if m atch:
        return match.group(1)
    retur n ""


def parse_extra_source_line(line, fall back_country=""):
    match = IP_PORT_RE.sear ch(line)
    if not match:
        return Non e
    ip, port = match.groups()
    port = po rt or "443"
    country = infer_country_from_ text(line) or normalize_country_code(fallback _country) or "ZZ"
    return ip, port, countr y


def parse_csv_source(text):
    """Parse  xgonce/Cloudflare_IP's CSV while tolerating U TF-8 BOM and headers."""
    text = text.lstr ip("\ufeff")
    first_line = next((line for  line in text.splitlines() if line.strip()), " ")
    if "IP" not in first_line or "端口"  not in first_line:
        return []
    rows  = []
    reader = csv.DictReader(text.splitl ines())
    for item in reader:
        ip =  str(item.get("IP", "")).strip()
        port  = str(item.get("端口", "")).strip() or "443 "
        country = normalize_country_code(it em.get("CF归属国", "")) or "ZZ"
        if  ip:
            rows.append((ip, port, count ry))
    return rows


def source_country_hin t(source):
    name = urllib.parse.unquote(ur llib.parse.urlparse(source).path)
    return  infer_country_from_text(name)


def add_extra _source_rows(rows):
    for source in EXTRA_S OURCES:
        before = len(rows)
        sk ipped_cf = 0
        skipped_region = 0
         try:
            text = fetch_text(source) 
        except RuntimeError as exc:
             print(f"warning: failed to fetch extra so urce {source}: {exc}", flush=True)
             continue

        parsed_rows = parse_csv_s ource(text)
        if not parsed_rows:
             fallback_country = source_country_hint (source)
            parsed_rows = [
                 parsed
                for line in te xt.splitlines()
                if (parsed :=  parse_extra_source_line(line, fallback_count ry))
            ]

        for parsed in par sed_rows:
            if not parsed:
                 continue
            ip, port, countr y = parsed
            if is_cloudflare_ip(ip ):
                skipped_cf += 1
                 continue
            if country == "ZZ"  and not ALLOW_UNKNOWN_EXTRA_SOURCE_COUNTRY:
                 skipped_region += 1
                 continue
            if country != "ZZ " and country not in APAC_CODES:
                 skipped_region += 1
                conti nue
            add_row(rows, ip, port, count ry)
        print(
            f"extra source  {source}: +{len(rows) - before} target rows  "
            f"(skipped_cf={skipped_cf}, ski pped_region={skipped_region})",
            f lush=True,
        )


def score_result(cn_ap i_latency):
    return cn_api_latency if cn_a pi_latency is not None else 999999


def pars e_latency_ms(value):
    if value is None:
         return None
    text = str(value).strip ().lower()
    match = re.search(r"(\d+(?:\.\ d+)?)\s*ms", text)
    if match:
        retu rn int(float(match.group(1)))
    try:
         return int(float(text))
    except ValueErr or:
        return None


def first_exit(payl oad):
    probe_results = payload.get("probe_ results") or {}
    for stack in ("ipv4", "ip v6"):
        probe = probe_results.get(stack ) or {}
        if probe.get("ok") and probe. get("exit"):
            return probe["exit"] 
    return {}


def test_tcp_latency(row):
     start = time.perf_counter()
    try:
         with socket.create_connection((row.ip, row .port), timeout=SPEED_TEST_TIMEOUT):
             latency_ms = int((time.perf_counter() - s tart) * 1000)
    except OSError:
        ret urn None

    return ProbeResult(
        ip= row.ip,
        port=row.port,
        countr y=row.country,
        cf_latency_ms=latency_ ms,
        score=999999,
    )


def test_pr oxyip_api_latency(row):
    query = urllib.pa rse.urlencode({"proxyip": f"{row.ip}:{row.por t}"})
    url = f"{PROXYIP_CHECK_API}?{query} "
    req = urllib.request.Request(url, heade rs={"User-Agent": "cfip-apac-feed/1.0"})
     try:
        with urllib.request.urlopen(req,  timeout=SPEED_TEST_TIMEOUT) as response:
             payload = json.loads(response.read() .decode("utf-8"))
    except (urllib.error.UR LError, TimeoutError, json.JSONDecodeError, O SError):
        return None

    if not payl oad.get("success"):
        return None
    t ry:
        cf_latency = int(float(payload.ge t("responseTime")))
    except (TypeError, Va lueError):
        return None

    exit_data  = first_exit(payload)
    exit_asn = str(exi t_data.get("asn", "")).strip()
    exit_org =  str(exit_data.get("asOrganization") or exit_ data.get("org") or "").strip()

    return Pr obeResult(
        ip=row.ip,
        port=ro w.port,
        country=row.country,
         cf_latency_ms=cf_latency,
        score=99999 9,
        colo=str(payload.get("colo", "")). strip(),
        exit_ip=str(exit_data.get("i p", "")).strip(),
        exit_country=str(ex it_data.get("country", "")).strip(),
         exit_asn=exit_asn,
        exit_org=exit_org, 
    )


def test_cn_tcping_api(row):
    que ry = urllib.parse.urlencode({"address": row.i p, "port": str(row.port)})
    url = f"{CN_TC PING_API}?{query}"
    req = urllib.request.R equest(url, headers={"User-Agent": "cfip-apac -feed/1.0"})
    try:
        with urllib.req uest.urlopen(req, timeout=CN_TCPING_TIMEOUT)  as response:
            payload = json.loads (response.read().decode("utf-8"))
    except  (urllib.error.URLError, TimeoutError, json.JS ONDecodeError, OSError):
        return None
 
    if int(payload.get("code", 0) or 0) != 2 00:
        return None
    latency = parse_l atency_ms((payload.get("data") or {}).get("pi ng"))
    if latency is None:
        return  None

    return ProbeResult(
        ip=row. ip,
        port=row.port,
        country=ro w.country,
        cf_latency_ms=None,
         score=score_result(latency),
        cn_api _latency_ms=latency,
        cn_api_source=CN _TCPING_API,
    )


def test_candidate(row): 
    if SPEED_TEST_MODE == "tcp":
        ret urn test_tcp_latency(row)
    if SPEED_TEST_M ODE == "cn_tcping_api":
        return test_c n_tcping_api(row)
    return test_proxyip_api _latency(row)


def probe_candidates(rows):
     if not ENABLE_SPEED_TEST:
        print("s peed test disabled; treating sorted rows as a vailable", flush=True)
        return [
             ProbeResult(row.ip, row.port, row.coun try, None, 999999)
            for row in sor ted(rows, key=row_sort_key)
        ]

    pr int(
        f"availability + latency testing  {len(rows)} rows with {SPEED_TEST_MODE} "
         f"(workers={SPEED_TEST_WORKERS}, timeou t={SPEED_TEST_TIMEOUT}s)",
        flush=True ,
    )
    results = []
    with ThreadPoolE xecutor(max_workers=SPEED_TEST_WORKERS) as ex ecutor:
        future_map = {executor.submit (test_candidate, row): row for row in rows}
         completed = 0
        for future in as _completed(future_map):
            completed  += 1
            result = future.result()
             if result is not None:
                 results.append(result)
            if com pleted % 100 == 0 or completed == len(future_ map):
                print(f"  tested {compl eted}/{len(future_map)}, available={len(resul ts)}", flush=True)
    return results


def e nrich_cn_api_latencies(results):
    if not E NABLE_CN_API_LATENCY or not results:
         return []

    print(
        f"CN API tcping  latency testing {len(results)} available row s "
        f"(workers={CN_TCPING_WORKERS}, t imeout={CN_TCPING_TIMEOUT}s)",
        flush= True,
    )
    by_key = {(result.ip, result. port, result.country): result for result in r esults}
    enriched = []
    rows = [
         ProxyRow(ip=result.ip, port=result.port, co untry=result.country)
        for result in r esults
    ]

    completed = 0
    updated =  0
    with ThreadPoolExecutor(max_workers=CN _TCPING_WORKERS) as executor:
        future_ map = {executor.submit(test_cn_tcping_api, ro w): row for row in rows}
        for future i n as_completed(future_map):
            compl eted += 1
            cn_result = future.resu lt()
            if cn_result is not None:
                 key = (cn_result.ip, cn_result. port, cn_result.country)
                curr ent = by_key[key]
                by_key[key]  = replace(
                    current,
                     cn_api_latency_ms=cn_result.c n_api_latency_ms,
                    cn_api_ source=cn_result.cn_api_source,
                     score=score_result(cn_result.cn_api_la tency_ms),
                )
                 enriched.append(by_key[key])
                 updated += 1
            if completed % 100 = = 0 or completed == len(future_map):
                 print(f"  CN API tested {completed}/{ len(future_map)}, updated={updated}", flush=T rue)

    return enriched


def select_top_re sults(results):
    by_country = {}
    for r esult in sorted(results, key=result_sort_key) :
        if result.output_country not in APA C_CODES:
            continue
        by_coun try.setdefault(result.output_country, []).app end(result)

    top_results = [
        resu lt
        for country in sorted(by_country)
         for result in by_country[country][:TO P_PER_COUNTRY]
    ]
    print(f"selected {le n(top_results)} top rows from {len(results)}  available rows", flush=True)
    return top_r esults


def collect_rows():
    countries =  request_json("/api/countries")
    available  = {country["code"] for country in countries}
     selected = sorted(APAC_CODES & available) 
    missing = sorted(APAC_CODES - available) 

    rows = set()
    ports_by_country = {}
     capped_countries = []
    total_hint = No ne

    print(f"selected countries: {', '.joi n(selected)}")
    if missing:
        print( f"missing from API: {', '.join(missing)}")

     for index, code in enumerate(selected, 1): 
        payload = {"country": code, "port":  "", "limit": LIMIT}
        data = request_js on("/api/query", method="POST", body=payload) 
        proxies = data.get("proxies", [])
         total_hint = data.get("totalProxies", t otal_hint)

        if len(proxies) >= 250:
             capped_countries.append(code)

         for proxy in proxies:
            add_pr oxy(rows, proxy, code)
            port = str (proxy.get("port", "")).strip()
            i f port:
                ports_by_country.setd efault(code, set()).add(port)

        print( f"[{index:02d}/{len(selected)}] {code}: {len( proxies)} rows", flush=True)
        time.sle ep(0.05)

    for code in capped_countries:
         ports = sorted(
            ports_by_c ountry.get(code, set()) | COMMON_CF_PORTS,
             key=lambda value: int(value) if val ue.isdigit() else 999999,
        )
        b efore = len(rows)
        print(f"{code}: por t backfill candidates: {len(ports)}", flush=T rue)
        for port in ports:
            p ayload = {"country": code, "port": port, "lim it": LIMIT}
            data = request_json(" /api/query", method="POST", body=payload)
             for proxy in data.get("proxies", []) :
                add_proxy(rows, proxy, code )
            time.sleep(0.03)
        print( f"{code}: +{len(rows) - before} rows after ba ckfill", flush=True)

    add_extra_source_ro ws(rows)
    return rows, total_hint


def wr ite_lines(path, lines):
    path.parent.mkdir (parents=True, exist_ok=True)
    path.write_ text("\n".join(lines) + "\n", encoding="utf-8 ")


def write_json(path, payload):
    path. parent.mkdir(parents=True, exist_ok=True)
     path.write_text(json.dumps(payload, ensure_a scii=False, indent=2) + "\n", encoding="utf-8 ")


def main():
    print("stage 1/5: pull I P sources")
    print("stage 2/5: merge and f ilter target rows")
    rows, total_hint = co llect_rows()

    write_lines(OUTPUT_PATH, [r ow.line for row in sorted(rows, key=row_sort_ key)])
    print(f"wrote {len(rows)} unique r ows to {OUTPUT_PATH}")

    print("stage 3/5:  availability check")
    print("stage 4/5: l atency test")
    results = probe_candidates( rows)
    results = enrich_cn_api_latencies(r esults)

    print("stage 5/5: score and keep  top entries per country/region")
    top_res ults = select_top_results(results)
    write_ lines(RAW_OUTPUT_PATH, [result.line for resul t in sorted(top_results, key=result_sort_key) ])
    write_lines(TOP_OUTPUT_PATH, [result.l ine for result in sorted(top_results, key=res ult_sort_key)])
    write_json(TOP_JSON_PATH,  [asdict(result) for result in sorted(top_res ults, key=result_sort_key)])
    print(f"wrot e {len(top_results)} final rows to {RAW_OUTPU T_PATH}")
    print(f"wrote {len(top_results) } top rows to {TOP_OUTPUT_PATH}")
    print(f "wrote {len(top_results)} top JSON rows to {T OP_JSON_PATH}")

    if total_hint is not Non e:
        print(f"api totalProxies hint: {to tal_hint}")


if __name__ == "__main__":
     try:
        main()
    except Exception as e xc:
        print(f"ERROR: {exc}", file=sys.s tderr)
        sys.exit(1)
 