"""Phase 3: flow structure over time - job centres, commuting communities, flow trends, shocks.

Usage: python scripts/05_flow_structure.py [metro]    -> outputs/<metro>/phase3/

Methods are chosen from the literature (see outputs/<metro>/phase3/METHODS.md); all random draws are seeded (SEED).
  Job centres  : local Moran's I on log job density (centred 3-yr mean jobs), queen contiguity, row-standardised,
                 999 conditional permutations, p<0.05. Core = High-High, or High-Low with density > metro P90.
                 Contiguous cores merged; centre needs >= 2% of metro jobs; persistence: candidate in >= 2 of the
                 3 years t-1..t+1 (Arribas-Bel & Sanz-Gracia 2014; Ha et al. 2024; Kane et al. 2018).
                 Robustness: Ha et al. 2024 rule, annual density >= P95 + contiguous cluster >= 2% of jobs.
  Communities  : Leiden modularity (Traag et al. 2019), undirected w_ij = F_ij + F_ji, within-metro tract pairs
                 >= 3 jobs, no self-loops (Nelson & Rae 2016); gamma = GAMMA_MAIN = 1.0 (modularity default). A
                 stability scan (grid 0.5-2.0, 50 seeds/yr, gamma_scan.csv) found ARI >= 0.90 plateaus only at
                 trivial (<= 0.7, 2-3 communities) or very fine (>= 1.7) resolutions, so the ARI rule is NOT used
                 to pick gamma; 0.7 and 1.7 are reported as sensitivity; annual consensus partition over 100 seeds
                 (Lancichinetti & Fortunato 2012); tracked by Jaccard theta = 0.3 (Greene et al. 2010).
                 Sensitivity: self-loops included.
  Flow trends  : pairs with mean >= 10 jobs (or first/last-5-year mean >= 10); Hamed-Rao modified Mann-Kendall
                 + Sen slope, Benjamini-Hochberg q < 0.05. Classes (Esri emerging-hot-spot logic, adapted):
                 new (<3 in each of first 5 yrs and last-5 mean >= 10), fading (reverse), intensifying/declining
                 (significant trend), persistent (>= 10 in >= 90 % of years, no trend), sporadic (rest).
  Artefacts    : jump-and-revert tract-years (|jobs - median(neighbour yrs)| > 50 % and > 500) flagged;
                 flows > 100 miles flagged; results reported with/without flagged pairs.
  Shocks       : 2007->2010 and 2019->2021/2024 vs linear pre-trend (2002-07, 2014-19); level-shift test at 2009
                 (documented LODES residence-synthesiser change; confounded with the recession).
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations

import duckdb
import geopandas as gpd
import igraph as ig
import leidenalg as la
import matplotlib
import numpy as np
import pandas as pd
import pymannkendall as mk
import statsmodels.api as sm

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import OUT, RAW, YEARS, STATE_FIPS, metro_def

SEED = 20261106
GAMMAS = np.round(np.arange(0.5, 2.01, 0.1), 2)
N_SCAN, N_CONS, THETA, MIN_EDGE = 50, 100, 0.3, 3
PERM, ALPHA = 999, 0.05
CENTRE_MIN_SHARE = 0.02
LONG_MI = 100
WORKERS = 16                      # processes for the per-year / per-pair work
GAMMA_MAIN, GAMMA_SENS = 1.0, (0.7, 1.7)


# ------------------------------------------------------------------ helpers
def ari(a, b):
    a, b = np.asarray(a), np.asarray(b)
    _, ai = np.unique(a, return_inverse=True); _, bi = np.unique(b, return_inverse=True)
    ct = np.zeros((ai.max() + 1, bi.max() + 1)); np.add.at(ct, (ai, bi), 1)
    c2 = lambda x: x * (x - 1) / 2
    s, sa, sb, n = c2(ct).sum(), c2(ct.sum(1)).sum(), c2(ct.sum(0)).sum(), c2(len(a))
    e = sa * sb / n
    return 1.0 if (sa + sb) / 2 == e else (s - e) / ((sa + sb) / 2 - e)


def leiden(G, gamma, seed):
    p = la.find_partition(G, la.RBConfigurationVertexPartition, weights="weight",
                          resolution_parameter=gamma, seed=int(seed), n_iterations=-1)
    return np.array(p.membership), p.quality()


def consensus(G, gamma, rng, n=N_CONS, tau=0.5, max_iter=10):
    """Lancichinetti & Fortunato (2012) consensus clustering."""
    N = G.vcount()
    parts = [leiden(G, gamma, s)[0] for s in rng.integers(0, 2**31, n)]
    for _ in range(max_iter):
        D = np.mean([(p[:, None] == p[None, :]) for p in parts], axis=0)
        np.fill_diagonal(D, 0)
        if np.all((D < 1e-9) | (D > 1 - 1e-9)):
            break
        D[D < tau] = 0
        iu = np.triu_indices(N, 1); keep = D[iu] > 0
        H = ig.Graph(n=N, edges=list(zip(iu[0][keep], iu[1][keep])))
        H.es["weight"] = D[iu][keep]
        parts = [leiden(H, gamma, s)[0] for s in rng.integers(0, 2**31, n)]
    return parts[0]


def local_moran(z, W, rng, perm=PERM):
    """Local Moran's I with conditional permutation pseudo p-values (folded, two-sided like PySAL's p_sim)."""
    n = len(z); lag = W @ z; I = z * lag
    k = (W > 0).sum(1).astype(int); p = np.ones(n)
    kmax = int(k.max())
    # one shared set of random draws without replacement (as PySAL's crand), reused for every tract
    R = np.argpartition(rng.random((perm, n - 1)), kmax, axis=1)[:, :kmax]
    for i in range(n):
        if k[i] == 0:
            continue
        others = np.delete(z, i)
        Ip = z[i] * others[R[:, :k[i]]].mean(1)
        larger = (Ip >= I[i]).sum() if I[i] >= 0 else (Ip <= I[i]).sum()
        larger = min(larger, perm - larger)
        p[i] = (larger + 1) / (perm + 1)
    return I, lag, p


def _mkgraph(n, edges, weights):
    G = ig.Graph(n=n, edges=edges); G.es["weight"] = weights; return G


def _lisa_job(a):
    z, W, seed = a
    return local_moran(z, W, np.random.default_rng(int(seed)))


def _scan_job(a):
    n, edges, weights, g, seeds = a
    G = _mkgraph(n, edges, weights)
    mem = [leiden(G, g, s)[0] for s in seeds]
    return dict(mean_ari=np.mean([ari(mem[i], mem[j]) for i, j in combinations(range(len(mem)), 2)]),
                n_comm=np.mean([len(set(m)) for m in mem]), modularity=G.modularity(mem[0], weights="weight", resolution=g))


def _cons_job(a):
    n, edges, weights, g, seed, nseeds = a
    return consensus(_mkgraph(n, edges, weights), g, np.random.default_rng(int(seed)), n=nseeds)


def _mk_job(v):
    try:
        r = mk.hamed_rao_modification_test(v); return r.Tau, r.p, r.slope
    except Exception:
        return np.nan, 1.0, np.nan


def gparts(G):
    return G.vcount(), [e.tuple for e in G.es], G.es["weight"]


def components(nodes, adj):
    nodes, out, seen = set(nodes), [], set()
    for t in sorted(nodes):
        if t in seen:
            continue
        comp, st = set(), [t]
        while st:
            u = st.pop()
            if u in comp:
                continue
            comp.add(u); st.extend(adj.get(u, set()) & nodes)
        seen |= comp; out.append(comp)
    return out


def main(metro="springfield"):
    M = metro_def(metro); C = M["counties"]
    od = OUT / metro; p3 = od / "phase3"; p3.mkdir(exist_ok=True); (p3 / "figures").mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    con = duckdb.connect()
    P = con.execute(f"SELECT * FROM '{od/'panel.parquet'}'").df()
    P["h_in"], P["w_in"] = P.h_node.str[:5].isin(C), P.w_node.str[:5].isin(C)
    nodes = pd.read_csv(od / "nodes.csv", dtype={"node": str, "county": str})
    tracts = sorted(nodes[nodes.type == "tract"].node)
    shp = pd.concat([gpd.read_file(RAW / "tiger" / f"tl_2020_{STATE_FIPS[s]}_tract.shp") for s in M["states"]], ignore_index=True)
    shp = shp[shp.GEOID.isin(tracts)].set_index("GEOID").loc[tracts]
    acres = (shp.ALAND / 4046.856).values
    nb = gpd.sjoin(shp.reset_index()[["GEOID", "geometry"]], shp.reset_index()[["GEOID", "geometry"]], predicate="intersects")
    nb = nb[nb.GEOID_left != nb.GEOID_right]
    adj = nb.groupby("GEOID_left").GEOID_right.apply(set).to_dict()
    ix = {t: i for i, t in enumerate(tracts)}
    W = np.zeros((len(tracts), len(tracts)))
    for a, bs in adj.items():
        for b in bs:
            W[ix[a], ix[b]] = 1
    W = W / W.sum(1, keepdims=True)
    T = pd.read_csv(od / "tables" / "tract_jobs_residents_year.csv", dtype={"tract": str})

    def jt_years(jt):
        return [y for y in YEARS if not (jt == "JT00" and y < 2010)]

    # ============================================================ artefact flags (jump-and-revert)
    flags = []
    for jt in ["JT02", "JT00"]:
        J = T[T.jt == jt].pivot(index="tract", columns="year", values="jobs").reindex(tracts).fillna(0)[jt_years(jt)]
        ys = list(J.columns)
        for k in range(1, len(ys) - 1):
            med = J[[ys[k - 1], ys[k + 1]]].median(1)
            dev = J[ys[k]] - med
            hit = (dev.abs() > 0.5 * med) & (dev.abs() > 500)
            for t in J.index[hit]:
                flags.append(dict(jt=jt, year=ys[k], tract=t, jobs=J.at[t, ys[k]], neighbour_median=med[t], dev=dev[t], kind="spike/dip"))
    FL = pd.DataFrame(flags); FL.to_csv(p3 / "artefact_tract_years.csv", index=False)
    art_tracts = {jt: set(FL[FL.jt == jt].tract) for jt in ["JT02", "JT00"]} if len(FL) else {"JT02": set(), "JT00": set()}
    print("artefact tract-years:", FL.groupby("jt").size().to_dict() if len(FL) else 0, flush=True)

    # ============================================================ job centres
    cen_rows, cen_sum = [], []
    for jt in ["JT02", "JT00"]:
        ys = jt_years(jt)
        J = T[T.jt == jt].pivot(index="tract", columns="year", values="jobs").reindex(tracts).fillna(0)[ys]
        J3 = J.T.rolling(3, center=True, min_periods=2).mean().T     # centred 3-yr mean
        cand = {}
        lisa = {}
        zs = {}
        for y in ys:
            dens = J3[y].values / acres; z = np.log(dens + 0.01); zs[y] = (z - z.mean()) / z.std()
        with ProcessPoolExecutor(WORKERS) as ex:
            lisa_res = dict(zip(ys, ex.map(_lisa_job, [(zs[y], W, rng.integers(0, 2**31)) for y in ys])))
        for y in ys:
            j = J3[y].values; dens = j / acres; z = zs[y]
            I, lag, p = lisa_res[y]
            p90 = np.percentile(dens, 90)
            hh = (z > 0) & (lag > 0) & (p < ALPHA)
            hl = (z > 0) & (lag < 0) & (p < ALPHA) & (dens > p90)
            core = [t for t, c in zip(tracts, hh | hl) if c]
            ok = set()
            for comp in components(core, adj):
                if j[[ix[t] for t in comp]].sum() >= CENTRE_MIN_SHARE * j.sum():
                    ok |= comp
            cand[y] = ok
            lisa[y] = dict(I=I, p=p, hh=hh, hl=hl, dens=dens)
        for k, y in enumerate(ys):
            win = ys[max(0, k - 1):k + 2]
            need = 2
            pers = {t for t in tracts if sum(t in cand[w] for w in win) >= need}
            jr = J[y].values                                   # report shares on the actual year's jobs
            comps = [c for c in components(pers, adj) if jr[[ix[t] for t in c]].sum() >= CENTRE_MIN_SHARE * jr.sum()]
            cset = set().union(*comps) if comps else set()
            L = lisa[y]
            for t in tracts:
                i = ix[t]
                cen_rows.append(dict(jt=jt, year=y, tract=t, jobs=jr[i], density3=round(L["dens"][i], 3), local_I=round(L["I"][i], 3),
                                     p=L["p"][i], lisa="HH" if L["hh"][i] else ("HL" if L["hl"][i] else ""),
                                     candidate=t in cand[y], centre=t in cset))
            # Ha et al. (2024) robustness: annual P95 density + cluster >= 2% of jobs
            d = jr / acres; top = [t for t in tracts if d[ix[t]] >= np.percentile(d, 95)]
            ha = [c for c in components(top, adj) if jr[[ix[t] for t in c]].sum() >= CENTRE_MIN_SHARE * jr.sum()]
            cen_sum.append(dict(jt=jt, year=y, n_centres=len(comps), n_centre_tracts=len(cset),
                                centre_share=jr[[ix[t] for t in cset]].sum() / jr.sum() if cset else 0,
                                centres=" | ".join(";".join(sorted(c)) for c in sorted(comps, key=lambda c: -jr[[ix[t] for t in c]].sum())),
                                ha_n_centres=len(ha), ha_share=sum(jr[[ix[t] for t in c]].sum() for c in ha) / jr.sum()))
    CEN = pd.DataFrame(cen_rows); CEN.to_csv(p3 / "centres.csv", index=False)
    CS = pd.DataFrame(cen_sum); CS.to_csv(p3 / "centres_summary.csv", index=False)
    print(CS[CS.jt == "JT02"][["year", "n_centres", "n_centre_tracts", "centre_share", "ha_n_centres", "ha_share"]].round(3).to_string(index=False), flush=True)

    # ============================================================ communities
    def graph(jt, y, self_loops=False):
        q = P[(P.jt == jt) & (P.year == y) & P.h_in & P.w_in].groupby(["h_node", "w_node"]).S000.sum().reset_index()
        q["a"], q["b"] = q.h_node.map(ix), q.w_node.map(ix)
        u = q.assign(i=np.minimum(q.a, q.b), j=np.maximum(q.a, q.b)).groupby(["i", "j"]).S000.sum().reset_index()
        u = u[u.S000 >= MIN_EDGE]
        if not self_loops:
            u = u[u.i != u.j]
        G = ig.Graph(n=len(tracts), edges=list(zip(u.i, u.j)))
        G.es["weight"] = u.S000.astype(float).tolist()
        return G

    scan = []
    G2 = {y: graph("JT02", y) for y in YEARS}
    GP = {y: gparts(G2[y]) for y in YEARS}
    if not (p3 / "gamma_scan.csv").exists():
        jobs = [(g, y, rng.integers(0, 2**31, N_SCAN)) for g in GAMMAS for y in YEARS]
        with ProcessPoolExecutor(WORKERS) as ex:
            outs = list(ex.map(_scan_job, [(*GP[y], g, seeds) for g, y, seeds in jobs], chunksize=4))
        scan = [dict(gamma=g, year=y, **o) for (g, y, _), o in zip(jobs, outs)]
    SC = pd.DataFrame(scan) if scan else pd.read_csv(p3 / "gamma_scan.csv")
    SC.to_csv(p3 / "gamma_scan.csv", index=False)
    pooled = SC.groupby("gamma").agg(mean_ari=("mean_ari", "mean"), min_ari=("mean_ari", "min"), n_comm=("n_comm", "mean"))
    # The ARI >= 0.90 rule selects either the degenerate low-resolution regime (gamma <= 0.7: 2-3 communities,
    # a near-trivial split) or gamma >= 1.7 (~25 neighbourhood clusters). We use the modularity default
    # gamma = 1.0 (standard in commuting-region studies) with 100-seed consensus to absorb seed instability,
    # and report gamma = 0.7 and 1.7 as sensitivity partitions.
    gamma = GAMMA_MAIN
    print(pooled.round(3).to_string(), "\nchosen gamma", gamma, flush=True)

    com_rows, com_sum, lab_rows = [], [], []
    for jt in ["JT02", "JT00"]:
        ys = jt_years(jt); prev = None; next_id = 0; raw = {}
        Gs = {y: (G2[y] if jt == "JT02" else graph(jt, y)) for y in ys}
        with ProcessPoolExecutor(WORKERS) as ex:
            mems = dict(zip(ys, ex.map(_cons_job, [(*gparts(Gs[y]), gamma, rng.integers(0, 2**31), N_CONS) for y in ys])))
        for y in ys:
            G = Gs[y]
            mem = mems[y]
            iso = np.array(G.degree()) == 0                      # isolated tracts get no community
            groups = {c: {tracts[i] for i in np.where((mem == c) & ~iso)[0]} for c in set(mem[~iso])}
            # Greene et al. (2010) matching with theta = 0.3
            ids, ev = {}, dict(births=0, deaths=0, merges=0, splits=0)
            if prev is None:
                for c in sorted(groups, key=lambda c: -len(groups[c])):
                    ids[c] = next_id; next_id += 1
                ev["births"] = len(groups)
            else:
                jac = [(len(groups[c] & pg) / len(groups[c] | pg), c, pid) for c in groups for pid, pg in prev.items()]
                hits = [x for x in jac if x[0] >= THETA]
                taken = set()
                for jv, c, pid in sorted(hits, reverse=True):
                    if c not in ids and pid not in taken:
                        ids[c] = pid; taken.add(pid)
                for c in groups:
                    if c not in ids:
                        ids[c] = next_id; next_id += 1
                curr_hits = pd.Series([c for _, c, _ in hits]).value_counts() if hits else pd.Series(dtype=int)
                prev_hits = pd.Series([p for _, _, p in hits]).value_counts() if hits else pd.Series(dtype=int)
                ev["merges"] = int((curr_hits >= 2).sum()); ev["splits"] = int((prev_hits >= 2).sum())
                ev["births"] = int(sum(c not in curr_hits.index for c in groups))
                ev["deaths"] = int(sum(p not in prev_hits.index for p in prev))
            cur = {ids[c]: g for c, g in groups.items()}
            m_vec = np.array([next((k for k, g in cur.items() if t in g), -1) for t in tracts])
            q = G.modularity(np.where(m_vec < 0, m_vec.max() + 1 + np.arange(len(m_vec)), m_vec).tolist(), weights="weight", resolution=gamma)
            a_prev = ari(raw[ys[ys.index(y) - 1]], m_vec) if prev is not None else np.nan
            raw[y] = m_vec
            com_sum.append(dict(jt=jt, year=y, gamma=gamma, n_communities=len(cur), modularity=q, ari_prev_year=a_prev,
                                n_isolated=int(iso.sum()), **ev))
            for k, g in cur.items():
                for t in g:
                    com_rows.append(dict(jt=jt, year=y, tract=t, community=k))
            prev = cur
        # self-loop sensitivity (JT02 only): ARI between partitions with and without self-loops
        if jt == "JT02":
            with ProcessPoolExecutor(WORKERS) as ex:
                sl_m = list(ex.map(_cons_job, [(*gparts(graph(jt, y, True)), gamma, rng.integers(0, 2**31), 30) for y in ys]))
            sl = [ari(raw[y], m_) for y, m_ in zip(ys, sl_m)]
            for row, v in zip([r for r in com_sum if r["jt"] == jt], sl):
                row["ari_selfloops"] = v
    sens = []
    for gs in GAMMA_SENS:
        prevp = None
        with ProcessPoolExecutor(WORKERS) as ex:
            mms = dict(zip(YEARS, ex.map(_cons_job, [(*GP[y], gs, rng.integers(0, 2**31), 30) for y in YEARS])))
        for y in YEARS:
            mm = mms[y]
            sens.append(dict(gamma=gs, year=y, n_communities=len(set(mm)), ari_prev_year=ari(prevp, mm) if prevp is not None else np.nan))
            prevp = mm
    pd.DataFrame(sens).to_csv(p3 / "communities_gamma_sensitivity.csv", index=False)
    CO = pd.DataFrame(com_rows); CO.to_csv(p3 / "communities.csv", index=False)
    CM = pd.DataFrame(com_sum); CM.to_csv(p3 / "communities_summary.csv", index=False)
    print(CM[CM.jt == "JT02"].round(3).to_string(index=False), flush=True)

    # community labels (nearest place to job-weighted centroid) and stable colour slots (greedy, neighbours differ)
    tj = T.groupby("tract").jobs.sum()
    nl = nodes.set_index("node")
    # candidate names: incorporated/census places inside the metro, the larger third by land area
    pl = pd.concat([gpd.read_file(RAW / "tiger" / f"tl_2020_{STATE_FIPS[s_]}_place.shp") for s_ in M["states"]], ignore_index=True)
    pl = gpd.GeoDataFrame(pl[["NAME", "ALAND"]], geometry=gpd.points_from_xy(pl.INTPTLON.astype(float), pl.INTPTLAT.astype(float)), crs=4326)
    pl = gpd.sjoin(pl, shp.reset_index()[["GEOID", "geometry"]].to_crs(4326), predicate="within")
    pl = pl[pl.ALAND >= pl.ALAND.quantile(0.67)] if len(pl) > 12 else pl
    PLACES = [(r.NAME, r.geometry.y, r.geometry.x) for r in pl.itertuples()]
    for jt in ["JT02", "JT00"]:
        c = CO[CO.jt == jt]
        size = c.groupby("community").size().sort_values(ascending=False)
        used_names = {}
        lab = {}
        for k in size.index:
            ts = c[c.community == k].tract.unique(); w = tj.reindex(ts).fillna(1).values + 1
            lon, lat = np.average(nl.loc[ts, "lon"], weights=w), np.average(nl.loc[ts, "lat"], weights=w)
            pl = min(PLACES, key=lambda p: (p[1] - lat) ** 2 + ((p[2] - lon) * 0.8) ** 2)
            dy, dx = (lat - pl[1]) * 111, (lon - pl[2]) * 88          # km
            comp = "central" if np.hypot(dx, dy) < 3 else ["E", "NE", "N", "NW", "W", "SW", "S", "SE"][int(((np.degrees(np.arctan2(dy, dx)) + 22.5) % 360) // 45)]
            lab[k] = (pl[0], comp)
        cnt = pd.Series([v[0] for v in lab.values()]).value_counts()
        seen = {}
        for k in size.index:
            nm, comp = lab[k]
            if cnt[nm] == 1:
                lab[k] = nm
            else:
                base_ = f"{nm} {comp}"; seen[base_] = seen.get(base_, 0) + 1
                lab[k] = base_ if seen[base_] == 1 else f"{base_} {seen[base_]}"
        cadj = {k: set() for k in size.index}
        for y, g in c.groupby("year"):
            m = dict(zip(g.tract, g.community))
            for a, bs in adj.items():
                for b in bs:
                    if a in m and b in m and m[a] != m[b]:
                        cadj[m[a]].add(m[b])
        slot = {}
        for k in size.index:
            bad = {slot[n] for n in cadj[k] if n in slot}
            slot[k] = next((s for s in range(8) if s not in bad), len(slot) % 8)
        for k in size.index:
            lab_rows.append(dict(jt=jt, community=k, label=lab[k], slot=slot[k], tract_years=int(size[k]),
                                 first=int(c[c.community == k].year.min()), last=int(c[c.community == k].year.max())))
    pd.DataFrame(lab_rows).to_csv(p3 / "community_labels.csv", index=False)

    # ============================================================ flow trends
    oc = pd.read_parquet(od.parent.parent / "parquet" / "oos" / "oos_county_centroids.parquet").set_index("cty")
    loc = pd.concat([nodes.set_index("node")[["lon", "lat"]], oc[["lon", "lat"]]])
    tn = nodes[nodes.type == "tract"]
    loc = pd.concat([loc, tn.groupby("county")[["lon", "lat"]].mean()])
    loc = loc[~loc.index.duplicated()]
    trows = []
    for jt in ["JT02", "JT00"]:
        ys = jt_years(jt); n = len(ys)
        for scale in ["metro", "nation"]:
            q = P[P.jt == jt].copy()
            if scale == "nation":
                q["h_node"], q["w_node"] = q.h_node.str[:5], q.w_node.str[:5]
            S = q.groupby(["h_node", "w_node", "year"]).S000.sum().unstack().reindex(columns=ys).fillna(0)
            S = S[S.index.get_level_values(0) != S.index.get_level_values(1)]
            f5, l5 = S.iloc[:, :5], S.iloc[:, -5:]
            elig = (S.mean(1) >= 10) | (f5.mean(1) >= 10) | (l5.mean(1) >= 10)
            S = S[elig]
            Sv = S.values.astype(float)
            with ProcessPoolExecutor(WORKERS) as ex:
                mks = list(ex.map(_mk_job, list(Sv), chunksize=200))
            res = [(h, w, v.mean(), v[:5].mean(), v[-5:].mean(), (v >= 10).mean(), (v[:5] < 3).all(), (v[-5:] < 3).all(), tau, p, slope)
                   for (h, w), v, (tau, p, slope) in zip(S.index, Sv, mks)]
            R_ = pd.DataFrame(res, columns=["h_node", "w_node", "mean", "first5", "last5", "share_ge10", "absent_first", "absent_last", "tau", "p", "sen_slope"])
            pv = R_.p.fillna(1).values; o = np.argsort(pv); m = len(pv)
            qv = np.empty(m); qv[o] = np.minimum.accumulate((pv[o] * m / np.arange(1, m + 1))[::-1])[::-1]
            R_["q"] = np.minimum(qv, 1)
            cls = np.where(R_.absent_first & (R_.last5 >= 10), "new",
                  np.where(R_.absent_last & (R_.first5 >= 10), "fading",
                  np.where((R_.q < 0.05) & (R_.tau > 0), "intensifying",
                  np.where((R_.q < 0.05) & (R_.tau < 0), "declining",
                  np.where(R_.share_ge10 >= 0.9, "persistent", "sporadic")))))
            R_["cls"] = cls
            hl, wl = loc.reindex(R_.h_node), loc.reindex(R_.w_node)
            la1, lo1, la2, lo2 = map(np.radians, (hl.lat.values, hl.lon.values, wl.lat.values, wl.lon.values))
            R_["miles"] = 3958.76 * 2 * np.arcsin(np.sqrt(np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2))
            R_["flag_long"] = R_.miles > LONG_MI
            R_["flag_artefact_tract"] = R_.h_node.isin(art_tracts[jt]) | R_.w_node.isin(art_tracts[jt])
            R_.insert(0, "scale", scale); R_.insert(0, "jt", jt)
            trows.append(R_)
    TR = pd.concat(trows); TR.to_csv(p3 / "flow_trends.csv", index=False)
    summ = []
    for (jt, scale), g in TR.groupby(["jt", "scale"]):
        for lab_, gg in [("all", g), ("excl. flagged", g[~g.flag_long & ~g.flag_artefact_tract])]:
            vc = gg.cls.value_counts()
            summ.append(dict(jt=jt, scale=scale, subset=lab_, pairs=len(gg), workers_mean=round(gg["mean"].sum()),
                             **{k: int(vc.get(k, 0)) for k in ["new", "intensifying", "persistent", "declining", "fading", "sporadic"]}))
    TS = pd.DataFrame(summ); TS.to_csv(p3 / "flow_trend_summary.csv", index=False)
    print(TS.to_string(index=False), flush=True)

    # ============================================================ shocks: pre-trend deviations, 2009 level shift, churn
    V = pd.read_csv(od / "tables" / "volumes_county_year.csv"); V = V[V.jt == "JT02"].set_index("year")
    D = pd.read_csv(od / "tables" / "commute_distance_year.csv")
    dm = D[(D.jt == "JT02") & (D.scope == "within_msa") & (D.group == "all")].set_index("year").median_mi
    DEC = pd.read_csv(od / "tables" / "distance_decay_poisson.csv"); beta = DEC[DEC.jt == "JT02"].set_index("year").beta_logd
    CSH = pd.read_csv(od / "tables" / "commutershed_core_jobs.csv"); core = CSH[CSH.jt == "JT02"].set_index("year").core
    cm2 = CM[CM.jt == "JT02"].set_index("year")
    ind = {"MSA jobs": V.msa_jobs_total, "In-commuters (MO)": V.inflow_mo, "In-commuters (other states)": V.inflow_aux,
           "Out-commuters (MO)": V.outflow_mo, "Out-commuters (other states)": V.outflow_oos,
           "Self-containment": V.self_contain_res, "Median commute (mi)": dm, "Distance-decay beta": beta,
           "Core-county share of core jobs": core, "Communities": cm2.n_communities}
    shock = []
    for name, s in ind.items():
        for (a, b), targets in [((2002, 2007), [2010]), ((2014, 2019), [2021, 2024])]:
            x = np.arange(a, b + 1); fit = np.polyfit(x, s.loc[a:b].values, 1)
            for t in targets:
                pred = np.polyval(fit, t)
                shock.append(dict(indicator=name, pretrend=f"{a}-{b}", year=t, actual=s.loc[t], pretrend_pred=pred,
                                  deviation=s.loc[t] - pred, deviation_pct=(s.loc[t] - pred) / abs(pred)))
    SH = pd.DataFrame(shock); SH.to_csv(p3 / "shock_windows.csv", index=False)
    brk = []
    for name, s in ind.items():
        y = s.loc[2002:2019]; X = sm.add_constant(np.column_stack([y.index - 2002, (y.index >= 2009).astype(float)]))
        for lab_, mask in [("all years", np.ones(len(y), bool)), ("excl. 2006", y.index != 2006)]:
            r = sm.OLS(y.values[mask], X[mask]).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
            brk.append(dict(indicator=name, sample=lab_, shift_2009=r.params[2], se=r.bse[2], p=r.pvalues[2]))
    pd.DataFrame(brk).to_csv(p3 / "break_test_2009.csv", index=False)
    # flow churn: volume share of year t-1 flows (pairs >= 10) that persist at >= 10 in year t
    ch = []
    q = P[P.jt == "JT02"].groupby(["year", "h_node", "w_node"]).S000.sum()
    for y in YEARS[1:]:
        a, b = q.loc[y - 1], q.loc[y]
        a10 = a[a >= 10]; b10 = b[b >= 10]
        both = a10.index.intersection(b10.index)
        ch.append(dict(year=y, pairs_prev=len(a10), pairs=len(b10), jaccard=len(both) / len(a10.index.union(b10.index)),
                       vol_persist=a10.loc[both].sum() / a10.sum()))
    pd.DataFrame(ch).to_csv(p3 / "flow_churn_JT02.csv", index=False)

    # ============================================================ figure: gamma scan
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(6, 4.4), sharex=True)
    ax.plot(pooled.index, pooled.mean_ari, color="#2a78d6", marker="o", ms=3, lw=2)
    ax.axhline(0.9, color="#52514e", lw=0.8, ls=":"); ax.axvline(gamma, color="#d9480f", lw=1)
    ax.set_ylabel("seed stability\n(mean pairwise ARI)")
    ax.set_title(f"Resolution scan, JT02 2002-2024 pooled; chosen gamma = {gamma}", loc="left", fontsize=9)
    ax2.plot(pooled.index, pooled.n_comm, color="#2a78d6", marker="o", ms=3, lw=2); ax2.axvline(gamma, color="#d9480f", lw=1)
    ax2.set_ylabel("communities\n(mean per year)"); ax2.set_xlabel("Leiden resolution gamma")
    fig.tight_layout(); [fig.savefig(p3 / "figures" / f"gamma_scan.{e}", dpi=200) for e in ("png", "svg")]; plt.close(fig)
    json.dump(dict(gamma=gamma, seed=SEED), open(p3 / "params.json", "w"))


if __name__ == "__main__":
    main(*sys.argv[1:])
