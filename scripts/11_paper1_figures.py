"""Figures and supplementary tables for the measurement paper (PAPER1_MEASUREMENT_DRAFT.md).

Fig 1  statewide same-county share, MO/KS/IL 2002-2024, 2007 and 2009 marked
Fig 2  share of counties with a >10 % year-on-year jump: resident-worker totals vs workplace totals, by state
Fig 6  post-2020 divergence for four counties: LODES same-county, ACS in-county, ACS work-from-home
Table S1  per-metro decomposition of the self-containment change
Outputs: outputs/external/figures/paper1_fig{1,2,6}.png, outputs/external/lodes_county_jump_shares.csv,
         outputs/manuscript/TABLE_S1_decomposition.csv
"""
from pathlib import Path
import duckdb, pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config
from config import OUT, PARQUET

EXT = OUT / "external"; FIG = EXT / "figures"; FIG.mkdir(parents=True, exist_ok=True)
LODES, ACS, WFH, GREY = "#2a78d6", "#eb6834", "#2f9e6a", "#7a7a7a"
STATE_COL = {"mo": "#2a78d6", "ks": "#8a5cc7", "il": "#d6a420"}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e6e6e6", "grid.linewidth": 0.6, "axes.axisbelow": True})


def shade(ax):
    ax.axvspan(2019.5, 2024.5, color="#000000", alpha=0.04, lw=0)
    for y in (2007, 2009):
        ax.axvline(y, color=GREY, ls=":", lw=0.8)


def statewide_series():
    """Same-county share of resident workers, JT00, MO/KS/IL 2002-2024: main (in-state jobs) + oos (jobs in other states)."""
    rows = []
    for st in ("mo", "ks", "il"):
        fips = config.STATE_FIPS[st]
        files = [str(p) for p in (PARQUET / st / "od").glob(f"{st}_od_main_JT00_*.parquet")]
        q = f"""
        WITH m AS (SELECT regexp_extract(filename, '([0-9]{{4}})\\.parquet$', 1)::INT AS yr,
                          SUM(S000) tot, SUM(CASE WHEN substr(w_geocode,1,5)=substr(h_geocode,1,5) THEN S000 END) same_cty,
                          SUM(CASE WHEN substr(w_geocode,1,11)=substr(h_geocode,1,11) THEN S000 END) same_tract
                   FROM read_parquet({files}, filename=true) GROUP BY 1),
        o AS (SELECT year AS yr, SUM(S000) oos FROM read_parquet('{PARQUET / "oos" / "res_outofstate.parquet"}')
              WHERE jt='JT00' AND substr(h_geocode,1,2)='{fips}' GROUP BY 1)
        SELECT m.yr, m.tot + COALESCE(o.oos,0) AS workers, m.same_cty, m.same_tract, COALESCE(o.oos,0) AS oos
        FROM m LEFT JOIN o USING (yr) ORDER BY 1"""
        d = duckdb.sql(q).df(); d["state"] = st
        d["same_cty_pct"] = 100 * d.same_cty / d.workers; d["same_tract_pct"] = 100 * d.same_tract / d.workers
        rows.append(d)
    S = pd.concat(rows); S.to_csv(EXT / "lodes_statewide_selfcontainment_all.csv", index=False); return S


def fig1(S):
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    shade(ax)
    lab = {"mo": "Missouri", "ks": "Kansas", "il": "Illinois"}
    for st, g in S.groupby("state"):
        g = g.sort_values("yr")
        ax.plot(g.yr, g.same_cty_pct, color=STATE_COL[st], lw=2, label=lab[st])
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.set_xlim(2001.5, 2024.5); ax.set_ylabel("workers employed in home county (%)")
    ax.set_title("Fig 1. Same-county share of resident workers, LODES JT00", loc="left", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "paper1_fig1.png", dpi=200); plt.close(fig)


def jump_shares():
    """Per state-year: share of counties (>= 500 workers) whose resident-worker total / workplace total moves > 10 %."""
    rows = []
    for st in ("mo", "ks", "il"):
        files = [str(p) for p in (PARQUET / st / "od").glob(f"{st}_od_*_JT00_*.parquet")]
        q = f"""
        WITH f AS (SELECT regexp_extract(filename, '([0-9]{{4}})\\.parquet$', 1)::INT AS yr,
                          substr(w_geocode,1,5) AS wc, substr(h_geocode,1,5) AS hc, S000
                   FROM read_parquet({files}, filename=true)),
        res AS (SELECT yr, hc AS cty, SUM(S000) n FROM f WHERE substr(hc,1,2)='{config.STATE_FIPS[st]}' GROUP BY 1,2),
        wrk AS (SELECT yr, wc AS cty, SUM(S000) n FROM f WHERE substr(wc,1,2)='{config.STATE_FIPS[st]}' GROUP BY 1,2)
        SELECT 'res' side, * FROM res UNION ALL SELECT 'work', * FROM wrk"""
        d = duckdb.sql(q).df()
        for side, g in d.groupby("side"):
            p = g.pivot(index="cty", columns="yr", values="n").sort_index(axis=1)
            p = p[(p.min(axis=1) >= 500)]
            ch = p.pct_change(axis=1).abs()
            for y in ch.columns[1:]:
                rows.append({"state": st, "side": side, "year": int(y), "n_counties": int(ch[y].notna().sum()),
                             "share_gt10": float((ch[y] > 0.10).mean())})
    J = pd.DataFrame(rows); J.to_csv(EXT / "lodes_county_jump_shares.csv", index=False); return J


def fig2(J):
    fig, axes = plt.subplots(1, 3, figsize=(8.5, 2.8), sharey=True)
    for ax, st in zip(axes, ("mo", "ks", "il")):
        shade(ax)
        for side, col, lab in (("res", ACS, "resident-worker totals"), ("work", LODES, "workplace job totals")):
            g = J[(J.state == st) & (J.side == side)].sort_values("year")
            ax.plot(g.year, 100 * g.share_gt10, color=col, lw=2, label=lab)
        ax.set_title({"mo": "Missouri", "ks": "Kansas", "il": "Illinois"}[st], loc="left", fontsize=9)
        ax.set_xlim(2002.5, 2024.5)
    axes[0].set_ylabel("counties with |Δ| > 10 % (%)"); axes[0].legend(frameon=False, fontsize=8, loc="upper right")
    fig.suptitle("Fig 2. Year-on-year instability of county totals, LODES JT00: residence side vs workplace side", x=0.01, ha="left", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "paper1_fig2.png", dpi=200); plt.close(fig)


def fig6():
    m = pd.read_csv(EXT / "acs_vs_lodes_samecounty.csv", dtype={"county": str})
    w = pd.read_csv(EXT / "acs_wfh_county_year.csv", dtype={"county": str}); w = w[w.src == "acs1"]
    names = {"29077": "Greene (Springfield)", "29095": "Jackson (Kansas City)", "20091": "Johnson KS", "29183": "St. Charles"}
    fig, axes = plt.subplots(1, 4, figsize=(10, 2.9), sharey=False)
    for ax, (c, nm) in zip(axes, names.items()):
        g = m[m.county == c].sort_values("year"); ww = w[w.county == c].sort_values("year")
        shade(ax)
        ax.plot(g.year, 100 * g.same_county_share, color=LODES, lw=2, label="LODES same-county")
        gg = g.dropna(subset=["in_county_share"])
        ax.plot(gg.year, 100 * gg.in_county_share, color=ACS, lw=2, marker="o", ms=3, label="ACS in-county (B08007)")
        ax.plot(ww.year, 100 * ww.wfh_share, color=WFH, lw=2, ls="--", label="ACS worked at home")
        ax.set_title(nm, loc="left", fontsize=9); ax.set_xlim(2009.5, 2024.5)
    axes[0].set_ylabel("%"); axes[0].legend(frameon=False, fontsize=7, loc="center left")
    fig.suptitle("Fig 6. After 2020 the ACS codes work-from-home at the home county; LODES keeps the employer address", x=0.01, ha="left", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "paper1_fig6.png", dpi=200); plt.close(fig)


def table_s1():
    s = pd.read_csv(OUT / "comparison" / "tables" / "self_containment.csv").set_index("year") * 100
    rows = []
    for k in config.METROS:
        g = s[k]
        rows.append({"metro": config.METROS[k]["name"], "2002-2006": g[2006] - g[2002], "2007 step": g[2007] - g[2006],
                     "2008": g[2008] - g[2007], "2009 step": g[2009] - g[2008], "2009-2010": g[2010] - g[2009],
                     "2010-2019 drift": g[2019] - g[2010], "2019-2024": g[2024] - g[2019], "total 2002-2024": g[2024] - g[2002],
                     "steps share %": 100 * (g[2007] - g[2006] + g[2009] - g[2008]) / (g[2024] - g[2002])})
    T = pd.DataFrame(rows).round(1); T.to_csv(OUT / "manuscript" / "TABLE_S1_decomposition.csv", index=False)
    print(T.to_string(index=False)); return T


if __name__ == "__main__":
    S = statewide_series(); fig1(S); print(S.pivot(index="yr", columns="state", values="same_cty_pct").round(1).to_string()); J = jump_shares(); fig2(J); fig6(); table_s1()
    print(J.pivot_table(index="year", columns=["state", "side"], values="share_gt10").round(2).to_string())


def fig4():
    """ACS 1-year in-county share vs LODES same-county share, 2005-2024, twelve counties."""
    m = pd.read_csv(EXT / "acs_vs_lodes_samecounty_all.csv", dtype={"county": str})
    a1 = m[m.period == 1]; lo = pd.read_csv(EXT / "lodes_county_samecounty_year.csv", dtype={"county": str})
    names = {"29077": "Greene (Springfield)", "29019": "Boone (Columbia)", "29051": "Cole (Jefferson City)", "29097": "Jasper (Joplin)",
             "29021": "Buchanan (St. Joseph)", "29031": "Cape Girardeau", "29095": "Jackson (KC)", "20091": "Johnson KS",
             "29189": "St. Louis County", "29510": "St. Louis city", "17163": "St. Clair IL", "17119": "Madison IL"}
    fig, axes = plt.subplots(3, 4, figsize=(10, 6.5))
    for ax, (c, nm) in zip(axes.flat, names.items()):
        shade(ax); ax.axvline(2011, color=GREY, ls=":", lw=0.8)
        g = lo[(lo.county == c) & (lo.year >= 2004)].sort_values("year")
        ax.plot(g.year, 100 * g.same_county_share, color=LODES, lw=2, label="LODES same-county")
        gg = a1[a1.county == c].sort_values("year")
        ax.plot(gg.year, 100 * gg.acs_share, color=ACS, lw=1.6, marker="o", ms=2.5, label="ACS 1-yr in-county")
        ax.set_title(nm, loc="left", fontsize=9); ax.set_xlim(2003.5, 2024.5)
    axes[0, 0].legend(frameon=False, fontsize=7, loc="lower left")
    fig.suptitle("Fig 4. Share of resident workers employed in their county, ACS 1-year vs LODES JT00, 2004-2024 (dotted: 2007, 2009, 2011)", x=0.01, ha="left", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "paper1_fig4.png", dpi=200); plt.close(fig)


if __name__ == "__main__":
    fig4()
