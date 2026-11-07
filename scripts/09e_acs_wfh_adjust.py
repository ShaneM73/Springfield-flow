"""Post-2020 convention adjustment: ACS codes a worker who worked at home in the home county, LODES at the employer.
Subtract the ACS worked-at-home count (B08301) from the B08007 in-county count so the two sources use the same
convention ('in-county workplace, excluding home'), then compare 2019 -> 2021..2024 changes and 2010-2019 slopes.

Output: outputs/external/acs_wfh_adjusted_vs_lodes.csv (county, year, acs_share, wfh_share, acs_adj_share, lodes_share)
        outputs/external/acs_wfh_adjusted_summary.csv (per county: changes 2019->2024 raw / adjusted / LODES; slopes 2010-19)
"""
import numpy as np, pandas as pd
import config
from config import OUT

EXT = OUT / "external"
A = pd.read_csv(EXT / "acs_b08007_county_year_all.csv", dtype={"county": str})
A = A[A.period == 1][["county", "name", "year", "workers", "in_county", "share"]].rename(columns={"share": "acs_share"})
W = pd.read_csv(EXT / "acs_wfh_county_year.csv", dtype={"county": str})
W = W[W.src == "acs1"][["county", "year", "workers", "wfh", "wfh_share"]].rename(columns={"workers": "workers_b08301"})
L = pd.read_csv(EXT / "lodes_county_samecounty_year.csv", dtype={"county": str})[["county", "year", "same_county_share"]].rename(columns={"same_county_share": "lodes_share"})
M = A.merge(W, on=["county", "year"], how="left").merge(L, on=["county", "year"], how="left")
M["universe_ratio"] = M.workers_b08301 / M.workers
M["acs_adj_share"] = (M.in_county - M.wfh) / M.workers
M.to_csv(EXT / "acs_wfh_adjusted_vs_lodes.csv", index=False)
print("B08301/B08007 universe ratio: min %.3f max %.3f" % (M.universe_ratio.min(), M.universe_ratio.max()))


def slope(g, col, y0=2010, y1=2019):
    g = g[(g.year >= y0) & (g.year <= y1)].dropna(subset=[col])
    return np.polyfit(g.year, g[col], 1)[0] * 100 if len(g) >= 5 else np.nan


rows = []
for c, g in M.groupby("county"):
    g = g.set_index("year")
    def chg(col, y):
        return 100 * (g[col].get(y, np.nan) - g[col].get(2019, np.nan))
    rows.append({"county": c, "name": g.name.iloc[0],
                 "wfh_2019": 100 * g.wfh_share.get(2019, np.nan), "wfh_2021": 100 * g.wfh_share.get(2021, np.nan), "wfh_2024": 100 * g.wfh_share.get(2024, np.nan),
                 "acs_raw_2019_24": chg("acs_share", 2024), "acs_adj_2019_24": chg("acs_adj_share", 2024), "lodes_2019_24": chg("lodes_share", 2024),
                 "acs_raw_2019_21": chg("acs_share", 2021), "acs_adj_2019_21": chg("acs_adj_share", 2021), "lodes_2019_21": chg("lodes_share", 2021),
                 "slope_acs_raw_10_19": slope(g.reset_index(), "acs_share"), "slope_acs_adj_10_19": slope(g.reset_index(), "acs_adj_share"),
                 "slope_lodes_10_19": slope(g.reset_index(), "lodes_share")})
S = pd.DataFrame(rows).round(2); S.to_csv(EXT / "acs_wfh_adjusted_summary.csv", index=False)
pd.set_option("display.width", 250)
print(S[["name", "wfh_2019", "wfh_2021", "wfh_2024", "acs_raw_2019_24", "acs_adj_2019_24", "lodes_2019_24", "slope_acs_raw_10_19", "slope_acs_adj_10_19", "slope_lodes_10_19"]].to_string(index=False))
w = M[M.year == 2019].set_index("county").workers
for col in ["acs_raw_2019_24", "acs_adj_2019_24", "lodes_2019_24", "acs_raw_2019_21", "acs_adj_2019_21", "lodes_2019_21", "slope_acs_raw_10_19", "slope_acs_adj_10_19", "slope_lodes_10_19"]:
    v = S.set_index("county")[col].dropna(); ww = w.reindex(v.index)
    print(f"{col:24s} mean {v.mean():6.2f}  weighted {np.average(v, weights=ww):6.2f}  n {len(v)}  corr with LODES: "
          f"{np.corrcoef(v, S.set_index('county').loc[v.index, col.replace('acs_raw', 'lodes').replace('acs_adj', 'lodes')])[0,1]:.2f}")
