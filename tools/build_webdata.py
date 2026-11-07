"""Build the web app's data files for one or more metros.

Usage: python tools/build_webdata.py [metro ...]       (default: every metro with phase-3 outputs)

Writes docs/data/<metro>/{app.json, flows_JT02.json, flows_JT00.json} and docs/data/index.json (metro list).
Requires: scripts 02, 04, 05 for the metro; docs/data/<metro>/basemap.json and docs/data/nation/basemap.json
(tools/build_basemap.py). Only flows of >= 10 workers are exported (LODES noise-infusion guidance);
metro totals in the charts use all flows.
"""
import json
import sys
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from config import OUT, METROS, PARQUET, RAW, YEARS, STATE_FIPS, HOME_STATE, metro_def, short_county  # noqa: E402

MIN_EXPORT = 10
R = 6371.0
SEG_ORDER = ["S000", "SE01", "SE02", "SE03", "SI01", "SI02", "SI03", "SA01", "SA02", "SA03"]
NATION_PLACES = [("Kansas City", 39.0997, -94.5786), ("St. Louis", 38.6270, -90.1994), ("Springfield", 37.2090, -93.2923),
                 ("Tulsa", 36.1540, -95.9928), ("Oklahoma City", 35.4676, -97.5164), ("Little Rock", 34.7465, -92.2896),
                 ("Dallas", 32.7767, -96.7970), ("Chicago", 41.8781, -87.6298), ("Denver", 39.7392, -104.9903),
                 ("Memphis", 35.1495, -90.0490), ("Wichita", 37.6872, -97.3301), ("Omaha", 41.2565, -95.9345),
                 ("Houston", 29.7604, -95.3698), ("Atlanta", 33.7490, -84.3880), ("Nashville", 36.1627, -86.7816),
                 ("Phoenix", 33.4484, -112.0740), ("Los Angeles", 34.0522, -118.2437), ("New York", 40.7128, -74.0060),
                 ("Minneapolis", 44.9778, -93.2650), ("Seattle", 47.6062, -122.3321), ("Indianapolis", 39.7684, -86.1581),
                 ("Des Moines", 41.5868, -93.6250)]


def laea(lon, lat, lon0, lat0):
    lon, lat, l0, p0 = map(np.radians, (np.asarray(lon, float), np.asarray(lat, float), lon0, lat0))
    k = np.sqrt(2 / (1 + np.sin(p0) * np.sin(lat) + np.cos(p0) * np.cos(lat) * np.cos(lon - l0)))
    return R * k * np.cos(lat) * np.sin(lon - l0), R * k * (np.cos(p0) * np.sin(lat) - np.sin(p0) * np.cos(lat) * np.cos(lon - l0))


def r(v, d=4):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), d)


def methods_text(M, flagged):
    cs = ", ".join(M["counties"].values())
    fl = ", ".join(f"{t[5:9]}.{t[9:]} in {y}" for t, y in flagged[:4]) or "none"
    return [
        f"<b>Data.</b> US Census LEHD LODES 8.5 origin-destination files, 2002–2024, on 2020 census blocks: the main and "
        f"aux files of {', '.join(s.upper() for s in M['states'])} plus every other state's aux file (residents of these states "
        f"working there). Each file was checked against its SHA-256 checksum. Flows are aggregated to 2020 tracts inside the "
        f"{len(M['counties'])}-county metro ({cs}) and to counties outside it. Only flows of ≥10 workers are drawn.",
        "<b>Job types.</b> Private jobs (JT02) are consistent for 2002–2024. All jobs (JT00) add federal jobs from 2010, and an "
        "OPM suppression in 2015 cuts federal jobs by 8.4% in Missouri.",
        "<b>In-state vs out-of-state.</b> In-state means Missouri. Residents of other states (including the Kansas or Illinois "
        "side of a metro's own commuter field) are counted as out-of-state when they live outside the metro.",
        "<b>Distance.</b> Straight-line miles between block internal points. The distance-decay β is the exponent of a "
        "doubly-constrained gravity model among the metro's tracts (Poisson maximum likelihood).",
        "<b>Commuting communities.</b> Leiden modularity (Traag et al. 2019) on the undirected tract network (pairs ≥3 workers, "
        "no self-loops), γ = 1.0. Each year's partition is a consensus over 100 seeds (Lancichinetti &amp; Fortunato 2012). "
        "Communities are tracked across years by Jaccard overlap ≥0.3 (Greene et al. 2010).",
        "<b>Job centres.</b> Local Moran's I (LISA) High-High clusters on log job density using 3-year centred means (queen "
        "contiguity, 999 permutations, p&lt;0.05). A centre must hold ≥2% of metro jobs and qualify in ≥2 of 3 consecutive "
        "years (Arribas-Bel &amp; Sanz-Gracia 2014; Ha et al. 2024).",
        "<b>Flow trends.</b> Each tract or county pair with ≥10 workers on average gets a Hamed–Rao modified Mann–Kendall test "
        "with Benjamini–Hochberg FDR (q&lt;0.05). Classes follow Esri's emerging-hot-spot logic: new, intensifying, persistent, "
        "declining, fading. Pairs that are neither are left grey.",
        f"<b>Caveats.</b> LODES places some workers of multi-site employers at headquarters, so long flows (&gt;100 mi, flagged) "
        f"can be reporting artefacts (Green et al. 2017). Tract job jumps that revert are reassignments, not real change "
        f"(flagged tract-years here: {fl}). The residence model changed in 2009, at the same time as the recession. Since 2020, "
        f"remote workers appear at their employer's address. Out-of-state files are missing for Michigan 2022–24 and a few "
        f"states in early years.",
    ]


def build(metro):
    M = metro_def(metro); od = OUT / metro; tb = od / "tables"; p3 = od / "phase3"
    web = ROOT / "docs" / "data"; wm = web / metro; wm.mkdir(parents=True, exist_ok=True)
    bm = json.load(open(wm / "basemap.json")); bn = json.load(open(web / "nation" / "basemap.json"))
    mm, nm = bm["meta"]["metro"], bn["meta"]["nation"]
    C = M["counties"]
    con = duckdb.connect()
    P = con.execute(f"SELECT * FROM '{od/'panel.parquet'}'").df()

    # ---- nodes
    mo_nodes = pd.read_csv(od / "nodes.csv", dtype={"node": str, "county": str})
    xw_q = " UNION ALL ".join(f"SELECT DISTINCT cty, ctyname FROM '{PARQUET / s / f'{s}_xwalk.parquet'}'" for s in M["states"])
    cname = con.execute(xw_q).df().drop_duplicates("cty").set_index("cty").ctyname
    oc = pd.read_parquet(PARQUET / "oos" / "oos_county_centroids.parquet")
    oc = oc.drop_duplicates("cty", keep="last").set_index("cty")
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
    mx, my = laea(nodes.lon, nodes.lat, mm["lon0"], mm["lat0"])
    nx, ny = laea(nodes.lon, nodes.lat, nm["lon0"], nm["lat0"])
    st_abbr = {s["id"]: s["abbr"] for s in bn["geo"]["states"]}

    def name(n):
        if len(n) == 11: return f"Tract {n[5:9]}.{n[9:]}"
        if n in cname.index: return short_county(cname[n])
        return str(oc.ctyname.get(n, n))
    jnodes = []
    for i, n in enumerate(nodes.itertuples()):
        kind = "t" if len(n.node) == 11 else ("c" if n.node.startswith(HOME_STATE) else "x")
        jnodes.append(dict(id=n.node, name=name(n.node), kind=kind, st=st_abbr.get(n.node[:2], ""),
                           msa=n.node[:5] in C, m=[round(mx[i], 2), round(my[i], 2)], n=[round(nx[i], 1), round(ny[i], 1)]))

    # ---- tracts & series
    shp = pd.concat([gpd.read_file(RAW / "tiger" / f"tl_2020_{STATE_FIPS[s]}_tract.shp") for s in M["states"]], ignore_index=True)
    acres = shp.set_index("GEOID").ALAND / 4046.856
    T = pd.read_csv(tb / "tract_jobs_residents_year.csv", dtype={"tract": str})
    tracts = {t: dict(i=idx[t], county=C[t[:5]], acres=round(float(acres[t]), 1)) for t in tr.node}
    series = {}
    for jt in ["JT02", "JT00"]:
        Tj = T[T.jt == jt]
        J = Tj.pivot(index="tract", columns="year", values="jobs").reindex(index=tr.node, columns=YEARS).fillna(0)
        Rw = Tj.pivot(index="tract", columns="year", values="res_workers").reindex(index=tr.node, columns=YEARS).fillna(0)
        series[jt] = {t: {"jobs": [None if (jt == "JT00" and y < 2010) else int(J.at[t, y]) for y in YEARS],
                          "res": [None if (jt == "JT00" and y < 2010) else int(Rw.at[t, y]) for y in YEARS]} for t in tr.node}

    # ---- indicators
    V = pd.read_csv(tb / "volumes_county_year.csv"); D = pd.read_csv(tb / "commute_distance_year.csv")
    CS = pd.read_csv(tb / "commutershed_core_jobs.csv"); DEC = pd.read_csv(tb / "distance_decay_poisson.csv")
    K = pd.read_csv(tb / "job_concentration.csv")
    PC = pd.read_csv(p3 / "centres_summary.csv"); CM = pd.read_csv(p3 / "communities_summary.csv")
    ind = {}
    for jt in ["JT02", "JT00"]:
        def col(df, c):
            d = df[df.jt == jt].set_index("year")[c]
            return [r(d[y]) if y in d.index else None for y in YEARS]
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
        c = com[com.jt == jt]; L = labs[labs.jt == jt]
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

    x, y = laea([p[2] for p in NATION_PLACES], [p[1] for p in NATION_PLACES], nm["lon0"], nm["lat0"])
    places = {"metro": bm["geo"]["places"],
              "nation": [dict(name=p[0], xy=[round(a, 2), round(b, 2)]) for p, a, b in zip(NATION_PLACES, x, y)]}
    af = p3 / "artefact_tract_years.csv"
    A = pd.read_csv(af, dtype={"tract": str}) if af.exists() and af.stat().st_size > 10 else pd.DataFrame(columns=["jt", "tract", "year"])
    flagged = [(t, int(y)) for t, y in A[A.jt == "JT02"][["tract", "year"]].drop_duplicates().values]
    app = dict(key=metro, name=M["name"], cbsa=M["cbsa"], states=[s.upper() for s in M["states"]],
               years=YEARS, shocks=[2008, 2020], coreName=C[M["core"]], counties=C, nodes=jnodes, tracts=tracts,
               tractSeries=series, indicators=ind, community=community, centres=centres, trend=trend, places=places,
               methods=methods_text(M, flagged))
    json.dump(app, open(wm / "app.json", "w"), separators=(",", ":"))

    # ---- flows
    P["hc"], P["wc"] = P.h_node.str[:5], P.w_node.str[:5]
    for jt in ["JT02", "JT00"]:
        out = {"metro": {}, "nation": {}}
        q = P[P.jt == jt]
        met = q.groupby(["year", "h_node", "w_node"])[SEG_ORDER].sum().reset_index()
        nat = q.groupby(["year", "hc", "wc"])[SEG_ORDER].sum().reset_index().rename(columns={"hc": "h_node", "wc": "w_node"})
        for key, df in (("metro", met), ("nation", nat)):
            df = df[(df.S000 >= MIN_EXPORT) & df.h_node.isin(idx) & df.w_node.isin(idx)]
            for yv, g in df.groupby("year"):
                if jt == "JT00" and yv < 2010:
                    continue
                arr = np.column_stack([g.h_node.map(idx), g.w_node.map(idx), g[SEG_ORDER].values]).astype(int)
                out[key][int(yv)] = arr.ravel().tolist()
        json.dump(out, open(wm / f"flows_{jt}.json", "w"), separators=(",", ":"))
    sizes = {f.name: round(f.stat().st_size / 1e6, 2) for f in sorted(wm.glob("*.json"))}
    print(metro, sizes, flush=True)
    return dict(key=metro, name=M["name"], cbsa=M["cbsa"], states=[s.upper() for s in M["states"]],
                counties=len(C), tracts=len(tracts), jobs2024=ind["JT02"]["jobs"][-1])


def main(metros):
    web = ROOT / "docs" / "data"
    done = [k for k in METROS if (OUT / k / "phase3" / "flow_trends.csv").exists()]
    metros = metros or done
    index_f = web / "index.json"
    index = {m["key"]: m for m in json.load(open(index_f))} if index_f.exists() else {}
    for k in metros:
        index[k] = build(k)
    json.dump([index[k] for k in METROS if k in index], open(index_f, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
