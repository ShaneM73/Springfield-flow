"""Download LODES 8 WAC files (S000, JT02) with firm-age / firm-size columns for MO, KS, IL.

    python scripts/10_firmsize_download.py              # 2011-2024
    python scripts/10_firmsize_download.py 2002 2010    # a year range

Files go to Data/<st>/wac/<st>_wac_S000_JT02_<year>.csv.gz. Existing non-empty files are skipped,
so the script can be re-run to resume. Nothing else under Data/ is touched.
"""
import os
import sys
import time
import urllib.request

from config import RAW

BASE = "https://lehd.ces.census.gov/data/lodes/LODES8"
STATES = ["mo", "ks", "il"]


def fetch(url, dest, tries=4):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "skip"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, dest)
            return "ok"
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return "missing"
            time.sleep(2 * (k + 1))
    return "failed"


def main(y0=2011, y1=2024):
    for st in STATES:
        for year in range(y0, y1 + 1):
            name = f"{st}_wac_S000_JT02_{year}.csv.gz"
            status = fetch(f"{BASE}/{st}/wac/{name}", str(RAW / st / "wac" / name))
            print(f"{status:8s} {name}", flush=True)


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    main(*args) if args else main()
