# ACS work-from-home adjustment (script 09e_acs_wfh_adjust.py, 2026-11-07)

ACS B08007 codes a worker who worked at home in the reference week in the home county; LODES codes every job at the employer. Subtracting the B08301 worked-at-home count from the B08007 in-county count gives a second ACS series, "non-home workplace in county", which removes *all* home workers including those whose employer is in the county. The raw and adjusted ACS series therefore bracket the LODES convention ("employer in county"): raw ACS is an upper bound, adjusted ACS a lower bound. Universe check: B08301 and B08007 worker totals are identical in every county-year.

| | ACS raw | ACS adjusted | LODES | n counties |
|---|---|---|---|---|
| Slope 2010–2019, pts/yr, mean (weighted) | −0.02 (−0.02), n = 21 | −0.22 (−0.22), n = 9 | −0.25 (−0.22), n = 21 | |
| Cross-county correlation with the LODES slope | 0.45 | 0.81 | | |
| Change 2019→2021, pts, mean (weighted) | +5.1 (+6.0), n = 21 | −9.4 (−10.2), n = 6 | −0.9 (−0.7) | |
| Change 2019→2024, pts, mean (weighted) | +3.5 (+3.8), n = 21 | −4.9 (−5.5), n = 8 | −1.2 (−0.6) | |

Reading: in 2010–2019 the LODES drift sits at the lower edge of the ACS bracket, i.e. it is consistent with the growth of home-based work for employers outside the county (the ACS worked-at-home share rose from about 4 to 6 per cent over the decade in these counties). After 2020 LODES sits inside a much wider bracket (+3.8 to −5.5). The 2007 and 2009 steps are unaffected by this adjustment (worked-at-home share was flat at 3–4 per cent in 2005–2012).

Files: `acs_wfh_adjusted_vs_lodes.csv` (county-year), `acs_wfh_adjusted_summary.csv` (county summary).
