# Does rising large-firm employment explain the 2010-2019 LODES drift?

Script: `scripts/10_firmsize_test.py` (data: `scripts/10_firmsize_download.py`). Run 2026-11-07.

## Hypothesis

LEHD places workers of multi-unit employers at establishments by imputation (U2W). Green, Kutzbach and Vilhuber (2017, CES-WP-17-34) show that LEHD assigned distance rises steeply with an employer's establishment count while ACS distance does not. If the share of jobs at large, multi-site firms rose over 2011-2019, LODES self-containment would fall and assigned distance rise with no change in anyone's commute. This note tests that with the LODES 8 WAC firm-size variables.

## Data

- **WAC JT02 (all private jobs), S000, MO/KS/IL, 2011-2024** (42 files, `Data/{mo,ks,il}/wac/`, LODES 8.5 vintage 20261014). Firm size CFS01-05 (0-19, 20-49, 50-249, 250-499, 500+ employees) and firm age CFA01-05 (0-1, 2-3, 4-5, 6-10, 11+ years). The technical document (LODESTechDoc8.5.pdf, footnotes 13-14) states these are "only available for data years 2011-2024, for All Private Jobs (JT02)"; firm size is "the national size of the firm in March of the previous year". A 2010 MO file was downloaded as a probe and its firm columns are all zero, so 2002-2010 were skipped. All three states are present in every year 2011-2024 (the only state gaps in that window are Alaska 2017+ and Michigan 2022+).
- **Firm size is the national firm, not the establishment**: a Walmart store, a hospital-system clinic or a bank branch counts as 500+. This is close to the "multi-site employer" concept of the hypothesis, but single-site large firms are also in the 500+ bin and small multi-site firms are not.
- **LODES OD** from the project's `outputs/<metro>/panel.parquet` (JT02, main+aux+oos, work tract inside the metro) and `blockflows.parquet` (block-pair straight-line miles, used for the >60 and >100 mile bins and the industry split). Panel and blockflows totals reconcile exactly for every metro-year. Metro = tracts in the metro's counties; OD jobs match WAC C000 to 0.0 % in the merged sample.

Outputs (all in `outputs/external/`): `wac_firmsize_tract_year.csv`, `wac_firmsize_metro_year.csv` (metro and statewide rows), `lodes_tract_distance_year.csv` (work tract x year 2002-2024: jobs, mean assigned distance, same-county share, >60/>100 mile shares, by-industry far tails), `lodes_firmsize_longdiff_tract.csv`, `lodes_firmsize_metro_year.csv`, `lodes_firmsize_residence_metro_year.csv`, `lodes_firmsize_destination_pairs.csv`, `lodes_firmsize_industry_tail_year.csv`, `lodes_firmsize_industry_tail.csv`, `lodes_firmsize_shiftshare.csv`, `lodes_firmsize_distance_tests.csv` (all regression rows), `figures/firmsize_vs_distance.png`.

## How much did large-firm employment rise?

Share of private jobs at firms with 500+ employees (WAC):

| Unit | 2011 | 2019 | 2024 |
|---|---|---|---|
| Missouri | 0.490 | 0.527 | 0.542 |
| Kansas | 0.471 | 0.503 | 0.512 |
| Illinois | 0.508 | 0.526 | 0.545 |
| Springfield | 0.502 | 0.537 | 0.534 |
| Columbia | 0.406 | 0.461 | 0.476 |
| Jefferson City | 0.382 | 0.434 | 0.448 |
| Joplin | 0.562 | 0.573 | 0.570 |
| St. Joseph | 0.549 | 0.585 | 0.593 |
| Cape Girardeau | 0.426 | 0.451 | 0.434 |
| Kansas City | 0.527 | 0.567 | 0.573 |
| St. Louis | 0.514 | 0.546 | 0.567 |

So the premise holds: +3.5 points (jobs-weighted across the eight metros) in 2011-2019, +1 to +5.5 points depending on the metro, about half a point a year. The 11+ year firm-age share also rose about 1-2 points (more in St. Joseph).

## Tests (JT02, jobs-weighted; full table in `lodes_firmsize_distance_tests.csv`)

Sample: work tracts with >= 50 jobs in both WAC and OD; 22,285 tract-years, 1,611 tracts, 2011-2024; long differences on 1,578 tracts present in 2011 and 2019.

**(a) Cross-section / panel, tract level, regressor = share of jobs at 500+ firms.**

| Outcome | metro + year FE (slope, SE) | tract + year FE (slope, SE) |
|---|---|---|
| Mean assigned distance (miles) | +8.7 (2.3) | +9.0 (2.6) |
| Share of jobs with home > 100 mi | +0.039 (0.010) | +0.042 (0.012) |
| Share of jobs with home > 60 mi | +0.029 (0.012) | +0.051 (0.014) |
| Same-county share of jobs | -0.143 (0.025) | -0.108 (0.011) |

All in the direction the hypothesis predicts and significant (SE clustered by tract). The 250+ share gives slightly larger slopes; the firm-age share works in the cross-section but not within tracts (same-county -0.05, distance n.s.), so it is firm size, not firm age, that carries the association.

**(b) Long differences 2011 -> 2019, tract level, metro FE** (figure `firmsize_vs_distance.png`):

| Outcome change | slope on d(500+ share) | SE | p | R2 | n |
|---|---|---|---|---|---|
| d mean distance (miles) | +11.3 | 4.3 | 0.008 | 0.05 | 1,578 |
| d share > 100 mi | +0.053 | 0.019 | 0.007 | 0.05 | 1,578 |
| d share > 60 mi | +0.064 | 0.024 | 0.007 | 0.05 | 1,578 |
| d same-county share | -0.133 | 0.019 | <1e-11 | 0.14 | 1,578 |

The sign is right in every metro for same-county share; it is individually significant in Springfield (-0.20), Kansas City (-0.09) and St. Louis (-0.18), not in the five small metros with 25-48 tracts. For mean distance only Springfield and St. Louis are significant; Joplin is negative (n.s.).

**(c) Metro-year panel 2011-2024 (n = 112)**, metro 500+ share vs metro outcomes:

| Outcome | metro FE only | metro + year FE |
|---|---|---|
| Same-county share of jobs (work side) | -0.45 (0.03) | -0.25 (0.08), p = 0.001 |
| Mean assigned distance | +59 (9) | +20 (12), p = 0.10 |
| Share > 100 mi | +0.18 (0.03) | +0.07 (0.04), p = 0.07 |
| Residence-based same-county share | -0.41 (0.03) | -0.09 (0.09), n.s. |
| Residence-based share > 100 mi | +0.16 (0.03) | -0.03 (0.07), n.s. |

Without year FE the slopes are large because both series trend; with year FE (which removes the common 2011-2024 drift, i.e. most of what we want to explain) only the work-side same-county share still co-moves with the large-firm share.

**(d) By industry, far tail (> 100 mi) share of jobs located in the metro, 2010-2019 trend (pp per year, jobs-weighted OLS):**

| | Goods SI01 | Trade/transport/utilities SI02 | Other services SI03 | All |
|---|---|---|---|---|
| Pooled, metro FE | +0.01 (0.02) | -0.03 (0.02) | **+0.06 (0.01), p < 1e-5** | +0.02 (0.01) |
| St. Louis | +0.06 (0.02) | +0.01 | +0.08 (0.01) | +0.05 |
| Jefferson City | +0.20 (0.04) | +0.11 | +0.12 (0.05) | +0.13 |
| Columbia | -0.18 (0.05) | -0.36 | +0.18 (0.05) | +0.01 |
| Kansas City | -0.05 | -0.06 | +0.03 (0.02) | -0.01 |
| Springfield | -0.02 | +0.13 | -0.00 | +0.02 |

The 2010-2019 far-tail drift on the workplace side is concentrated in services (SI03: pooled +0.45 points over 2010-2019) and absent in goods and SI02; the service drift is strongest in St. Louis, Columbia and Jefferson City. This is consistent with the mechanism (multi-site service employers: health systems, retail, staffing) but it is also consistent with any service-sector labour-market change, and the firm-size variables are not cross-tabulated with industry in LODES, so this remains circumstantial.

**(e) Residence side, destination-county test.** For each metro's resident workers, flows to each work county (inside or outside the metro, MO/KS/IL only, flow >= 20 in 2011; n = 755 pairs), log(flow 2019 / flow 2011) on the destination county's change in 500+ share, its 2011 level, its log job growth and a > 100 mile dummy, metro FE, weights = 2011 flow. The destination's job growth is the dominant predictor (elasticity 1.2, p < 1e-11); the change in its large-firm share is not (+0.57, SE 0.58). The far x d(500+ share) interaction is positive (+3.1, SE 1.2, p = 0.014), i.e. among far destinations flows did grow faster toward counties whose large-firm share rose, but the far-only subsample slope is imprecise (+1.3, SE 1.8, n = 415). Weak, not null.

## Shift-share: how much of the 2011-2019 decline does the large-firm change predict?

Predicted change in same-county share = (within-metro slope from (b), -0.133) x (metro change in 500+ share). `lodes_firmsize_shiftshare.csv`:

| Metro | d 500+ share | Observed d same-county (work side) | Predicted | Explained |
|---|---|---|---|---|
| Springfield | +0.035 | -0.005 | -0.005 | ~90 % (of a 0.5-point fall) |
| Columbia | +0.055 | +0.002 | -0.007 | rose, nothing to explain |
| Jefferson City | +0.052 | -0.033 | -0.007 | 21 % |
| Joplin | +0.011 | +0.004 | -0.001 | rose |
| St. Joseph | +0.035 | -0.021 | -0.005 | 23 % |
| Cape Girardeau | +0.025 | +0.017 | -0.003 | rose |
| Kansas City | +0.040 | -0.019 | -0.005 | 28 % |
| St. Louis | +0.032 | -0.014 | -0.004 | 30 % |
| **Pooled (jobs-weighted)** | **+0.035** | **-0.0143** | **-0.0047** | **33 %** (27 % with the within-tract slope) |

For mean assigned distance the pooled observed change is +1.6 miles against +0.4 predicted (25 %); for the > 100 mile share +0.27 points observed against +0.19 predicted (about 70 %, but the observed change is small and uneven: -1.2 points in Cape Girardeau, +1.4 in Jefferson City).

Residence-based same-county share (the measure in which the project's drift was reported) fell 2011-2019 by 0.6 (Springfield), 0.2 (Columbia), 2.8 (Jefferson City), 1.2 (Joplin), 0.6 (St. Joseph), 1.5 (Kansas City) and 1.4 (St. Louis) points and rose 4.9 in Cape Girardeau (its 2011 value is an outlier year); JT02 drift is smaller than the JT00 numbers in `ACS_LODES_WIDENING.md`.

## Verdict

The composition channel is real but only partial. Within tracts and across the 2011-2019 long differences, a higher share of jobs at 500+ employee firms goes with longer assigned distances, fatter far tails and a lower same-county share, with the right sign in all eight metros and slopes that are stable across specifications (about -0.11 to -0.14 same-county points per point of large-firm share, +9 to +11 miles per unit share). The large-firm share did rise, by 3.5 points, so the mechanism predicts roughly a third of the pooled 1.4-point fall in work-side same-county share, a quarter of the 1.6-mile rise in mean assigned distance, and in the three metros with a clear decline (Jefferson City, Kansas City, St. Louis) 20-30 % of it. It cannot explain the residence-side drift in the small metros: metro-year co-movement with year effects is null on the residence side, and the destination-county test finds only weak evidence that residents' flows grew faster toward counties where large-firm employment rose. Two caveats cut in opposite directions: (i) the tract-level association need not be an imputation artefact at all, since large employers may genuinely draw from wider labour sheds, so a third is an upper bound for this variable; (ii) the WAC variable is national firm size, not multi-establishment status or MWR non-compliance, and the imputation that matters can occur at the headquarters county of a firm located anywhere, so a one-variable test on the home metro's own jobs is a weak instrument for the mechanism. The honest summary: rising large-firm employment moves LODES distance measures in the predicted direction and accounts for a minority of the 2011-2019 drift; most of the drift remains unexplained by this test, and the service-sector concentration of the far-tail rise is suggestive but not probative.
