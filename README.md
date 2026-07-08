# CFIP APAC Feed

Generate an Asia-Pacific `all.txt` feed from `https://cfip.wxgqlfx.fun`.

Pipeline:

```text
pull IP sources -> merge/filter -> availability check -> latency test -> per-country Top10
```

`all.txt` output format:

```text
ip:port#CC
```

The script writes:

- `all.txt`: merged APAC feed.
- `top10.txt`: available and latency-ranked top entries, up to 10 per country/region.
- `top10.json`: structured metadata for scoring and future three-network latency fields.

`top10.txt` output format:

```text
ip:port#CC#cf=12ms#score=12
```

Run locally:

```bash
python fetch_apac.py
```

Optional environment variables:

```bash
CFIP_BASE_URL=https://cfip.wxgqlfx.fun
OUTPUT_PATH=all.txt
TOP_OUTPUT_PATH=top10.txt
TOP_JSON_PATH=top10.json
CFIP_LIMIT=10000
EXTRA_SOURCES=https://zip.cm.edu.kg/all.txt
TOP_PER_COUNTRY=10
ENABLE_SPEED_TEST=1
SPEED_TEST_MODE=proxyip_api
SPEED_TEST_TIMEOUT=30
SPEED_TEST_WORKERS=20
PROXYIP_CHECK_API=https://api.090227.xyz/check
```

The default country/region scope is controlled by `APAC_CODES` in `fetch_apac.py`.
Remote `EXTRA_SOURCES` should use `ip:port#CC` lines; only APAC country codes are kept.
By default, latency is measured with the same style as `check.proxyip.cmliussss.net`: the script calls a Cloudflare-side ProxyIP check API and ranks successful results by `responseTime`.
Set `SPEED_TEST_MODE=tcp` to use local TCP connect latency from the runner instead.
