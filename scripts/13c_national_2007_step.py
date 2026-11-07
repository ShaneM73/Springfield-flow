"""
Is the 2007 (and 2009) drop in the same-county share national?
Reads outputs/external/lodes_national_selfcontainment_2004_2011.csv and
lodes_national_residence_jumps.csv; writes NATIONAL_2007_STEP.md and
figures/national_2007_step.png.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "outputs", "external")
FIG = os.path.join(EXT, "figures", "national_2007_step.png")
MD = os.path.join(EXT, "NATIONAL_2007_STEP.md")
HI, LO = "#eb6834", "#2a78d6"
FOCUS = ["mo", "ks", "il"]
YEARS = list(range(2005, 2012))

s = pd.read_csv(os.path.join(EXT, "lodes_national_selfcontainment_2004_2011.csv"), dtype={"state": str})
j = pd.read_csv(os.path.join(EXT, "lodes_national_residence_jumps.csv"), dtype={"state": str})
man = pd.read_csv(os.path.join(EXT, "national_od_manifest.csv"), dtype={"state": str})


def dist(col, yr):
    d = s[(s.year == yr)].dropna(subset=[col]).set_index("state")[col]
    return d


def summarize(col, yr, label):
    d = dist(col, yr)
    lines = [f"**{yr} ({label}), n = {len(d)} states with both years**",
             "",
             f"- median change: {d.median():+.2f} pts; mean {d.mean():+.2f}; IQR [{d.quantile(.25):+.2f}, {d.quantile(.75):+.2f}]",
             f"- drop > 1 pt: {(d < -1).sum()} states; > 2 pts: {(d < -2).sum()}; > 3 pts: {(d < -3).sum()}",
             f"- no drop (change >= 0): {(d >= 0).sum()} states" + (
                 f" ({', '.join(x.upper() for x in d[d >= 0].sort_values(ascending=False).index)})" if (d >= 0).sum() else ""),
             f"- largest drops: " + ", ".join(f"{k.upper()} {v:+.2f}" for k, v in d.sort_values().head(8).items()),
             f"- MO/KS/IL: " + ", ".join(f"{k.upper()} {d.get(k, float('nan')):+.2f}" for k in FOCUS),
             ""]
    return lines


out = []
out.append("# Is the 2007 self-containment step national?\n")
out.append("Source: LODES 8 main OD files, job type JT02 (all private primary jobs), data years 2004-2011, "
           "all 50 states + DC (PR/VI excluded). Every number is computed directly from the csv.gz with DuckDB "
           "(`scripts/13b_national_od_compute.py`). `same_county_share` = share of a state's in-state workers "
           "(main file: live and work in the state) whose workplace block and home block share the first five "
           "digits (county); `same_tract_share` uses the first eleven digits. Year-on-year changes are in "
           "percentage points and are only reported where the previous data year exists for that state.\n")

present = man[man.present == 1].groupby("state").year.agg(["min", "max", "size"])
missing = man[man.present == 0]
out.append(f"Files present: {int(man.present.sum())} of {len(man)} state-years. "
           f"States with a late start (first JT02 year > 2004): "
           + ", ".join(f"{k.upper()} {int(v)}" for k, v in present["min"][present["min"] > 2004].items())
           + ".\n")

out.append("## 1. Distribution of the year-on-year change in the same-county share\n")
for yr, lab in [(2007, "2006->2007"), (2009, "2008->2009")]:
    out += summarize("d_same_county_pts", yr, lab)
out.append("**Other years, for comparison (same-county share, pts):**\n")
out.append("| year | n | median | mean | p10 | p90 | drop > 1 pt | drop > 2 pts | drop > 3 pts | rise > 1 pt |")
out.append("|---|---|---|---|---|---|---|---|---|---|")
for yr in YEARS:
    d = dist("d_same_county_pts", yr)
    out.append(f"| {yr-1}->{yr} | {len(d)} | {d.median():+.2f} | {d.mean():+.2f} | {d.quantile(.1):+.2f} | "
               f"{d.quantile(.9):+.2f} | {(d < -1).sum()} | {(d < -2).sum()} | {(d < -3).sum()} | {(d > 1).sum()} |")
out.append("")
out.append("**Same-tract share (pts):**\n")
out.append("| year | n | median | mean | p10 | p90 | drop > 0.5 pt | drop > 1 pt |")
out.append("|---|---|---|---|---|---|---|---|")
for yr in YEARS:
    d = dist("d_same_tract_pts", yr)
    out.append(f"| {yr-1}->{yr} | {len(d)} | {d.median():+.2f} | {d.mean():+.2f} | {d.quantile(.1):+.2f} | "
               f"{d.quantile(.9):+.2f} | {(d < -0.5).sum()} | {(d < -1).sum()} |")
out.append("")

# national pooled share (worker-weighted)
pool = s.groupby("year").agg(workers=("workers", "sum"),
                             same_county=("same_county_share", lambda x: np.average(x, weights=s.loc[x.index, "workers"])),
                             same_tract=("same_tract_share", lambda x: np.average(x, weights=s.loc[x.index, "workers"])),
                             n=("state", "size"))
# balanced panel: states present in all 8 years
full = present[present["size"] == 8].index
sb = s[s.state.isin(full)]
poolb = sb.groupby("year").agg(workers=("workers", "sum"),
                               same_county=("same_county_share", lambda x: np.average(x, weights=sb.loc[x.index, "workers"])),
                               same_tract=("same_tract_share", lambda x: np.average(x, weights=sb.loc[x.index, "workers"])))
out.append(f"**Worker-weighted national shares (balanced panel of {len(full)} states present 2004-2011):**\n")
out.append("| year | workers (M) | same-county % | change | same-tract % | change |")
out.append("|---|---|---|---|---|---|")
prev = None
for yr, r in poolb.iterrows():
    dc = f"{(r.same_county - prev.same_county)*100:+.2f}" if prev is not None else ""
    dt = f"{(r.same_tract - prev.same_tract)*100:+.2f}" if prev is not None else ""
    out.append(f"| {yr} | {r.workers/1e6:.1f} | {r.same_county*100:.2f} | {dc} | {r.same_tract*100:.2f} | {dt} |")
    prev = r
out.append("")

out.append("## 2. County-level residence vs workplace jumps\n")
out.append("Share of counties (>= 500 workers in both years) whose resident-worker total, or workplace-job total, "
           "changes by more than 10 % in absolute value from the previous year. Median across states, and the "
           "number of states where the share exceeds 0.25.\n")
out.append("| year | n states | median share_res_jump | mean | states > 0.25 | median share_work_jump | mean | states > 0.25 | pooled res share | pooled work share |")
out.append("|---|---|---|---|---|---|---|---|---|---|")
for yr in YEARS:
    d = j[j.year == yr]
    pr = d.n_res_jump_gt10.sum() / d.n_counties.sum()
    pw = d.n_work_jump_gt10.sum() / d.n_counties_work.sum()
    out.append(f"| {yr-1}->{yr} | {len(d)} | {d.share_res_jump_gt10.median():.3f} | {d.share_res_jump_gt10.mean():.3f} | "
               f"{(d.share_res_jump_gt10 > .25).sum()} | {d.share_work_jump_gt10.median():.3f} | "
               f"{d.share_work_jump_gt10.mean():.3f} | {(d.share_work_jump_gt10 > .25).sum()} | {pr:.3f} | {pw:.3f} |")
out.append("")
out.append("MO/KS/IL residence-jump shares by year: ")
for st in FOCUS:
    d = j[j.state == st].set_index("year")
    out.append(f"- {st.upper()}: " + ", ".join(f"{yr} {d.share_res_jump_gt10.get(yr, float('nan')):.2f}/"
                                              f"{d.share_work_jump_gt10.get(yr, float('nan')):.2f}" for yr in YEARS)
               + " (res/work)")
out.append("")

out.append("## 3. Ranked table: 2006->2007 change in same-county share, all states\n")
t = s[s.year == 2007][["state", "workers", "same_county_share", "d_same_county_pts", "d_same_tract_pts", "d_workers_pct"]]
t = t.merge(s[s.year == 2006][["state", "same_county_share"]].rename(columns={"same_county_share": "sc_2006"}), on="state", how="left")
t = t.merge(j[j.year == 2007][["state", "share_res_jump_gt10", "share_work_jump_gt10"]], on="state", how="left")
t = t.merge(s[s.year == 2009][["state", "d_same_county_pts"]].rename(columns={"d_same_county_pts": "d_2009"}), on="state", how="left")
t = t.sort_values("d_same_county_pts")
out.append("| rank | state | workers 2007 | same-county 2006 % | 2007 % | change 2007 (pts) | same-tract change 2007 | workers change % | res-jump share 2007 | work-jump share 2007 | change 2009 (pts) |")
out.append("|---|---|---|---|---|---|---|---|---|---|---|")
for i, r in enumerate(t.itertuples(), 1):
    f = lambda v, fmt: (fmt % v) if pd.notna(v) else "n/a"
    out.append(f"| {i} | {r.state.upper()} | {r.workers/1e6:.2f}M | {f(r.sc_2006*100 if pd.notna(r.sc_2006) else np.nan, '%.1f')} | "
               f"{r.same_county_share*100:.1f} | {f(r.d_same_county_pts, '%+.2f')} | {f(r.d_same_tract_pts, '%+.2f')} | "
               f"{f(r.d_workers_pct, '%+.1f')} | {f(r.share_res_jump_gt10, '%.2f')} | {f(r.share_work_jump_gt10, '%.2f')} | {f(r.d_2009, '%+.2f')} |")
out.append("")

# ---------- verdict ----------
d07 = dist("d_same_county_pts", 2007)
d09 = dist("d_same_county_pts", 2009)
others = pd.concat([dist("d_same_county_pts", y) for y in (2005, 2006, 2008, 2010, 2011)])
rank = {k: i + 1 for i, k in enumerate(d07.sort_values().index)}
out.append("## 4. Verdict\n")
out.append(f"- 2006->2007: {(d07 < -1).sum()} of {len(d07)} states drop more than 1 pt, {(d07 < -2).sum()} more than 2 pts, "
           f"{(d07 < -3).sum()} more than 3 pts; median {d07.median():+.2f} pts. In the five other transition years the "
           f"median change is {others.median():+.2f} pts and only {(others < -1).sum()} of {len(others)} state-years drop more than 1 pt.")
out.append(f"- 2008->2009: {(d09 < -1).sum()} of {len(d09)} states drop more than 1 pt, median {d09.median():+.2f} pts.")
out.append(f"- MO/KS/IL rank {', '.join(f'{k.upper()} {rank.get(k)}' for k in FOCUS)} of {len(d07)} in the size of the 2007 drop.")
jr07 = j[j.year == 2007]; jr08 = j[j.year == 2008]; jr05 = j[j.year == 2005]; jr06 = j[j.year == 2006]
out.append(f"- Residence-jump share, median across states: 2005 {jr05.share_res_jump_gt10.median():.3f}, 2006 {jr06.share_res_jump_gt10.median():.3f}, "
           f"2007 {jr07.share_res_jump_gt10.median():.3f}, 2008 {jr08.share_res_jump_gt10.median():.3f}; workplace-jump share: "
           f"2005 {jr05.share_work_jump_gt10.median():.3f}, 2006 {jr06.share_work_jump_gt10.median():.3f}, 2007 {jr07.share_work_jump_gt10.median():.3f}, 2008 {jr08.share_work_jump_gt10.median():.3f}.")
out.append("")
d11 = dist("d_same_county_pts", 2011)
jr11 = j[j.year == 2011]
t09 = dist("d_same_tract_pts", 2009)
out.append(
    f"**The 2007 step is national, not regional and not specific to MO/KS/IL.** Essentially every state's same-county "
    f"share falls between data years 2006 and 2007 (only {(d07 >= 0).sum()} of {len(d07)} states show no drop), the median drop "
    f"({d07.median():+.2f} pts) is roughly seven times the typical year-on-year change, the same-tract share falls in "
    f"{(dist('d_same_tract_pts', 2007) < 0).sum()} of {len(d07)} states in the same year, and MO, KS and IL sit in the middle of the "
    f"distribution (ranks {', '.join(str(rank.get(k)) for k in FOCUS)} of {len(d07)}). The largest drops are in low-density "
    f"western and plains states (ID, WY, SD, UT, MT) and the smallest in DE, CT, NH, MD, MS and OH. The county-level signature "
    f"matches: the share of counties whose resident-worker total jumps > 10 % is {jr05.share_res_jump_gt10.median():.2f} (2005), "
    f"{jr06.share_res_jump_gt10.median():.2f} (2006) and {jr07.share_res_jump_gt10.median():.2f} (2007) at the median state against "
    f"0.06-0.07 in 2008 and 2010, and {(jr05.share_res_jump_gt10 > .25).sum()}, {(jr06.share_res_jump_gt10 > .25).sum()} and "
    f"{(jr07.share_res_jump_gt10 > .25).sum()} states exceed 0.25 in 2005, 2006 and 2007 (2 in 2008, 0 in 2010), "
    f"while the workplace-jump share stays at {jr05.share_work_jump_gt10.median():.2f}-{jr07.share_work_jump_gt10.median():.2f} "
    f"with at most {max((jr05.share_work_jump_gt10 > .25).sum(), (jr06.share_work_jump_gt10 > .25).sum(), (jr07.share_work_jump_gt10 > .25).sum())} states above 0.25. "
    f"Workplace totals are stable in 2005-2007 everywhere; it is the residence side that moves.\n")
out.append(
    f"**The 2009 step is also national but looks different.** The same-county share falls in every state (median "
    f"{d09.median():+.2f} pts), but the same-tract share does not fall ({(t09 < 0).sum()} of {len(t09)} states, median "
    f"{t09.median():+.2f} pts), and in 2009 the workplace-jump share rises as much as the residence-jump share (medians "
    f"{jr08.share_work_jump_gt10.median():.2f} -> {j[j.year == 2009].share_work_jump_gt10.median():.2f} vs "
    f"{jr08.share_res_jump_gt10.median():.2f} -> {j[j.year == 2009].share_res_jump_gt10.median():.2f}), with total workers down "
    f"{s[s.year == 2009].d_workers_pct.median():+.1f} % at the median state. The 2009 change therefore mixes the recession "
    f"(real job losses that are geographically uneven) with a possible further residence or linkage change; it is not a clean "
    f"replica of 2007.\n")
out.append(
    f"**A further residence-side event in 2011.** The residence-jump share spikes again in 2010->2011 (median "
    f"{jr11.share_res_jump_gt10.median():.2f}, {(jr11.share_res_jump_gt10 > .25).sum()} states above 0.25) with no workplace "
    f"spike ({jr11.share_work_jump_gt10.median():.2f}), and the same-county share drops by more than 1 pt in {(d11 < -1).sum()} states, "
    f"concentrated in small rural states (WV, MT, VT, SD, ND, ME, AK). This is consistent with the end of the Composite Person Record era "
    f"(1999-2010) and a change of residence inputs for 2011, and should be treated as "
    f"another break, although a milder and more regional one than 2007.\n")
out.append("## 5. Caveats\n")
out.append("- Main files only (workers who live and work in the same state); interstate commuters are not included, so levels "
           "differ from the all-jobs JT00 main+aux series used elsewhere in this project (e.g. MO 2007 same-county share 55.0 % here "
           "vs 51.4 % in the JT00 series). The year-on-year changes are what matter here and they match (MO -2.9 pts in 2007 on both).")
out.append("- JT02 = private primary jobs. Federal jobs are absent in every year, so the 2010 federal-jobs addition in JT00 does not affect this series.")
out.append("- LODES 8 places every year on 2020 census blocks, so county and tract definitions are constant across years; "
           "Connecticut's 2022 planning regions are the 'counties' there (9 units).")
out.append(f"- Missing: DC 2004-2009 (no files), MA 2004-2010 (files exist but are stubs of 1-4 records and were excluded), "
           f"MA 2009 (404). Year-on-year changes are only computed where the previous year is present for the state.")
out.append("- The county-jump statistic uses counties with >= 500 workers (residence basis for the residence share, workplace basis "
           "for the workplace share) in both years, so states with few counties (DE 3, HI 5, RI 5, CT 9) give coarse shares.")
out.append("- Nothing here identifies the cause; the pattern (residence totals move, workplace totals do not, in every state at "
           "once, in a year with no documented LODES methodology change) is what points to a residence-input change on the LEHD side.")
out.append("")

with open(MD, "w") as f:
    f.write("\n".join(out))
print("\n".join(out))

# ---------- figure ----------
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": "#888", "axes.linewidth": 0.6,
                     "xtick.color": "#444", "ytick.color": "#444", "axes.labelcolor": "#333", "text.color": "#222"})
fig, axes = plt.subplots(1, 3, figsize=(13, 4.4), constrained_layout=True)
panels = [("d_same_county_pts", s, "Change in same-county share (pts)", "A. Same-county share, year-on-year change by state"),
          ("share_res_jump_gt10", j, "Share of counties with |change| > 10 %", "B. Resident-worker county totals jumping > 10 %"),
          ("share_work_jump_gt10", j, "Share of counties with |change| > 10 %", "C. Workplace-job county totals jumping > 10 %")]
rng = np.random.default_rng(3)
for ax, (col, df, ylab, title) in zip(axes, panels):
    for yr in YEARS:
        d = df[df.year == yr].dropna(subset=[col])
        c = HI if yr in (2007, 2009) else LO
        x = yr + rng.uniform(-0.22, 0.22, len(d))
        ax.scatter(x, d[col], marker="_", s=70, linewidths=0.9, color=c, alpha=0.75, zorder=3)
        med = d[col].median()
        ax.hlines(med, yr - 0.32, yr + 0.32, color=c, linewidth=2.0, zorder=4)
        ax.text(yr, 1.01, f"{med:+.1f}" if col.startswith("d_") else f"{med:.2f}",
                transform=ax.get_xaxis_transform(), ha="center", va="bottom", fontsize=7.5,
                color=c, fontweight="bold" if yr in (2007, 2009) else "normal")
        for st in FOCUS:
            v = d[d.state == st]
            if len(v):
                ax.annotate(st.upper(), (yr + 0.3, float(v[col].iloc[0])), fontsize=6.5, color="#333", va="center", ha="left")
    ax.set_title(title, fontsize=9.5, loc="left", pad=16)
    ax.set_ylabel(ylab)
    ax.set_xticks(YEARS)
    ax.set_xticklabels([str(y) for y in YEARS])
    ax.grid(axis="y", color="#e4e4e4", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    if col.startswith("d_"):
        ax.axhline(0, color="#999", linewidth=0.7, zorder=1)
    else:
        ax.set_ylim(bottom=-0.01)
fig.suptitle("LODES 8 JT02 main OD, 50 states + DC, data years 2005-2011 (change from previous year); "
             "each mark is one state, bar = median (value printed above each column); 2007 and 2009 highlighted; MO/KS/IL labelled",
             fontsize=8.5, color="#555")
os.makedirs(os.path.dirname(FIG), exist_ok=True)
fig.savefig(FIG, dpi=180)
print("figure:", FIG)
