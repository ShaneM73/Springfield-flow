"""Build the web app's data files (docs/data/app.json, flows_JT02.json, flows_JT00.json) from the pipeline outputs.

Usage: python tools/build_webdata.py [metro]       (default: springfield)
Requires: scripts 02, 04 and 05 to have run; docs/data/basemap.json (tools/build_basemap.py).
Only flows of >= 10 workers are exported (LODES noise-infusion guidance); metro totals in the charts use all flows.
"""
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from config import OUT, METROS, PARQUET, YEARS, SEG  # noqa: E402

MIN_EXPORT = 10
R = 6371.0
SEG_ORDER = ["S000", "SE01", "SE02", "SE03", "SI01", "SI02", "SI03", "SA01", "SA02", "SA03"]
PLACES = {
    "metro": [("Springfield", 37.2090, -93.2923), ("Nixa", 37.0434, -93.2944), ("Ozark", 37.0209, -93.2060),
              ("Republic", 37.1201, -93.4802), ("Marshfield", 37.3387, -92.9071), ("Bolivar", 37.6145, -93.4105),
              ("Buffalo", 37.6439, -93.0924), ("Branson", 36.6437, -93.2185), ("Lebanon", 37.6806, -92.6638),
              ("Mount Vernon", 37.1037, -93.8186), ("Willard", 37.3050, -93.4285), ("Seymour", 37.1464, -92.7688),
              ("Ava", 36.9520, -92.6604), ("Aurora", 36.9709, -93.7177), ("Stockton", 37.6989, -93.7963),
              ("Hermitage", 37.9414, -93.3163)],
    "nation": [("Springfield", 37.2090, -93.2923), ("Kansas City", 39.0997, -94.5786), ("St. Louis", 38.6270, -90.1994),
               ("Tulsa", 36.1540, -95.9928), ("Oklahoma City", 35.4676, -97.5164), ("Little Rock", 34.7465, -92.2896),
               ("Fayetteville", 36.0626, -94.1574), ("Dallas", 32.7767, -96.7970), ("Chicago", 41.8781, -87.6298),
               ("Denver", 39.7392, -104.9903), ("Memphis", 35.1495, -90.0490), ("Wichita", 37.6872, -97.3301),
               ("Omaha", 41.2565, -95.9345), ("Houston", 29.7604, -95.3698), ("Atlanta", 33.7490, -84.3880),
               ("Nashville", 36.1627, -86.7816), ("Phoenix", 33.4484, -112.0740), ("Los Angeles", 34.0522, -118.2437),
               ("New York", 40.7128, -74.0060), ("Minneapolis", 44.9778, -93.2650), ("Seattle", 47.6062, -122.3321)],
}


def laea(lon, lat, lon0, lat0):
    lon, lat, l0, p0 = map(np.radians, (np.asarray(lon, float), np.asarray(lat, float), lon0, lat0))
    k = np.sqrt(2 / (1 + np.sin(p0) * np.sin(lat) + np.cos(p0) * np.cos(lat) * np.cos(lon - l0)))
    return R * k * np.cos(lat) * np.sin(lon - l0), R * k * (np.cos(p0) * np.sin(lat) - np.sin(p0) * np.cos(lat) * np.cos(lon - l0))


def r(v, d=4):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), d)


def main(metro="springfield"):
    M = METROS[metro]; od = OUT / metro; tb = od / "tables"; p3 = od / "phase3"
    web = ROOT / "docs" / "data"
    bm = json.load(open(web / "basemap.json"))["meta"]
    C = M["counties"]
    con = duckdb.connect()
    P = con.execute(f"SELECT * FROM '{od/'panel.parquet'}'").df()

    # ---- nodes
    mo_nodes = pd.read_csv(od / "nodes.csv", dtype={"node": str, "county": str})
    xw = con.execute(f"SELECT DISTINCT cty, ctyname FROM '{PARQUET/'mo'/'mo_xwalk.parquet'}'").df().set_index("cty").ctyname
    oc = pd.read_parquet(PARQUET / "oos" / "oos_county_centroids.parquet")
    oc = oc.drop_duplicates("cty", keep="last").set_index("cty")   # AR xwalk holds a few Shelby Co., TN blocks
    used = set(P.h_node) | set(P.w_node)
    tr = mo_nodes[mo_nodes.type == "tract"].copy()
    tj = P[(P.jt == "JT00") & P.w_node.isin(tr.node)].groupby("w_node").S000.sum()
    msa_c = []
    for f in C:
        t = tr[tr.county == f]; w = tj.reindex(t.node).fillna(1).values
        msa_c.append(dict(node=f, type="county", county=f, lon=np.average(t.lon, weights=w), lat=np.average(t.lat, weights=w)))
    nodes = pd.concat([tr, pd.DataFrame(msa_c), mo_nodes[(mo_nodes.type == "county") & mo_nodes.node.isin(used)]], ignore_index=True)
    extra = sorted(n for n in used if len(n) == 5 and n not in set(nodes.node))
    nodes = pd.concat([nodes, pd.DataFrame([dict(node=n, type="county", county=n, lon=oc.lon.get(n), lat=oc.lat.get(n)) for n in extra])], ignore_index=True)
    nodes = nodes.dropna(subset=["lon"]).drop_duplicates("node").reset_index(drop=True)
    idx = {n: i for i, n in enumerate(nodes.node)}
    mx, my = laea(nodes.lon, nodes.lat, bm["metro"]["lon0"], bm["metro"]["lat0"])
    nx, ny = laea(nodes.lon, nodes.lat, bm["nation"]["lon0"], bm["nation"]["lat0"])
    st_abbr = {s["id"]: s["abbr"] for s in json.load(open(web / "basemap.json"))["geo"]["nation"]["states"]}

    def name(n):
        if len(n) == 11: return f"Tract {n[5:9]}.{n[9:]}"
        if n.startswith("29"): return xw.get(n, n).replace(", MO", "")
        return str(oc.ctyname.get(n, n))
    jnodes = []
    for i, n in enumerate(nodes.itertuples()):
        kind = "t" if len(n.node) == 11 else ("c" if n.node.startswith("29") else "x")
        jnodes.append(dict(id=n.node, name=name(n.node), kind=kind, st=st_abbr.get(n.node[:2], ""),
                           msa=n.node[:5] in C, m=[round(mx[i], 2), round(my[i], 2)], n=[round(nx[i], 1), round(ny[i], 1)]))

    # ---- tracts & series
    import geopandas as gpd
    shp = gpd.read_file(ROOT / "Data" / "tiger" / "tl_2020_29_tract.shp")
    acres = shp.set_index("GEOID").ALAND / 4046.856
    T = pd.read_csv(tb / "tract_jobs_residents_year.csv", dtype={"tract": str})
    tracts = {t: dict(i=idx[t], county=C[t[:5]], acres=round(float(acres[t]), 1)) for t in tr.node}
    series = {}
    for jt in ["JT02", "JT00"]:
        s = {}
        for t in tr.node:
            g = T[(T.jt == jt) & (T.tract == t)].set_index("year")
            s[t] = {"jobs": [None if (jt == "JT00" and y < 2010) else int(g.jobs.get(y, 0)) for y in YEARS],
                    "res": [None if (jt == "JT00" and y < 2010) else int(g.res_workers.get(y, 0)) for y in YEARS]}
        series[jt] = s

    # ---- indicators
    V = pd.read_csv(tb / "volumes_county_year.csv"); D = pd.read_csv(tb / "commute_distance_year.csv")
    CS = pd.read_csv(tb / "commutershed_core_jobs.csv"); DEC = pd.read_csv(tb / "distance_decay_poisson.csv")
    K = pd.read_csv(tb / "job_concentration.csv")
    PC = pd.read_csv(p3 / "centres_summary.csv"); CM = pd.read_csv(p3 / "communities_summary.csv")
    ind = {}
    for jt in ["JT02", "JT00"]:
        col = lambda df, c, f=lambda v: v: [r(f(df[(df.jt == jt) & (df.year == y)][c].iloc[0])) if len(df[(df.jt == jt) & (df.year == y)]) else None for y in YEARS]
        dm = D[(D.scope == "within_msa") & (D.group == "all")]
        ind[jt] = dict(jobs=col(V, "msa_jobs_total"), live_work=col(V, "live_work_msa"), in_mo=col(V, "inflow_mo"),
                       in_oos=col(V, "inflow_aux"), out_mo=col(V, "outflow_mo"), out_oos=col(V, "outflow_oos"),
                       med_mi=col(dm, "median_mi"), core_share=col(CS, "core"), sub_share=col(CS, "suburban MSA"),
                       outer_share=col(CS, "outer MO"), oos_share=col(CS, "out of state"), beta=col(DEC, "beta_logd"),
                       top5=col(K, "top5"), top10=col(K, "top10"), gini=col(K, "gini"),
                       centre_share=col(PC, "centre_share"), n_comm=col(CM, "n_communities"),
                       selfcont=col(V, "self_contain_res"))

    # ---- phase 3: communities, centres, trends
    com = pd.read_csv(p3 / "communities.csv", dtype={"tract": str})
    labs = pd.read_csv(p3 / "community_labels.csv")
    community, centres, trend = {}, {}, {}
    for jt in ["JT02", "JT00"]:
        c = com[com.jt == jt]
        L = labs[labs.jt == jt]
        community[jt] = {"years": {int(y): dict(zip(g.tract, g.community.astype(int))) for y, g in c.groupby("year")},
                         # <= 8 communities: one categorical slot each, by size; otherwise greedy slots from phase 3
                         "colours": ({int(a): k for k, a in enumerate(L.sort_values("tract_years", ascending=False).community)}
                                     if len(L) <= 8 else {int(a): int(b) for a, b in zip(L.community, L.slot)}),
                         "labels": {int(a): b for a, b in zip(L.community, L.label)}}
    cen = pd.read_csv(p3 / "centres.csv", dtype={"tract": str})
    for jt in ["JT02", "JT00"]:
        centres[jt] = {int(y): sorted(g.tract) for y, g in cen[(cen.jt == jt) & cen.centre].groupby("year")}
    tc = pd.read_csv(p3 / "flow_trends.csv", dtype={"h_node": str, "w_node": str})
    cls = {"new": 0, "intensifying": 1, "persistent": 2, "declining": 3, "fading": 4}
    for jt in ["JT02", "JT00"]:
        trend[jt] = {}
        for scale in ["metro", "nation"]:
            t = tc[(tc.jt == jt) & (tc.scale == scale) & tc.cls.isin(cls)]
            trend[jt][scale] = {f"{idx[h]}-{idx[w]}": cls[k] for h, w, k in zip(t.h_node, t.w_node, t.cls) if h in idx and w in idx}

    places = {}
    for sc_, pl in PLACES.items():
        x, y = laea([p[2] for p in pl], [p[1] for p in pl], bm[sc_]["lon0"], bm[sc_]["lat0"])
        places[sc_] = [dict(name=p[0], xy=[round(a, 2), round(b, 2)]) for p, a, b in zip(pl, x, y)]

    methods = json.load(open(p3 / "methods_web.json"))
    app = dict(years=YEARS, shocks=[2008, 2020], coreName=C[M["core"]], nodes=jnodes, tracts=tracts, tractSeries=series,
               indicators=ind, community=community, centres=centres, trend=trend, places=places, methods=methods)
    json.dump(app, open(web / "app.json", "w"), separators=(",", ":"))

    # ---- flows
    P["hc"], P["wc"] = P.h_node.str[:5], P.w_node.str[:5]
    for jt in ["JT02", "JT00"]:
        out = {"metro": {}, "nation": {}}
        q = P[P.jt == jt]
        met = q.groupby(["year", "h_node", "w_node"])[SEG_ORDER].sum().reset_index()
        nat = q.groupby(["year", "hc", "wc"])[SEG_ORDER].sum().reset_index().rename(columns={"hc": "h_node", "wc": "w_node"})
        for key, df in (("metro", met), ("nation", nat)):
            df = df[(df.S000 >= MIN_EXPORT) & df.h_node.isin(idx) & df.w_node.isin(idx)]
            for y, g in df.groupby("year"):
                if jt == "JT00" and y < 2010:
                    continue
                arr = np.column_stack([g.h_node.map(idx), g.w_node.map(idx), g[SEG_ORDER].values]).astype(int)
                out[key][int(y)] = arr.ravel().tolist()
        json.dump(out, open(web / f"flows_{jt}.json", "w"), separators=(",", ":"))
    for f in sorted(web.glob("*.json")):
        print(f.name, f"{f.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    main(*sys.argv[1:])
