"""Phase 2: time-series description of a metro's commuting flows, 2002-2024.

Usage: python scripts/04_describe.py [metro]      (default: springfield)

Primary series: JT02 (private jobs, consistent 2002-2024). JT00 (all jobs) reported for 2010+.
Inputs : outputs/<metro>/{blockflows.parquet, panel.parquet, nodes.csv}, Data/tiger tracts
Outputs: outputs/<metro>/tables/*.csv, outputs/<metro>/figures/*.png|svg

Fixed analysis choices (stated, with sensitivity where noted):
  LONG_MI     = 100  straight-line miles: "long-distance" flag for workplace-artifact check (sens. 50, 150)
  JUMP        = tract job change > 50% AND > 500 jobs year-over-year (handoff section 4.5)
  Job centre  = tract job density >= DENS jobs/acre AND jobs >= MINJ; contiguous tracts merged;
                centre must total >= CENTRE_MIN jobs. Default 5 jobs/acre, 1,000, 5,000 (sens. grid printed).
"""
import sys

import duckdb
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import statsmodels.api as sm

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import OUT, METROS, RAW, YEARS

LONG_MI = 100
DENS, MINJ, CENTRE_MIN = 5.0, 1000, 5000
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 2,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.dpi": 200})


def wmedian(x, w):
    o = np.argsort(x)
    x, w = np.asarray(x)[o], np.asarray(w)[o]
    c = np.cumsum(w)
    return float(x[np.searchsorted(c, c[-1] / 2)]) if c[-1] > 0 else np.nan


def line_chart(df, cols, title, ylabel, fname, figdir, labels=None, pct=False, jt00=None, note=None):
    """One indicator family vs year; JT02 solid, optional JT00 (2010+) dashed same colour."""
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for i, c in enumerate(cols):
        lab = (labels or {}).get(c, c)
        s = df[c].dropna()
        ax.plot(s.index, s.values, color=PAL[i % 8], label=lab, marker="o", ms=3)
        if jt00 is not None and c in jt00:
            t = jt00[c].dropna()
            ax.plot(t.index, t.values, color=PAL[i % 8], ls="--", lw=1.2, alpha=0.8)
        if len(cols) <= 4:
            ax.annotate(lab, (s.index[-1], s.values[-1]), xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=8, color=INK)
    for yr in (2008, 2020):
        ax.axvline(yr, color=INK2, lw=0.8, ls=":")
        ax.text(yr, 1.0, f" {yr}", transform=ax.get_xaxis_transform(), fontsize=7, color=INK2, va="top")
    ax.set_title(title, loc="left", fontsize=10, color=INK)
    ax.set_ylabel(ylabel)
    ax.set_xlim(2001.5, 2024.5 + (2.5 if len(cols) <= 4 else 0))
    if pct:
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    if len(cols) >= 2:
        ax.legend(frameon=False, fontsize=7, ncol=min(len(cols), 4), loc="upper left", bbox_to_anchor=(0, -0.12))
    foot = "Solid: JT02 private jobs." + (" Dashed: JT00 all jobs (2010+)." if jt00 is not None else "")
    fig.text(0.01, 0.005, foot + (" " + note if note else ""), fontsize=6.5, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    for ext in ("png", "svg"):
        fig.savefig(figdir / f"{fname}.{ext}")
    plt.close(fig)


def main(metro="springfield"):
    M = METROS[metro]
    od = OUT / metro
    tdir, fdir = od / "tables", od / "figures"
    tdir.mkdir(exist_ok=True); fdir.mkdir(exist_ok=True)
    C = M["counties"]; core = M["core"]
    con = duckdb.connect()
    P = con.execute(f"SELECT * FROM '{od/'panel.parquet'}'").df()
    P["hc"], P["wc"] = P.h_node.str[:5], P.w_node.str[:5]
    P["h_in"], P["w_in"] = P.hc.isin(C), P.wc.isin(C)
    B = con.execute(f"""SELECT year, jt, part, substr(h_geocode,1,5) hc, substr(w_geocode,1,5) wc,
                        S000, SA01,SA02,SA03,SE01,SE02,SE03,SI01,SI02,SI03, miles
                        FROM '{od/'blockflows.parquet'}' WHERE part='main'""").df()
    B["h_in"], B["w_in"] = B.hc.isin(C), B.wc.isin(C)

    # ---------- 1. county & metro volumes, ratios, self-containment ----------
    m = P[P.part == "main"]
    rows = []
    for (jt, yr), g in m.groupby(["jt", "year"]):
        a = P[(P.part == "aux") & (P.jt == jt) & (P.year == yr)]
        x = P[(P.part == "oos") & (P.jt == jt) & (P.year == yr)]      # metro residents working in other states
        r = dict(jt=jt, year=yr,
                 msa_jobs_mo=g.loc[g.w_in, "S000"].sum(), msa_jobs_aux=a.loc[a.w_in, "S000"].sum(),
                 live_work_msa=g.loc[g.w_in & g.h_in, "S000"].sum(),
                 inflow_mo=g.loc[g.w_in & ~g.h_in, "S000"].sum(), inflow_aux=a.loc[a.w_in, "S000"].sum(),
                 outflow_mo=g.loc[g.h_in & ~g.w_in, "S000"].sum(), outflow_oos=x.S000.sum(),
                 res_workers_mo=g.loc[g.h_in, "S000"].sum())
        r["res_workers_all"] = r["res_workers_mo"] + r["outflow_oos"]
        r["msa_jobs_total"] = r["msa_jobs_mo"] + r["msa_jobs_aux"]
        r["self_contain_res"] = r["live_work_msa"] / r["res_workers_all"]  # residents (any state of work) working in MSA
        r["self_suff_jobs"] = r["live_work_msa"] / r["msa_jobs_total"]     # MSA jobs filled by MSA residents
        for f, n in C.items():
            rw = g.loc[g.hc == f, "S000"].sum() + x.loc[x.hc == f, "S000"].sum(); jb = g.loc[g.wc == f, "S000"].sum() + a.loc[a.wc == f, "S000"].sum()
            r[f"{n}_res_workers"] = rw; r[f"{n}_jobs"] = jb; r[f"{n}_jobs_per_rw"] = jb / rw
            r[f"{n}_own_county"] = g.loc[(g.hc == f) & (g.wc == f), "S000"].sum() / rw
            r[f"{n}_in_msa"] = g.loc[(g.hc == f) & g.w_in, "S000"].sum() / rw
            r[f"{n}_to_core"] = g.loc[(g.hc == f) & (g.wc == core), "S000"].sum() / rw
        rows.append(r)
    V = pd.DataFrame(rows)
    V.loc[(V.jt == "JT00") & (V.year < 2010), V.columns[2:]] = np.nan   # federal jobs absent pre-2010
    V.to_csv(tdir / "volumes_county_year.csv", index=False)
    v2, v0 = V[V.jt == "JT02"].set_index("year"), V[V.jt == "JT00"].set_index("year")

    # tract jobs & resident workers per year (main + aux jobs)
    tj = (P[P.w_in].groupby(["jt", "year", "w_node"]).S000.sum().rename("jobs").reset_index()
          .rename(columns={"w_node": "tract"}))
    tr = (m[m.h_in].groupby(["jt", "year", "h_node"]).S000.sum().rename("res_workers").reset_index()
          .rename(columns={"h_node": "tract"}))
    T = tj.merge(tr, how="outer", on=["jt", "year", "tract"]).fillna(0)
    T.to_csv(tdir / "tract_jobs_residents_year.csv", index=False)

    # ---------- 2. commute distance ----------
    segs = {"S000": "all", "SE01": "earn <=1,250", "SE02": "earn 1,251-3,333", "SE03": "earn >3,333",
            "SI01": "goods", "SI02": "trade/transp/util", "SI03": "other services",
            "SA01": "age <=29", "SA02": "age 30-54", "SA03": "age 55+"}
    drows = []
    for (jt, yr), g in B.groupby(["jt", "year"]):
        win = g[g.h_in & g.w_in]
        jobs = g[g.w_in & g.miles.notna()]
        for col, lab in segs.items():
            drows.append(dict(jt=jt, year=yr, scope="within_msa", group=lab, workers=win[col].sum(),
                              median_mi=wmedian(win.miles, win[col]),
                              mean_mi=np.average(win.miles, weights=win[col]) if win[col].sum() else np.nan))
        for f, n in C.items():
            h = win[win.hc == f]
            drows.append(dict(jt=jt, year=yr, scope="within_msa", group=f"home {n}", workers=h.S000.sum(),
                              median_mi=wmedian(h.miles, h.S000), mean_mi=np.average(h.miles, weights=h.S000)))
        for lim in (None, 150, LONG_MI, 50):     # MSA jobs, all MO residents, with/without long-distance flows
            j = jobs if lim is None else jobs[jobs.miles <= lim]
            drows.append(dict(jt=jt, year=yr, scope="msa_jobs_mo_res", group="all" if lim is None else f"<= {lim} mi",
                              workers=j.S000.sum(), median_mi=wmedian(j.miles, j.S000),
                              mean_mi=np.average(j.miles, weights=j.S000)))
        lg = jobs[jobs.miles > LONG_MI]
        drows.append(dict(jt=jt, year=yr, scope="msa_jobs_mo_res", group=f"> {LONG_MI} mi (flag)",
                          workers=lg.S000.sum(), median_mi=wmedian(lg.miles, lg.S000) if len(lg) else np.nan,
                          mean_mi=np.average(lg.miles, weights=lg.S000) if len(lg) else np.nan))
    D = pd.DataFrame(drows)
    D.loc[(D.jt == "JT00") & (D.year < 2010), ["workers", "median_mi", "mean_mi"]] = np.nan
    D["age_period"] = np.where(~D.group.str.startswith("age"), "", np.where(D.year <= 2011, "2002-2011", "2012-2024"))
    D.to_csv(tdir / "commute_distance_year.csv", index=False)

    # long-distance flows into MSA jobs: share and largest origin/destination pairs
    L = (B[(B.jt == "JT02") & B.w_in].assign(long=lambda d: d.miles > LONG_MI)
         .groupby("year").apply(lambda g: pd.Series({"long_workers": g.loc[g.long, "S000"].sum(),
                                                     "share": g.loc[g.long, "S000"].sum() / g.S000.sum()}),
                                include_groups=False))
    L.to_csv(tdir / "long_distance_share_JT02.csv")

    # ---------- 3. commutershed of core-county jobs ----------
    ring = lambda hc: np.where(hc == core, "core", np.where(hc.isin(C), "suburban MSA", "outer MO"))
    cs = []
    for (jt, yr), g in P[P.wc == core].groupby(["jt", "year"]):
        s = g[g.part == "main"].groupby(ring(g[g.part == "main"].hc)).S000.sum()
        s["out of state"] = g.loc[g.part == "aux", "S000"].sum()
        s = s / s.sum()
        cs.append(dict(jt=jt, year=yr, **s.to_dict()))
    CS = pd.DataFrame(cs)
    CS.loc[(CS.jt == "JT00") & (CS.year < 2010), CS.columns[2:]] = np.nan
    CS.to_csv(tdir / "commutershed_core_jobs.csv", index=False)

    # distance-band shares (MSA jobs, MO residents) per year
    bins = [0, 2, 5, 10, 20, 35, 50, 100, 1e4]
    bl = ["0-2", "2-5", "5-10", "10-20", "20-35", "35-50", "50-100", "100+"]
    jb = B[B.w_in & B.miles.notna()].copy()
    jb["band"] = pd.cut(jb.miles, bins, labels=bl, right=False)
    DB = jb.groupby(["jt", "year", "band"], observed=False).S000.sum().unstack()
    DB = DB.div(DB.sum(1), axis=0).reset_index()
    DB.to_csv(tdir / "distance_bands_msa_jobs.csv", index=False)

    # distance decay: Poisson gravity among MSA tracts, origin & destination fixed effects, per year
    nodes = pd.read_csv(od / "nodes.csv", dtype={"node": str, "county": str})
    tn = nodes[nodes.type == "tract"].set_index("node")
    tracts = sorted(tn.index)
    lon, lat = np.radians(tn.loc[tracts, "lon"].values), np.radians(tn.loc[tracts, "lat"].values)
    dd = 3958.76 * 2 * np.arcsin(np.sqrt(np.sin((lat[:, None] - lat) / 2) ** 2 +
                                         np.cos(lat[:, None]) * np.cos(lat) * np.sin((lon[:, None] - lon) / 2) ** 2))
    grid = pd.DataFrame({"h_node": np.repeat(tracts, len(tracts)), "w_node": np.tile(tracts, len(tracts)),
                         "d": dd.ravel()})
    grid = grid[grid.h_node != grid.w_node]
    Hd = pd.get_dummies(grid.h_node, drop_first=True, dtype=float)
    Wd = pd.get_dummies(grid.w_node, drop_first=True, dtype=float)
    X = pd.concat([np.log(grid.d).rename("logd").to_frame(), Hd.add_prefix("h_"), Wd.add_prefix("w_")], axis=1)
    X = sm.add_constant(X).values
    dec = []
    for jt in ["JT02", "JT00"]:
        for yr in YEARS:
            if jt == "JT00" and yr < 2010:
                continue
            f = m[(m.jt == jt) & (m.year == yr) & m.h_in & m.w_in][["h_node", "w_node", "S000"]]
            y = grid.merge(f, how="left", on=["h_node", "w_node"]).S000.fillna(0).values
            res = sm.GLM(y, X, family=sm.families.Poisson()).fit()
            dec.append(dict(jt=jt, year=yr, beta_logd=-res.params[1], se=res.bse[1]))
    DEC = pd.DataFrame(dec)
    DEC.to_csv(tdir / "distance_decay_poisson.csv", index=False)

    # ---------- 4. job concentration & centres ----------
    shp = gpd.read_file(RAW / "tiger" / "tl_2020_29_tract.shp")
    shp = shp[shp.GEOID.isin(tracts)].to_crs(5070)
    shp["acres"] = shp.ALAND / 4046.856
    acres = shp.set_index("GEOID").acres
    nb = gpd.sjoin(shp[["GEOID", "geometry"]], shp[["GEOID", "geometry"]], predicate="touches")
    adj = nb.groupby("GEOID_left").GEOID_right.apply(set).to_dict()

    def centres(jobs, dens_thr, minj, cmin):
        dens = jobs / acres.reindex(jobs.index)
        cand = set(jobs.index[(dens >= dens_thr) & (jobs >= minj)])
        out, seen = [], set()
        for t in sorted(cand):
            if t in seen:
                continue
            comp, stack = set(), [t]
            while stack:
                u = stack.pop()
                if u in comp:
                    continue
                comp.add(u); stack.extend(adj.get(u, set()) & cand)
            seen |= comp
            if jobs[list(comp)].sum() >= cmin:
                out.append(comp)
        return out

    conc, cent_rows, sens = [], [], []
    for (jt, yr), g in T.groupby(["jt", "year"]):
        if jt == "JT00" and yr < 2010:
            continue
        j = g.set_index("tract").jobs.reindex(tracts).fillna(0).sort_values(ascending=False)
        sh = np.sort(j.values / j.sum())
        gini = 1 - 2 * np.sum(np.cumsum(sh) - sh / 2) / len(sh)
        cc = centres(j, DENS, MINJ, CENTRE_MIN)
        conc.append(dict(jt=jt, year=yr, top1=j.iloc[0] / j.sum(), top5=j.head(5).sum() / j.sum(),
                         top10=j.head(10).sum() / j.sum(), gini=gini, n_centres=len(cc),
                         centre_share=sum(j[list(c)].sum() for c in cc) / j.sum(), largest_tract=j.index[0]))
        for k, c in enumerate(sorted(cc, key=lambda c: -j[list(c)].sum())):
            cent_rows.append(dict(jt=jt, year=yr, rank=k + 1, n_tracts=len(c), jobs=j[list(c)].sum(),
                                  tracts=";".join(sorted(c))))
        if jt == "JT02":
            for dthr in (2.5, 5, 10):
                for cmin in (2500, 5000, 10000):
                    sens.append(dict(year=yr, dens=dthr, centre_min=cmin, n_centres=len(centres(j, dthr, MINJ, cmin))))
    CONC = pd.DataFrame(conc); CONC.to_csv(tdir / "job_concentration.csv", index=False)
    CENT = pd.DataFrame(cent_rows); CENT.to_csv(tdir / "job_centres.csv", index=False)
    SENS = pd.DataFrame(sens).pivot_table(index="year", columns=["dens", "centre_min"], values="n_centres")
    SENS.to_csv(tdir / "job_centres_sensitivity_JT02.csv")

    # persistence: how many years each tract is part of a centre (JT02)
    c2 = CENT[CENT.jt == "JT02"].assign(tract=lambda d: d.tracts.str.split(";")).explode("tract")
    pers = c2.groupby("tract").agg(years_in_centre=("year", "nunique"), first=("year", "min"), last=("year", "max"))
    pers.sort_values("years_in_centre", ascending=False).to_csv(tdir / "job_centre_persistence_JT02.csv")

    # ---------- 5. year-over-year tract job jumps (possible reporting artefacts) ----------
    J = T.sort_values("year").copy()
    J["prev"] = J.groupby(["jt", "tract"]).jobs.shift()
    J["chg"] = J.jobs - J.prev
    J["pct"] = J.chg / J.prev.replace(0, np.nan)
    jumps = J[(J.chg.abs() > 500) & ((J.pct.abs() > 0.5) | J.prev.eq(0))]
    jumps = jumps[~((jumps.jt == "JT00") & (jumps.year <= 2010))]
    jumps.sort_values(["jt", "year", "chg"]).to_csv(tdir / "tract_job_jumps.csv", index=False)

    # ---------- figures ----------
    n = list(C.values())
    line_chart(v2[[f"{c}_jobs" for c in n]] / 1e3, [f"{c}_jobs" for c in n], "Jobs by county (thousands)",
               "jobs (000)", "01_jobs_county", fdir, {f"{c}_jobs": c for c in n}, jt00=v0[[f"{c}_jobs" for c in n]] / 1e3)
    line_chart(v2[[f"{c}_res_workers" for c in n]] / 1e3, [f"{c}_res_workers" for c in n],
               "Resident workers by county (thousands; any state of work)", "workers (000)", "02_res_workers_county", fdir,
               {f"{c}_res_workers": c for c in n}, jt00=v0[[f"{c}_res_workers" for c in n]] / 1e3)
    line_chart(v2[[f"{c}_jobs_per_rw" for c in n]], [f"{c}_jobs_per_rw" for c in n], "Jobs per resident worker",
               "ratio", "03_jobs_per_rw", fdir, {f"{c}_jobs_per_rw": c for c in n},
               jt00=v0[[f"{c}_jobs_per_rw" for c in n]])
    line_chart(v2[[f"{c}_own_county" for c in n]], [f"{c}_own_county" for c in n],
               "Resident workers employed in own county", "share", "04_own_county", fdir,
               {f"{c}_own_county": c for c in n}, pct=True, jt00=v0[[f"{c}_own_county" for c in n]])
    line_chart(v2[[f"{c}_to_core" for c in n[1:]]], [f"{c}_to_core" for c in n[1:]],
               f"Suburban resident workers employed in {n[0]} County", "share", "05_to_core", fdir,
               {f"{c}_to_core": c for c in n[1:]}, pct=True, jt00=v0[[f"{c}_to_core" for c in n[1:]]])
    flows = ["live_work_msa", "inflow_mo", "outflow_mo", "inflow_aux", "outflow_oos"]
    line_chart(v2[flows] / 1e3, flows, "Metro flow volumes (thousands)", "workers (000)", "06_flow_volumes", fdir,
               {"live_work_msa": "live & work", "inflow_mo": "in from MO", "outflow_mo": "out to MO",
                "inflow_aux": "in from other states", "outflow_oos": "out to other states"}, jt00=v0[flows] / 1e3)
    line_chart(v2[["self_contain_res", "self_suff_jobs"]], ["self_contain_res", "self_suff_jobs"],
               "Metro self-containment", "share", "07_self_containment", fdir,
               {"self_contain_res": "residents working in metro", "self_suff_jobs": "metro jobs held by residents"},
               pct=True, jt00=v0[["self_contain_res", "self_suff_jobs"]])
    piv = lambda scope, groups, jt, col="median_mi": (D[(D.scope == scope) & (D.jt == jt) & D.group.isin(groups)]
                                                      .pivot(index="year", columns="group", values=col)[groups])
    for key, groups, title in [
            ("earn", ["earn <=1,250", "earn 1,251-3,333", "earn >3,333"], "by monthly earnings"),
            ("ind", ["goods", "trade/transp/util", "other services"], "by industry"),
            ("home", [f"home {c}" for c in n], "by home county"),
            ("all", ["all"], "all workers")]:
        line_chart(piv("within_msa", groups, "JT02"), groups, f"Median straight-line commute within metro, {title}",
                   "miles", f"08_median_mi_{key}", fdir, jt00=piv("within_msa", groups, "JT00"))
    ag = ["age <=29", "age 30-54", "age 55+"]
    a2 = piv("within_msa", ag, "JT02")
    line_chart(a2, ag, "Median straight-line commute within metro, by age", "miles", "08_median_mi_age", fdir,
               note="Age frame changes in 2012: compare within 2002-2011 and 2012-2024 only.")
    g4 = ["all", "<= 150 mi", f"<= {LONG_MI} mi", "<= 50 mi"]
    line_chart(piv("msa_jobs_mo_res", g4, "JT02", "mean_mi"), g4,
               "Mean commute to metro jobs, with and without long-distance flows", "miles", "09_mean_mi_longdist",
               fdir, note="MO residents only. Long flows may be HQ-reporting artefacts.")
    cs2, cs0 = CS[CS.jt == "JT02"].set_index("year"), CS[CS.jt == "JT00"].set_index("year")
    rc = ["core", "suburban MSA", "outer MO", "out of state"]
    line_chart(cs2[rc], rc, f"Where {n[0]} County jobs' workers live", "share of jobs", "10_commutershed", fdir,
               pct=True, jt00=cs0[rc])
    db2 = DB[DB.jt == "JT02"].set_index("year")
    fig, ax = plt.subplots(figsize=(7, 3.8))
    yrs = [2002, 2007, 2010, 2015, 2019, 2021, 2024]
    seq = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
    for c, yr in zip(seq, yrs):
        ax.plot(range(len(bl)), db2.loc[yr, bl].cumsum().values, color=c, marker="o", ms=3, label=str(yr))
    ax.set_xticks(range(len(bl)), bl); ax.set_xlabel("straight-line miles, home to work")
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title("Cumulative share of metro jobs by commute distance (JT02)", loc="left", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=7, title="year", title_fontsize=7)
    fig.tight_layout(); [fig.savefig(fdir / f"11_distance_cdf.{e}") for e in ("png", "svg")]; plt.close(fig)
    dec2, dec0 = DEC[DEC.jt == "JT02"].set_index("year"), DEC[DEC.jt == "JT00"].set_index("year")
    line_chart(dec2[["beta_logd"]], ["beta_logd"], "Distance-decay exponent among metro tracts (Poisson gravity, O/D fixed effects)",
               "beta (higher = steeper decay)", "12_distance_decay", fdir, {"beta_logd": "beta"}, jt00=dec0[["beta_logd"]])
    c2_, c0_ = CONC[CONC.jt == "JT02"].set_index("year"), CONC[CONC.jt == "JT00"].set_index("year")
    line_chart(c2_[["top1", "top5", "top10", "centre_share"]], ["top1", "top5", "top10", "centre_share"],
               "Job concentration among metro tracts", "share of metro jobs", "13_concentration", fdir,
               {"top1": "largest tract", "top5": "top 5 tracts", "top10": "top 10 tracts", "centre_share": "in job centres"},
               pct=True, jt00=c0_[["top1", "top5", "top10", "centre_share"]],
               note=f"Centres: contiguous tracts >= {DENS:g} jobs/acre & >= {MINJ:,} jobs, total >= {CENTRE_MIN:,}.")
    line_chart(c2_[["gini"]], ["gini"], "Gini coefficient of jobs across metro tracts", "Gini", "14_gini", fdir,
               {"gini": "Gini"}, jt00=c0_[["gini"]])
    print("tables:", sorted(p.name for p in tdir.glob("*.csv")))
    print("figures:", len(list(fdir.glob("*.png"))))


if __name__ == "__main__":
    main(*sys.argv[1:])
