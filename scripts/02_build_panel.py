"""Phase 1b: build the metro flow panel from the Parquet OD files.

Usage: python scripts/02_build_panel.py [metro]     (default: springfield)

Outputs in outputs/<metro>/
  blockflows.parquet : block-pair flows touching the metro, all years, JT00+JT02, with straight-line
                       distance (miles, block internal points; other states' points from their xwalks).
                       part: main = MO home & work; aux = home in another state, work in MO;
                       oos = home in the metro, work in another state.
  panel.parquet      : node x node x year x jt x part panel with all segment columns, plus
                       sum of S000*miles (dist_sum) so means can be rebuilt after aggregation.
                       Nodes: 2020 tract (11 digits) inside the metro; county FIPS (5 digits) outside.
                       part='main' = MO residents; part='aux' = residents of other states (separate origin class).
  nodes.csv          : node id, type, county, name, lon/lat (job+resident weighted block points, all years pooled).
"""
import sys

import duckdb

from config import PARQUET, OUT, METROS, SEG


def main(metro="springfield"):
    m = METROS[metro]
    od = OUT / metro
    od.mkdir(parents=True, exist_ok=True)
    cty = ",".join(f"'{c}'" for c in m["counties"])
    con = duckdb.connect()
    con.execute("SET threads=32")
    xw = PARQUET / "mo" / "mo_xwalk.parquet"
    con.execute(f"""CREATE TEMP TABLE xw AS SELECT tabblk2020 blk, cty, trct, cbsa,
                    blklatdd::DOUBLE lat, blklondd::DOUBLE lon FROM '{xw}'""")

    # sanity: metro county list == CBSA membership in the crosswalk
    xc = {r[0] for r in con.execute(f"SELECT DISTINCT cty FROM xw WHERE cbsa='{m['cbsa']}'").fetchall()}
    assert xc == set(m["counties"]), f"county list differs from CBSA {m['cbsa']}: {sorted(xc)}"

    segs = ", ".join(SEG)
    files = str(PARQUET / "mo" / "od" / "mo_od_*_JT0[02]_*.parquet")
    # out-of-state ends: block points from other states' crosswalks (written by 00_fetch_outofstate.py)
    oos = PARQUET / "oos"
    con.execute(f"""CREATE TEMP TABLE xa AS SELECT blk, lat, lon FROM xw
                    UNION ALL SELECT block, lat, lon FROM '{oos/'oos_blocks.parquet'}'""")
    con.execute(f"""
    CREATE TEMP TABLE bf AS
    WITH raw AS (
        SELECT split_part(filename, '_', -2) jt,
               split_part(regexp_extract(filename, '_od_([a-z]+)_', 1), '_', 1) part,
               regexp_extract(filename, '_(\\d{{4}})\\.parquet$', 1)::INT AS year,
               w_geocode, h_geocode, {segs}
        FROM read_parquet('{files}', filename=true)
        WHERE substr(w_geocode,1,5) IN ({cty}) OR substr(h_geocode,1,5) IN ({cty})
        UNION ALL   -- part 'oos': metro residents working in another state (that state's aux file)
        SELECT jt, 'oos', year, w_geocode, h_geocode, {segs}
        FROM '{oos/'mo_res_outofstate.parquet'}' WHERE substr(h_geocode,1,5) IN ({cty})
    )
    SELECT r.year, r.jt, r.part, r.w_geocode, r.h_geocode, {", ".join("r."+s for s in SEG)},
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

    # node locations: job- and resident-weighted mean of block points, MO main JT00, all years pooled
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
        print(f"{t}: {n:,} rows, {(od/(t+'.parquet')).stat().st_size/1e6:.1f} MB")


if __name__ == "__main__":
    main(*sys.argv[1:])
