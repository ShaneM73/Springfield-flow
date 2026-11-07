"""Annual ACS 1-year B08007 (place of work: worked in county of residence) for the metro counties,
2005-2024, against the LODES same-county share of resident workers. Tests whether the 2007 and 2009
steps in LODES self-containment appear in a survey series.

Outputs (outputs/external/):
  acs_b08007_county_year.csv      county, year, workers, in_county, in_county_share
  lodes_county_samecounty_year.csv county, year, res_workers, same_county, same_county_share
  acs_vs_lodes_samecounty.csv     merged, with first differences
"""
import importlib.util, io, re, sys, zipfile
from pathlib import Path
import duckdb, pandas as pd

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ext", HERE / "08_external_controls.py")
ext = importlib.util.module_from_spec(spec); spec.loader.exec_module(ext)
get, ST_NAMES, EXT, EXT_RAW = ext.get, ext.ST_NAMES, ext.EXT, ext.EXT_RAW
import config

TABLE = "B08007"
# cells: 001 total; 002 worked in state of residence; 003 worked in county of residence (all sexes)
CELLS = {"total": 1, "in": 3}


def seq_year(year, st):
    base = f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}"
    look = None
    for u in [f"{base}/documentation/user_tools/ACS_1yr_Seq_Table_Number_Lookup.txt",
              f"{base}/documentation/1_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt",
              f"{base}/documentation/user_tools/ACS_1yr_Seq_Table_Number_Lookup.csv",
              f"{base}/documentation/1_year/user_tools/Sequence_Number_and_Table_Number_Lookup.xls"]:
        look = get(u, EXT_RAW / "acs" / f"lookup_{year}.{u.rsplit('.', 1)[-1]}")
        if look:
            break
    if not look:
        print("no lookup", year); return None
    if u.endswith(".xls"):
        L = pd.read_excel(io.BytesIO(look), dtype=str)
    else:
        L = pd.read_csv(io.BytesIO(look), dtype=str, encoding="latin1")
    L.columns = [c.strip().lower().replace(" ", "_") for c in L.columns]
    tid = [c for c in L.columns if "table_id" in c][0]; seqc = [c for c in L.columns if "sequence" in c][0]
    startc = [c for c in L.columns if "start" in c][0]
    t = L[L[tid].str.strip() == TABLE]
    if t.empty:
        print("table not in lookup", year); return None
    seq = int(float(t[seqc].iloc[0])); start = int(float(t[startc].dropna().iloc[0]))
    zurls = [f"{base}/data/1_year_by_state/{ST_NAMES[st]}_All_Geographies.zip",
             f"{base}/data/1_year_by_state/{ST_NAMES[st]}.zip"]
    z = None
    for zu in zurls:
        z = get(zu, EXT_RAW / "acs" / f"{year}_{st}_1yr.zip")
        if z:
            break
    if not z:
        print("no zip", year, st); return None
    zf = zipfile.ZipFile(io.BytesIO(z)); names = zf.namelist()
    ef = [n for n in names if re.search(rf"e{year}1{st}{seq:04d}000\.txt$", n)]
    if not ef:
        print("no seq file", year, st, seq); return None
    E = pd.read_csv(zf.open(ef[0]), header=None, dtype=str).rename(columns={5: "logrecno"})
    col = lambda k: pd.to_numeric(E[start - 1 + CELLS[k] - 1], errors="coerce")
    gf = [n for n in names if re.search(rf"g{year}1{st}\.csv$", n)]
    if gf:
        G = pd.read_csv(zf.open(gf[0]), header=None, dtype=str, encoding="latin1")[[4, 48]].rename(columns={4: "logrecno", 48: "geoid"})
    else:
        gtxt = [n for n in names if re.search(rf"g{year}1{st}\.txt$", n)][0]
        lines = zf.open(gtxt).read().decode("latin1").splitlines()
        G = pd.DataFrame({"logrecno": [l[13:20] for l in lines], "geoid": [l[178:218].strip() for l in lines]})
    df = pd.DataFrame({"logrecno": E.logrecno, "workers": col("total"), "in_county": col("in")}).merge(G, on="logrecno")
    df = df[df.geoid.str.startswith("05000US")]
    df["county"] = df.geoid.str[-5:]
    return df[["county", "workers", "in_county"]].assign(year=year)


def table_based(year):
    d = get(f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}/table-based-SF/data/1YRData/acsdt1y{year}-{TABLE.lower()}.dat",
            EXT_RAW / "acs" / f"acsdt1y{year}-{TABLE.lower()}.dat")
    if not d:
        return None
    T = pd.read_csv(io.BytesIO(d), sep="|", dtype=str)
    T = T[T.GEO_ID.str.startswith("0500000US")]
    num = lambda c: pd.to_numeric(T[c], errors="coerce")
    return pd.DataFrame({"county": T.GEO_ID.str[-5:], "workers": num(f"{TABLE}_E001"),
                         "in_county": num(f"{TABLE}_E003"), "year": year})


def lodes_same_county(counties):
    con = duckdb.connect()
    P = config.PARQUET
    parts = []
    for st in ("mo", "ks", "il"):
        parts.append(f"SELECT h_geocode, w_geocode, S000, CAST(regexp_extract(filename,'([0-9]{{4}})[.]parquet',1) AS INT) AS yr "
                     f"FROM read_parquet('{P}/{st}/od/{st}_od_*_JT00_*.parquet', filename=true)")
    oos = P / "oos" / "res_outofstate.parquet"
    if oos.exists():
        cols = [c for c in con.sql(f"DESCRIBE SELECT * FROM '{oos}'").df().column_name]
        ycol = "year" if "year" in cols else "yr"
        parts.append(f"SELECT h_geocode, w_geocode, S000, {ycol} AS yr FROM '{oos}' WHERE jt='JT00'" if "jt" in cols else
                     f"SELECT h_geocode, w_geocode, S000, {ycol} AS yr FROM '{oos}'")
    cl = "','".join(counties)
    q = f"""WITH u AS ({' UNION ALL '.join(parts)})
    SELECT substr(h_geocode,1,5) AS county, yr AS year, sum(S000) AS res_workers,
           sum(S000) FILTER (substr(h_geocode,1,5)=substr(w_geocode,1,5)) AS same_county
    FROM u WHERE substr(h_geocode,1,5) IN ('{cl}') GROUP BY 1,2 ORDER BY 1,2"""
    d = con.sql(q).df()
    d["same_county_share"] = d.same_county / d.res_workers
    return d


def main():
    counties = sorted(ext.all_counties().keys())
    rows = []
    for y in range(2005, 2020):
        for st in ("mo", "ks", "il"):
            try:
                p = seq_year(y, st)
                if p is not None:
                    rows.append(p); print("seq", y, st, len(p), flush=True)
            except Exception as e:
                print("seq failed", y, st, repr(e)[:150], flush=True)
    for y in range(2021, 2025):
        p = table_based(y)
        if p is not None:
            rows.append(p); print("table-based", y, len(p), flush=True)
    A = pd.concat(rows, ignore_index=True).drop_duplicates(["county", "year"])
    A = A[A.county.isin(counties)].copy()
    A["in_county_share"] = A.in_county / A.workers
    A.to_csv(EXT / "acs_b08007_county_year.csv", index=False)
    L = lodes_same_county(counties)
    L.to_csv(EXT / "lodes_county_samecounty_year.csv", index=False)
    M = L.merge(A[["county", "year", "in_county_share", "workers"]], on=["county", "year"], how="left")
    M = M.sort_values(["county", "year"])
    M["d_lodes"] = M.groupby("county").same_county_share.diff()
    M["d_acs"] = M.groupby("county").in_county_share.diff()
    M.to_csv(EXT / "acs_vs_lodes_samecounty.csv", index=False)
    print(M[M.county.isin(["29077", "29019", "29051", "29097", "29021", "29031", "29095", "29189", "29510", "20091", "29183"])]
          .pivot(index="county", columns="year", values="in_county_share").round(3).to_string())


if __name__ == "__main__":
    main()
