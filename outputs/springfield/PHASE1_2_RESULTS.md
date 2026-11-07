# Springfield MSA (CBSA 44180): Phase 1–2 results, 2026-11-06

JT02 (private jobs) unless stated. Straight-line miles. LODES 8.5. Tables are in `tables/` and figures in `figures/`.

## Phase 1 checks
- 92 MO OD files (main + aux, JT00 + JT02, 2002–2024) plus the xwalk downloaded. Every file matches the server SHA-256 and has 15-digit geocodes; no empty files. Row counts and createdates are in `../manifest_mo.csv`.
- Mixed vintages: 2002–2020 = 20230321; 2021, 2022, 2023 and 2024 each come from a later vintage.
- Crosswalk CBSA 44180 = the 5 handoff counties; 117 tracts.
- 2022 JT00 handoff table reproduced: **43/43 measures match** (`validation_2022.csv`).
  - The "77.5 % of cross-tract commuters in pairs ≥10" figure is computed over **all cross-node flows touching the MSA**, with outside counties as nodes.
  - Restricted to within-MSA tract pairs, the share is 81.3 %.

> Note: Phase 3 later added out-of-state commuters. The resident-worker and self-containment figures below are MO-only; see PHASE3_RESULTS.md.

## Phase 2 headline numbers (JT02)
| Indicator | 2002 | 2007 | 2010 | 2019 | 2020 | 2024 |
|---|---|---|---|---|---|---|
| MSA jobs (MO + out-of-state residents) | 143,846 | 161,628 | 153,587 | 186,077 | 178,225 | 200,415 |
| In-commuters from rest of MO | 22,916 | 36,206 | 36,293 | 43,809 | 42,327 | 52,276 |
| Residents working in MSA (self-containment) | 87.5 % | 83.7 % | 80.6 % | 82.3 % | 82.5 % | 80.2 % |
| MSA jobs held by MSA residents | 82.7 % | 75.7 % | 74.4 % | 73.4 % | 73.3 % | 70.9 % |
| Greene jobs filled by Greene residents | 64.8 % | 56.6 % | 55.4 % | 54.2 % | 53.3 % | 51.2 % |
| … by outer-MO residents | 15.5 % | 22.0 % | 23.0 % | 22.9 % | 23.2 % | 25.3 % |
| Median commute within MSA (mi) | 5.2 | 6.0 | 6.1 | 6.4 | 6.5 | 6.5 |
| Mean commute to MSA jobs, all MO flows (mi) | 20.2 | 26.4 | 29.5 | 28.0 | 27.4 | 30.4 |
| … excluding flows > 100 mi | 12.8 | 15.6 | 15.6 | 16.1 | 16.2 | 16.8 |
| Share of MSA jobs with home > 100 mi | 5.0 % | 7.5 % | 9.7 % | 8.4 % | 7.9 % | 9.7 % |
| Distance-decay beta (tract gravity) | 0.98 | 0.94 | 0.89 | 0.84 | 0.82 | 0.80 |
| Top-5 tract job share | 31.6 % | 29.3 % | 32.7 % | 31.5 % | 31.7 % | 29.6 % |
| Gini of tract jobs | 0.62 | 0.59 | 0.61 | 0.60 | 0.59 | 0.57 |

What the table shows:
- **Growth outpaced self-containment:** jobs +39 % from 2002 to 2024; in-commuting from the rest of MO +128 %.
- **The commutershed is widening outward rather than suburbanizing.** Greene's own share fell 13.6 points. Outer-MO counties gained 9.8 points; the 4 suburban counties are flat at about 20 %.
- **Distance decay is weakening steadily** (beta 0.98 → 0.80). Three readings are consistent with this: 2008–09 is a step down, 2015–2021 is a steady decline, and 2021–24 is flat.
- **Job concentration is stable to slightly dispersing.** Top-5 tract share holds at about 30 %, Gini falls 0.62 → 0.57, and the largest tract is 29077002200 in every year. There is no sign of a new competing centre, so the pattern is monocentric with mild dispersion.
- **Suburban jobs-housing ratios barely moved** (Christian 0.48 → 0.48; Webster 0.43 → 0.56). Own-county work shares fell everywhere: Greene 86 → 77 %, Polk 42 → 29 %, Dallas 28 → 14 %.
- **Earnings gradient:** the median commute rose most for >$3,333 workers (5.8 → 7.2 mi). Goods-industry commutes are the longest (6.7 → 8.3).
- **Shocks:**
  - 2007→2010: jobs −5.0 %, but in-commuting held steady (+0.2 %), so self-containment fell.
  - 2019→2020: jobs −4.2 % (JT00 −3.8 %), in-commuting −3.4 %.
  - 2020→2024: full recovery, with in-commuting +19 % above 2019.
- **Long-distance artefact check:** mean distance to MSA jobs rose 50 % with all flows and 31 % with flows over 100 mi dropped. Most of the widening survives the check. The > 100 mi flows themselves average about 158 mi every year (KC/STL scale) and are 8–10 % of jobs.

## Caveats attached to the findings
1. **2006 residence anomaly:** about 9,000 Greene-job workers are shifted from suburban homes to Greene homes in 2006 only (Webster → Greene drops from 5,569 to 2,837, then 5,778 in 2007). Treat 2006 as an outlier year for any residence-based measure.
2. **2002–2007 rise:** in-commuting jumped from 22.9k to 36.2k, and much of the median-distance rise happens 2006→07. Early LODES years are known to be less reliable. I'd present 2002–2024 trends alongside 2010–2024 trends: from 2010 to 2024, jobs grew +30.5 % and in-commuting +44 %.
3. **Tract job jumps** (`tract_job_jumps.csv`, 22 tract-years). These are clear reporting reassignments:
   - 29077001100: −6,318 jobs in 2015, then +6,820 in 2016.
   - 29077002800: −4,264 in 2003 and +6,949 in 2009.

   They move jobs between neighbouring downtown tracts. They hardly affect metro-level measures, but they would create false "new / fading flows" in Phase 3, so these tract-years need handling.
4. Age shares are split at 2012. JT00 is reported only for 2010+. 2020–24 flows include remote workers placed at the employer's address.
5. **Outflow out of state is missing:** it needs the neighbour-state aux files (AR, KS, OK, …), which haven't been downloaded yet.

## Decision needed: job-centre definition
The current rule (contiguous tracts ≥ 5 jobs/acre and ≥ 1,000 jobs, totalling ≥ 5,000) **is unstable**. The downtown/medical centre flips between 4, 5, 7 and 11 tracts, and the largest tract sometimes splits off as its own centre. Centre share swings between 22 % and 40 % for definitional reasons rather than real change. Sensitivity grid: `job_centres_sensitivity_JT02.csv`.
Options:
- (a) Define centres once from pooled multi-year jobs and track their job share annually.
- (b) Count a tract in a centre only if it qualifies in ≥ k of 3 consecutive years.
- (c) Use a local-peak method (e.g. McMillen-style residuals from a density-gradient fit).
