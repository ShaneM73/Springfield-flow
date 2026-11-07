"""Phase 1a: manifest of raw LODES files + conversion to Parquet.

Usage: python scripts/01_manifest_parquet.py [state ...]   (default: mo)

Writes
  parquet/<st>/od/<st>_od_<part>_<jt>_<year>.parquet   (geocodes kept as 15-char strings)
  parquet/<st>/<st>_xwalk.parquet
  outputs/manifest_<st>.csv  : file, bytes, rows, sum_S000, createdate(s), sha256 check, download date
Raw files in Data/ are only read.
"""
import datetime as dt
import shutil
import sys

import duckdb
import pandas as pd

from config import RAW, PARQUET, OUT, MIN_FREE_GB


def free_gb():
    return shutil.disk_usage(RAW).free / 1e9


def main(states):
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for st in states:
        src = RAW / st
        dst = PARQUET / st / "od"
        dst.mkdir(parents=True, exist_ok=True)
        sha = pd.read_csv(src / "sha256_check.tsv", sep="\t").set_index("file")["sha256"].to_dict()
        rows = []
        for f in sorted((src / "od").glob(f"{st}_od_*.csv.gz")):
            out = dst / f.name.replace(".csv.gz", ".parquet")
            if not out.exists():
                if free_gb() < MIN_FREE_GB:
                    sys.exit(f"Stopping: only {free_gb():.2f} GB free on disk")
                con.execute(f"""COPY (SELECT * FROM read_csv('{f}', header=true,
                                types={{'w_geocode':'VARCHAR','h_geocode':'VARCHAR','createdate':'VARCHAR'}}))
                                TO '{out}' (FORMAT parquet, COMPRESSION zstd)""")
            n, s, cd, bad = con.execute(f"""SELECT count(*), sum(S000), string_agg(DISTINCT createdate, ';'),
                     sum(CASE WHEN length(w_geocode)<>15 OR length(h_geocode)<>15 THEN 1 ELSE 0 END)
                     FROM '{out}'""").fetchone()
            _, part, jt, yr = f.name.replace(".csv.gz", "").split("_")[1:]
            rows.append(dict(file=f.name, state=st, part=part, jt=jt, year=int(yr[:4]) if yr.isdigit() else yr,
                             bytes=f.stat().st_size, rows=n, sum_S000=s, createdate=cd, bad_geocodes=bad,
                             sha256=sha.get(f.name, "?"),
                             downloaded=dt.datetime.fromtimestamp(f.stat().st_mtime).date().isoformat()))
            print(f"{f.name}: {n:,} rows, S000={s:,}", flush=True)
        xw = src / f"{st}_xwalk.csv.gz"
        xo = PARQUET / st / f"{st}_xwalk.parquet"
        if not xo.exists():
            con.execute(f"""COPY (SELECT tabblk2020, st, cty, ctyname, trct, bgrp, cbsa, cbsaname, stplc, stplcname,
                                  blklatdd, blklondd, createdate
                           FROM read_csv('{xw}', header=true, all_varchar=true))
                           TO '{xo}' (FORMAT parquet, COMPRESSION zstd)""")
        n = con.execute(f"SELECT count(*) FROM '{xo}'").fetchone()[0]
        rows.append(dict(file=xw.name, state=st, part="xwalk", bytes=xw.stat().st_size, rows=n,
                         sha256=sha.get(xw.name, "?"),
                         downloaded=dt.datetime.fromtimestamp(xw.stat().st_mtime).date().isoformat()))
        man = pd.DataFrame(rows)
        man["version_txt"] = (src / "version.txt").read_text().strip().replace("\n", " | ")
        man.to_csv(OUT / f"manifest_{st}.csv", index=False)
        print(f"\n{st}: {len(man)} files; sha256 mismatches: {(man.sha256 == 'MISMATCH').sum()}; "
              f"bad geocodes: {man.bad_geocodes.fillna(0).sum():.0f}; free {free_gb():.2f} GB")


if __name__ == "__main__":
    main(sys.argv[1:] or ["mo"])
