"""
Per state-year self-containment and county totals from LODES 8 main OD JT02 files,
computed directly from the csv.gz with DuckDB (one file at a time, no parquet copies).

Outputs (outputs/external/):
  lodes_national_county_totals.csv   state, year, county, res_workers, work_jobs   (intermediate; resumable)
  lodes_national_selfcontainment_2004_2011.csv
  lodes_national_residence_jumps.csv
Progress logged to outputs/external/national_od.log.
"""
import csv
import os
import sys
import time

import duckdb
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "outputs", "external")
LOG = os.path.join(EXT, "national_od.log")
MANIFEST = os.path.join(EXT, "national_od_manifest.csv")
COUNTY = os.path.join(EXT, "lodes_national_county_totals.csv")
STATE = os.path.join(EXT, "lodes_national_state_raw.csv")   # per state-year totals (intermediate)
SELF = os.path.join(EXT, "lodes_national_selfcontainment_2004_2011.csv")
JUMPS = os.path.join(EXT, "lodes_national_residence_jumps.csv")
MIN_WORKERS = 500
THRESH = 0.10
STUB_WORKERS = 10_000


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def compute_one(con, path):
    rel = (f"read_csv('{path}', header=true, "
           f"types={{'w_geocode':'VARCHAR','h_geocode':'VARCHAR','S000':'BIGINT'}})")
    tot = con.execute(f"""
        SELECT sum(S000) AS workers,
               sum(CASE WHEN substr(w_geocode,1,5)=substr(h_geocode,1,5) THEN S000 ELSE 0 END) AS same_county,
               sum(CASE WHEN substr(w_geocode,1,11)=substr(h_geocode,1,11) THEN S000 ELSE 0 END) AS same_tract,
               count(*) AS n_rows
        FROM {rel}""").fetchone()
    cty = con.execute(f"""
        WITH r AS (SELECT substr(h_geocode,1,5) AS county, sum(S000) AS res_workers FROM {rel} GROUP BY 1),
             w AS (SELECT substr(w_geocode,1,5) AS county, sum(S000) AS work_jobs FROM {rel} GROUP BY 1)
        SELECT coalesce(r.county, w.county) AS county,
               coalesce(res_workers,0) AS res_workers, coalesce(work_jobs,0) AS work_jobs
        FROM r FULL OUTER JOIN w USING (county) ORDER BY 1""").fetchall()
    return tot, cty


def main():
    man = pd.read_csv(MANIFEST, dtype={"state": str})
    man = man[man.present == 1].sort_values(["state", "year"])
    done = set()
    if os.path.exists(STATE):
        prev = pd.read_csv(STATE, dtype={"state": str})
        done = set(zip(prev.state, prev.year))
    con = duckdb.connect()
    con.execute("SET memory_limit='8GB'")
    con.execute("SET threads=8")
    con.execute("SET preserve_insertion_order=false")
    new_state = not os.path.exists(STATE)
    new_cty = not os.path.exists(COUNTY)
    fs = open(STATE, "a", newline="")
    fc = open(COUNTY, "a", newline="")
    ws, wc = csv.writer(fs), csv.writer(fc)
    if new_state:
        ws.writerow(["state", "year", "workers", "same_county", "same_tract", "n_rows", "n_counties"])
    if new_cty:
        wc.writerow(["state", "year", "county", "res_workers", "work_jobs"])
    todo = [(r.state, int(r.year), os.path.join(ROOT, r.path)) for r in man.itertuples()
            if (r.state, int(r.year)) not in done]
    log(f"compute: {len(todo)} state-years to do ({len(done)} cached)")
    for i, (st, yr, path) in enumerate(todo, 1):
        t0 = time.time()
        try:
            tot, cty = compute_one(con, path)
        except Exception as e:
            log(f"[{i}/{len(todo)}] {st} {yr} FAILED: {e}")
            continue
        ws.writerow([st, yr, tot[0], tot[1], tot[2], tot[3], len(cty)])
        for c in cty:
            wc.writerow([st, yr, c[0], c[1], c[2]])
        fs.flush(); fc.flush()
        log(f"[{i}/{len(todo)}] {st} {yr} workers={tot[0]:,} same_cty={tot[1]/tot[0]:.4f} "
            f"same_tract={tot[2]/tot[0]:.4f} counties={len(cty)} ({time.time()-t0:.1f}s)")
    fs.close(); fc.close()
    build_outputs()


def build_outputs():
    s = pd.read_csv(STATE, dtype={"state": str}).drop_duplicates(["state", "year"]).sort_values(["state", "year"])
    # some early files are stubs with a handful of records (e.g. MA 2004-2010); treat them as absent
    stub = s.workers < STUB_WORKERS
    if stub.any():
        log("stub state-years excluded (workers < %d): %s" % (
            STUB_WORKERS, ", ".join(f"{r.state} {r.year} ({r.workers})" for r in s[stub].itertuples())))
        man = pd.read_csv(MANIFEST, dtype={"state": str})
        key = set(zip(s[stub].state, s[stub].year))
        is_stub = [(a, b) in key for a, b in zip(man.state, man.year)]
        man.loc[is_stub, "present"] = 0
        man.loc[is_stub, "status"] = "stub"
        man.to_csv(MANIFEST, index=False)
    s = s[~stub].copy()
    s["same_county_share"] = s.same_county / s.workers
    s["same_tract_share"] = s.same_tract / s.workers
    g = s.groupby("state")
    s["prev_year"] = g.year.shift(1)
    s["d_workers_pct"] = (s.workers / g.workers.shift(1) - 1) * 100
    s["d_same_county_pts"] = (s.same_county_share - g.same_county_share.shift(1)) * 100
    s["d_same_tract_pts"] = (s.same_tract_share - g.same_tract_share.shift(1)) * 100
    # only treat as a year-on-year change when the previous year is actually present
    gap = s.prev_year != s.year - 1
    s.loc[gap, ["d_workers_pct", "d_same_county_pts", "d_same_tract_pts"]] = float("nan")
    out = s[["state", "year", "workers", "same_county_share", "same_tract_share",
             "d_workers_pct", "d_same_county_pts", "d_same_tract_pts", "n_counties"]]
    out.to_csv(SELF, index=False, float_format="%.6f")
    log(f"wrote {SELF} ({len(out)} rows)")

    c = pd.read_csv(COUNTY, dtype={"state": str, "county": str}).drop_duplicates(["state", "year", "county"])
    c = c.sort_values(["state", "county", "year"])
    g = c.groupby(["state", "county"])
    c["prev_year"] = g.year.shift(1)
    c["res_prev"] = g.res_workers.shift(1)
    c["work_prev"] = g.work_jobs.shift(1)
    c = c[(c.prev_year == c.year - 1)]
    c["res_chg"] = c.res_workers / c.res_prev - 1
    c["work_chg"] = c.work_jobs / c.work_prev - 1
    # eligibility: >= 500 workers in both years (residence basis for res jumps, workplace basis for work jumps)
    cr = c[(c.res_workers >= MIN_WORKERS) & (c.res_prev >= MIN_WORKERS)]
    cw = c[(c.work_jobs >= MIN_WORKERS) & (c.work_prev >= MIN_WORKERS)]
    jr = cr.groupby(["state", "year"]).agg(n_counties=("county", "size"),
                                           n_res_jump_gt10=("res_chg", lambda x: (x.abs() > THRESH).sum()),
                                           share_res_jump_gt10=("res_chg", lambda x: (x.abs() > THRESH).mean()),
                                           median_abs_res_chg=("res_chg", lambda x: x.abs().median()))
    jw = cw.groupby(["state", "year"]).agg(n_counties_work=("county", "size"),
                                           n_work_jump_gt10=("work_chg", lambda x: (x.abs() > THRESH).sum()),
                                           share_work_jump_gt10=("work_chg", lambda x: (x.abs() > THRESH).mean()),
                                           median_abs_work_chg=("work_chg", lambda x: x.abs().median()))
    j = jr.join(jw, how="outer").reset_index()
    j.to_csv(JUMPS, index=False, float_format="%.4f")
    log(f"wrote {JUMPS} ({len(j)} rows)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--outputs-only":
        build_outputs()
    else:
        main()
