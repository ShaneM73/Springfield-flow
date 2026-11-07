"""External control series for every metro (free, key-less sources), to triangulate the LODES findings.

Usage: python scripts/08_external_controls.py [fetch|build|all]   (default all)   -> outputs/external/

Sources (raw copies in Data/external/, untouched)
  QCEW  : BLS annual averages by county, private ownership (own_code 5) and total (0), all industries,
          https://data.bls.gov/cew/data/api/{year}/a/area/{fips}.csv, 2002-2024.
  ACS WFH: table B08301 (means of transportation; _021 = worked from home) 1-year, county level:
          2010-2019 from the sequence-based summary files (1_year_by_state zips, MO/KS/IL), 2021-2024 from the
          table-based summary files; 2020 has no standard 1-year release. 5-year 2023 for small counties.
  ACS county-to-county commuting flows: 2006-10, 2011-15, 2016-20 tables (table1.xlsx).
  LODES statewide check: resident workers by county and year from the MO/KS/IL main files already in parquet/
          (is the 2006 residence anomaly Missouri-only?).

Outputs
  external/qcew_county_year.csv, external/acs_wfh_county_year.csv, external/acs_flows_metro.csv,
  external/lodes_residence_anomaly_statewide.csv, external/<metro>_controls.csv (merged metro series),
  external/figures/controls_small_multiples.png
"""
import io
import re
import sys
import time
import urllib.request
import zipfile

import duckdb
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import OUT, RAW, PARQUET, METROS, YEARS, STATE_FIPS, metro_def

EXT_RAW = RAW / "external"; EXT = OUT / "external"
ST_NAMES = {"mo": "Missouri", "ks": "Kansas", "il": "Illinois"}
UA = {"User-Agent": "springfield-flow-research/1.0"}


def get(url, dest=None, tries=4):
    if dest is not None and dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                data = r.read()
            if dest is not None:
                dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
            return data
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return None
            time.sleep(2 * (k + 1))
    return None


def all_counties():
    cs = {}
    for k in METROS:
        try:
            cs.update(metro_def(k)["counties"])
        except Exception:
            pass
    return cs


# ------------------------------------------------------------------ QCEW
def fetch_qcew(counties):
    rows = []
    for fips in sorted(counties):
        for y in YEARS:
            d = get(f"https://data.bls.gov/cew/data/api/{y}/a/area/{fips}.csv", EXT_RAW / "qcew" / f"{fips}_{y}.csv")
            if d is None:
                continue
            df = pd.read_csv(io.BytesIO(d), dtype={"area_fips": str})
            df = df[(df.industry_code == "10") & (df.own_code.isin([0, 5]))]
            for r in df.itertuples():
                rows.append(dict(county=fips, year=y, own="total" if r.own_code == 0 else "private", estabs=r.annual_avg_estabs,
                                 employment=r.annual_avg_emplvl, wages=r.total_annual_wages))
        print("qcew", fips, flush=True)
    Q = pd.DataFrame(rows); Q.to_csv(EXT / "qcew_county_year.csv", index=False); return Q


def fetch_qcew_zips(counties, years=range(2002, 2014)):
    """QCEW annual averages before the per-area API (2014+): download each year's annual_by_area zip, keep the county files."""
    rows = []
    for y in years:
        have = [EXT_RAW / "qcew" / f"{f}_{y}.csv" for f in counties]
        if not all(h.exists() for h in have):
            z = get(f"https://data.bls.gov/cew/data/files/{y}/csv/{y}_annual_by_area.zip", None)
            if z is None:
                print("qcew zip missing", y); continue
            zf = zipfile.ZipFile(io.BytesIO(z))
            for n in zf.namelist():
                m = re.search(r"/(\d{5}) ", n) or re.search(r"\.annual (\d{5}) ", n) or re.search(r"(\d{5})", n.split("/")[-1])
                if m and m.group(1) in counties:
                    (EXT_RAW / "qcew" / f"{m.group(1)}_{y}.csv").write_bytes(zf.read(n))
            print("qcew zip", y, flush=True)
        for fips in sorted(counties):
            f = EXT_RAW / "qcew" / f"{fips}_{y}.csv"
            if not f.exists():
                continue
            df = pd.read_csv(f, dtype={"area_fips": str, "industry_code": str})
            df = df[(df.industry_code == "10") & (df.own_code.isin([0, 5]))]
            est_col = "annual_avg_estabs" if "annual_avg_estabs" in df.columns else ("annual_avg_estabs_count" if "annual_avg_estabs_count" in df.columns else None)
            for _, r in df.iterrows():
                rows.append(dict(county=fips, year=y, own="total" if r.own_code == 0 else "private", estabs=r[est_col] if est_col else np.nan,
                                 employment=r.annual_avg_emplvl, wages=r.total_annual_wages))
    Q = pd.DataFrame(rows)
    old_f = EXT / "qcew_county_year.csv"
    if old_f.exists():
        Q = pd.concat([pd.read_csv(old_f, dtype={"county": str}), Q]).drop_duplicates(["county", "year", "own"], keep="last")
    Q.sort_values(["county", "year", "own"]).to_csv(old_f, index=False); return Q


def acs5_seq(year, st):
    """B08301 from the sequence-based 5-year summary file (All_Geographies_Not_Tracts_Block_Groups) for one state."""
    base = f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}"
    look = get(f"{base}/documentation/user_tools/ACS_5yr_Seq_Table_Number_Lookup.txt", EXT_RAW / "acs" / f"lookup5_{year}.txt")
    if not look:
        return None
    L = pd.read_csv(io.BytesIO(look), dtype=str, encoding="latin1")
    L.columns = [c.strip().lower().replace(" ", "_") for c in L.columns]
    tid = [c for c in L.columns if "table_id" in c][0]; seqc = [c for c in L.columns if "sequence" in c][0]
    startc = [c for c in L.columns if "start" in c][0]
    t = L[L[tid].str.strip() == "B08301"]
    seq = int(t[seqc].iloc[0]); start = int(float(t[startc].dropna().iloc[0]))
    z = get(f"{base}/data/5_year_by_state/{ST_NAMES[st]}_All_Geographies_Not_Tracts_Block_Groups.zip", None)
    if not z:
        return None
    zf = zipfile.ZipFile(io.BytesIO(z)); names = zf.namelist()
    ef = [n for n in names if re.search(rf"e{year}5{st}{seq:04d}000\.txt$", n)][0]
    E = pd.read_csv(zf.open(ef), header=None, dtype=str)
    tot = pd.to_numeric(E[start - 1], errors="coerce"); wfh = pd.to_numeric(E[start - 1 + 20], errors="coerce")
    gf = [n for n in names if re.search(rf"g{year}5{st}\.csv$", n)]
    if gf:
        G = pd.read_csv(zf.open(gf[0]), header=None, dtype=str, encoding="latin1")[[4, 48]].rename(columns={4: "logrecno", 48: "geoid"})
    else:
        gtxt = [n for n in names if re.search(rf"g{year}5{st}\.txt$", n)][0]
        lines = zf.open(gtxt).read().decode("latin1").splitlines()
        G = pd.DataFrame({"logrecno": [l[13:20] for l in lines], "geoid": [l[178:218].strip() for l in lines]})
    df = pd.DataFrame({"logrecno": E[5], "workers": tot, "wfh": wfh}).merge(G, on="logrecno")
    df = df[df.geoid.str.startswith("05000US")]; df["county"] = df.geoid.str[-5:]
    return df[["county", "workers", "wfh"]].assign(year=year, src="acs5")


def fetch_acs5(counties, years=(2014, 2019)):
    parts = []
    for y in years:
        for st in ("mo", "ks", "il"):
            try:
                p = acs5_seq(y, st)
                if p is not None:
                    parts.append(p); print("acs5 seq", y, st, len(p), flush=True)
            except Exception as e:
                print("acs5 seq failed", y, st, repr(e)[:120], flush=True)
    A = pd.concat(parts, ignore_index=True); A = A[A.county.isin(counties)].copy(); A["wfh_share"] = A.wfh / A.workers
    f = EXT / "acs_wfh_county_year.csv"
    if f.exists():
        A = pd.concat([pd.read_csv(f, dtype={"county": str}), A]).drop_duplicates(["county", "year", "src"], keep="last")
    A.sort_values(["county", "src", "year"]).to_csv(f, index=False); return A


def county_tail():
    """Share of each work county's jobs (MO residents, JT02) held by workers living > 100 miles away, by year."""
    con = duckdb.connect(); rows = []
    for k in METROS:
        bf = OUT / k / "blockflows.parquet"
        if not bf.exists():
            continue
        C = ",".join(f"'{c}'" for c in metro_def(k)["counties"])
        df = con.execute(f"""SELECT substr(w_geocode,1,5) county, year,
                                    sum(CASE WHEN miles > 100 THEN S000 ELSE 0 END) / sum(S000) tail_share,
                                    sum(CASE WHEN miles <= 5 THEN S000 ELSE 0 END) / sum(S000) near_share, sum(S000) jobs
                             FROM '{bf}' WHERE jt='JT02' AND miles IS NOT NULL AND substr(w_geocode,1,5) IN ({C})
                             GROUP BY 1, 2""").df()
        df["metro"] = k; rows.append(df)
    T = pd.concat(rows).drop_duplicates(["county", "year"]).sort_values(["county", "year"])
    T.to_csv(EXT / "lodes_county_distance_tail.csv", index=False); return T


# ------------------------------------------------------------------ ACS work-from-home, county, 1-year
def acs_seq(year, st):
    """B08301 from the sequence-based 1-year summary file for one state."""
    base = f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}"
    look_urls = [f"{base}/documentation/user_tools/ACS_1yr_Seq_Table_Number_Lookup.txt",
                 f"{base}/documentation/1_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt",
                 f"{base}/documentation/user_tools/ACS_1yr_Seq_Table_Number_Lookup.csv"]
    look = None
    for u in look_urls:
        look = get(u, EXT_RAW / "acs" / f"lookup_{year}.txt")
        if look:
            break
    if not look:
        return None
    L = pd.read_csv(io.BytesIO(look), dtype=str, encoding="latin1")
    L.columns = [c.strip().lower().replace(" ", "_") for c in L.columns]
    tid = [c for c in L.columns if "table_id" in c][0]; seqc = [c for c in L.columns if "sequence" in c][0]
    startc = [c for c in L.columns if "start" in c][0]
    t = L[L[tid].str.strip() == "B08301"]
    seq = int(t[seqc].iloc[0]); start = int(float(t[startc].dropna().iloc[0]))
    z = get(f"{base}/data/1_year_by_state/{ST_NAMES[st]}_All_Geographies.zip", EXT_RAW / "acs" / f"{year}_{st}_1yr.zip")
    if not z:
        return None
    zf = zipfile.ZipFile(io.BytesIO(z))
    names = zf.namelist()
    ef = [n for n in names if re.search(rf"e{year}1{st}{seq:04d}000\.txt$", n)][0]
    gf = [n for n in names if re.search(rf"g{year}1{st}\.csv$", n)]
    E = pd.read_csv(zf.open(ef), header=None, dtype=str)
    E = E.rename(columns={5: "logrecno"})
    # 'start' is the 1-based column of the table's first cell in the e-file (6 id columns precede the data)
    tot = pd.to_numeric(E[start - 1], errors="coerce"); wfh = pd.to_numeric(E[start - 1 + 20], errors="coerce")
    if gf:
        G = pd.read_csv(zf.open(gf[0]), header=None, dtype=str, encoding="latin1")
        G = G[[4, 48]].rename(columns={4: "logrecno", 48: "geoid"})
    else:  # fixed-width geography file
        gtxt = [n for n in names if re.search(rf"g{year}1{st}\.txt$", n)][0]
        lines = zf.open(gtxt).read().decode("latin1").splitlines()
        G = pd.DataFrame({"logrecno": [l[13:20] for l in lines], "geoid": [l[178:218].strip() for l in lines]})
    df = pd.DataFrame({"logrecno": E.logrecno, "workers": tot, "wfh": wfh}).merge(G, on="logrecno")
    df = df[df.geoid.str.startswith("05000US")]
    df["county"] = df.geoid.str[-5:]
    return df[["county", "workers", "wfh"]].assign(year=year, src="acs1")


def acs_table_based(year, period):
    d = get(f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}/table-based-SF/data/{period}YRData/acsdt{period}y{year}-b08301.dat",
            EXT_RAW / "acs" / f"acsdt{period}y{year}-b08301.dat")
    if not d:
        return None
    T = pd.read_csv(io.BytesIO(d), sep="|", dtype=str)
    T = T[T.GEO_ID.str.startswith("0500000US")]
    return pd.DataFrame({"county": T.GEO_ID.str[-5:], "workers": pd.to_numeric(T.B08301_E001, errors="coerce"),
                         "wfh": pd.to_numeric(T.B08301_E021, errors="coerce"), "year": year, "src": f"acs{period}"})


def fetch_acs_wfh(counties):
    parts = []
    for y in range(2010, 2020):
        for st in ("mo", "ks", "il"):
            try:
                p = acs_seq(y, st)
                if p is not None:
                    parts.append(p); print("acs1 seq", y, st, len(p), flush=True)
            except Exception as e:
                print("acs1 seq failed", y, st, repr(e)[:120], flush=True)
    for y in range(2021, 2025):
        p = acs_table_based(y, 1)
        if p is not None:
            parts.append(p); print("acs1 table-based", y, len(p), flush=True)
    for y in (2022, 2023):
        p = acs_table_based(y, 5)
        if p is not None:
            parts.append(p); print("acs5 table-based", y, len(p), flush=True)
    A = pd.concat(parts, ignore_index=True)
    A = A[A.county.isin(counties)].copy()
    A["wfh_share"] = A.wfh / A.workers
    A.to_csv(EXT / "acs_wfh_county_year.csv", index=False); return A


# ------------------------------------------------------------------ ACS county-to-county flows
FLOW_URLS = {"2006-2010": "https://www2.census.gov/programs-surveys/demo/tables/metro-micro/2010/commuting-employment-2010/table1.xlsx",
             "2011-2015": "https://www2.census.gov/programs-surveys/demo/tables/metro-micro/2015/commuting-flows-2015/table1.xlsx",
             "2016-2020": "https://www2.census.gov/programs-surveys/demo/tables/metro-micro/2020/commuting-flows-2020/table1.xlsx"}


def fetch_acs_flows():
    out = []
    for per, u in FLOW_URLS.items():
        d = get(u, EXT_RAW / "acs_flows" / f"table1_{per}.xlsx")
        if not d:
            print("flows missing", per); continue
        X = pd.read_excel(io.BytesIO(d), header=None, dtype=str)
        # layout: 0 residence state (2), 1 residence county (3), 2 workplace state (3 digits; US states = 0 + fips),
        # 3 workplace county (3), 4 workers, 5 MOE, then names. Data rows start where col 0 is a 2-digit code.
        X = X[X[0].astype(str).str.fullmatch(r"\d{2}") & X[1].astype(str).str.fullmatch(r"\d{3}")]
        # 2010 table: codes in cols 2-3 and counts in 4-5; 2015/2020 tables: names in 2-3, codes in 4-5, counts in 8-9
        ws, wc, nw, nm = (2, 3, 4, 5) if X[2].astype(str).str.fullmatch(r"\d{3}").mean() > 0.9 else (4, 5, 8, 9)
        X = X[X[ws].astype(str).str.fullmatch(r"\d{3}")]                   # drop foreign workplaces
        res = X[0] + X[1]; wk = X[ws].str[-2:] + X[wc].astype(str).str.zfill(3)
        F = pd.DataFrame({"period": per, "h_cty": res.values, "w_cty": wk.values,
                          "workers": pd.to_numeric(X[nw].astype(str).str.replace(",", ""), errors="coerce").values,
                          "moe": pd.to_numeric(X[nm].astype(str).str.replace(",", ""), errors="coerce").values})
        out.append(F[F.workers.notna()])
        print("flows", per, len(F), flush=True)
    FL = pd.concat(out, ignore_index=True); FL.to_csv(EXT / "acs_county_flows_raw.csv", index=False); return FL


# ------------------------------------------------------------------ LODES statewide residence check
def lodes_statewide():
    con = duckdb.connect(); rows = []
    for st in ("mo", "ks", "il"):
        f = str(PARQUET / st / "od" / f"{st}_od_main_JT02_*.parquet")
        df = con.execute(f"""SELECT regexp_extract(filename, '_(\\d{{4}})\\.parquet$', 1)::INT AS yr, substr(h_geocode,1,5) AS county, sum(S000) AS res_workers
                             FROM read_parquet('{f}', filename=true) GROUP BY 1, 2""").df().rename(columns={"yr": "year"})
        df["state"] = st; rows.append(df)
    R = pd.concat(rows).sort_values(["county", "year"])
    R["nb_mean"] = R.groupby("county").res_workers.transform(lambda s: (s.shift(1) + s.shift(-1)) / 2)
    R["dev_pct"] = (R.res_workers - R.nb_mean) / R.nb_mean
    R.to_csv(EXT / "lodes_residence_statewide.csv", index=False)
    S = (R[R.res_workers >= 2000].groupby(["state", "year"]).dev_pct
         .agg(n=lambda s: s.notna().sum(), share_abs_gt10=lambda s: (s.abs() > 0.10).mean(), mean_abs=lambda s: s.abs().mean(), sd=lambda s: s.std()).reset_index())
    S.to_csv(EXT / "lodes_residence_anomaly_statewide.csv", index=False)
    return S


# ------------------------------------------------------------------ merge per metro
def build(counties):
    Q = pd.read_csv(EXT / "qcew_county_year.csv", dtype={"county": str})
    A = pd.read_csv(EXT / "acs_wfh_county_year.csv", dtype={"county": str}) if (EXT / "acs_wfh_county_year.csv").exists() else None
    FL = pd.read_csv(EXT / "acs_county_flows_raw.csv", dtype={"h_cty": str, "w_cty": str}) if (EXT / "acs_county_flows_raw.csv").exists() else None
    frows = []
    for k in METROS:
        try:
            M = metro_def(k)
        except Exception:
            continue
        C = set(M["counties"])
        V = pd.read_csv(OUT / k / "tables" / "volumes_county_year.csv"); V = V[V.jt == "JT02"].set_index("year")
        q = Q[Q.county.isin(C)].groupby(["year", "own"]).employment.sum().unstack()
        out = pd.DataFrame(index=YEARS)
        out["lodes_jt02_jobs"] = V.msa_jobs_total; out["qcew_private_emp"] = q.get("private"); out["qcew_total_emp"] = q.get("total")
        out["lodes_in_commuters"] = V.inflow_mo + V.inflow_aux; out["lodes_self_containment"] = V.self_contain_res
        if A is not None:
            a = A[A.county.isin(C) & (A.src == "acs1")].groupby("year")[["workers", "wfh"]].sum()
            out["acs1_wfh_share"] = (a.wfh / a.workers)
            out["acs1_counties_covered"] = A[A.county.isin(C) & (A.src == "acs1")].groupby("year").county.nunique()
            a5 = A[A.county.isin(C) & (A.src == "acs5")].groupby("year")[["workers", "wfh"]].sum()
            out["acs5_wfh_share"] = (a5.wfh / a5.workers)
        out.index.name = "year"; out.to_csv(EXT / f"{k}_controls.csv")
        if FL is not None:
            for per, g in FL.groupby("period"):
                hin, win = g.h_cty.isin(C), g.w_cty.isin(C)
                lw = g[hin & win].workers.sum(); res = g[hin].workers.sum(); jobs = g[win].workers.sum()
                yrs = [int(per[:4]) + i for i in range(5)]
                lv = V.loc[[y for y in yrs if y in V.index]]
                frows.append(dict(metro=k, period=per, acs_live_work=lw, acs_resident_workers=res, acs_jobs=jobs,
                                  acs_self_containment=lw / res, acs_in_commuters=jobs - lw, acs_in_share=(jobs - lw) / jobs,
                                  lodes_self_containment=lv.self_contain_res.mean(), lodes_in_share=((lv.inflow_mo + lv.inflow_aux) / lv.msa_jobs_total).mean(),
                                  lodes_jobs=lv.msa_jobs_total.mean()))
    if frows:
        pd.DataFrame(frows).to_csv(EXT / "acs_flows_metro.csv", index=False)
    # figure: LODES vs QCEW private employment (indexed 2002 = 100) and ACS WFH share
    ks = [k for k in METROS if (EXT / f"{k}_controls.csv").exists()]
    fig, axes = plt.subplots(2, 4, figsize=(13, 6), sharex=True)
    for ax, k in zip(axes.ravel(), ks):
        o = pd.read_csv(EXT / f"{k}_controls.csv").set_index("year")
        ax.plot(o.index, o.lodes_jt02_jobs / o.lodes_jt02_jobs.iloc[0] * 100, color="#2a78d6", lw=2, label="LODES JT02 jobs")
        ax.plot(o.index, o.qcew_private_emp / o.qcew_private_emp.iloc[0] * 100, color="#eb6834", lw=2, label="QCEW private employment")
        ax.set_title(METROS[k]["name"] + " (2002 = 100)", loc="left", fontsize=9)
        for yr in (2008, 2020): ax.axvline(yr, color="#52514e", lw=0.7, ls=":")
    h, l = axes[0, 0].get_legend_handles_labels(); fig.legend(h, l, loc="lower center", ncol=2, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.06, 1, 1)); (EXT / "figures").mkdir(exist_ok=True)
    fig.savefig(EXT / "figures" / "lodes_vs_qcew.png", dpi=200); plt.close(fig)
    if A is not None:
        fig, ax = plt.subplots(figsize=(7, 3.8))
        pal = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
        for i, k in enumerate(ks):
            o = pd.read_csv(EXT / f"{k}_controls.csv").set_index("year")
            s = o.acs1_wfh_share.dropna(); ax.plot(s.index, s.values, color=pal[i % 8], marker="o", ms=3, lw=1.6, label=METROS[k]["name"])
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0)); ax.set_title("ACS 1-year: share of workers who worked from home (metro counties with 1-year data)", loc="left", fontsize=9)
        ax.legend(frameon=False, fontsize=7, ncol=2); fig.tight_layout(); fig.savefig(EXT / "figures" / "acs_wfh_share.png", dpi=200); plt.close(fig)


def main(mode="all"):
    EXT.mkdir(parents=True, exist_ok=True); EXT_RAW.mkdir(parents=True, exist_ok=True)
    counties = all_counties()
    if mode in ("fetch", "all"):
        fetch_qcew(counties)
        fetch_acs_flows()
        lodes_statewide()
        fetch_acs_wfh(counties)
    if mode in ("fetch2", "all"):
        fetch_qcew_zips(counties)
        fetch_acs5(counties)
        county_tail()
    if mode in ("build", "all"):
        build(counties)
    print("done")


if __name__ == "__main__":
    main(*sys.argv[1:])
