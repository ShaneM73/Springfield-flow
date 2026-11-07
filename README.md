# Springfield, MO commuting flows — LODES 2002–2024

Annual, artefact-aware analysis of commuting **flow** networks in Missouri's metros, 2002–2024, from US Census LEHD LODES 8.5: in-state and out-of-state commuters, job centres, commuting communities, flow trends and shocks. Springfield (CBSA 44180) is the pilot; Columbia, Jefferson City, Joplin, St. Joseph and Cape Girardeau are the other small/mid metros, with Kansas City and St. Louis as large-metro benchmarks.

**Web app:** <https://shanem73.github.io/Springfield-flow/> is a 3D space-time cube in the style of the [European Spatiotemporal Geography](https://github.com/ShaneM73/European_spatiotemporal_geography) atlas. Each year is a layer of tract-to-tract flows over relief, with a metro picker, metro and national scales, commuting communities, job centres and flow-trend classes.

Results: [Phase 1–2](outputs/springfield/PHASE1_2_RESULTS.md) · [Phase 3](outputs/springfield/PHASE3_RESULTS.md) · [Methods & citations](outputs/springfield/phase3/METHODS.md)

Status (2026-11-07): Phases 1–3 done for Springfield and running for the other seven metros; cross-metro comparison in `outputs/comparison/`; manuscript materials in `outputs/manuscript/`.

## Data note: LODES is now 8.5

The LEHD server moved to **LODES 8.5 (vintage 20261014)**, which adds **2024**. All years still use 2020 blocks. The 2022 files are byte-identical to the ones used in the earlier session (SHA-256 checked), so the validation still applies.
Vintages by year (`outputs/manifest_mo.csv`): 2002–2020 = 20230321, 2021 = 20231016, 2022 = 20240920, 2023 = 20251202, 2024 = 20261014.

## Layout

```
Data/                    raw downloads, untouched (plus 3 originals at top level)
  {mo,ks,il}/od/*.csv.gz main+aux, JT00+JT02, 2002-2024 (92 files each); sha256_check.tsv; version.txt
  tiger/                 TIGER 2020 tracts and places for MO, KS, IL (land area, contiguity, town labels)
parquet/{mo,ks,il}/      full-state Parquet copies of every OD file + xwalk
parquet/oos/             rows of every other state's aux files with a MO/KS/IL home (res_outofstate.parquet), block points
outputs/manifest_mo.csv  file, bytes, rows, sum_S000, createdate, sha256, download date, version
outputs/<metro>/         counties.json, blockflows.parquet, panel.parquet, nodes.csv, tables/, figures/, phase3/, pipeline.log
outputs/comparison/      cross-metro tables and figures (scripts/06_compare.py)
scripts/                 config.py (METROS), 00_fetch_outofstate.py ... 06_compare.py, run_metro.sh, run_all.sh
download_lodes.py        downloads to Data/, years 2002-2024, state list on CLI, SHA-256 verification
docs/                    web app (three.js) + its data; served by GitHub Pages
tools/                   basemap (terrain + outlines) and web-data builders
.venv/                   python venv on top of conda env `wetland` (+ pyarrow duckdb igraph leidenalg pymannkendall statsmodels)
```

Run:
```
python download_lodes.py -j 6 mo ks il                        # main+aux, JT00+JT02, 2002-2024, SHA-256 checked
cd scripts
python 00_fetch_outofstate.py          # every other state's aux file, streamed; keeps MO/KS/IL-home rows only
python 01_manifest_parquet.py mo ks il # manifest + Parquet
python 02_build_panel.py <metro>       # block flows + tract/county panel (parts: main, aux, oos)
python 03_validate_2022.py             # reproduces the Springfield 2022 cross-section (43/43)
python 04_describe.py <metro>          # Phase 2 indicators, tables, figures
python 05_flow_structure.py <metro>    # Phase 3 centres, communities, trends, shocks (seeded)
python 06_compare.py                   # cross-metro comparison
./run_all.sh                           # all metros in parallel, then the web data
cd .. && python tools/build_basemap.py --raw <cache> && python tools/build_webdata.py   # web app data
```
Serve the app locally with `cd docs && python -m http.server`.
To add a metro, add an entry to `METROS` in `scripts/config.py` (CBSA code, states, core county; the county list is read from the crosswalks) and run `scripts/run_metro.sh <key>`.

**Not in git:** raw LODES files (`Data/`), Parquet copies (`parquet/`), the block-level and tract panels, and the venv. All of them can be rebuilt with the scripts.

## Data dictionary

**panel.parquet**: one row per year × jt × part × h_node × w_node.
`year`; `jt` JT00 all jobs / JT02 private jobs; `part` main (MO home and work) / aux (home in another state, work in MO) / oos (home in the metro, work in another state); `h_node`, `w_node` are an 11-digit 2020 tract inside the MSA, or a 5-digit county FIPS outside it (in any state); `S000` total workers; `SA01-03` age ≤29 / 30–54 / 55+; `SE01-03` monthly earnings ≤$1,250 / $1,251–3,333 / >$3,333; `SI01-03` goods / trade-transport-utilities / other services; `dist_sum` = Σ S000 × straight-line miles at block level (mean distance = dist_sum / dist_n); `dist_n` workers with a computable distance; `n_blockpairs`.
**blockflows.parquet**: same segment columns at block-pair level plus `miles` (haversine between xwalk block internal points; null when home is out of state).
**nodes.csv**: node, type, county, lon/lat (job- plus resident-weighted mean of block points, MO main JT00, all years pooled).

## Tables (outputs/springfield/tables)
| file | content |
|---|---|
| volumes_county_year.csv | MSA jobs (MO + aux), live-work, in/outflow, self-containment, and per county: jobs, resident workers, ratio, own-county, in-MSA and to-Greene shares |
| tract_jobs_residents_year.csv | tract jobs (main + aux) and resident workers |
| commute_distance_year.csv | median/mean miles: within MSA overall, by earnings, industry, age (`age_period` split at 2012), home county; MSA jobs with long flows dropped at 150/100/50 mi |
| long_distance_share_JT02.csv | workers in MSA jobs living > 100 mi away |
| commutershed_core_jobs.csv | where Greene's job-holders live: Greene / 4 suburban counties / outer MO / out of state |
| distance_bands_msa_jobs.csv | share of MSA jobs by distance band |
| distance_decay_poisson.csv | beta on log distance, Poisson gravity among 117 tracts with origin and destination fixed effects, intrazonal excluded |
| job_concentration.csv | top-1/5/10 tract shares, Gini, job centres |
| job_centres*.csv | centres per year, persistence per tract, threshold sensitivity grid |
| tract_job_jumps.csv | tract-year changes > 500 jobs and > 50 % (check against QCEW) |

JT00 values before 2010 are set to NaN (federal jobs missing).
