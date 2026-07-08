# CFIP APAC Feed

Generate an Asia-Pacific `all.txt` feed from `https://cfip.wxgqlfx.fun`.

Output format:

```text
ip:port#CC
```

The script writes:

- `all.txt`: merged APAC feed.
- `top10.txt`: TCP-latency-tested top entries, up to 10 per country/region.

Run locally:

```bash
python fetch_apac.py
```

Optional environment variables:

```bash
CFIP_BASE_URL=https://cfip.wxgqlfx.fun
OUTPUT_PATH=all.txt
TOP_OUTPUT_PATH=top10.txt
CFIP_LIMIT=10000
EXTRA_SOURCES=https://zip.cm.edu.kg/all.txt
TOP_PER_COUNTRY=10
ENABLE_SPEED_TEST=1
SPEED_TEST_TIMEOUT=2.0
SPEED_TEST_WORKERS=80
```

The default country/region scope is controlled by `APAC_CODES` in `fetch_apac.py`.
Remote `EXTRA_SOURCES` should use `ip:port#CC` lines; only APAC country codes are kept.
Latency is measured from the runner that executes the script, so GitHub Actions latency represents GitHub's network, not every user's local route.
