"""Cross-metro comparison: Missouri small/mid metros vs Kansas City and St. Louis, 2002-2024 (JT02 unless stated).

Usage: python scripts/06_compare.py            -> outputs/comparison/{tables,figures}
Reads each metro's Phase 2/3 tables; metros without outputs are skipped.
"""
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import OUT, METROS, YEARS

BENCH = ["kansascity", "stlouis"]
# fixed colour per metro (categorical slots; benchmarks take the last two slots and are dashed)
PAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 8.5, "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.6, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
                     "savefig.dpi": 200})
KEY_YEARS = [2002, 2007, 2010, 2019, 2020, 2024]


def load(metro):
    od = OUT / metro; tb = od / "tables"; p3 = od / "phase3"
    if not (p3 / "flow_trend_summary.csv").exists():
        return None
    V = pd.read_csv(tb / "volumes_county_year.csv")
    D = pd.read_csv(tb / "commute_distance_year.csv")
    CS = pd.read_csv(tb / "commutershed_core_jobs.csv")
    DEC = pd.read_csv(tb / "distance_decay_poisson.csv")
    K = pd.read_csv(tb / "job_concentration.csv")
    PC = pd.read_csv(p3 / "centres_summary.csv")
    CM = pd.read_csv(p3 / "communities_summary.csv")
    L = pd.read_csv(tb / "long_distance_share_JT02.csv").assign(jt="JT02")
    rows = []

    def add(df, col, name, f=lambda v: v):
        for _, r in df.iterrows():
            rows.append(dict(metro=metro, jt=r.jt, year=int(r.year), indicator=name, value=f(r[col])))
    add(V, "msa_jobs_total", "jobs")
    add(V, "self_contain_res", "self_containment")
    add(V, "self_suff_jobs", "job_self_sufficiency")
    V["in_share"] = (V.inflow_mo + V.inflow_aux) / V.msa_jobs_total
    add(V, "in_share", "in_commuter_share_of_jobs")
    V["oos_share_jobs"] = V.inflow_aux / V.msa_jobs_total
    add(V, "oos_share_jobs", "out_of_state_share_of_jobs")
    V["out_share"] = (V.outflow_mo + V.outflow_oos) / V.res_workers_all
    add(V, "out_share", "out_commuter_share_of_residents")
    dm = D[(D.scope == "within_msa") & (D.group == "all")]
    add(dm, "median_mi", "median_commute_mi")
    for g, nm in [("earn <=1,250", "median_mi_low_earn"), ("earn >3,333", "median_mi_high_earn"), ("goods", "median_mi_goods")]:
        add(D[(D.scope == "within_msa") & (D.group == g)], "median_mi", nm)
    m100 = D[(D.scope == "msa_jobs_mo_res") & (D.group == "<= 100 mi")]
    add(m100, "mean_mi", "mean_mi_to_jobs_le100")
    add(CS, "core", "core_county_share_of_core_jobs")
    add(CS, "outer MO", "outer_MO_share_of_core_jobs")
    add(CS, "out of state", "out_of_state_share_of_core_jobs")
    add(DEC, "beta_logd", "distance_decay_beta")
    add(K, "top5", "top5_tract_share"); add(K, "top10", "top10_tract_share"); add(K, "gini", "gini_tract_jobs")
    add(PC, "n_centres", "n_centres"); add(PC, "centre_share", "centre_share"); add(PC, "ha_n_centres", "n_centres_ha")
    add(CM, "n_communities", "n_communities"); add(CM, "modularity", "modularity"); add(CM, "ari_prev_year", "ari_prev_year")
    add(L, "share", "long_distance_share")
    return pd.DataFrame(rows)


def main():
    cd = OUT / "comparison"; (cd / "tables").mkdir(parents=True, exist_ok=True); (cd / "figures").mkdir(exist_ok=True)
    parts = [x for x in (load(m) for m in METROS) if x is not None]
    I = pd.concat(parts, ignore_index=True)
    I.loc[(I.jt == "JT00") & (I.year < 2010), "value"] = np.nan
    I.to_csv(cd / "tables" / "indicators_long.csv", index=False)
    metros = [m for m in METROS if m in set(I.metro)]
    names = {m: METROS[m]["name"] for m in metros}
    J = I[I.jt == "JT02"]

    # wide table per indicator and a key-year summary with changes
    summ = []
    for ind, g in J.groupby("indicator"):
        w = g.pivot(index="year", columns="metro", values="value")[[m for m in metros if m in g.metro.unique()]]
        w.to_csv(cd / "tables" / f"{ind}.csv")
        for m in w.columns:
            s = w[m]
            summ.append(dict(indicator=ind, metro=m, **{str(y): s.get(y) for y in KEY_YEARS},
                             chg_2002_2024=s.get(2024) - s.get(2002) if pd.notna(s.get(2002)) else np.nan,
                             chg_2010_2024=s.get(2024) - s.get(2010) if pd.notna(s.get(2010)) else np.nan,
                             pct_2002_2024=(s.get(2024) / s.get(2002) - 1) if s.get(2002) else np.nan))
    S = pd.DataFrame(summ); S.to_csv(cd / "tables" / "summary_key_years.csv", index=False)

    # metro profile 2024
    prof = []
    for m in metros:
        g = J[(J.metro == m) & (J.year == 2024)].set_index("indicator").value
        g2 = J[(J.metro == m) & (J.year == 2002)].set_index("indicator").value
        prof.append(dict(metro=m, name=names[m], benchmark=m in BENCH, jobs_2024=g.get("jobs"), jobs_growth_2002_24=g.get("jobs") / g2.get("jobs") - 1,
                         self_containment_2024=g.get("self_containment"), self_containment_chg=g.get("self_containment") - g2.get("self_containment"),
                         median_mi_2024=g.get("median_commute_mi"), median_mi_chg=g.get("median_commute_mi") - g2.get("median_commute_mi"),
                         beta_2024=g.get("distance_decay_beta"), beta_chg=g.get("distance_decay_beta") - g2.get("distance_decay_beta"),
                         top5_2024=g.get("top5_tract_share"), top5_chg=g.get("top5_tract_share") - g2.get("top5_tract_share"),
                         n_centres_2024=g.get("n_centres"), centre_share_2024=g.get("centre_share"),
                         n_communities_2024=g.get("n_communities"), modularity_2024=g.get("modularity"), modularity_chg=g.get("modularity") - g2.get("modularity"),
                         out_of_state_share_jobs_2024=g.get("out_of_state_share_of_jobs"), long_distance_share_2024=g.get("long_distance_share")))
    PR = pd.DataFrame(prof); PR.to_csv(cd / "tables" / "metro_profiles.csv", index=False)

    # shocks, trends, breaks side by side
    sh, tr, br = [], [], []
    for m in metros:
        p3 = OUT / m / "phase3"
        sh.append(pd.read_csv(p3 / "shock_windows.csv").assign(metro=m))
        tr.append(pd.read_csv(p3 / "flow_trend_summary.csv").assign(metro=m))
        br.append(pd.read_csv(p3 / "break_test_2009.csv").assign(metro=m))
    SH = pd.concat(sh); SH.to_csv(cd / "tables" / "shock_windows_all.csv", index=False)
    SH.pivot_table(index=["indicator", "pretrend", "year"], columns="metro", values="deviation_pct").round(3).to_csv(cd / "tables" / "shock_deviation_pct_wide.csv")
    TR = pd.concat(tr)
    for c in ["new", "intensifying", "persistent", "declining", "fading", "sporadic"]:
        TR[c + "_share"] = TR[c] / TR.pairs
    TR.to_csv(cd / "tables" / "flow_trend_summary_all.csv", index=False)
    pd.concat(br).to_csv(cd / "tables" / "break_test_2009_all.csv", index=False)

    # ---- figures: small multiples, one panel per indicator, one line per metro
    panels = [("self_containment", "Residents working in own metro", True), ("median_commute_mi", "Median commute within metro (mi)", False),
              ("distance_decay_beta", "Distance-decay β", False), ("out_of_state_share_of_jobs", "Metro jobs held by other-state residents", True),
              ("top5_tract_share", "Top-5 tract share of jobs", True), ("centre_share", "Jobs in persistent centres", True),
              ("n_communities", "Commuting communities", False), ("modularity", "Modularity of communities", False),
              ("core_county_share_of_core_jobs", "Core-county jobs held by core residents", True),
              ("outer_MO_share_of_core_jobs", "Core-county jobs held by outer-MO residents", True),
              ("long_distance_share", "Jobs with home > 100 mi", True), ("in_commuter_share_of_jobs", "In-commuter share of jobs", True)]
    fig, axes = plt.subplots(4, 3, figsize=(11, 11.5), sharex=True)
    for ax, (ind, title, pct) in zip(axes.ravel(), panels):
        w = J[J.indicator == ind].pivot(index="year", columns="metro", values="value")
        for k, m in enumerate(metros):
            if m not in w: continue
            ax.plot(w.index, w[m], color=PAL[k % 8], lw=2.2 if m in BENCH else 1.6, ls="--" if m in BENCH else "-", label=names[m])
        for yr in (2008, 2020):
            ax.axvline(yr, color=INK2, lw=0.7, ls=":")
        ax.set_title(title, loc="left", fontsize=9, color=INK)
        if pct: ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.0))
    fig.suptitle("Missouri metros, private jobs (JT02), 2002–2024; dashed = Kansas City and St. Louis benchmarks", x=0.01, ha="left", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    for e in ("png", "svg"):
        fig.savefig(cd / "figures" / f"indicators_small_multiples.{e}")
    plt.close(fig)

    # indexed (2002 = 100) panel for jobs & commuter volumes
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharex=True)
    for ax, (ind, title) in zip(axes, [("jobs", "Metro jobs"), ("in_commuter_share_of_jobs", "In-commuter share of jobs"), ("out_commuter_share_of_residents", "Out-commuter share of residents")]):
        w = J[J.indicator == ind].pivot(index="year", columns="metro", values="value")
        for k, m in enumerate(metros):
            if m not in w: continue
            s = w[m] / w[m].loc[2002] * 100
            ax.plot(s.index, s, color=PAL[k % 8], lw=2.2 if m in BENCH else 1.6, ls="--" if m in BENCH else "-", label=names[m])
        for yr in (2008, 2020): ax.axvline(yr, color=INK2, lw=0.7, ls=":")
        ax.set_title(title + " (2002 = 100)", loc="left", fontsize=9, color=INK)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    for e in ("png", "svg"):
        fig.savefig(cd / "figures" / f"indexed_volumes.{e}")
    plt.close(fig)

    # shock deviation bars
    sub = SH[(SH.indicator.isin(["MSA jobs", "In-commuters (MO)", "Self-containment", "Distance-decay beta", "Median commute (mi)"]))]
    piv = sub.pivot_table(index=["indicator", "year"], columns="metro", values="deviation_pct")
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8), sharey=False)
    for ax, yr in zip(axes, [2010, 2021, 2024]):
        d = piv.xs(yr, level="year")[[m for m in metros if m in piv.columns]]
        x = np.arange(len(d.index)); wdt = 0.8 / len(d.columns)
        for k, m in enumerate(d.columns):
            ax.bar(x + k * wdt - 0.4 + wdt / 2, d[m].values * 100, wdt, color=PAL[metros.index(m) % 8], label=names[m],
                   hatch="//" if m in BENCH else None, edgecolor="#fcfcfb", linewidth=0.5)
        ax.axhline(0, color=INK2, lw=0.8); ax.set_xticks(x, [i.replace(" (", "\n(") for i in d.index], fontsize=7)
        ax.set_title(f"{yr} vs pre-trend ({'2002-07' if yr == 2010 else '2014-19'}), % deviation", loc="left", fontsize=9, color=INK)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=4, frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    for e in ("png", "svg"):
        fig.savefig(cd / "figures" / f"shock_deviations.{e}")
    plt.close(fig)
    pd.set_option("display.width", 250)
    print(PR.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
