# D.P.U. 24-41 Topology-Size Calibration Report

**Run date:** 2026-08-13  
**Status:** Accepted on held-out seeds; reference settings promoted

## Method

`12_calibrate_outage_sizes.js` built a deterministic Connecticut calibration
network around all 299 repository substations, allocated exactly 1,633,000
Census-derived customer accounts, and generated 2,377 non-overlapping jobs per
seed. The network contained 1,495 feeders, 8,968 laterals, and 71,497 candidate
segments with a maximum candidate length of 0.25 km.

Customer accounts assigned directly to each lateral segment were partitioned
into disjoint compact load groups. The repeated deterministic group pattern is
`[1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 5, 8, 12, 15]`; a segment-keyed partial cycle
handles the remainder while conserving every account. These are generic sizing
units, not asserted transformer or damage-type labels. Simulation runs do not
sample their final customer counts from the target CSV. Larger network failures
still receive the exact sum of all customer accounts downstream of the selected
segment, and overlapping customer subtrees are rejected.

The final search evaluated 25 feeder/service weight combinations. Lateral
susceptibility remained the reference value of 1. The sole fitting objective
was mean total-variation distance over the 13 target job shares across
calibration seeds 101, 211, 307, 401, and 503. Held-out seeds were 1009, 1103,
1201, 1301, and 1409. Customer-share statistics, quantiles, tail concentration,
and PCAO were excluded from the objective.

Acceptance thresholds were recorded before tuning:

- Held-out mean job-share total variation at most 0.15
- Held-out maximum absolute bin error at most 0.10
- Held-out job share outside `[1, 4096)` at most 0.01

## Accepted reference settings

- Candidate length: 0.25 km
- Feeder susceptibility: 0.10
- Lateral susceptibility: 1.00
- Small customer-group failure weight: 0.75
- Maximum small-group size: 15 customer accounts

These settings were promoted to `DEFAULT_CONFIG` only after passing all three
held-out limits.

| Held-out metric | Result | Limit or target | Status |
|---|---:|---:|---|
| Mean job-share total variation | 0.1007 | ≤ 0.15 | Pass |
| Mean maximum absolute bin error | 0.0578 | ≤ 0.10 | Pass |
| Mean overflow job share | 0.0025 | ≤ 0.01 | Pass |
| Mean customer-share total variation | 0.1625 | Secondary only | Reported |
| Mean customers per job | 146.77 | Target 128.74 | Reported |
| Median customers per job | 14.2 | Target 16 | Reported |
| 90th percentile | 352.24 | Target 325 | Reported |
| 99th percentile | 1,929.48 | Target 1,779.64 | Reported |
| Largest-1% customer share | 23.18% | Approx. 19% | Reported |

## Held-out job-share comparison

Values are averages over the five held-out seeds.

| Customers per job | Target | Simulated | Difference |
|---|---:|---:|---:|
| 1 | 0.21708 | 0.21245 | -0.00463 |
| 2 | 0.03450 | 0.05124 | +0.01674 |
| 3–4 | 0.06226 | 0.06167 | -0.00059 |
| 5–7 | 0.06437 | 0.06243 | -0.00194 |
| 8–15 | 0.10980 | 0.13101 | +0.02120 |
| 16–31 | 0.11695 | 0.05915 | -0.05780 |
| 32–63 | 0.11359 | 0.08624 | -0.02735 |
| 64–127 | 0.09676 | 0.10501 | +0.00825 |
| 128–255 | 0.06184 | 0.09415 | +0.03231 |
| 256–511 | 0.05217 | 0.06841 | +0.01624 |
| 512–1023 | 0.04081 | 0.03837 | -0.00244 |
| 1024–2047 | 0.02398 | 0.02095 | -0.00303 |
| 2048–4095 | 0.00589 | 0.00639 | +0.00050 |
| Outside 1–4095 | 0 | 0.00252 | +0.00252 |

## Interpretation and remaining limits

The structural gap found by the first rejected fit is resolved well enough to
pass the frozen distribution limits. Adding compact topology leaf groups gives
the selector the missing small-job resolution, while finer lateral segments
provide more intermediate downstream totals. Most synthetic jobs are now small
and the network still produces an occasional long tail.

Acceptance does not mean an exact match. The largest remaining job-bin error is
the shortage of 16–31-customer jobs. Mean size and largest-1% concentration are
also somewhat high. They remain reported validation outputs and were not used
to change the declared fitting objective after results were observed.

Individual website scenarios can differ from the calibration-network averages
because weather and customer exposure change which network locations are
selected, and the requested job count may differ from 2,377. The website
therefore recalculates all bin and checklist statistics for every generated
scenario instead of displaying the calibration report as if it were that
scenario's result.

PCAO remains an independent output and was not optimized. In the current UI all
generated failures are assumed active at peak before restoration starts, so the
displayed PCAO* equals mean customers per job. It is therefore not yet directly
comparable with the historical approximately-37 value; concurrent failure and
restoration timing is still required for that comparison.
