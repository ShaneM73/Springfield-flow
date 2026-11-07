# Is the 2007 self-containment step national?

Source: LODES 8 main OD files, job type JT02 (all private primary jobs), data years 2004-2011, all 50 states + DC (PR/VI excluded). Every number is computed directly from the csv.gz with DuckDB (`scripts/13b_national_od_compute.py`). `same_county_share` = share of a state's in-state workers (main file: live and work in the state) whose workplace block and home block share the first five digits (county); `same_tract_share` uses the first eleven digits. Year-on-year changes are in percentage points and are only reported where the previous data year exists for that state.

Files present: 395 of 408 state-years. States with a late start (first JT02 year > 2004): DC 2010, MA 2011.

## 1. Distribution of the year-on-year change in the same-county share

**2007 (2006->2007), n = 49 states with both years**

- median change: -2.61 pts; mean -2.42; IQR [-3.11, -1.86]
- drop > 1 pt: 43 states; > 2 pts: 36; > 3 pts: 15
- no drop (change >= 0): 0 states
- largest drops: ID -4.41, WY -4.41, SD -4.05, UT -3.97, WV -3.65, MT -3.53, IA -3.39, AR -3.34
- MO/KS/IL: MO -2.87, KS -2.83, IL -2.85

**2009 (2008->2009), n = 49 states with both years**

- median change: -1.69 pts; mean -1.70; IQR [-2.16, -1.30]
- drop > 1 pt: 41 states; > 2 pts: 15; > 3 pts: 1
- no drop (change >= 0): 0 states
- largest drops: NH -3.24, AL -2.94, NM -2.89, NC -2.68, MO -2.66, TN -2.65, MS -2.53, OK -2.48
- MO/KS/IL: MO -2.66, KS -2.11, IL -1.72

**Other years, for comparison (same-county share, pts):**

| year | n | median | mean | p10 | p90 | drop > 1 pt | drop > 2 pts | drop > 3 pts | rise > 1 pt |
|---|---|---|---|---|---|---|---|---|---|
| 2004->2005 | 49 | -0.33 | -0.36 | -0.73 | +0.20 | 3 | 0 | 0 | 0 |
| 2005->2006 | 49 | -0.22 | -0.18 | -0.73 | +0.62 | 2 | 1 | 1 | 3 |
| 2006->2007 | 49 | -2.61 | -2.42 | -3.55 | -0.87 | 43 | 36 | 15 | 0 |
| 2007->2008 | 49 | -0.54 | -0.53 | -1.13 | -0.07 | 8 | 0 | 0 | 1 |
| 2008->2009 | 49 | -1.69 | -1.70 | -2.65 | -0.71 | 41 | 15 | 1 | 0 |
| 2009->2010 | 49 | -0.32 | -0.33 | -0.71 | +0.14 | 2 | 0 | 0 | 0 |
| 2010->2011 | 50 | -0.61 | -0.95 | -2.51 | +0.15 | 17 | 8 | 4 | 1 |

**Same-tract share (pts):**

| year | n | median | mean | p10 | p90 | drop > 0.5 pt | drop > 1 pt |
|---|---|---|---|---|---|---|---|
| 2004->2005 | 49 | -0.08 | -0.08 | -0.25 | +0.04 | 0 | 0 |
| 2005->2006 | 49 | -0.03 | -0.03 | -0.12 | +0.13 | 1 | 0 |
| 2006->2007 | 49 | -0.52 | -0.61 | -1.18 | -0.23 | 27 | 9 |
| 2007->2008 | 49 | -0.10 | -0.09 | -0.24 | +0.04 | 0 | 0 |
| 2008->2009 | 49 | +0.08 | +0.19 | -0.23 | +0.54 | 1 | 1 |
| 2009->2010 | 49 | -0.14 | -0.19 | -0.55 | +0.03 | 6 | 1 |
| 2010->2011 | 50 | -0.11 | -0.39 | -1.48 | +0.14 | 15 | 7 |

**Worker-weighted national shares (balanced panel of 49 states present 2004-2011):**

| year | workers (M) | same-county % | change | same-tract % | change |
|---|---|---|---|---|---|
| 2004 | 99.0 | 61.59 |  | 5.13 |  |
| 2005 | 101.2 | 61.25 | -0.34 | 5.07 | -0.06 |
| 2006 | 103.1 | 61.18 | -0.07 | 5.04 | -0.03 |
| 2007 | 104.2 | 58.97 | -2.21 | 4.63 | -0.41 |
| 2008 | 104.2 | 58.42 | -0.55 | 4.57 | -0.06 |
| 2009 | 98.9 | 56.64 | -1.78 | 4.65 | +0.08 |
| 2010 | 98.2 | 56.42 | -0.22 | 4.50 | -0.15 |
| 2011 | 100.7 | 56.00 | -0.42 | 4.43 | -0.07 |

## 2. County-level residence vs workplace jumps

Share of counties (>= 500 workers in both years) whose resident-worker total, or workplace-job total, changes by more than 10 % in absolute value from the previous year. Median across states, and the number of states where the share exceeds 0.25.

| year | n states | median share_res_jump | mean | states > 0.25 | median share_work_jump | mean | states > 0.25 | pooled res share | pooled work share |
|---|---|---|---|---|---|---|---|---|---|
| 2004->2005 | 49 | 0.084 | 0.119 | 7 | 0.078 | 0.083 | 3 | 0.123 | 0.087 |
| 2005->2006 | 49 | 0.119 | 0.178 | 15 | 0.069 | 0.099 | 5 | 0.175 | 0.102 |
| 2006->2007 | 49 | 0.224 | 0.227 | 23 | 0.086 | 0.098 | 2 | 0.257 | 0.109 |
| 2007->2008 | 49 | 0.056 | 0.085 | 2 | 0.061 | 0.072 | 1 | 0.098 | 0.084 |
| 2008->2009 | 49 | 0.213 | 0.214 | 19 | 0.154 | 0.181 | 14 | 0.225 | 0.192 |
| 2009->2010 | 49 | 0.065 | 0.066 | 0 | 0.076 | 0.088 | 1 | 0.080 | 0.099 |
| 2010->2011 | 50 | 0.261 | 0.262 | 27 | 0.090 | 0.092 | 1 | 0.308 | 0.119 |

MO/KS/IL residence-jump shares by year: 
- MO: 2005 0.25/0.09, 2006 0.29/0.04, 2007 0.33/0.06, 2008 0.15/0.05, 2009 0.16/0.12, 2010 0.17/0.06, 2011 0.25/0.09 (res/work)
- KS: 2005 0.12/0.08, 2006 0.46/0.12, 2007 0.47/0.19, 2008 0.09/0.15, 2009 0.20/0.10, 2010 0.07/0.06, 2011 0.30/0.18 (res/work)
- IL: 2005 0.13/0.05, 2006 0.08/0.05, 2007 0.20/0.07, 2008 0.11/0.03, 2009 0.06/0.09, 2010 0.04/0.06, 2011 0.33/0.10 (res/work)

## 3. Ranked table: 2006->2007 change in same-county share, all states

| rank | state | workers 2007 | same-county 2006 % | 2007 % | change 2007 (pts) | same-tract change 2007 | workers change % | res-jump share 2007 | work-jump share 2007 | change 2009 (pts) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ID | 0.52M | 73.3 | 68.9 | -4.41 | -0.64 | +3.9 | 0.44 | 0.15 | -1.54 |
| 2 | WY | 0.19M | 83.9 | 79.4 | -4.41 | -1.53 | +1.8 | 0.27 | 0.00 | -1.36 |
| 3 | SD | 0.29M | 74.3 | 70.3 | -4.05 | -1.37 | +1.5 | 0.31 | 0.07 | -1.69 |
| 4 | UT | 0.99M | 73.3 | 69.4 | -3.97 | -0.54 | +5.1 | 0.35 | 0.15 | -1.40 |
| 5 | WV | 0.49M | 61.3 | 57.7 | -3.65 | -1.16 | -0.3 | 0.09 | 0.06 | -0.68 |
| 6 | MT | 0.34M | 80.1 | 76.6 | -3.53 | -1.22 | +2.5 | 0.20 | 0.09 | -1.31 |
| 7 | IA | 1.16M | 65.2 | 61.8 | -3.39 | -1.27 | +1.1 | 0.08 | 0.04 | -1.74 |
| 8 | AR | 0.92M | 63.3 | 60.0 | -3.34 | -0.82 | -0.2 | 0.32 | 0.09 | -2.03 |
| 9 | GA | 3.24M | 43.7 | 40.4 | -3.33 | -0.48 | +1.2 | 0.34 | 0.19 | -1.96 |
| 10 | NC | 3.21M | 56.2 | 53.1 | -3.16 | -0.45 | +2.0 | 0.22 | 0.07 | -2.68 |
| 11 | SC | 1.49M | 59.2 | 56.0 | -3.14 | -0.58 | +2.2 | 0.28 | 0.09 | -1.79 |
| 12 | NM | 0.61M | 76.7 | 73.6 | -3.12 | -0.82 | +3.8 | 0.34 | 0.34 | -2.89 |
| 13 | ND | 0.24M | 76.4 | 73.3 | -3.11 | -1.79 | +1.6 | 0.33 | 0.17 | -0.67 |
| 14 | TX | 8.28M | 63.8 | 60.7 | -3.10 | -0.50 | +3.6 | 0.29 | 0.14 | -1.87 |
| 15 | ME | 0.47M | 68.2 | 65.1 | -3.08 | -1.15 | -0.0 | 0.00 | 0.00 | -1.62 |
| 16 | AL | 1.53M | 62.5 | 59.6 | -2.89 | -0.54 | +1.9 | 0.22 | 0.06 | -2.94 |
| 17 | MO | 2.06M | 57.9 | 55.0 | -2.87 | -0.77 | +0.9 | 0.33 | 0.06 | -2.66 |
| 18 | IL | 4.72M | 63.0 | 60.1 | -2.85 | -0.48 | +0.8 | 0.20 | 0.07 | -1.72 |
| 19 | KS | 0.99M | 70.2 | 67.4 | -2.83 | -0.60 | +2.3 | 0.47 | 0.19 | -2.11 |
| 20 | AZ | 2.19M | 88.2 | 85.5 | -2.71 | -0.36 | +1.1 | 0.27 | 0.20 | -1.24 |
| 21 | LA | 1.46M | 55.3 | 52.7 | -2.65 | -0.51 | +3.8 | 0.31 | 0.22 | -1.81 |
| 22 | NE | 0.70M | 69.8 | 67.2 | -2.63 | -1.16 | +1.2 | 0.18 | 0.07 | -1.67 |
| 23 | OR | 1.34M | 64.9 | 62.3 | -2.62 | -0.61 | +1.6 | 0.06 | 0.06 | -1.50 |
| 24 | VT | 0.22M | 72.6 | 70.0 | -2.61 | -1.05 | -0.9 | 0.29 | 0.07 | -0.45 |
| 25 | TN | 2.17M | 60.9 | 58.3 | -2.61 | -0.47 | -1.1 | 0.18 | 0.10 | -2.65 |
| 26 | VA | 2.74M | 39.1 | 36.6 | -2.51 | -0.52 | +1.3 | 0.41 | 0.16 | -1.30 |
| 27 | FL | 6.78M | 62.5 | 60.0 | -2.49 | -0.48 | +0.8 | 0.31 | 0.15 | -1.90 |
| 28 | IN | 2.34M | 58.6 | 56.2 | -2.40 | -0.60 | -0.1 | 0.22 | 0.10 | -2.41 |
| 29 | PA | 4.64M | 62.1 | 59.8 | -2.38 | -0.62 | +1.5 | 0.19 | 0.09 | -1.64 |
| 30 | AK | 0.21M | 82.0 | 79.7 | -2.29 | -0.33 | +2.6 | 0.31 | 0.31 | -2.22 |
| 31 | WI | 2.29M | 61.5 | 59.3 | -2.21 | -0.68 | +0.3 | 0.11 | 0.09 | -2.37 |
| 32 | CO | 1.87M | 48.5 | 46.3 | -2.20 | -0.44 | +2.2 | 0.36 | 0.13 | -0.37 |
| 33 | KY | 1.37M | 59.1 | 56.9 | -2.19 | -0.50 | +1.5 | 0.16 | 0.18 | -1.81 |
| 34 | MN | 2.17M | 55.1 | 53.0 | -2.11 | -0.55 | +2.0 | 0.34 | 0.09 | -0.72 |
| 35 | OK | 1.17M | 62.8 | 60.8 | -2.01 | -0.58 | +2.1 | 0.36 | 0.15 | -2.48 |
| 36 | WA | 2.27M | 70.7 | 68.7 | -2.01 | -0.38 | +1.5 | 0.26 | 0.08 | -2.16 |
| 37 | RI | 0.36M | 68.6 | 66.7 | -1.86 | -0.66 | -0.4 | 0.00 | 0.00 | -1.14 |
| 38 | NJ | 3.00M | 47.8 | 46.2 | -1.64 | -0.50 | +0.7 | 0.19 | 0.00 | -1.95 |
| 39 | MI | 3.41M | 55.6 | 53.9 | -1.63 | -0.43 | -2.1 | 0.04 | 0.09 | -1.44 |
| 40 | NY | 6.39M | 54.4 | 52.8 | -1.53 | -0.29 | -0.2 | 0.13 | 0.03 | -0.72 |
| 41 | CA | 12.70M | 66.8 | 65.3 | -1.49 | +0.22 | +0.7 | 0.23 | 0.04 | -1.69 |
| 42 | HI | 0.50M | 92.2 | 90.9 | -1.38 | -0.43 | +1.8 | 0.00 | 0.00 | -0.78 |
| 43 | NV | 1.08M | 94.2 | 93.1 | -1.06 | -0.33 | +1.3 | 0.21 | 0.20 | -0.19 |
| 44 | MD | 1.85M | 47.9 | 47.0 | -0.95 | -0.34 | -0.5 | 0.04 | 0.04 | -1.64 |
| 45 | NH | 0.47M | 63.4 | 62.9 | -0.54 | -0.08 | -0.3 | 0.20 | 0.00 | -3.24 |
| 46 | CT | 1.31M | 68.8 | 68.3 | -0.49 | -0.15 | -0.3 | 0.00 | 0.00 | -1.19 |
| 47 | OH | 4.31M | 56.4 | 56.0 | -0.42 | -0.04 | +0.0 | 0.10 | 0.05 | -2.38 |
| 48 | DE | 0.29M | 84.9 | 84.6 | -0.35 | -0.24 | -2.2 | 0.00 | 0.00 | -1.15 |
| 49 | MS | 0.83M | 53.4 | 53.2 | -0.16 | +0.05 | +3.1 | 0.56 | 0.10 | -2.53 |

## 4. Verdict

- 2006->2007: 43 of 49 states drop more than 1 pt, 36 more than 2 pts, 15 more than 3 pts; median -2.61 pts. In the five other transition years the median change is -0.38 pts and only 32 of 246 state-years drop more than 1 pt.
- 2008->2009: 41 of 49 states drop more than 1 pt, median -1.69 pts.
- MO/KS/IL rank MO 17, KS 19, IL 18 of 49 in the size of the 2007 drop.
- Residence-jump share, median across states: 2005 0.084, 2006 0.119, 2007 0.224, 2008 0.056; workplace-jump share: 2005 0.078, 2006 0.069, 2007 0.086, 2008 0.061.

**The 2007 step is national, not regional and not specific to MO/KS/IL.** Essentially every state's same-county share falls between data years 2006 and 2007 (only 0 of 49 states show no drop), the median drop (-2.61 pts) is roughly seven times the typical year-on-year change, the same-tract share falls in 47 of 49 states in the same year, and MO, KS and IL sit in the middle of the distribution (ranks 17, 19, 18 of 49). The largest drops are in low-density western and plains states (ID, WY, SD, UT, MT) and the smallest in DE, CT, NH, MD, MS and OH. The county-level signature matches: the share of counties whose resident-worker total jumps > 10 % is 0.08 (2005), 0.12 (2006) and 0.22 (2007) at the median state against 0.06-0.07 in 2008 and 2010, and 7, 15 and 23 states exceed 0.25 in 2005, 2006 and 2007 (2 in 2008, 0 in 2010), while the workplace-jump share stays at 0.08-0.09 with at most 5 states above 0.25. Workplace totals are stable in 2005-2007 everywhere; it is the residence side that moves.

**The 2009 step is also national but looks different.** The same-county share falls in every state (median -1.69 pts), but the same-tract share does not fall (19 of 49 states, median +0.08 pts), and in 2009 the workplace-jump share rises as much as the residence-jump share (medians 0.06 -> 0.15 vs 0.06 -> 0.21), with total workers down -5.2 % at the median state. The 2009 change therefore mixes the recession (real job losses that are geographically uneven) with a possible further residence or linkage change; it is not a clean replica of 2007.

**A further residence-side event in 2011.** The residence-jump share spikes again in 2010->2011 (median 0.26, 27 states above 0.25) with no workplace spike (0.09), and the same-county share drops by more than 1 pt in 17 states, concentrated in small rural states (WV, MT, VT, SD, ND, ME, AK). This is consistent with the end of the Composite Person Record era (1999-2010) and a change of residence inputs for 2011, and should be treated as another break, although a milder and more regional one than 2007.

## 5. Caveats

- Main files only (workers who live and work in the same state); interstate commuters are not included, so levels differ from the all-jobs JT00 main+aux series used elsewhere in this project (e.g. MO 2007 same-county share 55.0 % here vs 51.4 % in the JT00 series). The year-on-year changes are what matter here and they match (MO -2.9 pts in 2007 on both).
- JT02 = private primary jobs. Federal jobs are absent in every year, so the 2010 federal-jobs addition in JT00 does not affect this series.
- LODES 8 places every year on 2020 census blocks, so county and tract definitions are constant across years; Connecticut's 2022 planning regions are the 'counties' there (9 units).
- Missing: DC 2004-2009 (no files), MA 2004-2010 (files exist but are stubs of 1-4 records and were excluded), MA 2009 (404). Year-on-year changes are only computed where the previous year is present for the state.
- The county-jump statistic uses counties with >= 500 workers (residence basis for the residence share, workplace basis for the workplace share) in both years, so states with few counties (DE 3, HI 5, RI 5, CT 9) give coarse shares.
- Nothing here identifies the cause; the pattern (residence totals move, workplace totals do not, in every state at once, in a year with no documented LODES methodology change) is what points to a residence-input change on the LEHD side.
