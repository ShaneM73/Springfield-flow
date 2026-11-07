"""
Download LODES 8 main OD files (JT02, 2004-2011) for all 50 states + DC into
Data/national/od/, 6 parallel workers, skipping existing files. MO/KS/IL are
read from Data/{st}/od/ (already downloaded) and not fetched again.

Writes outputs/external/national_od_manifest.csv (state, year, bytes, present, path)
and appends to outputs/external/national_od.log.
"""
import concurrent.futures as cf
import csv
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://lehd.ces.census.gov/data/lodes/LODES8"
OUT = os.path.join(ROOT, "Data", "national", "od")
LOCAL = {"mo", "ks", "il"}
STATES = ["al", "ak", "az", "ar", "ca", "co", "ct", "de", "dc", "fl", "ga", "hi", "id", "il",
          "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne",
          "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd",
          "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy"]
YEARS = range(2004, 2012)
LOG = os.path.join(ROOT, "outputs", "external", "national_od.log")
MANIFEST = os.path.join(ROOT, "outputs", "external", "national_od_manifest.csv")


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def path_for(st, yr):
    if st in LOCAL:
        return os.path.join(ROOT, "Data", st, "od", f"{st}_od_main_JT02_{yr}.csv.gz")
    return os.path.join(OUT, f"{st}_od_main_JT02_{yr}.csv.gz")


def fetch(st, yr, tries=4):
    dest = path_for(st, yr)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return st, yr, "exists", os.path.getsize(dest)
    if st in LOCAL:
        return st, yr, "missing-local", 0
    url = f"{BASE}/{st}/od/{st}_od_main_JT02_{yr}.csv.gz"
    tmp = dest + ".part"
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, dest)
            return st, yr, "ok", os.path.getsize(dest)
        except Exception as e:
            if getattr(e, "code", None) == 404:
                if os.path.exists(tmp):
                    os.remove(tmp)
                return st, yr, "404", 0
            if k == tries - 1:
                if os.path.exists(tmp):
                    os.remove(tmp)
                return st, yr, f"error:{e}", 0
            time.sleep(5 * (k + 1))


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    jobs = [(st, yr) for st in STATES for yr in YEARS]
    log(f"download: {len(jobs)} state-years, 6 workers")
    results = {}
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(fetch, st, yr) for st, yr in jobs]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            st, yr, status, nbytes = fut.result()
            results[(st, yr)] = (status, nbytes)
            if status not in ("exists",):
                log(f"[{i}/{len(jobs)}] {st} {yr} {status} {nbytes/1e6:.1f} MB")
    total = sum(b for s, b in results.values())
    log(f"download done in {time.time()-t0:.0f}s; total {total/1e9:.2f} GB; "
        f"ok={sum(s=='ok' for s,_ in results.values())} exists={sum(s=='exists' for s,_ in results.values())} "
        f"404={sum(s=='404' for s,_ in results.values())} "
        f"err={sum(s.startswith('error') for s,_ in results.values())}")
    with open(MANIFEST, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["state", "year", "bytes", "present", "status", "path"])
        for st in STATES:
            for yr in YEARS:
                status, nbytes = results[(st, yr)]
                present = status in ("ok", "exists")
                w.writerow([st, yr, nbytes, int(present), status,
                            os.path.relpath(path_for(st, yr), ROOT) if present else ""])
    log(f"manifest written: {MANIFEST}")


if __name__ == "__main__":
    main()
