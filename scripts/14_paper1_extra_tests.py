"""Extra diagnostics requested in the EPB-style review of the measurement paper.

1. National year-effects test: annual change in the state same-county share (JT02 main, 2005-2011) on year dummies
   with state fixed effects, SE clustered by state; sign tests per year; the 2007 effect against the other years.
2. Age composition of the 2007 step in Missouri, Kansas and Illinois: same-county share by age band (SA01 <=29,
   SA02 30-54, SA03 55+), JT00 main, 2004-2010. If the step is an address-lag artefact it should be largest for the young.
3. Far-tail check: share of metro jobs held by residents > 100 miles away, 2006 vs 2007, from lodes_incommute_annual_step.csv.

Outputs: outputs/external/national_year_effects.csv, lodes_step_by_age.csv, PAPER1_EXTRA_TESTS.md
"""
import numpy as np, pandas as pd, duckdb, statsmodels.formula.api as smf
from scipy import stats
import config
from config import OUT, PARQUET

EXT = OUT / "external"
lines = ["# Extra tests for the measurement paper (script 14, 2026-11-07)\n"]

# 1. national year effects
N = pd.read_csv(EXT / "lodes_national_selfcontainment_2004_2011.csv")
N = N.dropna(subset=["d_same_county_pts"]).copy(); N["yr"] = N.year.astype(str)
m = smf.ols("d_same_county_pts ~ C(yr) - 1 + C(state)", data=N).fit(cov_type="cluster", cov_kwds={"groups": N.state})
rows = []
for y in sorted(N.year.unique()):
    g = N[N.year == y].d_same_county_pts
    neg = int((g < 0).sum()); n = len(g)
    rows.append({"year": y, "n_states": n, "median_change": g.median(), "mean_change": g.mean(), "n_negative": neg,
                 "sign_test_p": stats.binomtest(neg, n, 0.5, alternative="greater").pvalue,
                 "year_effect": m.params.get(f"C(yr)[{y}]", np.nan), "cluster_se": m.bse.get(f"C(yr)[{y}]", np.nan)})
Y = pd.DataFrame(rows); Y.to_csv(EXT / "national_year_effects.csv", index=False)
# year effects are relative to the omitted state; report the mean year effect instead (first differences, so state FE ~0)
m0 = smf.ols("d_same_county_pts ~ C(yr) - 1", data=N).fit(cov_type="cluster", cov_kwds={"groups": N.state})
Y["year_effect_nofe"] = [m0.params[f"C(yr)[{y}]"] for y in Y.year]; Y["se_nofe"] = [m0.bse[f"C(yr)[{y}]"] for y in Y.year]
other = Y[~Y.year.isin([2007, 2009])]
z07 = (Y.loc[Y.year == 2007, "year_effect_nofe"].iloc[0] - other.year_effect_nofe.mean()) / other.year_effect_nofe.std(ddof=1)
# placebo: distribution of state-year changes outside 2007/2009 vs the 2007 changes
pl = N[~N.year.isin([2007, 2009])].d_same_county_pts; s07 = N[N.year == 2007].d_same_county_pts
ks = stats.ks_2samp(s07, pl); mw = stats.mannwhitneyu(s07, pl, alternative="less")
lines += ["## 1. National year effects (JT02 main, annual change in same-county share, points)\n",
          Y[["year", "n_states", "median_change", "mean_change", "n_negative", "sign_test_p", "year_effect_nofe", "se_nofe"]].round(4).to_string(index=False),
          f"\nThe 2007 year effect is {z07:.1f} SD of the other non-step years' effects below their mean. "
          f"Share of placebo state-years (2005, 2006, 2008, 2010, 2011) with a drop at least as large as the median 2007 state: "
          f"{(pl <= s07.median()).mean():.3f}. KS test 2007 vs placebo D = {ks.statistic:.2f}, p = {ks.pvalue:.1e}; Mann-Whitney p = {mw.pvalue:.1e}.\n"]
Y.to_csv(EXT / "national_year_effects.csv", index=False)

# 2. age composition of the step
rows = []
for st in ("mo", "ks", "il"):
    files = [str(p) for p in (PARQUET / st / "od").glob(f"{st}_od_main_JT00_*.parquet")]
    q = f"""SELECT regexp_extract(filename, '([0-9]{{4}})\\.parquet$', 1)::INT AS yr,
                   SUM(SA01) a1, SUM(SA02) a2, SUM(SA03) a3,
                   SUM(CASE WHEN substr(w_geocode,1,5)=substr(h_geocode,1,5) THEN SA01 END) s1,
                   SUM(CASE WHEN substr(w_geocode,1,5)=substr(h_geocode,1,5) THEN SA02 END) s2,
                   SUM(CASE WHEN substr(w_geocode,1,5)=substr(h_geocode,1,5) THEN SA03 END) s3
            FROM read_parquet({files}, filename=true) WHERE yr BETWEEN 2004 AND 2010 GROUP BY 1 ORDER BY 1"""
    d = duckdb.sql(q).df(); d["state"] = st
    for k in (1, 2, 3):
        d[f"same_cty_age{k}"] = 100 * d[f"s{k}"] / d[f"a{k}"]
    rows.append(d)
A = pd.concat(rows, ignore_index=True); A.to_csv(EXT / "lodes_step_by_age.csv", index=False)
T = A.pivot(index="yr", columns="state", values=["same_cty_age1", "same_cty_age2", "same_cty_age3"]).round(1)
chg = A.sort_values("yr").groupby("state")[["same_cty_age1", "same_cty_age2", "same_cty_age3"]].diff()
A2 = A.assign(**{c + "_d": chg[c] for c in chg.columns})
lines += ["\n## 2. Same-county share by age band (JT00 main), 2004-2010\n", T.to_string(),
          "\nYear-on-year change in 2007 by age band (points):\n",
          A2[A2.yr == 2007][["state", "same_cty_age1_d", "same_cty_age2_d", "same_cty_age3_d"]].round(2).to_string(index=False),
          "\nYear-on-year change in 2009 by age band (points):\n",
          A2[A2.yr == 2009][["state", "same_cty_age1_d", "same_cty_age2_d", "same_cty_age3_d"]].round(2).to_string(index=False)]

# 3. far tail 2006 vs 2007
F = pd.read_csv(EXT / "lodes_incommute_annual_step.csv"); F = F[(F.jt == "JT00") & (F.year.isin([2006, 2007, 2008]))]
P = F.pivot(index="metro", columns="year", values="far%"); P["d_2007"] = P[2007] - P[2006]
lines += ["\n## 3. Share of metro jobs held by residents > 100 miles away (JT00), 2006-2008\n", P.round(2).to_string()]
(EXT / "PAPER1_EXTRA_TESTS.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
