# Springfield MSA: in-state + out-of-state flows and flow structure (Phase 3), 2026-11-06

JT02 (private jobs) unless stated. Methods and citations: `phase3/METHODS.md`. Tables: `phase3/*.csv`.

## Out-of-state commuters (new)
Every state's LODES aux file was screened for Missouri residents: 2,252 files, all SHA-256 verified. The metro's out-of-state links grew:

| | 2002 | 2010 | 2019 | 2024 |
|---|---|---|---|---|
| Metro residents working in other states | 1,115 | 2,919 | 4,664 | 4,906 |
| Residents of other states working in the metro | 1,922 | 2,996 | 5,737 | 6,091 |

- **Top destinations in 2024:** Kansas 1,360, Arkansas 1,229, Oklahoma 514, Texas 429, Illinois 231.
- **Self-containment** now counts residents working anywhere: 86.8 % in 2002, 78.1 % in 2024.
- **Gaps:** some out-of-state files don't exist (Michigan 2022–24, plus a few states in early years). Michigan is not a major Springfield destination.

## Job centres (LISA, persistent)
- **One persistent centre** every year: 32–38 contiguous Springfield tracts holding **48–61 %** of metro jobs (47.9 % in 2024).
- **Robustness (Ha et al. 2024 relative rule):** 2 centres every year, with a share falling from 24.2 % (2002) to 20.8 % (2024).
- **Conclusion:** both rules say **monocentric, with mild dispersion out of the densest tracts**. No suburban subcentre reaches 2 % of metro jobs under either rule.

## Commuting communities (Leiden, γ = 1.0, 100-seed consensus)
- **Count:** 5 communities in 2002–10, 4 in 2011–21, then 5 again in 2022–24, when the Strafford/eastern Greene community splits off again.
- **Persistent communities:** Springfield S, Springfield NE, Nixa (Christian Co.) and Bolivar (Polk Co.).
- **Modularity falls steadily: 0.17 → 0.12.** Commuting sub-regions are becoming less self-contained, so the metro is integrating into one commuting field.
- **Year-to-year agreement (ARI)** is usually 0.8–0.97 but **dips to 0.65–0.69 in 2009–2011**. That is the recession window, and also the documented 2009 LODES residence-model change; the two can't be separated.
- **Sensitivity:**
  - γ = 0.7 gives 2–3 communities that never change.
  - γ = 1.7 gives 21–30 neighbourhood clusters, rising over time.
  - Including self-loops changes partitions only modestly (ARI 0.70–1.00).

## Flow trends (Hamed–Rao Mann–Kendall + FDR)
| Scale | Pairs | New | Intensifying | Persistent | Declining | Fading | Sporadic |
|---|---|---|---|---|---|---|---|
| Metro (tract/county), all | 5,786 | 236 | 2,099 | 1,264 | 700 | 5 | 1,482 |
| Metro, excl. flagged | 4,452 | 101 | 1,550 | 1,037 | 553 | 4 | 1,207 |
| National (county), all | 701 | 54 | 454 | 94 | 13 | 1 | 85 |
| National, excl. flagged | 302 | 3 | 190 | 67 | 8 | 0 | 34 |

Flagged pairs are those over 100 mi or touching a reassignment tract.

- **Growth dominates:** intensifying flows outnumber declining ones about 3 : 1, and almost no flows fade. Classes use absolute counts, so the metro's 39 % job growth is part of this.
- **Most "new" national links don't survive the artefact check:** 51 of 54 are over 100 miles, consistent with headquarters reporting.

## Shocks
| | 2010 vs 2002–07 trend | 2021 vs 2014–19 trend | 2024 vs 2014–19 trend |
|---|---|---|---|
| Metro jobs | −9.6 % | −4.5 % | −1.0 % |
| In-commuters from MO | −12.8 % | +0.5 % | +8.5 % |
| In-commuters from other states | −9.3 % | −16.0 % | −21.3 % |
| Self-containment (pts) | −2.1 | −0.9 | −1.9 |

- **2009 level shift** (2002–19, HAC): jobs −10.5k (p < 0.001), self-containment −3.2 points (p = 0.001), distance-decay β −0.045 (p = 0.002). The result holds with 2006 excluded. It is confounded with the residence-model change.
- **Flow churn:** the volume share of pairs ≥ 10 that persist to the next year is usually about 0.92. It is lowest in 2009 (0.885) and 2011 (0.889); 2020 is 0.909.

## Answers so far, for Springfield (RQ1–3)
1. **Monocentric, not polycentric.** The commuting field is integrating (falling modularity, weaker distance decay) and reaching further outward (outer-MO share up), while one centre keeps about half of the jobs.
2. **The widening is real and mostly survives the artefact checks** (the 100-mile cap removes about a third of the distance increase). High earners and goods industries reach furthest. Most new long-distance links are probably artefacts.
3. **2008–09 reorganized flows more than 2020 did:** larger pre-trend gaps, the community-partition break, peak churn. By 2024, 2020 had left mainly a lasting drop in in-commuting from other states. The KC/STL comparison is next.
