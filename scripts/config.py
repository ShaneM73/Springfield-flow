"""Shared settings for the Springfield (and later multi-metro) LODES flow pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "Data"                 # raw downloads, never modified
PARQUET = ROOT / "parquet"          # full-state OD as Parquet (one file per state/part/jt/year)
OUT = ROOT / "outputs"              # panels, tables, figures (per metro subfolder)

YEARS = list(range(2002, 2025))     # LODES 8.5 (vintage 20261014) covers 2002-2024
JOB_TYPES = ["JT00", "JT02"]
SEG = ["S000", "SA01", "SA02", "SA03", "SE01", "SE02", "SE03", "SI01", "SI02", "SI03"]

# Metro definitions: CBSA code -> county FIPS list (checked against xwalk `cbsa`).
METROS = {
    "springfield": {"cbsa": "44180", "name": "Springfield, MO",
                    "counties": {"29077": "Greene", "29043": "Christian", "29225": "Webster",
                                 "29167": "Polk", "29059": "Dallas"},
                    "core": "29077"},
}

MIN_FREE_GB = 0.5   # stop writing if /home free space drops below this

# the project venv sits on top of the conda 'wetland' env; point PROJ at that env's database
import os as _os
_os.environ.setdefault("PROJ_DATA", str(Path.home() / ".conda/envs/wetland/share/proj"))
