"""
Download LODES 8 origin-destination files for the Springfield commuting project.

Run (Python 3.8+, no extra packages):
    python download_lodes.py            # every state in PLAN
    python download_lodes.py mo         # only the listed states

Files go into ./Data/<state>/od/ plus each state's crosswalk and version.txt.
Each OD file and crosswalk is checked against the server's .sha256sum (computed on
the uncompressed CSV); results are written to Data/<state>/sha256_check.tsv.
Re-running skips files already downloaded, so an interrupted run can be resumed.
"""
import gzip
import hashlib
import os
import re
import sys
import time
import urllib.request

BASE = "https://lehd.ces.census.gov/data/lodes/LODES8"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data")

# Missouri: all OD files (main = live and work in MO, aux = live elsewhere, work in MO).
# Neighbours: their aux files hold Missouri residents who work in that state (outbound commuters).
# Kansas and Illinois also need main files, because the Kansas City and St. Louis metros cross the state line.
PLAN = {
    "mo": ["main", "aux"],
    "ks": ["main", "aux"],
    "il": ["main", "aux"],
    "ar": ["aux"], "ok": ["aux"], "ia": ["aux"], "ne": ["aux"], "ky": ["aux"], "tn": ["aux"],
}

# JT00 = all jobs, JT02 = all private jobs (consistent 2002-2023; federal jobs enter JT00 in 2010).
# Add "JT01", "JT03", "JT04", "JT05" here if you want every job type.
JOB_TYPES = ["JT00", "JT02"]

YEARS = range(2002, 2025)  # LODES 8.5 (Oct 2026) covers 2002-2024


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
        except Exception as e:  # network hiccup or a file that does not exist for that year
            if getattr(e, "code", None) == 404:
                return "missing"
            time.sleep(2 * (k + 1))
    return "failed"


def sha_ok(url_gz, dest):
    """Compare sha256 of the uncompressed file with the server's .sha256sum."""
    try:
        with urllib.request.urlopen(url_gz.replace(".csv.gz", ".csv.sha256sum"), timeout=60) as r:
            want = r.read().decode().split()[0]
    except Exception:
        return "nosum"
    h = hashlib.sha256()
    with gzip.open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "match" if h.hexdigest() == want else "MISMATCH"


def listing(state):
    """File names actually present in the state's od/ folder."""
    with urllib.request.urlopen(f"{BASE}/{state}/od/", timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    return set(re.findall(r'href="([a-z]{2}_od_[a-z]+_JT\d\d_\d{4}\.csv\.gz)"', html))


def main():
    summary = {}
    states = sys.argv[1:] or list(PLAN)
    for st in states:
        parts = PLAN[st]
        present = listing(st)
        checks = []
        for part in parts:
            for jt in JOB_TYPES:
                for yr in YEARS:
                    name = f"{st}_od_{part}_{jt}_{yr}.csv.gz"
                    if name not in present:
                        continue
                    url, dest = f"{BASE}/{st}/od/{name}", os.path.join(OUT, st, "od", name)
                    res = fetch(url, dest)
                    chk = sha_ok(url, dest) if res in ("ok", "skip") else "-"
                    checks.append((name, res, chk))
                    summary[res] = summary.get(res, 0) + 1
                    print(f"{res:7s} {chk:8s} {name}", flush=True)
        for extra in [f"{st}_xwalk.csv.gz", "version.txt"]:
            url = f"{BASE}/{st}/{extra}"
            res = fetch(url, os.path.join(OUT, st, extra))
            chk = sha_ok(url, os.path.join(OUT, st, extra)) if extra.endswith(".csv.gz") and res in ("ok", "skip") else "-"
            checks.append((extra, res, chk))
            print(f"{res:7s} {chk:8s} {st}/{extra}", flush=True)
        with open(os.path.join(OUT, st, "sha256_check.tsv"), "w") as f:
            f.write("file\tdownload\tsha256\n")
            f.writelines("\t".join(c) + "\n" for c in checks)
    print("\nDone:", summary)


if __name__ == "__main__":
    main()
