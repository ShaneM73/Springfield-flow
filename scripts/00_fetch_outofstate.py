"""Fetch Missouri residents who work in other states (other states' aux files) plus the block
coordinates needed for out-of-state ends.

Raw out-of-state aux files are NOT stored (only the rows we need). Each file is streamed into memory,
its SHA-256 (on the uncompressed CSV) is checked against the server's .sha256sum, and only rows with a
home block in Missouri, Kansas or Illinois (HOME_STATES; the states our metros touch) are kept.

Outputs
  parquet/oos/res_outofstate.parquet     : year, jt, w_state + all OD columns, rows with home in HOME_STATES
  parquet/oos/oos_blocks.parquet         : block, state, county, county name, cbsa, cbsa name, lat, lon,
                                           for every out-of-state block that appears in an MO-related flow
                                           (workplaces of MO residents; homes of MO aux workers)
  parquet/oos/oos_county_centroids.parquet : unweighted mean block point per out-of-state county
  outputs/manifest_outofstate.csv        : per file: bytes, rows total, rows kept, S000 kept, sha256 status
"""
import concurrent.futures as cf
import datetime as dt
import gzip
import hashlib
import io
import re
import time
import urllib.request

import duckdb
import pandas as pd

from config import PARQUET, OUT, YEARS

BASE = "https://lehd.ces.census.gov/data/lodes/LODES8"
HOME_STATES = ("29", "20", "17")    # MO, KS, IL
DST = PARQUET / "oos"
UA = {"User-Agent": "springfield-flow-research/1.0"}


def get(url, tries=5):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(3 * (k + 1))
    raise RuntimeError(f"failed: {url}")


def states():
    html = get(f"{BASE}/").decode()
    return sorted(set(re.findall(r'href="([a-z]{2})/"', html)) - {"mo", "us", "pr"})


def one(st, jt, yr, present):
    name = f"{st}_od_aux_{jt}_{yr}.csv.gz"
    if name not in present:
        return dict(file=name, status="absent")
    gz = get(f"{BASE}/{st}/od/{name}")
    raw = gzip.decompress(gz)
    want = get(f"{BASE}/{st}/od/{name.replace('.csv.gz', '.csv.sha256sum')}")
    sha = "nosum" if want is None else ("match" if hashlib.sha256(raw).hexdigest() == want.decode().split()[0] else "MISMATCH")
    df = pd.read_csv(io.BytesIO(raw), dtype={"w_geocode": str, "h_geocode": str, "createdate": str})
    keep = df[df.h_geocode.str[:2].isin(HOME_STATES)].copy()
    keep.insert(0, "w_state", st); keep.insert(0, "jt", jt); keep.insert(0, "year", yr)
    return dict(file=name, status="ok", bytes=len(gz), rows=len(df), rows_kept=len(keep),
                S000_kept=int(keep.S000.sum()), sha256=sha, createdate=";".join(sorted(df.createdate.unique())),
                fetched=dt.date.today().isoformat(), data=keep)


def main():
    DST.mkdir(parents=True, exist_ok=True)
    sts = states()
    listing = {}
    for st in sts:
        html = get(f"{BASE}/{st}/od/").decode()
        listing[st] = set(re.findall(r'href="([a-z]{2}_od_aux_JT0[02]_\d{4}\.csv\.gz)"', html))
    jobs = [(st, jt, yr) for st in sts for jt in ("JT00", "JT02") for yr in YEARS]
    print(f"{len(sts)} states, {len(jobs)} candidate files", flush=True)
    res = []
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(one, st, jt, yr, listing[st]): (st, jt, yr) for st, jt, yr in jobs}
        for i, f in enumerate(cf.as_completed(futs)):
            r = f.result(); res.append(r)
            if i % 100 == 0:
                print(i, r["file"], r["status"], r.get("rows_kept"), flush=True)
    data = pd.concat([r.pop("data") for r in res if "data" in r], ignore_index=True)
    data.to_parquet(DST / "res_outofstate.parquet", compression="zstd", index=False)
    man = pd.DataFrame(res).sort_values("file")
    man.to_csv(OUT / "manifest_outofstate.csv", index=False)
    print(man.status.value_counts().to_dict(), man.sha256.value_counts().to_dict(),
          f"kept rows {len(data):,}", flush=True)

    # block coordinates for out-of-state ends
    con = duckdb.connect()
    need = set(data.w_geocode)
    for s in ("mo", "ks", "il"):          # homes of the aux workers of the states our metros touch
        aux = str(PARQUET / s / "od" / f"{s}_od_aux_JT0[02]_*.parquet")
        need |= {r[0] for r in con.execute(f"SELECT DISTINCT h_geocode FROM read_parquet('{aux}')").fetchall()}
    need_st = {b[:2] for b in need}
    fips2st = {}
    blocks, cents = [], []
    for st in sts:
        xw = pd.read_csv(io.BytesIO(gzip.decompress(get(f"{BASE}/{st}/{st}_xwalk.csv.gz"))), dtype=str,
                         usecols=["tabblk2020", "st", "cty", "ctyname", "cbsa", "cbsaname", "blklatdd", "blklondd"])
        fips2st[xw.st.iloc[0]] = st
        xw[["blklatdd", "blklondd"]] = xw[["blklatdd", "blklondd"]].astype(float)
        cents.append(xw.groupby(["cty", "ctyname"], as_index=False)[["blklatdd", "blklondd"]].mean().assign(state=st))
        if xw.st.iloc[0] in need_st:
            blocks.append(xw[xw.tabblk2020.isin(need)].assign(state=st))
        print("xwalk", st, flush=True)
    pd.concat(blocks).rename(columns={"tabblk2020": "block", "blklatdd": "lat", "blklondd": "lon"}) \
        .to_parquet(DST / "oos_blocks.parquet", compression="zstd", index=False)
    pd.concat(cents).rename(columns={"blklatdd": "lat", "blklondd": "lon"}) \
        .to_parquet(DST / "oos_county_centroids.parquet", compression="zstd", index=False)
    print("done", flush=True)


if __name__ == "__main__":
    main()
