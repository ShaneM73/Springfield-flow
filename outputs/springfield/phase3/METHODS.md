# Methods and data-consistency choices (Phase 3)

These choices come from a literature review run on 2026-11-06 (Claude subagent; citations checked against abstracts and full texts where noted). Exact parameters live in `scripts/05_flow_structure.py`. Random seed: 20261106.

## 1. LODES data inconsistencies

| Issue | What the literature documents | Choice here |
|---|---|---|
| Federal jobs | Federal jobs enter JT00 in 2010 (LODES TechDoc 8.x). OPM suppressions cut federal jobs in 2015: −14 % nationally, −8.4 % in Missouri (LODES Federal Employment Data Note). | **JT02** (private jobs) is the headline series for 2002–2024. JT00 is shown for 2010+, with the 2015 break noted. |
| Residence imputation | Each LODES year is produced independently. The residence synthesiser added ownership, sex, race and ethnicity strata in **2009** (Graham, Kutzbach & McKenzie 2014, CES-WP-14-38). | Level-shift test at 2009 (`break_test_2009.csv`). This break is **confounded with the recession** and can't be separated from it. |
| Workplace (re)assignment | About 40 % of jobs are at multi-unit employers and are assigned to establishments by imputation. Headquarters reporting lengthens commutes: 54.9 % of LODES commuters work in their home county vs 72.5 % in the ACS (Green, Kutzbach & Vilhuber 2017, CES-WP-17-34). | Tract-years that jump and revert (> 50 % and > 500 jobs from the median of the neighbouring years) are flagged. Pairs touching them are flagged in the trend tests, and results are shown with and without them. Centres use 3-year centred means. |
| Long-distance commutes | Cut-offs used in the literature range from 50 to 200 miles: Nelson & Rae 2016 used 160 km, Green et al. 2017 used 200 mi. | Pairs **> 100 miles** are flagged. Indicators are reported with flows capped at 50, 100 and 150 mi. |
| Noise infusion | Cells of ≥ 10 jobs are very accurate; 3–9 is a transition zone (McKinney, Green, Vilhuber & Abowd 2021, *JSSAM*, doi:10.1093/jssam/smaa029). | Network edges need ≥ 3 jobs; pair-level inference and the map need ≥ 10. |
| State coverage | Several states are missing in early or late years. | Missouri is complete for 2002–2024. Out-of-state files are missing for AK 2017–24, AZ 2002–03, DC 2002–09, **MI 2022–24**, MS 2002–03 and NH 2002 (`outputs/manifest_outofstate.csv`). None of these is a major Springfield destination. |
| 2006 residence anomaly | Not documented in the TechDoc or the OnTheMap data notices. | Treated as an outlier year. The break tests are re-run excluding 2006. Worth reporting to CES.OnTheMap.Feedback@census.gov. |

## 2. Job centres

- **Measure:** local Moran's I on log job density, using centred 3-year mean jobs.
- **Settings:** queen contiguity, row-standardised weights, 999 conditional permutations, p < 0.05.
- **Core tracts:** a tract is a core if it is High-High, or High-Low with density above the metro 90th percentile (isolated campuses).
- **Size floor:** contiguous cores are merged, and a centre must hold ≥ 2 % of metro jobs.
- **Persistence:** a tract must be a candidate in ≥ 2 of the 3 years t−1 to t+1.
- **Precedent:** LISA employment centres across 359 US metros (Arribas-Bel & Sanz-Gracia 2014, *Urban Geography* 35:980), including medium-sized city-regions (Riguelle, Thomas & Verhetsel 2007, *J. Econ. Geogr.* 7:193). Persistence rules for annual LODES centres: Ha, Lee, Kim & Hipp 2024 (*Cities* 145:104669); Kane, Hipp & Kim 2018 (*Urban Studies* 55:844).
- **Robustness:** Ha et al.'s relative rule (annual density ≥ P95, cluster ≥ 2 % of jobs) is reported alongside (`centres_summary.csv`: ha_*).

## 3. Commuting communities

- **Algorithm:** Leiden modularity (Traag, Waltman & van Eck 2019, *Sci. Rep.* 9:5233). It guarantees connected communities, which Louvain doesn't.
- **Network:** undirected weights w_ij = F_ij + F_ji, using within-metro tract pairs with ≥ 3 jobs. Self-loops are excluded (Nelson & Rae 2016, *PLOS ONE*). Including them is a sensitivity check (`ari_selfloops`; He et al. 2020).
- **Resolution:** a stability scan (γ 0.5–2.0, 50 seeds per year, `gamma_scan.csv`) found ARI ≥ 0.90 plateaus only in two regimes. One is trivial (γ ≤ 0.7: 2–3 communities). The other is very fine (γ ≥ 1.7: about 25 neighbourhood clusters). Between them, mean pairwise ARI is about 0.84. **I used γ = 1.0**, the modularity default used in commuting-region work. Each annual partition is a consensus over 100 seeds (Lancichinetti & Fortunato 2012, *Sci. Rep.* 2:336), which absorbs seed instability. γ = 0.7 and γ = 1.7 are reported as sensitivity runs (`communities_gamma_sensitivity.csv`).
- **Tracking:** communities are matched across years by Jaccard similarity of tract membership, θ = 0.3 (Greene, Doyle & Cunningham 2010, ASONAM). Births, deaths, merges and splits are counted.

## 4. Flow trends

- **Which pairs:** OD pairs (tract level in the metro; county level at national scale) with a mean of ≥ 10 jobs, or a first- or last-5-year mean of ≥ 10.
- **Test:** Hamed–Rao modified Mann–Kendall (corrects for serial correlation) with Sen's slope. Multiple testing is controlled by Benjamini–Hochberg FDR, q < 0.05.
- **Classes** (adapted from Esri's Emerging Hot Spot Analysis; we found no published per-OD Mann–Kendall precedent):
  - **new:** < 3 jobs in each of the first 5 years and a last-5-year mean ≥ 10.
  - **fading:** the reverse.
  - **intensifying / declining:** a significant trend.
  - **persistent:** ≥ 10 jobs in ≥ 90 % of years with no trend.
  - **sporadic:** everything else.
- **Caveat:** classes use absolute counts, so metro job growth (+39 %) pushes many pairs into "intensifying".

## 5. Shocks

- **Pre-trend deviations:** 2007→2010 against a linear 2002–07 trend, and 2019→2021/2024 against a 2014–19 trend (`shock_windows.csv`).
- **Flow churn:** year-to-year Jaccard and volume persistence of pairs with ≥ 10 jobs (`flow_churn_JT02.csv`).
- **Community stability:** year-to-year ARI of the community partitions.

Proposals of ours rather than published standards: the 50 % jump flag, the 2 % centre floor and the flow-class cut-offs.
