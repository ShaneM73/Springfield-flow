# Literature review: methods for annual LODES commuting-flow analysis (2026-11-06)

Produced by a research subagent for this project; citations were checked against abstracts, publisher pages or full texts unless marked "from memory". The chosen parameters are in `springfield/phase3/METHODS.md`.

## 1. Identifying job centres in a time series

- Giuliano & Small 1991 (*Reg. Sci. Urban Econ.*): fixed cutoffs, 10 jobs/acre and 10,000 jobs. Giuliano, Redfearn, Agarwal, Li & Zhuang 2007, *Environment and Planning A* 39(12):2935, doi:10.1068/a393: fixed 10-10 and 20-20 cutoffs on harmonised tracts for 1980, 1990, 2000, reported as bounds; the system of centres was stable.
- **Ha, Lee, Kim & Hipp 2024**, *Cities* 145:104669, doi:10.1016/j.cities.2023.104669. Annual LODES WAC 2002–2019, blocks aggregated to 1-sq-mile hexagons (following Giuliano et al. 2019). Density cutoff = the 95th percentile within each year, 10,000-job size cutoff, candidates screened with McDonald–Prather density-gradient regressions, re-run for each of 18 years. A centre is "persistent" if more than half its area qualifies in every year.
- Kane, Hipp & Kim 2018, *Urban Studies* 55(4):844, doi:10.1177/0042098016678341. Point-based employment data, nonparametric method, 1997 vs 2014; only 43% of centre land area was in a centre in both years; persistence score labels centres stable, emerging or dying.
- McMillen 2001, *J. Urban Econ.* 50(3):448, doi:10.1006/juec.2001.2228: candidates are significant positive residuals from a locally weighted smooth of log density. Redfearn 2007, *JUE* 61(3):519: nonparametric method returning centroids and boundaries.
- **Arribas-Bel & Sanz-Gracia 2014**, *Urban Geography* 35(7):980, doi:10.1080/02723638.2014.940693. LISA on employment density for 359 US metros in 1990, 2000, 2010, including small ones; number of centres unchanged for 74.9% of metros (1990–2000) and 85.2% (2000–2010). Riguelle, Thomas & Verhetsel 2007, *J. Econ. Geogr.* 7(2):193, doi:10.1093/jeg/lbl025: local spatial autocorrelation subcentres in four medium-sized Belgian city-regions.
- Background: Agarwal, Giuliano & Redfearn 2012, *Ann. Reg. Sci.* 48:433; Hajrasouliha & Hamidi 2017, *Urban Geography* 38(3):420; Leslie 2010, *Int. Reg. Sci. Rev.* 33(2):205; Cladera, Marmolejo & Moix 2009, *Urban Studies* 46(13):2841.

**Choice:** local Moran's I on log job density (centred 3-year mean), queen contiguity, row-standardised, 999 permutations, p < 0.05; core = High-High or High-Low above the metro P90; contiguous cores merged; centre ≥ 2% of metro jobs; persistence ≥ 2 of 3 consecutive years; robustness with Ha et al.'s P95 rule.

## 2. Community detection on commuting flows

- **Nelson & Rae 2016**, *PLOS ONE* 11(11):e0166083. Tract-to-tract ACS 2006–10 flows, Combo (modularity), intrazonal flows and orphans removed, distance caps tested (160 km for maps, 262 km final), ≤ 50 communities, tuned by a visual coherence check.
- Farmer & Fotheringham 2011, *Environment and Planning A* 43(11):2723, doi:10.1068/a44136; De Montis, Caschili & Chessa 2013, *EPJ ST* 215:75; He, Glasser, Pritchard, Bhamidi & Kaza 2020, *PLOS ONE* 15(4):e0230941 (self-loops matter: ~90 US counties form single-county communities).
- Traag, Waltman & van Eck 2019, *Scientific Reports* 9:5233, doi:10.1038/s41598-019-41695-z (Leiden guarantees connected communities; Louvain yields up to 25% badly connected). Lancichinetti & Fortunato 2012, *Scientific Reports* 2:336 (consensus clustering).
- **Greene, Doyle & Cunningham 2010**, ASONAM pp. 176–183: Jaccard matching across time steps, θ ≤ 0.3 worked best, θ ≥ 0.5 inappropriate.
- From memory, not re-checked: Ratti et al. 2010 *PLOS ONE*; Thiemann et al. 2010 *PLOS ONE*; Leicht & Newman 2008 *PRL*; Fortunato & Barthélemy 2007 *PNAS*.
- No commuting paper was found that selects the Leiden resolution by ARI stability.

**Choice:** undirected w_ij = F_ij + F_ji, pairs ≥ 3 jobs, no self-loops (sensitivity with); Leiden modularity; γ fixed (scan 0.5–2.0 showed stable plateaus only at trivial or very fine resolutions, so γ = 1.0 was used with 100-seed consensus); Greene matching θ = 0.3.

## 3. LODES data inconsistencies

- **Graham, Kutzbach & McKenzie 2014**, CES-WP-14-38: each LODES year is produced independently; ~40% of jobs are at multi-unit employers and are imputed to establishments; the residence synthesiser's stratification broadened in **2009**; cells of 1–2 jobs are imputed.
- **Green, Kutzbach & Vilhuber 2017**, CES-WP-17-34: LODES shows longer commutes and lower within-county rates than the ACS (54.9% vs 72.5%), attributed to establishment assignment and headquarters reporting; 200-mile cap used.
- Spear 2011, NCHRP 08-36 Task 98: 97% of covered employment in reported establishments; 5.61% non-compliance among multi-unit employers.
- **McKinney, Green, Vilhuber & Abowd 2021**, *JSSAM*, doi:10.1093/jssam/smaa029: estimates very accurate for cells ≥ 10 jobs; 3–9 is a transition zone.
- LODESTechDoc 8.3 (Rev. 20241105): states without OD/WAC: AR, AZ, DC, MA, MS, NH in 2002; AZ, DC, MA, MS in 2003; DC, MA 2004–09; MA 2010. Missouri complete from 2002. Federal jobs enter JT00 in 2010; the Federal Employment Data Note adds the 2015 OPM suppression (−14% nationally, −8.4% in Missouri).
- No documentation of a 2006 residence anomaly was found; the documented break is 2009.

**Choice:** JT02 headline; JT00 2010+ with a 2015 flag; jump-and-revert tract-years flagged; 3-year centred means for centres; ≥ 3 jobs for network edges, ≥ 10 for pair inference; pairs > 100 miles flagged; 2009 level-shift test.

## 4. Flow trend classification

- Esri "How Emerging Hot Spot Analysis works": Mann–Kendall on each location's Gi* series; new / persistent (≥ 90% of steps) / intensifying / diminishing.
- Tao & Thill 2016, *Geographical Analysis* 48(4):355, doi:10.1111/gean.12100: flow K-function.
- No published paper was found that runs Mann–Kendall on each OD pair of commuting flows.

**Choice:** pairs with mean ≥ 10 (or first/last-5 mean ≥ 10); Hamed–Rao modified Mann–Kendall + Sen slope; Benjamini–Hochberg q < 0.05; classes new / fading / intensifying / declining / persistent / sporadic.

## Uncertain or unverified
- 2006 Missouri residence anomaly: undocumented.
- TechDoc 8.5 not read (8.3 was).
- No Census guidance on long-distance LODES commutes was found; practitioners use 50 (Graham, CTPP list) to 200 miles (Green et al. 2017).
- The 2% centre floor, the 50% jump flag, the ARI ≥ 0.90 plateau rule and the flow-class cutoffs are project proposals, not published standards.
