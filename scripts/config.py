"""Shared settings for the multi-metro LODES flow pipeline (Missouri metros + KC/STL benchmarks)."""
import json
import os as _os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "Data"                 # raw downloads, never modified
PARQUET = ROOT / "parquet"          # full-state OD as Parquet (one file per state/part/jt/year)
OUT = ROOT / "outputs"              # panels, tables, figures (per metro subfolder)

YEARS = list(range(2002, 2025))     # LODES 8.5 (vintage 20261014) covers 2002-2024
JOB_TYPES = ["JT00", "JT02"]
SEG = ["S000", "SA01", "SA02", "SA03", "SE01", "SE02", "SE03", "SI01", "SI02", "SI03"]
STATE_FIPS = {"mo": "29", "ks": "20", "il": "17"}
HOME_STATE = "29"                   # "in-state" = Missouri; other ends are "other states"

# Metro definitions (Census CBSA codes as coded in the LODES 8.5 crosswalk). County lists are read from the
# crosswalks of the listed states, so they always match the delineation LODES uses. core = county with most jobs.
METROS = {
    "springfield":   {"cbsa": "44180", "name": "Springfield, MO",       "states": ["mo"],       "core": "29077"},
    "columbia":      {"cbsa": "17860", "name": "Columbia, MO",          "states": ["mo"],       "core": "29019"},
    "jeffcity":      {"cbsa": "27620", "name": "Jefferson City, MO",    "states": ["mo"],       "core": "29051"},
    "joplin":        {"cbsa": "27900", "name": "Joplin, MO-KS",         "states": ["mo", "ks"], "core": "29097"},
    "stjoseph":      {"cbsa": "41140", "name": "St. Joseph, MO-KS",     "states": ["mo", "ks"], "core": "29021"},
    "capegirardeau": {"cbsa": "16020", "name": "Cape Girardeau, MO-IL", "states": ["mo", "il"], "core": "29031"},
    "kansascity":    {"cbsa": "28140", "name": "Kansas City, MO-KS",    "states": ["mo", "ks"], "core": "29095"},
    "stlouis":       {"cbsa": "41180", "name": "St. Louis, MO-IL",      "states": ["mo", "il"], "core": "29189"},
}

MIN_FREE_GB = 0.5   # stop writing if /home free space drops below this


def short_county(name):
    """'Greene County, MO' -> 'Greene'; 'St. Louis city, MO' -> 'St. Louis city'; non-MO keep a state tag."""
    base, st = (name.rsplit(", ", 1) + [""])[:2]
    base = base.replace(" County", "").replace(" Parish", "")
    return base if st in ("MO", "") else f"{base} {st}"


def metro_def(key):
    """Metro dict with 'counties' {fips: short name} resolved from the crosswalks (cached in outputs/<key>/)."""
    m = dict(METROS[key]); m["key"] = key
    cache = OUT / key / "counties.json"
    if cache.exists():
        m["counties"] = json.load(open(cache))
    else:
        import duckdb
        q = " UNION ALL ".join(f"SELECT DISTINCT cty, ctyname FROM '{PARQUET / s / f'{s}_xwalk.parquet'}' WHERE cbsa='{m['cbsa']}'"
                               for s in m["states"])
        rows = sorted(duckdb.sql(q).fetchall())
        m["counties"] = {c: short_county(n) for c, n in rows}
        cache.parent.mkdir(parents=True, exist_ok=True)
        json.dump(m["counties"], open(cache, "w"), indent=1)
    assert m["core"] in m["counties"], f"core {m['core']} not in {key}"
    # core county first (several outputs treat the first county as the core)
    m["counties"] = {m["core"]: m["counties"][m["core"]], **{c: n for c, n in m["counties"].items() if c != m["core"]}}
    assert {c[:2] for c in m["counties"]} == {STATE_FIPS[s] for s in m["states"]}, f"state list mismatch for {key}"
    return m


# the project venv sits on top of the conda 'wetland' env; point PROJ at that env's database
_os.environ.setdefault("PROJ_DATA", str(Path.home() / ".conda/envs/wetland/share/proj"))
