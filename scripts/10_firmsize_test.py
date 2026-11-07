"""Does rising large-firm (multi-site) employment explain the 2010-2019 LODES drift toward longer assigned commutes?

Hypothesis: LEHD assigns workers of multi-unit employers to establishments by imputation, which inflates assigned
distance; Green, Kutzbach & Vilhuber (2017, CES-WP-17-34) show LEHD distance rises steeply with the employer's
establishment count while ACS distance does not. If the share of jobs at large firms rose 2011-2019, that could
mechanically lower LODES self-containment. LODES 8 WAC files carry firm size (CFS01-05) and firm age (CFA01-05)
for JT02 (all private jobs) in 2011-2024 only (zeros in earlier years; LODESTechDoc8.5 footnote 13).

Usage: python scripts/10_firmsize_test.py            (after scripts/10_firmsize_download.py)

Inputs : Data/{mo,ks,il}/wac/*_wac_S000_JT02_{2011..2024}.csv.gz, outputs/<metro>/panel.parquet (JT02, all parts),
         outputs/<metro>/blockflows.parquet (block-pair miles), outputs/<metro>/counties.json via metro_def().
Outputs: outputs/external/wac_firmsize_tract_year.csv, wac_firmsize_metro_year.csv, lodes_tract_distance_year.csv,
         lodes_firmsize_distance_tests.csv, lodes_firmsize_industry_tail.csv, lodes_firmsize_shiftshare.csv,
         figures/firmsize_vs_distance.png
"""
import sys
import time

import duckdb
import matplotlib
import numpy as np
import pandas as pd
import statsmodels.api as sm

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import OUT, RAW, METROS, metro_def

EXT = OUT / "external"; FIG = EXT / "figures"
Y0, Y1 = 2011, 2019                   # long-difference window (firm variables start in 2011)
MIN_JOBS = 50                         # tract-year must have >= this many jobs in both WAC and OD to enter the tests
COLORS = ["#2a78d6", "#eb6834", "#2f9e6a", "#8a5cc7", "#d6a420", "#c9407a", "#1b9aaa", "#7a7a7a"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
ORDER = ["springfield", "columbia", "jeffcity", "joplin", "stjoseph", "capegirardeau", "kansascity", "stlouis"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ----------------------------------------------------------------------------------------------- 1. WAC firm shares
def build_wac(con):
    county_metro = [(c, k) for k in ORDER for c in metro_def(k)["counties"]]
    con.execute("CREATE OR REPLACE TABLE county_metro AS SELECT * FROM (VALUES " +
                ",".join(f"('{c}','{k}')" for c, k in county_metro) + ") t(cty, metro)")
    glob = str(RAW / "*" / "wac" / "*_wac_S000_JT02_*.csv.gz")
    con.execute(f"""
        CREATE OR REPLACE TABLE wac_tract AS
        SELECT substr(w_geocode, 1, 11) AS tract, substr(w_geocode, 1, 5) AS cty, substr(w_geocode, 1, 2) AS st,
               CAST(regexp_extract(filename, '_(\\d{{4}})\\.csv', 1) AS INTEGER) AS year,
               sum(C000) AS jobs, sum(CFS05) AS cfs05, sum(CFS04) AS cfs04, sum(CFS03) AS cfs03, sum(CFS02) AS cfs02,
               sum(CFS01) AS cfs01, sum(CFA05) AS cfa05, sum(CFA01 + CFA02) AS cfa_young
        FROM read_csv('{glob}', filename=true, types={{'w_geocode': 'VARCHAR'}}, union_by_name=true)
        WHERE year BETWEEN 2011 AND 2024
        GROUP BY 1, 2, 3, 4""")
    con.execute("""
        CREATE OR REPLACE TABLE wac_tract_m AS
        SELECT w.*, m.metro FROM wac_tract w LEFT JOIN county_metro m USING (cty)""")
    tract = con.execute("""
        SELECT tract, cty, st, metro, year, jobs,
               cfs05 / jobs AS sh_500p, (cfs04 + cfs05) / jobs AS sh_250p, (cfs02 + cfs03) / jobs AS sh_20_249,
               cfs01 / jobs AS sh_0_19, cfa05 / jobs AS sh_age11p, cfa_young / jobs AS sh_age0_3
        FROM wac_tract_m WHERE jobs > 0 ORDER BY tract, year""").df()
    tract.to_csv(EXT / "wac_firmsize_tract_year.csv", index=False)
    metro = con.execute("""
        SELECT metro AS unit, 'metro' AS level, year, sum(jobs) AS jobs, sum(cfs05)/sum(jobs) AS sh_500p,
               (sum(cfs04)+sum(cfs05))/sum(jobs) AS sh_250p, (sum(cfs02)+sum(cfs03))/sum(jobs) AS sh_20_249,
               sum(cfs01)/sum(jobs) AS sh_0_19, sum(cfa05)/sum(jobs) AS sh_age11p, sum(cfa_young)/sum(jobs) AS sh_age0_3
        FROM wac_tract_m WHERE metro IS NOT NULL GROUP BY 1, 2, 3
        UNION ALL
        SELECT CASE st WHEN '29' THEN 'MO' WHEN '20' THEN 'KS' WHEN '17' THEN 'IL' END, 'state', year, sum(jobs),
               sum(cfs05)/sum(jobs), (sum(cfs04)+sum(cfs05))/sum(jobs), (sum(cfs02)+sum(cfs03))/sum(jobs),
               sum(cfs01)/sum(jobs), sum(cfa05)/sum(jobs), sum(cfa_young)/sum(jobs)
        FROM wac_tract_m GROUP BY 1, 2, 3 ORDER BY level DESC, unit, year""").df()
    metro.to_csv(EXT / "wac_firmsize_metro_year.csv", index=False)
    log("WAC: tract-years", len(tract), "| metro-years", (metro.level == "metro").sum())
    return tract, metro


# ------------------------------------------------------------------------------------- 2. LODES distance per work tract
def build_lodes(con):
    frames = []
    for k in ORDER:
        d = OUT / k
        # panel: jobs, assigned-distance mean, same-county share (h_node county = first 5 digits of tract or county)
        p = con.execute(f"""
            SELECT w_node AS tract, year, sum(S000) AS jobs, sum(dist_sum) AS dist_sum, sum(dist_n) AS dist_n,
                   sum(CASE WHEN substr(h_node,1,5) = substr(w_node,1,5) THEN S000 ELSE 0 END) AS same_cty,
                   sum(CASE WHEN length(h_node) = 5 THEN S000 ELSE 0 END) AS from_outside_metro,
                   sum(SI01) AS si01, sum(SI02) AS si02, sum(SI03) AS si03
            FROM '{d / "panel.parquet"}' WHERE jt = 'JT02' AND length(w_node) = 11 GROUP BY 1, 2""").df()
        # (length 11 = work tract inside the metro; 5-digit w_node rows are out-commuters to outside counties)
        # blockflows: far-tail bins from block-pair straight-line miles, overall and by industry
        b = con.execute(f"""
            SELECT substr(w_geocode,1,11) AS tract, year, sum(S000) AS jobs_bf,
                   sum(CASE WHEN miles IS NOT NULL THEN S000 ELSE 0 END) AS n_miles,
                   sum(CASE WHEN miles > 60 THEN S000 ELSE 0 END) AS far60,
                   sum(CASE WHEN miles > 100 THEN S000 ELSE 0 END) AS far100,
                   sum(CASE WHEN miles > 100 THEN SI01 ELSE 0 END) AS far100_si01,
                   sum(CASE WHEN miles > 100 THEN SI02 ELSE 0 END) AS far100_si02,
                   sum(CASE WHEN miles > 100 THEN SI03 ELSE 0 END) AS far100_si03,
                   sum(CASE WHEN miles IS NOT NULL THEN SI01 ELSE 0 END) AS n_si01,
                   sum(CASE WHEN miles IS NOT NULL THEN SI02 ELSE 0 END) AS n_si02,
                   sum(CASE WHEN miles IS NOT NULL THEN SI03 ELSE 0 END) AS n_si03
            FROM '{d / "blockflows.parquet"}' WHERE jt = 'JT02' GROUP BY 1, 2""").df()
        x = p.merge(b, on=["tract", "year"], how="left"); x.insert(0, "metro", k)
        log(f"LODES {k}: tract-years {len(x)}, panel jobs 2019 {int(x.loc[x.year==2019,'jobs'].sum())}, "
            f"blockflows jobs 2019 {int(x.loc[x.year==2019,'jobs_bf'].sum())}")
        frames.append(x)
    t = pd.concat(frames, ignore_index=True)
    t["mean_dist"] = t.dist_sum / t.dist_n
    t["sh_same_cty"] = t.same_cty / t.jobs
    t["sh_far60"] = t.far60 / t.n_miles
    t["sh_far100"] = t.far100 / t.n_miles
    t.to_csv(EXT / "lodes_tract_distance_year.csv", index=False)
    return t


# ------------------------------------------------------------------------------------------------- 3. regressions
def wdemean(df, cols, by, w):
    """Weighted within transformation: subtract the w-weighted group mean of each col (one-way FE)."""
    out = df.copy()
    ww = df[w]
    for c in cols:
        gm = (df[c] * ww).groupby(df[by]).transform("sum") / ww.groupby(df[by]).transform("sum")
        out[c] = df[c] - gm
    return out


def wls(df, y, x, w, fe=(), absorb=None, cluster=None):
    """Jobs-weighted regression of y on x with dummy FE (fe) and optionally one absorbed FE (absorb, by demeaning).
    Returns slope, SE, t, p, within-R2 (after absorbing), n."""
    d = df.dropna(subset=[y, x, w]).copy()
    d = d[d[w] > 0]
    X = pd.DataFrame({x: d[x].astype(float)}, index=d.index)
    for f in fe:
        X = X.join(pd.get_dummies(d[f], prefix=f, drop_first=True, dtype=float))
    X["const"] = 1.0
    Y = d[y].astype(float)
    if absorb:
        tmp = X.join(Y.rename("_y")); tmp[w] = d[w]; tmp[absorb] = d[absorb]
        tmp = wdemean(tmp, [c for c in X.columns if c != "const"] + ["_y"], absorb, w)
        X = tmp[X.columns]; Y = tmp["_y"]
    kw = {}
    if cluster is not None:
        kw = dict(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[cluster])[0]})
    else:
        kw = dict(cov_type="HC1")
    r = sm.WLS(Y, X, weights=d[w].astype(float)).fit(**kw)
    return dict(slope=r.params[x], se=r.bse[x], t=r.tvalues[x], p=r.pvalues[x], r2=r.rsquared, n=int(r.nobs))


def run_tests(wac_t, wac_m, lodes_t):
    rows = []
    def add(test, outcome, regressor, spec, res, note=""):
        rows.append(dict(test=test, outcome=outcome, regressor=regressor, spec=spec, **res, note=note))

    # -- merged tract-year panel (2011-2024)
    m = lodes_t.merge(wac_t.drop(columns=["metro"]), on=["tract", "year"], suffixes=("", "_wac"))
    m = m[(m.jobs >= MIN_JOBS) & (m.jobs_wac >= MIN_JOBS)].copy()
    m["w"] = m.jobs
    log(f"merged tract-years {len(m)} ({m.tract.nunique()} tracts); OD/WAC job ratio "
        f"{m.jobs.sum() / m.jobs_wac.sum():.3f}")
    outcomes = {"mean_dist": "mean assigned distance (miles)", "sh_far100": "share of jobs with home >100 mi",
                "sh_far60": "share of jobs with home >60 mi", "sh_same_cty": "same-county share of jobs"}
    for xv in ["sh_500p", "sh_250p", "sh_age11p"]:
        for yv, lab in outcomes.items():
            add("a_cross_section", yv, xv, "metro+year FE, jobs-weighted, cluster tract",
                wls(m, yv, xv, "w", fe=("metro", "year"), cluster="tract"), lab)
            add("a2_within_tract", yv, xv, "tract+year FE, jobs-weighted, cluster tract",
                wls(m, yv, xv, "w", fe=("year",), absorb="tract", cluster="tract"), lab)

    # -- long differences 2011 -> 2019 within metro
    a = m[m.year == Y0].set_index("tract"); b = m[m.year == Y1].set_index("tract")
    common = a.index.intersection(b.index)
    ld = pd.DataFrame({"metro": a.loc[common, "metro"], "w": (a.loc[common, "jobs"] + b.loc[common, "jobs"]) / 2})
    for v in ["sh_500p", "sh_250p", "sh_age11p", "mean_dist", "sh_far100", "sh_far60", "sh_same_cty"]:
        ld["d_" + v] = b.loc[common, v] - a.loc[common, v]
    ld["jobs_2011"] = a.loc[common, "jobs"]; ld["jobs_2019"] = b.loc[common, "jobs"]
    ld.index.name = "tract"
    ld.reset_index().to_csv(EXT / "lodes_firmsize_longdiff_tract.csv", index=False)
    for xv in ["d_sh_500p", "d_sh_250p", "d_sh_age11p"]:
        for yv in ["d_mean_dist", "d_sh_far100", "d_sh_far60", "d_sh_same_cty"]:
            add("b_long_diff_2011_2019", yv, xv, "metro FE, jobs-weighted, HC1",
                wls(ld, yv, xv, "w", fe=("metro",)), f"tract changes {Y0}->{Y1}")
            add("b_long_diff_2011_2019", yv, xv, "no FE, jobs-weighted, HC1", wls(ld, yv, xv, "w"),
                f"tract changes {Y0}->{Y1}")
        # per metro slopes for the headline pair
    for k in ORDER:
        sub = ld[ld.metro == k]
        for yv in ["d_mean_dist", "d_sh_far100", "d_sh_same_cty"]:
            add("b_long_diff_by_metro", yv, "d_sh_500p", f"{k}, jobs-weighted, HC1", wls(sub, yv, "d_sh_500p", "w"), k)

    # -- metro-year panel 2011-2024
    my = lodes_t.groupby(["metro", "year"]).agg(jobs=("jobs", "sum"), dist_sum=("dist_sum", "sum"), dist_n=("dist_n", "sum"),
                                                  same_cty=("same_cty", "sum"), far100=("far100", "sum"),
                                                  n_miles=("n_miles", "sum")).reset_index()
    my["mean_dist"] = my.dist_sum / my.dist_n; my["sh_same_cty"] = my.same_cty / my.jobs; my["sh_far100"] = my.far100 / my.n_miles
    wm = wac_m[wac_m.level == "metro"].rename(columns={"unit": "metro", "jobs": "jobs_wac"})
    my = my.merge(wm[["metro", "year", "jobs_wac", "sh_500p", "sh_250p", "sh_age11p"]], on=["metro", "year"])
    my = my[(my.year >= 2011) & (my.year <= 2024)].copy(); my["w"] = my.jobs
    my.to_csv(EXT / "lodes_firmsize_metro_year.csv", index=False)
    for xv in ["sh_500p", "sh_250p", "sh_age11p"]:
        for yv in ["sh_same_cty", "mean_dist", "sh_far100"]:
            add("c_metro_panel_2011_2024", yv, xv, "metro FE, jobs-weighted, HC1", wls(my, yv, xv, "w", fe=("metro",)),
                "within-metro slope over time (common trend not absorbed)")
            add("c_metro_panel_2011_2024", yv, xv, "metro+year FE, jobs-weighted, HC1",
                wls(my, yv, xv, "w", fe=("metro", "year")), "within-metro slope net of common year shocks")
    tests = pd.DataFrame(rows)
    tests.to_csv(EXT / "lodes_firmsize_distance_tests.csv", index=False)

    # -- shift-share: how much of the 2011->2019 metro decline in same-county share does the large-firm change predict?
    beta_cs = tests.query("test=='a_cross_section' and outcome=='sh_same_cty' and regressor=='sh_500p'").slope.iloc[0]
    beta_ld = tests.query("test=='b_long_diff_2011_2019' and outcome=='d_sh_same_cty' and regressor=='d_sh_500p' and spec.str.startswith('metro FE')",
                          engine="python").slope.iloc[0]
    beta_wt = tests.query("test=='a2_within_tract' and outcome=='sh_same_cty' and regressor=='sh_500p'").slope.iloc[0]
    ss = []
    for k in ORDER:
        r0 = my[(my.metro == k) & (my.year == Y0)].iloc[0]; r1 = my[(my.metro == k) & (my.year == Y1)].iloc[0]
        d_sc = r1.sh_same_cty - r0.sh_same_cty; d_lf = r1.sh_500p - r0.sh_500p
        ss.append(dict(metro=k, sh_same_cty_2011=r0.sh_same_cty, sh_same_cty_2019=r1.sh_same_cty, d_same_cty=d_sc,
                       sh_500p_2011=r0.sh_500p, sh_500p_2019=r1.sh_500p, d_sh_500p=d_lf,
                       d_mean_dist=r1.mean_dist - r0.mean_dist, d_sh_far100=r1.sh_far100 - r0.sh_far100,
                       pred_cross_section=beta_cs * d_lf, pred_within_tract=beta_wt * d_lf, pred_long_diff=beta_ld * d_lf,
                       explained_cross_section=(beta_cs * d_lf) / d_sc if d_sc != 0 else np.nan,
                       explained_within_tract=(beta_wt * d_lf) / d_sc if d_sc != 0 else np.nan,
                       explained_long_diff=(beta_ld * d_lf) / d_sc if d_sc != 0 else np.nan))
    ss = pd.DataFrame(ss)
    ss.to_csv(EXT / "lodes_firmsize_shiftshare.csv", index=False)
    return tests, m, ld, my, ss


# ---------------------------------------------------------------------------------------------- 3d. industry tails
def industry_tails(lodes_t):
    g = lodes_t[(lodes_t.year >= 2002)].groupby(["metro", "year"])[
        ["far100_si01", "far100_si02", "far100_si03", "n_si01", "n_si02", "n_si03", "far100", "n_miles"]].sum().reset_index()
    for s in ["si01", "si02", "si03"]:
        g["sh_far100_" + s] = g["far100_" + s] / g["n_" + s]
    g["sh_far100_all"] = g.far100 / g.n_miles
    g.to_csv(EXT / "lodes_firmsize_industry_tail_year.csv", index=False)
    rows = []
    for k in ORDER + ["pooled"]:
        sub = g if k == "pooled" else g[g.metro == k]
        sub = sub[(sub.year >= 2010) & (sub.year <= 2019)]
        for s, lab in [("si01", "goods (SI01)"), ("si02", "trade/transport/utilities (SI02)"), ("si03", "other services (SI03)"), ("all", "all")]:
            y = sub["sh_far100_" + s]; w = sub["n_" + s] if s != "all" else sub["n_miles"]
            X = pd.DataFrame({"year": sub.year.astype(float), "const": 1.0}, index=sub.index)
            if k == "pooled":
                X = X.join(pd.get_dummies(sub.metro, prefix="m", drop_first=True, dtype=float))
            r = sm.WLS(y, X, weights=w).fit(cov_type="HC1")
            lv0 = sub[sub.year == 2010]; lv1 = sub[sub.year == 2019]
            def wavg(df, s):
                return (df["far100_" + s].sum() / df["n_" + s].sum()) if s != "all" else df.far100.sum() / df.n_miles.sum()
            rows.append(dict(metro=k, industry=lab, level_2010=wavg(lv0, s), level_2019=wavg(lv1, s),
                             change_2010_2019=wavg(lv1, s) - wavg(lv0, s), slope_pp_per_year=100 * r.params["year"],
                             se_pp_per_year=100 * r.bse["year"], p=r.pvalues["year"], n_years=len(sub)))
    ind = pd.DataFrame(rows)
    ind.to_csv(EXT / "lodes_firmsize_industry_tail.csv", index=False)
    return ind


# ------------------------------------------------------------------------------------------- 3e. residence side
def residence_side(con, tests):
    """The project's drift is residence-based self-containment. A resident mis-assigned to a distant headquarters is an
    out-commuter, which the work-tract firm-size share of the home metro cannot see. Two checks:
    (i) residence-based series per metro-year (resident workers, same-county share, far-tail share of residents);
    (ii) destination-county test: did flows from metro residents 2011->2019 grow faster toward counties whose
         large-firm share rose (controlling for the destination's job growth), especially far destinations?"""
    # (i) resident series from the panel (h_node tract inside metro) and blockflows (home block inside metro)
    res = []
    for k in ORDER:
        d = OUT / k
        cl = ",".join(f"'{c}'" for c in metro_def(k)["counties"])
        p = con.execute(f"""
            SELECT year, sum(S000) AS res_workers,
                   sum(CASE WHEN substr(h_node,1,5) = substr(w_node,1,5) THEN S000 ELSE 0 END) AS res_same_cty,
                   sum(CASE WHEN length(w_node) = 5 THEN S000 ELSE 0 END) AS res_out_metro,
                   sum(dist_sum) AS dist_sum, sum(dist_n) AS dist_n
            FROM '{d / "panel.parquet"}' WHERE jt = 'JT02' AND length(h_node) = 11 GROUP BY 1""").df()
        b = con.execute(f"""
            SELECT year, sum(CASE WHEN miles IS NOT NULL THEN S000 ELSE 0 END) AS n_miles,
                   sum(CASE WHEN miles > 100 THEN S000 ELSE 0 END) AS far100,
                   sum(CASE WHEN miles > 60 THEN S000 ELSE 0 END) AS far60
            FROM '{d / "blockflows.parquet"}' WHERE jt = 'JT02' AND substr(h_geocode,1,5) IN ({cl}) GROUP BY 1""").df()
        x = p.merge(b, on="year"); x.insert(0, "metro", k); res.append(x)
    res = pd.concat(res, ignore_index=True)
    res["res_sh_same_cty"] = res.res_same_cty / res.res_workers
    res["res_sh_out_metro"] = res.res_out_metro / res.res_workers
    res["res_mean_dist"] = res.dist_sum / res.dist_n
    res["res_sh_far100"] = res.far100 / res.n_miles; res["res_sh_far60"] = res.far60 / res.n_miles
    res.to_csv(EXT / "lodes_firmsize_residence_metro_year.csv", index=False)

    # (ii) destination-county pairs: metro residents -> work county (inside or outside the metro), 2011 and 2019
    wac_cty = con.execute("""
        SELECT cty, year, sum(jobs) AS jobs_dest, sum(cfs05)/sum(jobs) AS sh_500p_dest FROM wac_tract
        WHERE year IN (2011, 2019) GROUP BY 1, 2""").df()
    pairs = []
    for k in ORDER:
        d = OUT / k
        q = con.execute(f"""
            SELECT substr(w_node,1,5) AS cty, year, sum(S000) AS flow, sum(dist_sum) AS dist_sum, sum(dist_n) AS dist_n,
                   max(CASE WHEN length(w_node) = 11 THEN 1 ELSE 0 END) AS inside_metro
            FROM '{d / "panel.parquet"}' WHERE jt = 'JT02' AND length(h_node) = 11 AND year IN (2011, 2019)
            GROUP BY 1, 2""").df()
        q.insert(0, "metro", k); pairs.append(q)
    pairs = pd.concat(pairs, ignore_index=True)
    pairs["dist"] = pairs.dist_sum / pairs.dist_n
    w = pairs.pivot_table(index=["metro", "cty", "inside_metro"], columns="year", values=["flow", "dist"]).reset_index()
    w.columns = ["metro", "cty", "inside_metro", "dist_2011", "dist_2019", "flow_2011", "flow_2019"]
    wc = wac_cty.pivot_table(index="cty", columns="year", values=["jobs_dest", "sh_500p_dest"]).reset_index()
    wc.columns = ["cty", "jobs_dest_2011", "jobs_dest_2019", "sh_500p_dest_2011", "sh_500p_dest_2019"]
    w = w.merge(wc, on="cty")                       # destination counties in MO/KS/IL only (WAC coverage)
    w = w[(w.flow_2011 >= 20) & (w.flow_2019 >= 1) & (w.jobs_dest_2011 > 0)].copy()
    w["lg_flow"] = np.log(w.flow_2019 / w.flow_2011)
    w["lg_jobs_dest"] = np.log(w.jobs_dest_2019 / w.jobs_dest_2011)
    w["d_sh_500p_dest"] = w.sh_500p_dest_2019 - w.sh_500p_dest_2011
    w["far100"] = (w.dist_2011 > 100).astype(float)
    w["far_x_d500"] = w.far100 * w.d_sh_500p_dest
    w["w"] = w.flow_2011
    w.to_csv(EXT / "lodes_firmsize_destination_pairs.csv", index=False)

    def fit(df, xs, label):
        X = pd.DataFrame({x: df[x].astype(float) for x in xs}, index=df.index)
        X = X.join(pd.get_dummies(df.metro, prefix="m", drop_first=True, dtype=float)); X["const"] = 1.0
        r = sm.WLS(df.lg_flow.astype(float), X, weights=df.w.astype(float)).fit(cov_type="HC1")
        for x in xs:
            tests.append(dict(test="e_destination_county_2011_2019", outcome="log(flow_2019/flow_2011) metro residents -> dest county",
                              regressor=x, spec=label, slope=r.params[x], se=r.bse[x], t=r.tvalues[x], p=r.pvalues[x],
                              r2=r.rsquared, n=int(r.nobs), note="controls: " + ", ".join(xs) + "; metro FE; weights flow_2011"))
    fit(w, ["d_sh_500p_dest", "sh_500p_dest_2011", "lg_jobs_dest", "far100"], "all destination counties")
    fit(w, ["d_sh_500p_dest", "sh_500p_dest_2011", "lg_jobs_dest", "far100", "far_x_d500"], "all destinations, far x d500 interaction")
    fit(w[w.far100 == 1], ["d_sh_500p_dest", "sh_500p_dest_2011", "lg_jobs_dest"], "far destinations (>100 mi) only")
    fit(w[w.inside_metro == 0], ["d_sh_500p_dest", "sh_500p_dest_2011", "lg_jobs_dest", "far100"], "destinations outside the metro only")
    return res, w


# ---------------------------------------------------------------------------------------------------- 4. figure
def figure(ld, tests):
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#bbbbbb", "axes.labelcolor": "#333333",
                         "xtick.color": "#555555", "ytick.color": "#555555", "axes.titleweight": "normal"})
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.6), dpi=150)
    panels = [("d_mean_dist", "Change in mean assigned distance (miles)"),
              ("d_sh_far100", "Change in share of jobs with home >100 mi"),
              ("d_sh_same_cty", "Change in same-county share of jobs")]
    x = "d_sh_500p"
    for ax, (yv, ylab) in zip(axes, panels):
        for i, k in enumerate(ORDER):
            s = ld[ld.metro == k]
            size = np.clip(np.sqrt(s.w) / 3, 4, 40)
            ax.scatter(s[x], s[yv], s=size, marker=MARKERS[i], facecolors="none", edgecolors=COLORS[i], linewidths=0.6,
                       alpha=0.75, label=METROS[k]["name"])
        res = tests.query("test=='b_long_diff_2011_2019' and outcome==@yv and regressor==@x and spec.str.startswith('metro FE')",
                          engine="python").iloc[0]
        # within-metro fitted slope through the weighted means
        d = ld.dropna(subset=[x, yv]); xm = np.average(d[x], weights=d.w); ym = np.average(d[yv], weights=d.w)
        xs = np.array([d[x].quantile(0.02), d[x].quantile(0.98)])
        ax.plot(xs, ym + res.slope * (xs - xm), color="#222222", lw=1.2)
        ax.text(0.02, 0.97, f"within-metro slope {res.slope:+.3g} (SE {res.se:.2g}), n={res.n}", transform=ax.transAxes,
                va="top", ha="left", fontsize=8, color="#333333",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="#cccccc", lw=0.5))
        ax.axhline(0, color="#999999", lw=0.6); ax.axvline(0, color="#999999", lw=0.6)
        ax.grid(True, color="#e6e6e6", lw=0.6); ax.set_axisbelow(True)
        ax.set_xlabel("Change in share of jobs at 500+ employee firms")
        ax.set_ylabel(ylab)
        lo, hi = d[yv].quantile([0.005, 0.995]); pad = 0.08 * (hi - lo); ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlim(d[x].quantile(0.005) - 0.02, d[x].quantile(0.995) + 0.02)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    h, l = axes[0].get_legend_handles_labels()
    leg = fig.legend(h, l, loc="lower center", ncol=8, frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.02),
                     markerscale=1.6, handletextpad=0.2, columnspacing=1.0)
    for hh in leg.legend_handles:
        hh.set_alpha(1); hh.set_sizes([30])
    fig.suptitle("Work-tract changes 2011 to 2019, LODES JT02 (private jobs): large-firm share vs assigned commute distance "
                 "(marker size ~ sqrt of tract jobs)",
                 fontsize=10, y=0.995)
    fig.tight_layout(rect=(0, 0.06, 1, 0.97))
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "firmsize_vs_distance.png", bbox_inches="tight")
    plt.close(fig)


def main():
    EXT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    wac_t, wac_m = build_wac(con)
    lodes_t = build_lodes(con)
    tests, m, ld, my, ss = run_tests(wac_t, wac_m, lodes_t)
    ind = industry_tails(lodes_t)
    extra = []
    res, pairs = residence_side(con, extra)
    # (c, residence side) metro-year panel: metro's own large-firm share vs residence-based self-containment
    rm = res.merge(my[["metro", "year", "sh_500p", "sh_250p"]], on=["metro", "year"]); rm["w"] = rm.res_workers
    for yv in ["res_sh_same_cty", "res_sh_far100", "res_mean_dist"]:
        for spec, fe in [("metro FE, res-weighted, HC1", ("metro",)), ("metro+year FE, res-weighted, HC1", ("metro", "year"))]:
            extra.append(dict(test="c_metro_panel_residence_2011_2024", outcome=yv, regressor="sh_500p", spec=spec,
                              **wls(rm, yv, "sh_500p", "w", fe=fe), note="residence-based outcome vs the home metro's own large-firm share"))
    tests = pd.concat([tests, pd.DataFrame(extra)], ignore_index=True)
    tests.to_csv(EXT / "lodes_firmsize_distance_tests.csv", index=False)
    figure(ld, tests)
    pd.set_option("display.width", 200, "display.max_rows", 500)
    print(tests.to_string()); print(ss.to_string()); print(ind.to_string())
    print(res[res.year.isin([2010, 2011, 2019, 2024])].to_string())
    log("done")


if __name__ == "__main__":
    main()
