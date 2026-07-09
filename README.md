# CFIP Target Region Feed

Generate a filtered ProxyIP feed from `https://cfip.wxgqlfx.fun`.

Pipeline:

```text
pull IP sources -> region filter -> availability check -> API tcping latency -> per-country Top10 -> raw.all
```

`all.txt` output format:

```text
ip:port#CC
```

The script writes:

- `all.txt`: merged target-region feed.
- `raw.all`: final feed, up to 10 API-latency-ranked entries per exit country/region.
- `top10.txt`: same text output as `raw.all`.
- `top10.json`: structured metadata.

`raw.all` output format:

```text
ip:port#CC#51ms
```

`CC` in `raw.all` is the ProxyIP exit country/region reported by the availability check, not the source/input country label.

Run locally:

```bash
python fetch_apac.py
```

Optional environment variables:

```bash
CFIP_BASE_URL=https://cfip.wxgqlfx.fun
OUTPUT_PATH=all.txt
RAW_OUTPUT_PATH=raw.all
TOP_OUTPUT_PATH=top10.txt
TOP_JSON_PATH=top10.json
CFIP_LIMIT=10000
EXTRA_SOURCES=https://zip.cm.edu.kg/all.txt,https://bestcf.pages.dev/cmliu/all.txt,https://bestcf.pages.dev/luoli/all.txt,https://bestcf.pages.dev/s5gy/all.txt,https://bestcf.pages.dev/lzj/all.txt,https://bestcf.pages.dev/tiancheng/all.txt,https://bestcf.pages.dev/tiancheng/hk.txt,https://bestcf.pages.dev/tiancheng/sg.txt,https://bestcf.pages.dev/tiancheng/jp.txt,https://bestcf.pages.dev/tiancheng/kr.txt,https://bestcf.pages.dev/tiancheng/us.txt,https://bestcf.pages.dev/moistr/all.txt
EXCLUDE_CLOUDFLARE_IPS=1
ALLOW_UNKNOWN_EXTRA_SOURCE_COUNTRY=0
CF_IPS_V4_URL=https://www.cloudflare.com/ips-v4
CF_IPS_V6_URL=https://www.cloudflare.com/ips-v6
TOP_PER_COUNTRY=10
ENABLE_SPEED_TEST=1
SPEED_TEST_MODE=proxyip_api
SPEED_TEST_TIMEOUT=30
SPEED_TEST_WORKERS=20
PROXYIP_CHECK_API=https://api.090227.xyz/check
ENABLE_CN_API_LATENCY=1
CN_TCPING_API=https://v2.xxapi.cn/api/tcping
CN_TCPING_WORKERS=8
CN_TCPING_TIMEOUT=15
```

The default country/region scope is controlled by `APAC_CODES` in `fetch_apac.py`; the current scope is `TW`, `HK`, `MO`, `SG`, `MY`, `KR`, `JP`, and `US`.
Remote `EXTRA_SOURCES` can use `ip:port#CC`, BestCF-style text lines, or any line where the first usable candidate is `ip:port`.
Cloudflare-owned IP ranges are excluded before candidates are written to `all.txt`.
Extra-source rows without a detectable country/region are skipped by default.
By default, availability is checked with the same style as `check.proxyip.cmliussss.net`: the script calls a Cloudflare-side ProxyIP check API.
After that, only rows that also return a latency from the configured TCPing API are kept.
Final ranking uses `cn_api_latency_ms` only, and final output is filtered again by the checked exit country/region.
