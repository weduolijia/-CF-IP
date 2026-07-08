# CFIP APAC Feed

Generate an Asia-Pacific `all.txt` feed from `https://cfip.wxgqlfx.fun`.

Output format:

```text
ip:port#CC
```

Run locally:

```bash
python fetch_apac.py
```

Optional environment variables:

```bash
CFIP_BASE_URL=https://cfip.wxgqlfx.fun
OUTPUT_PATH=all.txt
CFIP_LIMIT=10000
EXTRA_SOURCES=https://zip.cm.edu.kg/all.txt
```

The default country/region scope is controlled by `APAC_CODES` in `fetch_apac.py`.
Remote `EXTRA_SOURCES` should use `ip:port#CC` lines; only APAC country codes are kept.
