"""Margins of error for ACS B08007 (worked in county of residence) and formal tests against the LODES steps and trends.

Reads only files already cached by scripts 09 / 09c under Data/external/acs/ (no new downloads):
  1-year 2005-2019: the m-files next to the e-files in the cached sequence zips (same cell positions);
  1-year 2021-2024 and 5-year 2021-2023: the *_M001 / *_M003 columns of the table-based .dat files;
  5-year 2009-2020: m-files in the cached per-sequence zips.
MOEs are the published 90 % margins. MOE of the share p = in_county / workers uses the Census ratio/proportion formula
  MOE_p = sqrt(MOE_num^2 - p^2 MOE_den^2) / den, falling back to sqrt(MOE_num^2 + p^2 MOE_den^2) / den if the radicand is negative.
A published MOE of -555555555 (controlled estimate) is treated as 0; other negative codes as missing.

Outputs (outputs/external/):
  acs_b08007_county_year_moe.csv   county, year, period, workers, workers_moe, in_county, in_county_moe, share, share_moe
  acs_vs_lodes_step_tests.csv      (a) per county and year change 2005->06 .. 2011->12, ACS change +/- MOE vs LODES change; pooled rows
  acs_vs_lodes_slope_tests.csv     (b) per county 2010-2019 WLS slope of the ACS share with MOE-based SE vs the LODES slope
  acs_vs_lodes_slope_tests_pooled.csv  (b) same for the pooled 16-MO and 21-county series
  ACS_B08007_MOE_TESTS.md          summary
"""
import importlib.util, io, re, sys, zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("x9c", HERE / "09c_acs_b08007_extend.py")
x = importlib.util.module_from_spec(spec); spec.loader.exec_module(x)
ext, EXT, ACS, STATES, TABLE = x.ext, x.EXT, x.ACS, x.STATES, x.TABLE
read_lookup, geo_from_txt, geo_from_csv, member = x.read_lookup, x.geo_from_txt, x.geo_from_csv, x.member
Z90 = 1.645
CELLS = {"workers": 1, "in_county": 3}


def clean_moe(s):
    v = pd.to_numeric(s, errors="coerce")
    v = v.where(v != -555555555, 0.0)
    return v.where(v >= 0)


def lookup_for(year, period):
    cands = sorted(ACS.glob(f"lookup{'5' if period == 5 else ''}_{year}.*"))
    if not cands:
        return None
    f = cands[0]
    return read_lookup(f.read_bytes(), str(f))


def em_table(e_bytes, m_bytes, G, start, year, period):
    E = pd.read_csv(io.BytesIO(e_bytes), header=None, dtype=str)
    Mm = pd.read_csv(io.BytesIO(m_bytes), header=None, dtype=str)
    df = pd.DataFrame({"logrecno": E[5]})
    for k, c in CELLS.items():
        df[k] = pd.to_numeric(E[start - 1 + c - 1], errors="coerce")
        df[k + "_moe"] = clean_moe(Mm[start - 1 + c - 1]).values if len(Mm) == len(E) else np.nan
    df = df.merge(G, on="logrecno")
    df = df[df.geoid.str.startswith("05000US")].copy()
    df["county"] = df.geoid.str[-5:]
    return df.drop(columns=["logrecno", "geoid"]).assign(year=year, period=period)


def one_year(year, st):
    ls = lookup_for(year, 1)
    if ls is None:
        print("no cached 1-yr lookup", year); return None
    seq, start = ls
    if year == 2005:
        zp = ACS / f"{year}_{st}_1yr_seq{seq}.zip"; gp = ACS / f"g{year}1{st}.txt"
        if not zp.exists() or not gp.exists():
            print("missing cache", year, st); return None
        zf = zipfile.ZipFile(zp)
        e = zf.read(member(zf, rf"{st}{seq:07d}e\.2005-1yr$")); mn = member(zf, rf"{st}{seq:07d}m\.2005-1yr$")
        G = geo_from_txt(gp.read_bytes())
    elif year in (2006, 2007, 2008):
        zp = ACS / f"{year}_{st}_1yr_seq{seq}.zip"; gp = ACS / f"g{year}1{st}.txt"
        if not zp.exists() or not gp.exists():
            print("missing cache", year, st); return None
        zf = zipfile.ZipFile(zp)
        e = zf.read(member(zf, rf"e{year}1{st}{seq:04d}000\.txt$")); mn = member(zf, rf"m{year}1{st}{seq:04d}000\.txt$")
        G = geo_from_txt(gp.read_bytes())
    else:
        zp = ACS / f"{year}_{st}_1yr.zip"
        if not zp.exists():
            print("missing cache", year, st); return None
        zf = zipfile.ZipFile(zp)
        e = zf.read(member(zf, rf"e{year}1{st}{seq:04d}000\.txt$")); mn = member(zf, rf"m{year}1{st}{seq:04d}000\.txt$")
        gc = member(zf, rf"g{year}1{st}\.csv$")
        G = geo_from_csv(zf.read(gc)) if gc else geo_from_txt(zf.read(member(zf, rf"g{year}1{st}\.txt$")))
    if mn is None:
        print("NO M-FILE", year, st, "seq", seq); return None
    return em_table(e, zf.read(mn), G, start, year, 1)


def five_year(year, st):
    ls = lookup_for(year, 5)
    if ls is None:
        print("no cached 5-yr lookup", year); return None
    seq, start = ls
    zp = ACS / f"{year}_{st}_5yr_seq{seq}.zip"
    if not zp.exists():
        print("missing 5-yr cache", year, st); return None
    zf = zipfile.ZipFile(zp)
    e = zf.read(member(zf, rf"e{year}5{st}{seq:04d}000\.txt$")); mn = member(zf, rf"m{year}5{st}{seq:04d}000\.txt$")
    if mn is None:
        print("NO 5-yr M-FILE", year, st); return None
    gc = ACS / f"g{year}5{st}.csv"; gt = ACS / f"g{year}5{st}.txt"
    G = geo_from_csv(gc.read_bytes()) if gc.exists() else geo_from_txt(gt.read_bytes())
    return em_table(e, zf.read(mn), G, start, year, 5)


def table_based(year, period):
    p = ACS / f"acsdt{period}y{year}-{TABLE.lower()}.dat"
    if not p.exists():
        print("missing table-based", year, period); return None
    T = pd.read_csv(p, sep="|", dtype=str)
    T = T[T.GEO_ID.str.startswith("0500000US")]
    num = lambda c: pd.to_numeric(T[c], errors="coerce")
    return pd.DataFrame({"county": T.GEO_ID.str[-5:], "workers": num(f"{TABLE}_E001"), "workers_moe": clean_moe(T[f"{TABLE}_M001"]),
                         "in_county": num(f"{TABLE}_E003"), "in_county_moe": clean_moe(T[f"{TABLE}_M003"]), "year": year, "period": period})


def share_moe(num, num_moe, den, den_moe):
    p = num / den
    rad = num_moe ** 2 - p ** 2 * den_moe ** 2
    alt = np.sqrt(num_moe ** 2 + p ** 2 * den_moe ** 2) / den
    return p, np.where(rad >= 0, np.sqrt(np.clip(rad, 0, None)) / den, alt)


def build_moe(counties):
    rows, missing = [], []
    for y in list(range(2005, 2020)):
        for st in STATES:
            try:
                p = one_year(y, st)
                if p is None:
                    missing.append(f"1-yr {y} {st}")
                else:
                    rows.append(p)
            except Exception as e:
                print("1-yr failed", y, st, repr(e)[:160]); missing.append(f"1-yr {y} {st}: {repr(e)[:80]}")
    for y in (2021, 2022, 2023, 2024):
        p = table_based(y, 1)
        rows.append(p) if p is not None else missing.append(f"1-yr {y}")
    for y in range(2009, 2021):
        for st in STATES:
            try:
                p = five_year(y, st)
                if p is None:
                    missing.append(f"5-yr {y} {st}")
                else:
                    rows.append(p)
            except Exception as e:
                print("5-yr failed", y, st, repr(e)[:160]); missing.append(f"5-yr {y} {st}: {repr(e)[:80]}")
    for y in (2021, 2022, 2023):
        p = table_based(y, 5)
        rows.append(p) if p is not None else missing.append(f"5-yr {y}")
    A = pd.concat(rows, ignore_index=True)
    A = A[A.county.isin(counties)].drop_duplicates(["county", "year", "period"])
    A = A[A.workers > 0].copy()
    A["share"], A["share_moe"] = share_moe(A.in_county, A.in_county_moe, A.workers, A.workers_moe)
    A = A.sort_values(["county", "period", "year"]).reset_index(drop=True)
    return A[["county", "year", "period", "workers", "workers_moe", "in_county", "in_county_moe", "share", "share_moe"]], missing


# ------------------------------------------------------------------ tests
def step_tests(A, L, counties):
    one = A[(A.period == 1) & (A.year.between(2005, 2012))]
    full = one.groupby("county").year.nunique(); core = sorted(full[full == 8].index)
    one = one[one.county.isin(core)].merge(L[["county", "year", "lodes_share", "res_workers"]], on=["county", "year"])
    rows = []
    for c, d in one.groupby("county"):
        d = d.set_index("year")
        for y in range(2006, 2013):
            da = d.share[y] - d.share[y - 1]; moe = np.sqrt(d.share_moe[y] ** 2 + d.share_moe[y - 1] ** 2)
            dl = d.lodes_share[y] - d.lodes_share[y - 1]
            rows.append(dict(unit=c, name=counties[c], change=f"{y-1}->{y}", acs_change=da, acs_change_moe=moe,
                             acs_lo=da - moe, acs_hi=da + moe, lodes_change=dl,
                             lodes_outside_acs90=bool(dl < da - moe or dl > da + moe), lodes_drop_ruled_out=bool(dl < da - moe)))
    # pooled series: MOE of a sum = sqrt(sum of squares); share MOE by the ratio formula; LODES pooled weighted by resident workers
    for label, cs in (("POOLED_MO16", [c for c in core if c.startswith("29")]), ("POOLED_ALL21", core)):
        d = one[one.county.isin(cs)].groupby("year").agg(workers=("workers", "sum"), in_county=("in_county", "sum"),
                                                        workers_moe=("workers_moe", lambda s: np.sqrt((s ** 2).sum())),
                                                        in_county_moe=("in_county_moe", lambda s: np.sqrt((s ** 2).sum())),
                                                        lodes_same=("lodes_share", lambda s: (s * one.loc[s.index, "res_workers"]).sum()),
                                                        lodes_res=("res_workers", "sum"))
        d["share"], d["share_moe"] = share_moe(d.in_county, d.in_county_moe, d.workers, d.workers_moe)
        d["lodes_share"] = d.lodes_same / d.lodes_res
        for y in range(2006, 2013):
            da = d.share[y] - d.share[y - 1]; moe = np.sqrt(d.share_moe[y] ** 2 + d.share_moe[y - 1] ** 2)
            dl = d.lodes_share[y] - d.lodes_share[y - 1]
            rows.append(dict(unit=label, name=f"{label} (n={len(cs)})", change=f"{y-1}->{y}", acs_change=da, acs_change_moe=moe,
                             acs_lo=da - moe, acs_hi=da + moe, lodes_change=dl,
                             lodes_outside_acs90=bool(dl < da - moe or dl > da + moe), lodes_drop_ruled_out=bool(dl < da - moe)))
    S = pd.DataFrame(rows)
    levels = one.groupby("county").agg(share_moe_mean=("share_moe", "mean"))
    return S, core, levels


def wls_slope(years, p, moe):
    """WLS of p on year with weights 1/SE^2 (SE = MOE/1.645). Returns slope, sampling-based SE (delta method, treats the
    linear model as exact) and the residual-based SE (classic WLS with dispersion scaling)."""
    se = moe / Z90; w = 1 / se ** 2
    xbar = np.sum(w * years) / np.sum(w); ybar = np.sum(w * p) / np.sum(w)
    sxx = np.sum(w * (years - xbar) ** 2)
    b = np.sum(w * (years - xbar) * (p - ybar)) / sxx; a = ybar - b * xbar
    se_samp = np.sqrt(1 / sxx)
    resid = p - a - b * years; dof = len(p) - 2
    se_resid = np.sqrt(np.sum(w * resid ** 2) / dof / sxx)
    return b, se_samp, se_resid


def slope_tests(A, L, counties):
    one = A[(A.period == 1) & (A.year.between(2010, 2019))]
    rows = []
    for c, d in one.groupby("county"):
        if len(d) < 6:
            continue
        d = d.sort_values("year")
        b, se_s, se_r = wls_slope(d.year.values.astype(float), d.share.values, d.share_moe.values)
        ols = np.polyfit(d.year.values.astype(float), d.share.values, 1)[0]
        l = L[(L.county == c) & (L.year.between(2010, 2019))].sort_values("year")
        bl = np.polyfit(l.year.values.astype(float), l.lodes_share.values, 1)[0]
        l2 = l[l.year >= 2011]
        bl11 = np.polyfit(l2.year.values.astype(float), l2.lodes_share.values, 1)[0] if len(l2) >= 5 else np.nan
        rows.append(dict(county=c, name=counties[c], n_years=len(d), acs_slope_wls=b, acs_slope_ols=ols, se_sampling=se_s, se_residual=se_r,
                         ci90_lo=b - Z90 * se_s, ci90_hi=b + Z90 * se_s, ci90_lo_resid=b - Z90 * se_r, ci90_hi_resid=b + Z90 * se_r,
                         lodes_slope=bl, lodes_slope_2011_19=bl11,
                         lodes_outside_ci90=bool(bl < b - Z90 * se_s or bl > b + Z90 * se_s),
                         lodes_decline_ruled_out=bool(bl < b - Z90 * se_s),
                         lodes_decline_ruled_out_resid=bool(bl < b - Z90 * se_r),
                         lodes1119_decline_ruled_out=bool(bl11 < b - Z90 * se_s) if not np.isnan(bl11) else np.nan))
    # pooled series 2010-2019 (same construction as in step_tests)
    core = sorted(one.groupby("county").year.nunique().pipe(lambda s: s[s == 10]).index)
    onel = one[one.county.isin(core)].merge(L[["county", "year", "lodes_share", "res_workers"]], on=["county", "year"])
    pooled = []
    for label, cs in (("POOLED_MO16", [c for c in core if c.startswith("29")]), ("POOLED_ALL21", core)):
        d = onel[onel.county.isin(cs)]
        d = d.groupby("year").agg(workers=("workers", "sum"), in_county=("in_county", "sum"),
                                  workers_moe=("workers_moe", lambda s: np.sqrt((s ** 2).sum())),
                                  in_county_moe=("in_county_moe", lambda s: np.sqrt((s ** 2).sum())),
                                  lodes_same=("lodes_share", lambda s: (s * onel.loc[s.index, "res_workers"]).sum()),
                                  lodes_res=("res_workers", "sum")).reset_index()
        d["share"], d["share_moe"] = share_moe(d.in_county, d.in_county_moe, d.workers, d.workers_moe)
        d["lodes_share"] = d.lodes_same / d.lodes_res
        b, se_s, se_r = wls_slope(d.year.values.astype(float), d.share.values, d.share_moe.values)
        bl = np.polyfit(d.year.values.astype(float), d.lodes_share.values, 1)[0]
        d2 = d[d.year >= 2011]; bl11 = np.polyfit(d2.year.values.astype(float), d2.lodes_share.values, 1)[0]
        pooled.append(dict(unit=label, n_counties=len(cs), acs_slope_wls=b, se_sampling=se_s, se_residual=se_r, ci90_lo=b - Z90 * se_s, ci90_hi=b + Z90 * se_s,
                           lodes_slope=bl, lodes_slope_2011_19=bl11, lodes_decline_ruled_out=bool(bl < b - Z90 * se_s),
                           lodes1119_decline_ruled_out=bool(bl11 < b - Z90 * se_s), share_moe_mean=d.share_moe.mean()))
    return pd.DataFrame(rows), pd.DataFrame(pooled)


def md_table(df, fmt="{:.3f}"):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else fmt.format(v))
            elif isinstance(v, (bool, np.bool_)):
                cells.append("yes" if v else "no")
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def write_report(A, S, core, levels, T, PT, missing, counties):
    o = ["# ACS B08007 margins of error and tests against LODES\n",
         "Generated by `scripts/09d_acs_b08007_moe.py`. All MOEs are the published 90 % margins; the share MOE uses the Census proportion formula "
         "(ratio form when the radicand is negative). SE = MOE / 1.645.\n"]
    cov = A.groupby("period").agg(years=("year", "nunique"), first=("year", "min"), last=("year", "max"), rows=("county", "size"),
                                  rows_with_moe=("share_moe", lambda s: int(s.notna().sum()))).reset_index()
    o.append("## MOE coverage\n"); o.append(md_table(cov, "{:.0f}")); o.append("")
    o.append("Files with no usable m-file / MOE columns: " + (", ".join(missing) if missing else "none") + ".\n")
    lv = A[(A.period == 1) & A.county.isin(core)].groupby("county").agg(share_2012=("share", lambda s: s.iloc[7] if len(s) > 7 else np.nan),
                                                                         mean_share_moe=("share_moe", "mean"), workers_2012=("workers", lambda s: s.iloc[7] if len(s) > 7 else np.nan))
    lv = lv.reset_index(); lv["name"] = lv.county.map(counties); lv["mean_share_moe_pts"] = lv.mean_share_moe * 100
    o.append("Typical 1-year MOE on the in-county share (percentage points, mean over 2005-2024) for the 21 1-year counties:\n")
    o.append(md_table(lv[["county", "name", "mean_share_moe_pts"]], "{:.2f}")); o.append("")
    five = A[A.period == 5]
    o.append(f"5-year share MOE (pts): median {five.share_moe.median()*100:.2f}, 90th percentile {five.share_moe.quantile(.9)*100:.2f}, "
             f"max {five.share_moe.max()*100:.2f} ({counties[five.loc[five.share_moe.idxmax(), 'county']]}, {int(five.loc[five.share_moe.idxmax(), 'year'])}).\n")

    # (a)
    o.append("## (a) Year-to-year steps 2005-2012: ACS change +/- 90 % MOE vs the LODES change\n")
    cty = S[~S.unit.str.startswith("POOLED")]
    summ = cty.groupby("change").agg(n=("unit", "size"), acs_mean=("acs_change", "mean"), acs_moe_median=("acs_change_moe", "median"),
                                     lodes_mean=("lodes_change", "mean"), lodes_outside_acs90=("lodes_outside_acs90", "sum"),
                                     lodes_drop_ruled_out=("lodes_drop_ruled_out", "sum")).reset_index()
    for c in ("acs_mean", "acs_moe_median", "lodes_mean"):
        summ[c] *= 100
    summ = summ.rename(columns={"acs_mean": "ACS mean chg (pts)", "acs_moe_median": "median MOE of chg (pts)", "lodes_mean": "LODES mean chg (pts)",
                                "lodes_outside_acs90": "LODES chg outside ACS 90% CI (counties)", "lodes_drop_ruled_out": "LODES drop below ACS lower bound (counties)"})
    o.append(md_table(summ, "{:.2f}")); o.append("")
    P = S[S.unit.str.startswith("POOLED")].copy()
    for c in ("acs_change", "acs_change_moe", "acs_lo", "acs_hi", "lodes_change"):
        P[c] *= 100
    o.append("Pooled series (estimates summed over counties, MOE of the sum = sqrt(sum of squared MOEs), share MOE by the ratio formula; LODES weighted by resident workers), percentage points:\n")
    o.append(md_table(P[["name", "change", "acs_change", "acs_change_moe", "acs_lo", "acs_hi", "lodes_change", "lodes_outside_acs90", "lodes_drop_ruled_out"]], "{:.2f}")); o.append("")
    det = cty[cty.change.isin(["2006->2007", "2008->2009"])].copy()
    for c in ("acs_change", "acs_change_moe", "lodes_change"):
        det[c] *= 100
    det = det.pivot(index="name", columns="change", values=["acs_change", "acs_change_moe", "lodes_change", "lodes_drop_ruled_out"])
    det.columns = [f"{a} {b}" for a, b in det.columns]; det = det.reset_index()
    o.append("County detail for the two LODES step years (pts):\n"); o.append(md_table(det, "{:.2f}")); o.append("")
    g07 = summ[summ.change == "2006->2007"].iloc[0]; g09 = summ[summ.change == "2008->2009"].iloc[0]
    p07 = P[(P.unit == "POOLED_MO16") & (P.change == "2006->2007")].iloc[0]; p09 = P[(P.unit == "POOLED_MO16") & (P.change == "2008->2009")].iloc[0]
    o.append(f"**Result (a).** 2006->2007: in {int(g07['LODES drop below ACS lower bound (counties)'])} of {int(g07.n)} counties the LODES drop is larger than the lower bound of the ACS "
             f"90 % interval for the change (ACS rules out a drop that large); the LODES change lies outside the ACS interval (either side) in {int(g07['LODES chg outside ACS 90% CI (counties)'])}. "
             f"2008->2009: {int(g09['LODES drop below ACS lower bound (counties)'])} of {int(g09.n)} ruled out, {int(g09['LODES chg outside ACS 90% CI (counties)'])} outside. "
             f"Pooled 16 Missouri counties: 2006->07 ACS change {p07.acs_change:+.2f} +/- {p07.acs_change_moe:.2f} pts (interval {p07.acs_lo:+.2f} to {p07.acs_hi:+.2f}) vs LODES {p07.lodes_change:+.2f} "
             f"({'ruled out' if p07.lodes_drop_ruled_out else 'not ruled out'}); 2008->09 ACS {p09.acs_change:+.2f} +/- {p09.acs_change_moe:.2f} ({p09.acs_lo:+.2f} to {p09.acs_hi:+.2f}) vs LODES "
             f"{p09.lodes_change:+.2f} ({'ruled out' if p09.lodes_drop_ruled_out else 'not ruled out'}).\n")

    # (b)
    o.append("## (b) 2010-2019 trend: WLS slope of the ACS 1-year share (weights 1/SE^2) vs the LODES OLS slope\n")
    Tt = T.copy()
    for c in ("acs_slope_wls", "acs_slope_ols", "se_sampling", "se_residual", "ci90_lo", "ci90_hi", "lodes_slope", "lodes_slope_2011_19"):
        Tt[c] *= 100
    o.append("Percentage points per year. `se_sampling` is the delta-method SE from the published MOEs alone (treats the linear trend as exact); "
             "`se_residual` is the classic WLS SE scaled by the residual dispersion (8 d.o.f.). The 90 % interval shown uses `se_sampling`; "
             "`lodes_slope_2011_19` drops 2010 because of the 2010->11 LODES discontinuity in several Missouri counties.\n")
    o.append(md_table(Tt[["county", "name", "n_years", "acs_slope_wls", "se_sampling", "se_residual", "ci90_lo", "ci90_hi", "lodes_slope", "lodes_slope_2011_19",
                          "lodes_outside_ci90", "lodes_decline_ruled_out", "lodes_decline_ruled_out_resid", "lodes1119_decline_ruled_out"]], "{:.3f}")); o.append("")
    n = len(T)
    o.append(f"**Result (b).** ACS WLS slope mean {Tt.acs_slope_wls.mean():+.3f} pts/yr (median {Tt.acs_slope_wls.median():+.3f}); LODES slope mean {Tt.lodes_slope.mean():+.3f} "
             f"(2011-19: {Tt.lodes_slope_2011_19.mean():+.3f}). Median sampling SE of the ACS slope {Tt.se_sampling.median():.3f} pts/yr, median residual SE {Tt.se_residual.median():.3f}. "
             f"ACS rules out a decline as steep as the LODES 2010-19 slope in {int(T.lodes_decline_ruled_out.sum())}/{n} counties with the sampling SE "
             f"({int(T.lodes_decline_ruled_out_resid.sum())}/{n} with the residual SE); LODES slope outside the ACS 90 % interval either side in {int(T.lodes_outside_ci90.sum())}/{n}; "
             f"using the LODES 2011-19 slope instead, {int(T.lodes1119_decline_ruled_out.fillna(False).astype(bool).sum())}/{n} ruled out. "
             f"ACS slope significantly negative (90 %, sampling SE) in {int((T.ci90_hi < 0).sum())}/{n} counties and significantly positive in {int((T.ci90_lo > 0).sum())}/{n}.\n")

    Pp = PT.copy()
    for c in ("acs_slope_wls", "se_sampling", "se_residual", "ci90_lo", "ci90_hi", "lodes_slope", "lodes_slope_2011_19", "share_moe_mean"):
        Pp[c] *= 100
    o.append("Pooled series 2010-2019 (pts/yr; `share_moe_mean` = mean 90 % MOE of the pooled share, pts):\n")
    o.append(md_table(Pp, "{:.3f}")); o.append("")
    pm = Pp[Pp.unit == "POOLED_MO16"].iloc[0]
    o.append(f"Pooled 16 Missouri counties: ACS slope {pm.acs_slope_wls:+.3f} +/- {Z90*pm.se_sampling:.3f} pts/yr (90 %, sampling SE; interval {pm.ci90_lo:+.3f} to {pm.ci90_hi:+.3f}) "
             f"vs LODES {pm.lodes_slope:+.3f} (2011-19: {pm.lodes_slope_2011_19:+.3f}); LODES decline {'ruled out' if pm.lodes_decline_ruled_out else 'not ruled out'}.\n")

    # (c)
    o.append("## (c) What the MOEs allow us to say\n")
    med_moe = lv.mean_share_moe_pts.median(); big3 = lv.nsmallest(3, "mean_share_moe_pts").name.tolist()
    o.append(f"Sampling error. The published 90 % MOE on a county's 1-year in-county share is {med_moe:.1f} points for the median 1-year county "
             f"(range {lv.mean_share_moe_pts.min():.1f}-{lv.mean_share_moe_pts.max():.1f}; smallest in {', '.join(big3)}), so a single county's year-to-year change carries a 90 % half-width of "
             f"{(cty.acs_change_moe*100).quantile(.1):.1f}-{(cty.acs_change_moe*100).quantile(.9):.1f} points and cannot, on its own, separate a 1-3 point step from noise; the per-county counts in (a) "
             f"({int(g07['LODES drop below ACS lower bound (counties)'])}/21 in 2007, {int(g09['LODES drop below ACS lower bound (counties)'])}/21 in 2009) therefore understate what the survey says. "
             f"What the MOEs do allow: (1) pooling the 16 Missouri counties cuts the MOE of the pooled share to about {P[P.unit=='POOLED_MO16'].acs_change_moe.iloc[0]/np.sqrt(2):.2f} points, and the pooled ACS change in "
             f"2006->07 ({p07.acs_change:+.2f} +/- {p07.acs_change_moe:.2f}) and 2008->09 ({p09.acs_change:+.2f} +/- {p09.acs_change_moe:.2f}) excludes the {-p07.lodes_change:.1f} and {-p09.lodes_change:.1f} point LODES drops in the same counties, "
             f"so neither LODES step is present in the residence-based survey; (2) over 2010-2019 the pooled Missouri ACS slope is {pm.acs_slope_wls:+.2f} +/- {Z90*pm.se_sampling:.2f} pts/yr against a LODES slope of "
             f"{pm.lodes_slope:+.2f}, and at the county level the ACS interval excludes a decline as steep as LODES in {int(T.lodes_decline_ruled_out.sum())} of 21 counties (median sampling SE of a county slope "
             f"{Tt.se_sampling.median():.2f} pts/yr, so only the larger counties and the steepest LODES declines are individually decisive). What they do not allow: a county-level verdict on steps of 1-3 points; "
             f"any statement about counties under 65,000 before the 5-year series; and inference from the 5-year series as if its windows were independent (median 5-year share MOE "
             f"{five.share_moe.median()*100:.1f} pts, but consecutive windows share 80 % of their sample, so adjacent 5-year changes are far more uncertain than the MOEs of two windows imply). "
             "MOEs also cover sampling error only, not the non-sampling differences in universe, place-of-work reporting and work-from-home treatment that produce the 15-20 point level gap between the two series.\n")
    (EXT / "ACS_B08007_MOE_TESTS.md").write_text("\n".join(o))


def main():
    counties = ext.all_counties()
    A, missing = build_moe(counties)
    A.to_csv(EXT / "acs_b08007_county_year_moe.csv", index=False)
    L = pd.read_csv(EXT / "lodes_county_samecounty_year.csv", dtype={"county": str}).rename(columns={"same_county_share": "lodes_share"})
    S, core, levels = step_tests(A, L, counties)
    S.to_csv(EXT / "acs_vs_lodes_step_tests.csv", index=False)
    T, PT = slope_tests(A, L, counties)
    T.to_csv(EXT / "acs_vs_lodes_slope_tests.csv", index=False)
    PT.to_csv(EXT / "acs_vs_lodes_slope_tests_pooled.csv", index=False)
    write_report(A, S, core, levels, T, PT, missing, counties)
    print("missing:", missing)
    g = A[(A.county == "29077") & (A.period == 1)]
    print(g[["year", "workers", "workers_moe", "in_county", "in_county_moe", "share", "share_moe"]].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
