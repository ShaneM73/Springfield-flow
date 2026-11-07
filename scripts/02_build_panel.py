"""Phase 1b: build a metro's flow panel from the Parquet OD files (works for metros spanning several states).

Usage: python scripts/02_build_panel.py <metro>     (default: springfield)

Every LODES job appears in exactly one file: the work state's `main` file when home and work are in the same state,
otherwise the work state's `aux` file. A metro's flows are therefore
  - main + aux files of every state the metro touches (all rows with home or work in the metro), plus
  - other states' aux files, rows with a home block in the metro (parquet/oos/res_outofstate.parquet).

Outputs in outputs/<metro>/
  blockflows.parquet : block-pair flows touching the metro, all years, JT00+JT02, with
                       src (state file the row came from), part (main/aux of that file, 'oos' = third-state aux)
                       and straight-line miles between block internal points.
  panel.parquet      : node x node x year x jt x part panel with all segment columns, dist_sum (sum S000*miles), dist_n.
                       Nodes: 2020 tract (11 digits) inside the metro, county FIPS (5 digits) outside (any state).
                       Home / work state = first two digits of the node.
  nodes.csv          : metro tracts and in-state (metro states) counties: job+resident weighted block points.
"""
import sys

import duckdb

from config import PARQUET, OUT, SEG, STATE_FIPS, metro_def


def main(metro="springfield"):
    m = metro_def(metro)
    od = OUT / metro
    od.mkdir(parents=True, exist_ok=True)
    cty = ",".join(f"'{c}'" for c in m["counties"])
    sts = m["states"]
    con = duckdb.connect()
    con.execute("SET threads=32")
    xw_union = " UNION ALL ".join(f"""SELECT tabblk2020 blk, cty, trct, cbsa, blklatdd::DOUBLE lat, blklondd::DOUBLE lon
                                      FROM '{PARQUET / s / f'{s}_xwalk.parquet'}'""" for s in sts)
    con.execute(f"CREATE TEMP TABLE xw AS {xw_union}")
    oos = PARQUET / "oos"
    con.execute(f"""CREATE TEMP TABLE xa AS SELECT blk, lat, lon FROM xw
                    UNION ALL SELECT block, lat, lon FROM '{oos/'oos_blocks.parquet'}'
                    WHERE block NOT IN (SELECT blk FROM xw)""")

    segs = ", ".join(SEG)
    parts = []
    for s in sts:
        f = str(PARQUET / s / "od" / f"{s}_od_*_JT0[02]_*.parquet")
        parts.append(f"""SELECT '{s}' src, split_part(filename, '_', -2) jt,
               regexp_extract(filename, '_od_([a-z]+)_', 1) part,
               regexp_extract(filename, '_(\\d{{4}})\\.parquet$', 1)::INT AS year, w_geocode, h_geocode, {segs}
        FROM read_parquet('{f}', filename=true)
        WHERE substr(w_geocode,1,5) IN ({cty}) OR substr(h_geocode,1,5) IN ({cty})""")
    in_sts = ",".join(f"'{s}'" for s in sts)
    parts.append(f"""SELECT w_state src, jt, 'oos' part, year, w_geocode, h_geocode, {segs}
        FROM '{oos/'res_outofstate.parquet'}'
        WHERE substr(h_geocode,1,5) IN ({cty}) AND w_state NOT IN ({in_sts})""")
    con.execute(f"""
    CREATE TEMP TABLE bf AS
    WITH raw AS ({" UNION ALL ".join(parts)})
    SELECT r.year, r.jt, r.src, r.part, r.w_geocode, r.h_geocode, {", ".join("r."+s for s in SEG)},
           CASE WHEN hx.lat IS NULL OR wx.lat IS NULL THEN NULL ELSE
             3958.7613 * 2 * asin(sqrt(pow(sin(radians(wx.lat-hx.lat)/2),2) +
               cos(radians(hx.lat))*cos(radians(wx.lat))*pow(sin(radians(wx.lon-hx.lon)/2),2))) END AS miles
    FROM raw r LEFT JOIN xa hx ON r.h_geocode = hx.blk LEFT JOIN xa wx ON r.w_geocode = wx.blk
    """)
    con.execute(f"COPY bf TO '{od/'blockflows.parquet'}' (FORMAT parquet, COMPRESSION zstd)")

    node = lambda g: f"CASE WHEN substr({g},1,5) IN ({cty}) THEN substr({g},1,11) ELSE substr({g},1,5) END"
    con.execute(f"""
    COPY (SELECT year, jt, part, {node('h_geocode')} h_node, {node('w_geocode')} w_node,
                 {", ".join(f"sum({s})::INT {s}" for s in SEG)},
                 sum(S000*miles) dist_sum, sum(CASE WHEN miles IS NULL THEN 0 ELSE S000 END)::INT dist_n,
                 count(*)::INT n_blockpairs
          FROM bf GROUP BY ALL ORDER BY ALL)
    TO '{od/'panel.parquet'}' (FORMAT parquet, COMPRESSION zstd)""")

    # node locations: job- and resident-weighted mean of block points, main files JT00, all years pooled
    con.execute(f"""
    COPY (
      WITH w AS (SELECT blk, sum(n) n FROM (
          SELECT w_geocode blk, S000 n FROM bf WHERE jt='JT00' AND part='main'
          UNION ALL SELECT h_geocode, S000 FROM bf WHERE jt='JT00' AND part='main') GROUP BY blk)
      SELECT CASE WHEN x.cty IN ({cty}) THEN x.trct ELSE x.cty END node,
             CASE WHEN x.cty IN ({cty}) THEN 'tract' ELSE 'county' END type,
             any_value(x.cty) county,
             sum(w.n*x.lon)/sum(w.n) lon, sum(w.n*x.lat)/sum(w.n) lat
      FROM w JOIN xw x ON w.blk = x.blk GROUP BY 1, 2 ORDER BY 1)
    TO '{od/'nodes.csv'}' (HEADER)""")
    for t in ["blockflows", "panel"]:
        n = con.execute(f"SELECT count(*) FROM '{od/(t+'.parquet')}'").fetchone()[0]
        print(f"{metro} {t}: {n:,} rows, {(od/(t+'.parquet')).stat().st_size/1e6:.1f} MB", flush=True)
    nn = con.execute(f"SELECT count(*) FROM '{od/'nodes.csv'}' WHERE type='tract'").fetchone()[0]
    print(f"{metro}: {len(m['counties'])} counties, {nn} tracts", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
