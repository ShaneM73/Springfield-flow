"""Extend the ACS B08007 (place of work: worked in county of residence) series backwards and add the 5-year releases.

Adds to script 09 (which covers ACS 1-year 2010, 2012-2019, 2021-2024):
  * ACS 1-year 2005-2009 and 2011 (pre-2010 summary files have a different directory layout and lookup files).
  * ACS 5-year B08007 for every release 2005-09 (end year 2009) through 2019-23, all 51 metro counties.
  * Comparison with LODES same-county share, both annual and averaged over the matching 5-year window.

Bulk-file sources (no API key), all under https://www2.census.gov/programs-surveys/acs/summary_file/{year}/ :
  2005 1-yr : documentation/Chapter_5_tables_summary_list.xls (seq 22, start 70); data/{State}/{st}{seq:07d}.2005-1yr.zip
              (member {st}{seq:07d}e.2005-1yr); geography data/{State}/{st}geo.2005-1yr (fixed width, LOGRECNO 14-20, GEOID 111-150)
  2006 1-yr : documentation/merge_5_6_final.txt (tab-separated; seq 29, start 58); data/{State}/2006 1{st}{seq:04d}000.zip; g20061{st}.txt (GEOID 176-215)
  2007 1-yr : documentation/1_year/merge_5_6_final.xls (seq 33, start 58); data/1_year/{State}/20071{st}{seq:04d}000.zip; g20071{st}.txt (GEOID 176-215)
  2008 1-yr : documentation/1_year/user_tools/merge_5_6.xls (seq 33, start 58); data/1_year/{State}/20081{st}{seq:04d}000.zip; g20081{st}.txt
  2009 1-yr : documentation/1_year/user_tools/merge_5_6.txt (seq 33, start 58); data/1_year_by_state/{State}.zip (whole state; has g20091{st}.txt)
  2011 1-yr : documentation/1_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt; data/1_year_by_state/{State}_All_Geographies.zip
  2009 5-yr : documentation/5_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt (seq 25, start 58);
              data/5_year_seq_by_state/{State}/All_Geographies_Not_Tracts_Block_Groups/20095{st}{seq:04d}000.zip + g20095{st}.txt
  2010-12 5-yr: documentation/5_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt; same per-sequence zips + g{year}5{st}.csv
  2013-20 5-yr: documentation/user_tools/ACS_5yr_Seq_Table_Number_Lookup.txt; same per-sequence zips + g{year}5{st}.csv
  2021-23 5-yr: table-based-SF/data/5YRData/acsdt5y{year}-b08007.dat
The GEOID column of the fixed-width geography files is located from the state record ("04000US..") rather than hard-coded.

B08007 shell (identical 2005-2023, verified from each year's lookup and by the cell identities c1=c6+c11, c2=c3+c4, c1=c2+c5):
  001 Total; 002 Worked in state of residence; 003 Worked in county of residence; 004 Worked outside county of residence;
  005 Worked outside state of residence; 006-010 Male (same breakdown); 011-015 Female (same breakdown).

Outputs (outputs/external/):
  acs_b08007_county_year_all.csv     county, name, year (end year for 5-yr), period (1|5), workers, in_county, share
  acs_vs_lodes_samecounty_all.csv    merged with LODES annual share and LODES mean over the matching 5-year window
  figures/acs5_vs_lodes_slopes.png   5-year-window slopes 2009-2019 and 2019->2023 change, ACS vs LODES, 51 counties
  ACS_B08007_EXTENSION.md            tables and findings
Raw downloads are cached under Data/external/acs/.
"""
import importlib.util, io, re, sys, zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("ext", HERE / "08_external_controls.py")
ext = importlib.util.module_from_spec(spec); spec.loader.exec_module(ext)
get, ST_NAMES, EXT, EXT_RAW = ext.get, ext.ST_NAMES, ext.EXT, ext.EXT_RAW

TABLE = "B08007"
BASE = "https://www2.census.gov/programs-surveys/acs/summary_file"
ACS = EXT_RAW / "acs"
STATES = ("mo", "ks", "il")
CELLS = {"workers": 1, "in_county": 3}
ACS_COLOR, LODES_COLOR = "#eb6834", "#2a78d6"


# ------------------------------------------------------------------ generic readers
def read_lookup(raw, url):
    """Return (sequence number, start position) of B08007 from any of the lookup-file flavours."""
    if url.endswith((".xls", ".xlsx")):
        L = pd.read_excel(io.BytesIO(raw), dtype=str)
    elif b"\t" in raw[:4000]:
        L = pd.read_csv(io.BytesIO(raw), sep="\t", dtype=str, encoding="latin1")
    else:
        L = pd.read_csv(io.BytesIO(raw), dtype=str, encoding="latin1")
    L.columns = [str(c).strip().lower().replace(" ", "_") for c in L.columns]
    tid = next(c for c in L.columns if c in ("table_id", "tblid") or "table_id" in c)
    seqc = next(c for c in L.columns if c.startswith("seq"))
    startc = next(c for c in L.columns if "start" in c or c == "position")
    t = L[L[tid].str.strip() == TABLE]
    if t.empty:
        raise ValueError(f"{TABLE} not in lookup {url}")
    start = pd.to_numeric(t[startc], errors="coerce"); start = start[start > 0].iloc[0]
    return int(float(t[seqc].iloc[0])), int(start)


def geo_from_txt(raw):
    lines = raw.decode("latin1").splitlines()
    first = next(l for l in lines if "04000US" in l); idx = first.index("04000US")
    return pd.DataFrame({"logrecno": [l[13:20] for l in lines], "geoid": [l[idx:idx + 40].strip() for l in lines]})


def geo_from_csv(raw):
    G = pd.read_csv(io.BytesIO(raw), header=None, dtype=str, encoding="latin1")
    return G[[4, 48]].rename(columns={4: "logrecno", 48: "geoid"})


def county_table(efile_bytes, G, start, year, period):
    E = pd.read_csv(io.BytesIO(efile_bytes), header=None, dtype=str)
    df = pd.DataFrame({"logrecno": E[5]})
    for k, c in CELLS.items():
        df[k] = pd.to_numeric(E[start - 1 + c - 1], errors="coerce")
    df = df.merge(G, on="logrecno")
    df = df[df.geoid.str.startswith("05000US")].copy()
    df["county"] = df.geoid.str[-5:]
    return df[["county", "workers", "in_county"]].assign(year=year, period=period)


def member(zf, pattern):
    m = [n for n in zf.namelist() if re.search(pattern, n)]
    return m[0] if m else None


# ------------------------------------------------------------------ ACS 1-year, pre-2010 layouts + 2011
def one_year(year, st):
    S = ST_NAMES[st]; b = f"{BASE}/{year}"
    if year == 2005:
        look_url = f"{b}/documentation/Chapter_5_tables_summary_list.xls"
    elif year == 2006:
        look_url = f"{b}/documentation/merge_5_6_final.txt"
    elif year == 2007:
        look_url = f"{b}/documentation/1_year/merge_5_6_final.xls"
    elif year == 2008:
        look_url = f"{b}/documentation/1_year/user_tools/merge_5_6.xls"
    elif year == 2009:
        look_url = f"{b}/documentation/1_year/user_tools/merge_5_6.txt"
    else:
        look_url = f"{b}/documentation/1_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt"
    look = get(look_url, ACS / f"lookup_{year}.{look_url.rsplit('.', 1)[-1]}")
    if not look:
        print("no 1-yr lookup", year, look_url); return None
    seq, start = read_lookup(look, look_url)

    if year == 2005:
        z = get(f"{b}/data/{S}/{st}{seq:07d}.2005-1yr.zip", ACS / f"{year}_{st}_1yr_seq{seq}.zip")
        g = get(f"{b}/data/{S}/{st}geo.2005-1yr", ACS / f"g{year}1{st}.txt")
        if not z or not g:
            print("no 2005 data", st); return None
        zf = zipfile.ZipFile(io.BytesIO(z)); e = zf.read(member(zf, rf"{st}{seq:07d}e\.2005-1yr$")); G = geo_from_txt(g)
    elif year in (2006, 2007, 2008):
        d = f"{b}/data/{S}" if year == 2006 else f"{b}/data/1_year/{S}"
        z = get(f"{d}/{year}1{st}{seq:04d}000.zip", ACS / f"{year}_{st}_1yr_seq{seq}.zip")
        g = get(f"{d}/g{year}1{st}.txt", ACS / f"g{year}1{st}.txt")
        if not z or not g:
            print("no data", year, st); return None
        zf = zipfile.ZipFile(io.BytesIO(z)); e = zf.read(member(zf, rf"e{year}1{st}{seq:04d}000\.txt$")); G = geo_from_txt(g)
    else:  # 2009, 2011: whole-state zip (same cache name as script 09)
        z = None
        for zu in (f"{b}/data/1_year_by_state/{S}_All_Geographies.zip", f"{b}/data/1_year_by_state/{S}.zip"):
            z = get(zu, ACS / f"{year}_{st}_1yr.zip")
            if z:
                break
        if not z:
            print("no state zip", year, st); return None
        zf = zipfile.ZipFile(io.BytesIO(z)); e = zf.read(member(zf, rf"e{year}1{st}{seq:04d}000\.txt$"))
        gc = member(zf, rf"g{year}1{st}\.csv$")
        G = geo_from_csv(zf.read(gc)) if gc else geo_from_txt(zf.read(member(zf, rf"g{year}1{st}\.txt$")))
    print(f"1-yr {year} {st}: seq {seq} start {start}", flush=True)
    return county_table(e, G, start, year, 1)


# ------------------------------------------------------------------ ACS 5-year
def five_year_seq(year, st):
    S = ST_NAMES[st]; b = f"{BASE}/{year}"
    if year <= 2012:
        look_url = f"{b}/documentation/5_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt"
    else:
        look_url = f"{b}/documentation/user_tools/ACS_5yr_Seq_Table_Number_Lookup.txt"
    look = get(look_url, ACS / f"lookup5_{year}.txt")
    if not look:
        print("no 5-yr lookup", year, look_url); return None
    seq, start = read_lookup(look, look_url)
    d = f"{b}/data/5_year_seq_by_state/{S}/All_Geographies_Not_Tracts_Block_Groups"
    z = get(f"{d}/{year}5{st}{seq:04d}000.zip", ACS / f"{year}_{st}_5yr_seq{seq}.zip")
    if not z:
        print("no 5-yr seq zip", year, st); return None
    zf = zipfile.ZipFile(io.BytesIO(z)); e = zf.read(member(zf, rf"e{year}5{st}{seq:04d}000\.txt$"))
    g = get(f"{d}/g{year}5{st}.csv", ACS / f"g{year}5{st}.csv")
    if g:
        G = geo_from_csv(g)
    else:
        g = get(f"{d}/g{year}5{st}.txt", ACS / f"g{year}5{st}.txt")
        if not g:
            print("no 5-yr geo", year, st); return None
        G = geo_from_txt(g)
    print(f"5-yr {year} {st}: seq {seq} start {start}", flush=True)
    return county_table(e, G, start, year, 5)


def five_year_table_based(year):
    d = get(f"{BASE}/{year}/table-based-SF/data/5YRData/acsdt5y{year}-{TABLE.lower()}.dat", ACS / f"acsdt5y{year}-{TABLE.lower()}.dat")
    if not d:
        print("no table-based 5-yr", year); return None
    T = pd.read_csv(io.BytesIO(d), sep="|", dtype=str)
    T = T[T.GEO_ID.str.startswith("0500000US")]
    num = lambda c: pd.to_numeric(T[c], errors="coerce")
    print(f"5-yr {year} table-based", flush=True)
    return pd.DataFrame({"county": T.GEO_ID.str[-5:], "workers": num(f"{TABLE}_E001"), "in_county": num(f"{TABLE}_E003"),
                         "year": year, "period": 5})


# ------------------------------------------------------------------ assembly
def build_acs(counties):
    rows = []
    for y in (2005, 2006, 2007, 2008, 2009, 2011):
        for st in STATES:
            try:
                p = one_year(y, st)
                if p is not None:
                    rows.append(p)
            except Exception as e:
                print("1-yr failed", y, st, repr(e)[:200], flush=True)
    for y in range(2009, 2021):
        for st in STATES:
            try:
                p = five_year_seq(y, st)
                if p is not None:
                    rows.append(p)
            except Exception as e:
                print("5-yr failed", y, st, repr(e)[:200], flush=True)
    for y in (2021, 2022, 2023):
        p = five_year_table_based(y)
        if p is not None:
            rows.append(p)
    new = pd.concat(rows, ignore_index=True)
    old = pd.read_csv(EXT / "acs_b08007_county_year.csv", dtype={"county": str}).assign(period=1)
    A = pd.concat([old[["county", "year", "period", "workers", "in_county"]], new], ignore_index=True)
    A = A[A.county.isin(counties)].drop_duplicates(["county", "year", "period"]).dropna(subset=["workers"])
    A = A[A.workers > 0].copy()
    A["share"] = A.in_county / A.workers
    A["name"] = A.county.map(counties)
    A = A.sort_values(["county", "period", "year"]).reset_index(drop=True)
    return A[["county", "name", "year", "period", "workers", "in_county", "share"]]


def merge_lodes(A):
    L = pd.read_csv(EXT / "lodes_county_samecounty_year.csv", dtype={"county": str})
    L = L.sort_values(["county", "year"])
    L["lodes_share"] = L.same_county_share
    # trailing 5-year mean of the LODES share, ending in `year` (window year-4 .. year), with the number of years available
    g = L.groupby("county").lodes_share
    L["lodes_share_window5"] = g.transform(lambda s: s.rolling(5, min_periods=3).mean())
    L["lodes_window_n"] = g.transform(lambda s: s.rolling(5, min_periods=1).count())
    M = A.merge(L[["county", "year", "res_workers", "lodes_share", "lodes_share_window5", "lodes_window_n"]], on=["county", "year"], how="left")
    M["lodes_match"] = np.where(M.period == 5, M.lodes_share_window5, M.lodes_share)
    M["diff_acs_minus_lodes"] = M.share - M.lodes_match
    return M.rename(columns={"workers": "acs_workers", "in_county": "acs_in_county", "share": "acs_share", "res_workers": "lodes_res_workers"})


def slope(df, xcol, ycol):
    d = df.dropna(subset=[ycol])
    if len(d) < 5:
        return np.nan
    return np.polyfit(d[xcol].astype(float), d[ycol].astype(float), 1)[0]


def window_stats(M):
    """Per-county slopes of the ACS 5-yr share and of the LODES window mean over end years 2009-2019, plus the 2019->2023 change."""
    F = M[(M.period == 5)]
    out = []
    for c, d in F.groupby("county"):
        d = d.set_index("year")
        w = d.loc[(d.index >= 2009) & (d.index <= 2019)].reset_index()
        rec = dict(county=c, name=d.name.iloc[0], n_points=len(w),
                   acs_slope=slope(w, "year", "acs_share"), lodes_slope=slope(w, "year", "lodes_share_window5"),
                   acs_change_19_23=d.acs_share.get(2023, np.nan) - d.acs_share.get(2019, np.nan),
                   lodes_change_19_23=d.lodes_share_window5.get(2023, np.nan) - d.lodes_share_window5.get(2019, np.nan),
                   acs_2019=d.acs_share.get(2019, np.nan), lodes_2019=d.lodes_share_window5.get(2019, np.nan),
                   workers_2019=d.acs_workers.get(2019, np.nan))
        out.append(rec)
    return pd.DataFrame(out)


def scatter_figure(W, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    panels = [("acs_slope", "lodes_slope", "5-year-window slope, end years 2009-2019 (share points / yr)", 100),
              ("acs_change_19_23", "lodes_change_19_23", "Change 2015-19 -> 2019-23 (share points)", 100)]
    core = {"29077": "Greene", "29095": "Jackson", "29189": "St. Louis Co.", "20091": "Johnson KS", "29019": "Boone", "29510": "St. Louis city"}
    for ax, (ya, xl, title, k) in zip(axes, panels):
        x = W[xl] * k; y = W[ya] * k
        lo = min(np.nanmin(x), np.nanmin(y)); hi = max(np.nanmax(x), np.nanmax(y)); pad = 0.06 * (hi - lo)
        ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad], color=LODES_COLOR, lw=0.8, ls="--", alpha=0.6, zorder=1, label="equality")
        ax.axhline(0, color="#d0d0d0", lw=0.6, zorder=0); ax.axvline(0, color="#d0d0d0", lw=0.6, zorder=0)
        ax.scatter(x, y, s=np.clip(W.workers_2019 / 4000, 12, 160), facecolor="none", edgecolor=ACS_COLOR, lw=0.9, zorder=3)
        resid = (y - x).abs()
        label = set(W.loc[resid.nlargest(3).index, "county"]) | set(core)
        for i, (_, r) in enumerate(W[W.county.isin(label)].sort_values(ya).iterrows()):
            dy = 4 if i % 2 == 0 else -9
            ax.annotate(core.get(r["county"], r["name"]), (r[xl] * k, r[ya] * k), fontsize=6.5, color="#444", xytext=(4, dy), textcoords="offset points")
        ax.set_xlabel(f"LODES, mean over the same 5-year window ({'pts/yr' if 'slope' in xl else 'pts'})", color=LODES_COLOR)
        ax.set_ylabel(f"ACS 5-year B08007 ({'pts/yr' if 'slope' in ya else 'pts'})", color=ACS_COLOR)
        ax.set_title(title, fontsize=10)
        ax.grid(True, color="#e6e6e6", lw=0.5); ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.set_xlim(np.nanmin(x) - pad, np.nanmax(x) + pad); ax.set_ylim(np.nanmin(y) - pad, np.nanmax(y) + pad)
    fig.suptitle("Within-county share of resident workers working in their county: ACS 5-year vs LODES (51 metro counties)", fontsize=11)
    fig.text(0.01, 0.01, "Marker size ~ ACS workers 2015-19. Dashed line: equality. Points = percentage points.", fontsize=7, color="#666")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    path.parent.mkdir(parents=True, exist_ok=True); fig.savefig(path, dpi=160); plt.close(fig)


def md_table(df, fmt=None):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append("" if np.isnan(v) else (fmt or "{:.3f}").format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report(A, M, W, counties):
    out = [f"# ACS B08007 extension: 1-year 2005-2011 and 5-year 2005-09 .. 2019-23\n",
           "Generated by `scripts/09c_acs_b08007_extend.py`. Share = B08007 cell 003 (worked in county of residence) / cell 001 (workers 16+), "
           "universe = workers 16 and over by county of residence. LODES = same-county share of resident workers (JT00, S000, all 51 counties, "
           "`lodes_county_samecounty_year.csv`).\n"]
    # --- coverage
    cov = A.groupby("period").year.agg(["min", "max", "nunique"]).reset_index()
    out.append("## Coverage\n")
    out.append(md_table(cov))
    out.append("")
    n1 = A[A.period == 1].groupby("year").county.nunique()
    out.append("Counties with 1-year estimates by year: " + ", ".join(f"{y}: {n}" for y, n in n1.items()) + ".\n")

    # --- (i) 1-year, 2005-2012
    out.append("## (i) ACS 1-year vs LODES annual, 2005-2012: is there a 2007 or a 2009 step?\n")
    one = M[(M.period == 1) & (M.year.between(2005, 2012))]
    core = one.groupby("county").year.nunique()
    core = core[core >= 6].index.tolist()
    piv_a = one[one.county.isin(core)].pivot(index="county", columns="year", values="acs_share")
    piv_l = one[one.county.isin(core)].pivot(index="county", columns="year", values="lodes_share")
    tab = pd.DataFrame({"county": piv_a.index, "name": [counties[c] for c in piv_a.index]})
    for y in range(2005, 2013):
        tab[f"ACS {y}"] = (piv_a[y].values * 100) if y in piv_a else np.nan
    tab2 = pd.DataFrame({"county": piv_l.index, "name": [counties[c] for c in piv_l.index]})
    for y in range(2005, 2013):
        tab2[f"LODES {y}"] = (piv_l[y].values * 100) if y in piv_l else np.nan
    out.append("ACS 1-year in-county share (%), counties with 1-year estimates in at least 6 of the 8 years (2011 1-year added here; 2010 and 2012 from script 09):\n")
    out.append(md_table(tab, "{:.1f}")); out.append("")
    out.append("LODES same-county share (%), same counties:\n")
    out.append(md_table(tab2, "{:.1f}")); out.append("")
    # pooled series across the Missouri 1-year counties and all core counties
    mo_core = [c for c in core if c.startswith("29")]
    pooled = []
    for label, cs in (("Missouri 1-yr counties (pooled)", mo_core), ("All 1-yr counties (pooled)", core)):
        d = one[one.county.isin(cs)]
        full = d.groupby("year").county.nunique()
        yrs = full[full == len(cs)].index
        d = d[d.year.isin(yrs)]
        pa = d.groupby("year").apply(lambda g: g.acs_in_county.sum() / g.acs_workers.sum(), include_groups=False) * 100
        pl = d.groupby("year").apply(lambda g: (g.lodes_share * g.lodes_res_workers).sum() / g.lodes_res_workers.sum(), include_groups=False) * 100
        pooled.append((label, len(cs), pa, pl))
    rows = []
    for label, n, pa, pl in pooled:
        r = {"series": f"{label}, n={n}: ACS"}; r.update({str(y): pa.get(y, np.nan) for y in range(2005, 2013)}); rows.append(r)
        r = {"series": f"{label}, n={n}: LODES"}; r.update({str(y): pl.get(y, np.nan) for y in range(2005, 2013)}); rows.append(r)
    out.append("Pooled shares (%) (sum of in-county workers / sum of workers over the listed counties; LODES weighted by resident workers):\n")
    out.append(md_table(pd.DataFrame(rows), "{:.1f}")); out.append("")
    # year-to-year changes, mean and median across core counties
    chg = []
    for y in range(2006, 2013):
        da = (piv_a[y] - piv_a[y - 1]) * 100 if (y in piv_a and y - 1 in piv_a) else pd.Series(dtype=float)
        dl = (piv_l[y] - piv_l[y - 1]) * 100 if (y in piv_l and y - 1 in piv_l) else pd.Series(dtype=float)
        chg.append({"change": f"{y-1}->{y}", "ACS mean": da.mean(), "ACS median": da.median(), "ACS n": int(da.notna().sum()),
                    "LODES mean": dl.mean(), "LODES median": dl.median(),
                    "share of counties where ACS fell": float((da < 0).sum()) / max(da.notna().sum(), 1),
                    "corr(dACS,dLODES)": da.corr(dl) if da.notna().sum() > 3 else np.nan})
    C = pd.DataFrame(chg)
    out.append("Year-to-year change in the share (percentage points), across the same counties:\n")
    out.append(md_table(C, "{:.2f}")); out.append("")
    # verdict text
    def pick(y):
        r = C[C.change == f"{y-1}->{y}"].iloc[0]; return r["ACS mean"], r["LODES mean"], r["share of counties where ACS fell"]
    a07, l07, f07 = pick(2007); a09, l09, f09 = pick(2009)
    a08, l08, _ = pick(2008); a10, l10, _ = pick(2010)
    typical = C[~C.change.isin(["2006->2007", "2008->2009"])]["ACS mean"].abs().mean()
    out.append(f"**Reading.** Across the 1-year counties, LODES changes by a mean of {l07:+.2f} points in 2007 and {l09:+.2f} points in 2009 "
               f"(2008: {l08:+.2f}, 2010: {l10:+.2f}). The ACS 1-year share moves {a07:+.2f} points in 2007 (fell in {f07:.0%} of counties) "
               f"and {a09:+.2f} points in 2009 (fell in {f09:.0%} of counties); the mean absolute ACS year-to-year move in the other years is "
               f"{typical:.2f} points, which is the sampling-noise scale of 1-year county estimates. "
               + ("The ACS shows no 2007 step comparable to LODES. " if abs(a07) < max(0.5 * abs(l07), typical) else "The ACS shows a 2007 move in the same direction as LODES. ")
               + ("The ACS shows no 2009 step comparable to LODES." if abs(a09) < max(0.5 * abs(l09), typical) else "The ACS shows a 2009 move in the same direction as LODES.")
               + " See the pooled rows above for the aggregate picture.\n")
    l11 = piv_l[2011] - piv_l[2010]; a11 = piv_a[2011] - piv_a[2010]
    big11 = [(counties[c], v * 100) for c, v in l11.items() if v > 0.03]
    if big11:
        out.append("Note the 2010->2011 LODES jump in " + ", ".join(f"{n} (+{v:.1f} pts)" for n, v in big11)
                   + f" (ACS 2011 change in the same counties: {', '.join(f'{a11[c]*100:+.1f}' for c in l11[l11 > 0.03].index)} pts): "
                   "a LODES-side discontinuity with no counterpart in the ACS (possibly the 2010-11 entry of federal workers and/or a change in "
                   "Missouri employer address assignment; not investigated here).\n")

    # --- (ii) 5-year windows
    out.append("## (ii) ACS 5-year vs window-averaged LODES, all 51 counties\n")
    five = M[M.period == 5]
    pooled5 = five.groupby("year").apply(lambda g: pd.Series({"ACS pooled share": g.acs_in_county.sum() / g.acs_workers.sum() * 100,
                                                              "LODES window mean (pooled, weighted)": (g.lodes_share_window5 * g.lodes_res_workers).sum() / g.lodes_res_workers.sum() * 100,
                                                              "n counties": len(g)}), include_groups=False).reset_index()
    pooled5["window"] = pooled5.year.apply(lambda y: f"{y-4}-{y}")
    out.append("Pooled over the 51 counties, by 5-year window (end year = ACS release year; LODES = mean of the five annual shares in the same window):\n")
    out.append(md_table(pooled5[["window", "ACS pooled share", "LODES window mean (pooled, weighted)", "n counties"]], "{:.2f}")); out.append("")
    Wt = W.copy()
    for c in ("acs_slope", "lodes_slope", "acs_change_19_23", "lodes_change_19_23"):
        Wt[c] = Wt[c] * 100
    Wt["acs_2019"] *= 100; Wt["lodes_2019"] *= 100
    Wt = Wt.sort_values("lodes_slope")
    Wt = Wt.rename(columns={"acs_slope": "ACS slope 09-19 (pts/yr)", "lodes_slope": "LODES slope 09-19 (pts/yr)",
                            "acs_change_19_23": "ACS chg 19->23 (pts)", "lodes_change_19_23": "LODES chg 19->23 (pts)",
                            "acs_2019": "ACS 2015-19 (%)", "lodes_2019": "LODES 2015-19 mean (%)", "n_points": "n windows"})
    out.append("Per-county slopes over end years 2009-2019 (OLS on the 11 overlapping windows) and the 2015-19 -> 2019-23 change:\n")
    out.append(md_table(Wt[["county", "name", "n windows", "ACS 2015-19 (%)", "LODES 2015-19 mean (%)", "ACS slope 09-19 (pts/yr)", "LODES slope 09-19 (pts/yr)",
                            "ACS chg 19->23 (pts)", "LODES chg 19->23 (pts)"]], "{:.2f}")); out.append("")
    ok = W.dropna(subset=["acs_slope", "lodes_slope"])
    r_slope = np.corrcoef(ok.acs_slope, ok.lodes_slope)[0, 1]
    ok2 = W.dropna(subset=["acs_change_19_23", "lodes_change_19_23"])
    r_chg = np.corrcoef(ok2.acs_change_19_23, ok2.lodes_change_19_23)[0, 1]
    wmean = lambda s, w: np.nansum(s * w) / np.nansum(w[s.notna()])
    out.append(f"Summary: slopes 2009-2019, mean across counties ACS {W.acs_slope.mean()*100:+.3f} pts/yr vs LODES {W.lodes_slope.mean()*100:+.3f} pts/yr "
               f"(worker-weighted {wmean(W.acs_slope, W.workers_2019)*100:+.3f} vs {wmean(W.lodes_slope, W.workers_2019)*100:+.3f}); "
               f"cross-county correlation of slopes r = {r_slope:.2f} (n = {len(ok)}); counties where both slopes have the same sign: "
               f"{int((np.sign(ok.acs_slope) == np.sign(ok.lodes_slope)).sum())}/{len(ok)}. "
               f"2019->2023 change: mean ACS {W.acs_change_19_23.mean()*100:+.2f} pts vs LODES {W.lodes_change_19_23.mean()*100:+.2f} pts, r = {r_chg:.2f}.\n")
    il = W[W.county.str.startswith("17")]; mo = W[W.county.str.startswith("29")]
    out.append(f"Interpretation: over 2009-2019 the ACS 5-year share is nearly flat (worker-weighted {wmean(W.acs_slope, W.workers_2019)*100:+.2f} pts/yr) "
               f"while the LODES window mean falls {wmean(W.lodes_slope, W.workers_2019)*100:+.2f} pts/yr; the cross-county ordering agrees moderately "
               f"(r = {r_slope:.2f}) but the LODES decline is broader (negative LODES slope in {int((W.lodes_slope < 0).sum())}/51 counties vs ACS "
               f"{int((W.acs_slope < 0).sum())}/51). The 2019->2023 divergence runs the other way: the ACS share rises in {int((W.acs_change_19_23 > 0).sum())}/51 counties "
               f"(mean {W.acs_change_19_23.mean()*100:+.2f} pts; Illinois counties {il.acs_change_19_23.mean()*100:+.2f}, Missouri {mo.acs_change_19_23.mean()*100:+.2f}) "
               "because B08007 assigns people who work from home to their county of residence, so the post-2020 remote-work shift raises the ACS in-county share "
               "mechanically, whereas LODES keeps assigning those jobs to the employer's establishment address and its window mean keeps drifting down.\n")
    out.append("Figure: `outputs/external/figures/acs5_vs_lodes_slopes.png`.\n")

    # --- (iii) caveats
    out.append("## (iii) Caveats\n")
    out.append("\n".join([
        "- ACS estimates carry sampling error. 1-year county estimates (65,000+ population) have margins of error on the in-county share of roughly 1-3 points "
        "for the large counties and more for the smaller ones; year-to-year moves of that size are noise, so only a step that is both large and common to most counties is evidence. "
        "MOEs were not extracted here (the m-files are in the same zips if needed).",
        "- 5-year releases overlap: consecutive windows share four of five sample years, so the 11 'slopes' over 2009-2019 are fitted to heavily autocorrelated points and the effective number of independent windows is about 2-3. The LODES comparison series is averaged over the identical calendar windows, so this affects both series equally but inflates the apparent smoothness of both.",
        "- The ACS universe is workers 16+ who worked last week (residence-based, place of work as reported, including self-employed and workers not covered by UI); LODES covers UI-covered jobs (plus federal from 2010) with workplace and residence as recorded administratively, and includes multiple jobholding. Levels are therefore not expected to agree; the comparison is about changes.",
        "- 2020 has no standard ACS 1-year release; the 2016-20 5-year release is included (sequence-based files) but its 2020 sample is affected by the pandemic non-response and the Bureau's experimental weighting.",
        "- Pre-2010 1-year counties: only counties with population 65,000+ are published (16 in Missouri, 4-5 in Kansas and Illinois within the metros), so the 2005-2009 comparison covers the core counties only. Smaller metro counties enter only through the 5-year series (first release 2005-09).",
        "- County of residence vs county of work in ACS is self-reported place of work (address of the workplace last week); for people with no fixed workplace it is where they reported to, which can differ from the LODES administrative workplace (often an employer's reporting unit).",
        "- LODES state coverage: the 'all 51 counties' LODES share uses MO, KS and IL OD files plus the out-of-state residence file where available; cross-state flows for counties on the state line (Kansas City, St. Louis) depend on the partner state's file being present for that year.",
    ]))
    out.append("")
    (EXT / "ACS_B08007_EXTENSION.md").write_text("\n".join(out))


def main():
    counties = ext.all_counties()
    A = build_acs(counties)
    A.to_csv(EXT / "acs_b08007_county_year_all.csv", index=False)
    M = merge_lodes(A)
    M.to_csv(EXT / "acs_vs_lodes_samecounty_all.csv", index=False)
    W = window_stats(M)
    scatter_figure(W, EXT / "figures" / "acs5_vs_lodes_slopes.png")
    write_report(A, M, W, counties)
    g = M[(M.county == "29077")].pivot(index="period", columns="year", values="acs_share")
    print("Greene County ACS share by year:\n", (g * 100).round(1).to_string())
    print("1-yr counties by year:", A[A.period == 1].groupby("year").county.nunique().to_dict())
    print("5-yr counties by year:", A[A.period == 5].groupby("year").county.nunique().to_dict())


if __name__ == "__main__":
    main()
