# D.P.U. 24-41 Road-Network Topology-Size Calibration Report

**Run date:** 2026-08-18
**Status:** Accepted on held-out seeds; road-network reference settings promoted

## Why recalibration was required

The previous accepted report used a deterministic synthetic calibration
network. The production website later changed to `data/road_grid.json`, whose
feeders and laterals follow OpenStreetMap roads. Because downstream customer
totals depend on network geometry, weights fitted to the synthetic network were
not valid evidence for the road network. No Census, weather, or D.P.U. target
data changed.

`12_calibrate_outage_sizes.js` now reconstructs the road network with the same
source-order substation matching, line ordering, and nearest-feeder lateral
attachment rule as `03_grid_simulation.html`. Source order is required because
the HIFLD data contain duplicate substation names. A regression test verifies
that duplicate names remain distinct and every lateral starts at its exact
feeder anchor.

## Method

The calibration network contains all 299 repository substations, 1,749
feeders, 8,137 laterals, and 185,571 candidate segments with a maximum length
of 0.075 km. Exactly 1,633,000 Census-derived customer accounts are allocated
to the rooted network. Each run selects 2,377 non-overlapping failures.

Customer accounts assigned directly to each segment are partitioned into
disjoint compact load groups. The deterministic repeated pattern is
`[1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 5, 8, 12, 15]`; a segment-keyed partial cycle
conserves the remainder. These are generic customer-sizing units, not asserted
equipment or damage types. Simulations do not sample final customer counts
from the target CSV. A network failure receives the integer sum of all
customers downstream, and ancestor/descendant overlaps are rejected.

The final search evaluated 40 feeder/small-group weight combinations while
lateral susceptibility remained the reference value of 1. The feeder grid was
extended down to 0.001 after the first corrected run placed its optimum at the
lower search boundary. The only fitting
objective was mean total-variation distance across the 13 target job shares on
calibration seeds 101, 211, 307, 401, and 503. Held-out seeds were 1009, 1103,
1201, 1301, and 1409. Customer-share statistics, quantiles, tail concentration,
and PCAO were excluded from the objective.

The acceptance limits were unchanged:

- Held-out mean job-share total variation at most 0.15
- Held-out maximum absolute bin error at most 0.10
- Held-out job share outside `[1, 4096)` at most 0.01

## Accepted reference settings

- Candidate length: 0.075 km
- Feeder susceptibility: 0.003
- Lateral susceptibility: 1.00
- Small customer-group failure weight: 0.80
- Maximum small-group size: 15 customer accounts

These settings were promoted only after passing all three held-out limits.

| Held-out metric | Result | Limit or target | Status |
|---|---:|---:|---|
| Mean job-share total variation | 0.1397 | ≤ 0.15 | Pass |
| Mean maximum absolute bin error | 0.0786 | ≤ 0.10 | Pass |
| Mean overflow job share | 0.00025 | ≤ 0.01 | Pass |
| Mean customer-share total variation | 0.2229 | Secondary only | Reported |
| Mean customers per job | 125.17 | Target 128.74 | Reported |
| Median customers per job | 12.6 | Target 16 | Reported |
| 90th percentile | 366.00 | Target 325 | Reported |
| 99th percentile | 1,223.63 | Target about 1,780 | Reported |
| Largest-1% customer share | 14.54% | Approx. 19% | Reported |

## Held-out job-share comparison

Values are averages over the five held-out seeds.

| Customers per job | Target | Simulated | Difference |
|---|---:|---:|---:|
| 1 | 0.21708 | 0.23315 | +0.01607 |
| 2 | 0.03450 | 0.04838 | +0.01388 |
| 3–4 | 0.06226 | 0.05646 | -0.00581 |
| 5–7 | 0.06437 | 0.06512 | +0.00076 |
| 8–15 | 0.10980 | 0.12486 | +0.01506 |
| 16–31 | 0.11695 | 0.03837 | -0.07859 |
| 32–63 | 0.11359 | 0.07244 | -0.04114 |
| 64–127 | 0.09676 | 0.10450 | +0.00774 |
| 128–255 | 0.06184 | 0.10728 | +0.04544 |
| 256–511 | 0.05217 | 0.08666 | +0.03450 |
| 512–1023 | 0.04081 | 0.04544 | +0.00463 |
| 1024–2047 | 0.02398 | 0.01506 | -0.00892 |
| 2048–4095 | 0.00589 | 0.00202 | -0.00387 |
| Outside 1–4095 | 0 | 0.00025 | +0.00025 |

## Interpretation and remaining limits

The shorter candidates represent possible break positions more precisely along
the road lines. This makes downstream totals change in smaller increments and
restores some of the intermediate job sizes that the 0.25 km road-network run
skipped. The component weights change how often eligible feeder, lateral, and
small-group failures are selected; they do not assign a desired size to an
individual outage.

Acceptance does not mean an exact match. The largest remaining difference is a
shortage of 16–31-customer jobs. Mean size is close to the supplied target,
while the largest-1% concentration is low. These remain reported validation
outputs and were not added to the fitting loss.

Individual website scenarios can differ from these neutral multi-seed averages
because weather and customer exposure change which locations are selected, and
the requested job count may differ from 2,377. The website therefore computes
the comparison again for every generated scenario.

PCAO remains independent and was not optimized. The current provisional UI
value assumes all generated failures are active before restoration starts, so
it is not yet directly comparable with the historical approximately-37 value.
