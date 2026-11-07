"""Phase 4: formal structure tests and robustness, answering the critical review (outputs/manuscript/CRITICAL_REVIEW.md).

Usage: python scripts/07_structure_tests.py <metro>      -> outputs/<metro>/phase4/

JT02, tract level, within-metro flows (home and work both in the metro) unless stated.
  1. polycentricity_indices.csv  : annual Angel-Blei-style shares (main LISA centre / other centres / outside centres /
                                   same-tract), Green (2007) functional polycentricity P_F, destination and OD entropy
                                   (Marin et al. 2022, normalised), destination HHI, share of jobs in net-attractor tracts,
                                   rank-size slope of centre job counts (when >= 2 centres).
  2. gravity_null_modularity.csv : observed Leiden modularity (gamma = 1) vs 100 Poisson draws from the fitted
                                   doubly-constrained gravity model (Expert et al. 2011 logic): z-score and excess Q;
                                   plus communities of the residual network (F - T)+ (Odell et al. 2022) and their
                                   agreement (ARI) with the configuration-null partition.
  3. flow_trends_residual.csv    : per-pair Hamed-Rao Mann-Kendall on log((F+1)/(T+1)), i.e. growth- and
                                   distance-adjusted; BH q < 0.05; year-permutation baseline for the expected count.
  4. break_scan.csv              : level-shift (trend + step, HAC) at every candidate year 2005-2016 for the main
                                   indicators; max-|t| year reported (placebo scan); 2009/2011/2012 highlighted.
  5. shock_robustness.csv        : 2010/2021/2024 deviations from linear and log-linear pre-trends on 2002-07,
                                   2004-07, 2014-19; and raw changes.
  6. residence_anomaly.csv       : per county-year, resident workers vs the mean of the neighbouring years (%);
                                   documents the 2006 anomaly and tests for others.
  7. beta_robustness.csv         : distance-decay beta with pair-bootstrap SE (50 draws; 2002, 2010, 2019, 2024) and a
                                   marginal-invariance placebo (2002 flow shares IPF-scaled to 2024 margins).
  8. earnings_composition.csv    : nominal earnings-band shares of within-metro workers by year.
  9. artefact_regimes.csv        : multi-year job regimes per tract (> 50 % and > 500 from the tract's median).
"""
import importlib
import json
import sys
from itertools import combinations

import duckdb
import igraph as ig
import leidenalg as la
import numpy as np
import pandas as pd
import pymannkendall as mk
import statsmodels.api as sm

from config import OUT, YEARS, metro_def

d04 = importlib.import_module("04_describe")
decay_fit = d04.decay_beta
SEED = 20261107
N_NULL, N_BOOT, N_PERM = 100, 50, 20
MIN_EDGE, MIN_PAIR = 3, 10


def ari(a, b):
    a, b = np.asarray(a), np.asarray(b)
    _, ai = np.unique(a, return_inverse=True); _, bi = np.unique(b, return_inverse=True)
    ct = np.zeros((ai.max() + 1, bi.max() + 1)); np.add.at(ct, (ai, bi), 1)
    c2 = lambda x: x * (x - 1) / 2
    s, sa, sb, n = c2(ct).sum(), c2(ct.sum(1)).sum(), c2(ct.sum(0)).sum(), c2(len(a))
    e = sa * sb / n
    return 1.0 if (sa + sb) / 2 == e else (s - e) / ((sa + sb) / 2 - e)


def dc_fit(F, d, beta):
    """Doubly-constrained gravity expected flows for a given beta (intrazonal excluded)."""
    n = len(F); off = ~np.eye(n, dtype=bool)
    F = np.where(off, F, 0.0); O, D = F.sum(1), F.sum(0)
    K = np.where(off, np.exp(-beta * np.log(np.where(off, d, 1.0))), 0.0)
    a = np.ones(n); b = np.ones(n)
    for _ in range(500):
        a_new = np.divide(O, K @ b, out=np.zeros(n), where=(K @ b) > 0)
        b_new = np.divide(D, K.T @ a_new, out=np.zeros(n), where=(K.T @ a_new) > 0)
        if np.allclose(a_new, a, rtol=1e-9) and np.allclose(b_new, b, rtol=1e-9):
            a, b = a_new, b_new; break
        a, b = a_new, b_new
    return a[:, None] * K * b[None, :]


def leiden_q(W, gamma=1.0, seed=0):
    n = len(W); iu = np.triu_indices(n, 1); keep = W[iu] >= MIN_EDGE
    G = ig.Graph(n=n, edges=list(zip(iu[0][keep], iu[1][keep]))); G.es["weight"] = W[iu][keep].astype(float).tolist()
    p = la.find_partition(G, la.RBConfigurationVertexPartition, weights="weight", resolution_parameter=gamma, seed=int(seed), n_iterations=-1)
    return np.array(p.membership), G.modularity(p.membership, weights="weight", resolution=gamma), G


def gravity_modularity(W, T, membership):
    """Modularity of a partition under a gravity null (Expert et al. 2011): Q = 1/2m sum (A_ij - T_ij) delta."""
    m2 = W.sum()
    Tn = T * (W.sum() / T.sum())
    same = membership[:, None] == membership[None, :]
    return float(((W - Tn) * same).sum() / m2)


def mk_series(v):
    try:
        r = mk.hamed_rao_modification_test(v); return r.Tau, r.p, r.slope
    except Exception:
        return np.nan, 1.0, np.nan


def bh(p):
    p = np.asarray(p, float); o = np.argsort(p); m = len(p); q = np.empty(m)
    q[o] = np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]
    return np.minimum(q, 1)


def main(metro):
    M = metro_def(metro); C = M["counties"]; core = M["core"]
    od = OUT / metro; p4 = od / "phase4"; p4.mkdir(exist_ok=True)
    rng = np.random.default_rng(SEED)
    con = duckdb.connect()
    P = con.execute(f"SELECT * FROM '{od/'panel.parquet'}' WHERE jt='JT02'").df()
    P["h_in"], P["w_in"] = P.h_node.str[:5].isin(C), P.w_node.str[:5].isin(C)
    nodes = pd.read_csv(od / "nodes.csv", dtype={"node": str, "county": str})
    tn = nodes[nodes.type == "tract"].set_index("node"); tracts = sorted(tn.index); n = len(tracts); ix = {t: i for i, t in enumerate(tracts)}
    lon, lat = np.radians(tn.loc[tracts, "lon"].values), np.radians(tn.loc[tracts, "lat"].values)
    dd = 3958.76 * 2 * np.arcsin(np.sqrt(np.sin((lat[:, None] - lat) / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat) * np.sin((lon[:, None] - lon) / 2) ** 2))
    T_ = pd.read_csv(od / "tables" / "tract_jobs_residents_year.csv", dtype={"tract": str}); T_ = T_[T_.jt == "JT02"]
    jobs_all = T_.pivot(index="tract", columns="year", values="jobs").reindex(index=tracts, columns=YEARS).fillna(0)   # incl. in-commuters
    cen = pd.read_csv(od / "phase3" / "centres.csv", dtype={"tract": str}); cen = cen[cen.jt == "JT02"]
    csum = pd.read_csv(od / "phase3" / "centres_summary.csv"); csum = csum[csum.jt == "JT02"].set_index("year")
    cm = pd.read_csv(od / "phase3" / "communities_summary.csv"); cm = cm[cm.jt == "JT02"].set_index("year")
    DEC = pd.read_csv(od / "tables" / "distance_decay_poisson.csv"); DEC = DEC[DEC.jt == "JT02"].set_index("year").beta_logd

    # flow matrices per year
    Fy = {}
    for y in YEARS:
        f = P[(P.year == y) & P.h_in & P.w_in].groupby(["h_node", "w_node"]).S000.sum()
        F = np.zeros((n, n)); F[[ix[h] for h, _ in f.index], [ix[w] for _, w in f.index]] = f.values; Fy[y] = F
    off = ~np.eye(n, dtype=bool)

    # ================================================================ 1. polycentricity indices
    rows = []
    for y in YEARS:
        F = Fy[y]; j = jobs_all[y].values; tot = j.sum()
        comps = [set(c.split(";")) for c in str(csum.at[y, "centres"]).split(" | ")] if isinstance(csum.at[y, "centres"], str) and csum.at[y, "centres"] else []
        cj = sorted([j[[ix[t] for t in c]].sum() for c in comps], reverse=True)
        main_sh = cj[0] / tot if cj else 0; other_sh = sum(cj[1:]) / tot if len(cj) > 1 else 0
        rs = np.polyfit(np.log(np.arange(1, len(cj) + 1)), np.log(cj), 1)[0] if len(cj) >= 2 else np.nan
        Fo = np.where(off, F, 0); s_in = Fo.sum(0); s_out = Fo.sum(1)
        sig = s_in.std(); star = np.zeros(n); star[0] = s_in.sum(); sig_max = star.std()
        dens = (Fo >= MIN_PAIR).sum() / (n * (n - 1))
        pf = (1 - sig / sig_max) * dens if sig_max > 0 else np.nan
        ps = j / tot; dest_H = -(ps[ps > 0] * np.log(ps[ps > 0])).sum() / np.log(n)
        po = F / F.sum(); od_H = -(po[po > 0] * np.log(po[po > 0])).sum() / np.log(n * n)
        # resident workers living in metro (origins): net attractor = jobs > resident workers
        rw = T_[T_.year == y].set_index("tract").res_workers.reindex(tracts).fillna(0).values
        attr = ps[j > rw].sum()
        rows.append(dict(year=y, n_centres=len(cj), main_centre_share=main_sh, other_centres_share=other_sh,
                         outside_centres_share=1 - main_sh - other_sh, same_tract_share=np.trace(F) / F.sum(),
                         rank_size_slope=rs, functional_polycentricity=pf, network_density_ge10=dens,
                         dest_entropy_norm=dest_H, od_entropy_norm=od_H, dest_hhi=(ps ** 2).sum(),
                         attractor_job_share=attr, n_attractor_tracts=int((j > rw).sum())))
    PI = pd.DataFrame(rows); PI.to_csv(p4 / "polycentricity_indices.csv", index=False)

    # ================================================================ 2. gravity-null modularity & residual communities
    gq = []
    Ty = {}
    for y in YEARS:
        F = Fy[y]; beta = DEC[y]; T = dc_fit(F, dd, beta); Ty[y] = T
        W = np.where(off, F + F.T, 0)
        mem, q_obs, G = leiden_q(W, 1.0, SEED)
        q_null = []
        for k in range(N_NULL):
            S = rng.poisson(T); Ws = np.where(off, S + S.T, 0)
            q_null.append(leiden_q(Ws, 1.0, SEED + k + 1)[1])
        q_null = np.array(q_null)
        Rw = np.clip(F - T, 0, None); Rw = np.where(off, Rw + Rw.T, 0)
        mem_r, q_r, _ = leiden_q(Rw, 1.0, SEED)
        gq.append(dict(year=y, beta=beta, q_obs=q_obs, q_null_mean=q_null.mean(), q_null_sd=q_null.std(),
                       z=(q_obs - q_null.mean()) / q_null.std() if q_null.std() > 0 else np.nan, q_excess=q_obs - q_null.mean(),
                       q_gravity_null=gravity_modularity(W, np.where(off, T + T.T, 0), mem),
                       n_comm_config=len(set(mem)), n_comm_residual=len(set(mem_r)), ari_residual_vs_config=ari(mem, mem_r),
                       residual_flow_share=np.clip(F - T, 0, None).sum() / F[off].sum()))
    GQ = pd.DataFrame(gq); GQ.to_csv(p4 / "gravity_null_modularity.csv", index=False)

    # ================================================================ 3. residual-based flow trends
    Fs = np.stack([Fy[y] for y in YEARS]); Ts = np.stack([Ty[y] for y in YEARS])
    mean_f = Fs.mean(0); elig = off & ((mean_f >= MIN_PAIR) | (Fs[:5].mean(0) >= MIN_PAIR) | (Fs[-5:].mean(0) >= MIN_PAIR))
    ii, jj = np.where(elig)
    R = np.log((Fs[:, ii, jj] + 1) / (Ts[:, ii, jj] + 1))        # years x pairs
    res = [mk_series(R[:, k]) for k in range(len(ii))]
    TR = pd.DataFrame(dict(h_node=[tracts[i] for i in ii], w_node=[tracts[j] for j in jj], mean_flow=mean_f[ii, jj],
                           mean_expected=Ts.mean(0)[ii, jj], miles=dd[ii, jj],
                           tau=[r[0] for r in res], p=[r[1] for r in res], sen_slope=[r[2] for r in res]))
    TR["q"] = bh(TR.p.fillna(1))
    TR["cls"] = np.where((TR.q < 0.05) & (TR.tau > 0), "intensifying_beyond_gravity",
                np.where((TR.q < 0.05) & (TR.tau < 0), "declining_beyond_gravity", "no_trend"))
    # raw-count comparison on the same pairs
    raw = [mk_series(Fs[:, i, j]) for i, j in zip(ii, jj)]
    TR["tau_raw"] = [r[0] for r in raw]; TR["q_raw"] = bh(np.array([r[1] for r in raw]))
    TR["cls_raw"] = np.where((TR.q_raw < 0.05) & (TR.tau_raw > 0), "intensifying", np.where((TR.q_raw < 0.05) & (TR.tau_raw < 0), "declining", "no_trend"))
    TR.to_csv(p4 / "flow_trends_residual.csv", index=False)
    # year-permutation baseline (same permutation for all pairs; preserves cross-pair dependence)
    perm_counts = []
    for k in range(N_PERM):
        pm = rng.permutation(len(YEARS)); pr = [mk_series(R[pm, kk])[1] for kk in range(len(ii))]
        perm_counts.append(int((bh(np.array(pr)) < 0.05).sum()))
    summ = dict(pairs=len(TR), sig_residual=int((TR.q < 0.05).sum()), intens_residual=int((TR.cls == "intensifying_beyond_gravity").sum()),
                decl_residual=int((TR.cls == "declining_beyond_gravity").sum()), sig_raw=int((TR.q_raw < 0.05).sum()),
                intens_raw=int((TR.cls_raw == "intensifying").sum()), decl_raw=int((TR.cls_raw == "declining").sum()),
                perm_expected_sig_mean=float(np.mean(perm_counts)), perm_expected_sig_max=int(np.max(perm_counts)))
    json.dump(summ, open(p4 / "flow_trends_residual_summary.json", "w"), indent=1)

    # ================================================================ 4. break scan & 5. shock robustness
    V = pd.read_csv(od / "tables" / "volumes_county_year.csv"); V = V[V.jt == "JT02"].set_index("year")
    D = pd.read_csv(od / "tables" / "commute_distance_year.csv")
    dm = D[(D.jt == "JT02") & (D.scope == "within_msa") & (D.group == "all")].set_index("year").median_mi
    CSH = pd.read_csv(od / "tables" / "commutershed_core_jobs.csv"); CSH = CSH[CSH.jt == "JT02"].set_index("year")
    ind = {"MSA jobs": V.msa_jobs_total, "In-commuters (all)": V.inflow_mo + V.inflow_aux, "Out-commuters (all)": V.outflow_mo + V.outflow_oos,
           "Self-containment": V.self_contain_res, "Median commute (mi)": dm, "Distance-decay beta": DEC,
           "Core-county share of core jobs": CSH.core, "Modularity": cm.modularity, "Functional polycentricity": PI.set_index("year").functional_polycentricity,
           "Main-centre share": PI.set_index("year").main_centre_share}
    scan = []
    for name, s in ind.items():
        y = s.loc[2002:2019].dropna(); x = y.index.values
        for b in range(2005, 2017):
            X = sm.add_constant(np.column_stack([x - 2002, (x >= b).astype(float)]))
            r = sm.OLS(y.values, X).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
            scan.append(dict(indicator=name, break_year=b, shift=r.params[2], t=r.tvalues[2], p=r.pvalues[2]))
    BS = pd.DataFrame(scan)
    best = BS.loc[BS.groupby("indicator").t.apply(lambda t: t.abs().idxmax())].rename(columns={"break_year": "max_t_year"})
    BS.to_csv(p4 / "break_scan.csv", index=False)
    best.merge(BS[BS.break_year.isin([2009, 2011, 2012])].pivot(index="indicator", columns="break_year", values="t").add_prefix("t_"), on="indicator") \
        .to_csv(p4 / "break_scan_summary.csv", index=False)
    sh = []
    for name, s in ind.items():
        for (a, b, kind), targets in [((2002, 2007, "linear"), [2010]), ((2004, 2007, "linear"), [2010]), ((2002, 2007, "loglinear"), [2010]),
                                      ((2014, 2019, "linear"), [2021, 2024]), ((2014, 2019, "loglinear"), [2021, 2024])]:
            seg = s.loc[a:b].dropna()
            if len(seg) < 3 or (kind == "loglinear" and (seg <= 0).any()):
                continue
            fit = np.polyfit(seg.index, np.log(seg.values) if kind == "loglinear" else seg.values, 1)
            for t in targets:
                pred = np.polyval(fit, t); pred = np.exp(pred) if kind == "loglinear" else pred
                sh.append(dict(indicator=name, pretrend=f"{a}-{b} {kind}", year=t, actual=s.get(t), pretrend_pred=pred,
                               deviation_pct=(s.get(t) - pred) / abs(pred), raw_change_pct=(s.get(t) / s.get(b) - 1) if s.get(b) else np.nan))
    pd.DataFrame(sh).to_csv(p4 / "shock_robustness.csv", index=False)

    # ================================================================ 6. residence anomaly
    ra = []
    for f, nm in C.items():
        s = V[f"{nm}_res_workers"]
        for y in YEARS[1:-1]:
            nb = (s[y - 1] + s[y + 1]) / 2
            ra.append(dict(county=f, name=nm, year=y, res_workers=s[y], neighbour_mean=nb, dev_pct=(s[y] - nb) / nb))
    RA = pd.DataFrame(ra); RA.to_csv(p4 / "residence_anomaly.csv", index=False)

    # ================================================================ 7. beta robustness
    br = []
    for y in (2002, 2010, 2019, 2024):
        F = Fy[y]; b0, se0 = decay_fit(F, dd)
        pairs = np.array(np.where(off)).T; w = F[off]
        boots = []
        for k in range(N_BOOT):
            samp = rng.choice(len(pairs), len(pairs), replace=True)
            Fb = np.zeros_like(F); np.add.at(Fb, (pairs[samp, 0], pairs[samp, 1]), w[samp])
            boots.append(decay_fit(Fb, dd)[0])
        br.append(dict(year=y, beta=b0, se_profile=se0, se_bootstrap=np.std(boots), boot_lo=np.percentile(boots, 2.5), boot_hi=np.percentile(boots, 97.5)))
    # marginal-invariance placebo: 2002 flow pattern scaled by IPF to 2024 margins
    F02, F24 = Fy[2002], Fy[2024]; K = np.where(off, F02, 0).astype(float) + 1e-9
    O, Dd = np.where(off, F24, 0).sum(1), np.where(off, F24, 0).sum(0); a = np.ones(n); b = np.ones(n)
    for _ in range(300):
        a = np.divide(O, K @ b, out=np.zeros(n), where=(K @ b) > 0); b = np.divide(Dd, K.T @ a, out=np.zeros(n), where=(K.T @ a) > 0)
    placebo = decay_fit(a[:, None] * K * b[None, :], dd)[0]
    BR = pd.DataFrame(br); BR["placebo_2002pattern_2024margins"] = placebo; BR.to_csv(p4 / "beta_robustness.csv", index=False)

    # ================================================================ 8. earnings composition
    E = P[P.h_in & P.w_in].groupby("year")[["SE01", "SE02", "SE03"]].sum()
    E = E.div(E.sum(1), axis=0).rename(columns={"SE01": "share_le_1250", "SE02": "share_1251_3333", "SE03": "share_gt_3333"})
    E.to_csv(p4 / "earnings_composition.csv")

    # ================================================================ 9. multi-year artefact regimes
    reg = []
    for t in tracts:
        s = jobs_all.loc[t]; med = s.median()
        bad = (s - med).abs() > np.maximum(0.5 * med, 500)
        if bad.any() and med > 0:
            yrs = [int(y) for y in s.index[bad]]
            reg.append(dict(tract=t, median_jobs=med, n_years=len(yrs), years=";".join(map(str, yrs)),
                            min_jobs=s.min(), max_jobs=s.max()))
    pd.DataFrame(reg, columns=["tract", "median_jobs", "n_years", "years", "min_jobs", "max_jobs"]).to_csv(p4 / "artefact_regimes.csv", index=False)

    pd.set_option("display.width", 250)
    print(metro, "\n", PI[PI.year.isin([2002, 2010, 2019, 2024])].round(3).to_string(index=False))
    print(GQ[GQ.year.isin([2002, 2010, 2019, 2024])].round(3).to_string(index=False))
    print(summ)
    print(BR.round(3).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
