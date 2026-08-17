# D.P.U. 24-41 Customer-Outage Size Targets

This directory preserves the aggregate National Grid storm-job size targets
supplied by Dr. Dave Wanik for customer-impact calibration.

## Provenance

- **Underlying source:** National Grid regulatory filing, D.P.U. 24-41
- **Description supplied by advisor:** 2,377 storm jobs with a customer count
  for each job
- **Received from:** Dr. Dave Wanik by email
- **Received by project:** 2026-08-13
- **Repository purpose:** calibrate and validate topology-derived customers per
  synthetic outage

The original 2,377-row job list was referenced in the email but was not included
in the files received by this repository. These two aggregate CSV files are
therefore the preserved calibration source currently available to the project.

## Files

### `dpu31_size_target_bins.csv`

Thirteen customer-size bins with:

- `lo`: inclusive lower edge
- `hi`: exclusive upper edge
- `jobs`: number of jobs in the bin
- `job_share`: fraction of all jobs in the bin
- `cust_share`: fraction of summed customer-job impacts in the bin

The half-open convention `[lo, hi)` is the interpretation used by the automated
tests and future model comparison. It makes the first row the one-customer jobs
and the second row the two-customer jobs, consistent with the supplied 25th
percentile of two customers.

### `dpu31_size_target_quantiles.csv`

Eight percentile checkpoints from the supplied 2,377-job size distribution.
Fractional values at upper percentiles are ordinary interpolated quantiles;
individual simulated outage sizes must still be positive integers.

## Integrity checks

The committed values reproduce:

| Check | Value |
|---|---:|
| Jobs | 2,377 |
| Sum of job shares | 1.0 |
| Sum of customer shares | 1.0 |
| Implied customer-job impacts | 306,020 |
| Mean customers per job | 128.7421119058 |
| Jobs affecting at most two customers | 598 (25.1578%) |
| Jobs below 16 customers | 1,160 (48.8010%) |
| Jobs in 512-or-more bins | 168 (7.0677%) |
| Customer share from 512-or-more bins | 62.4230% |
| Jobs in 1,024-or-more bins | 71 (2.9870%) |
| Customer share from 1,024-or-more bins | 39.2772% |

`tests/dpu31_size_target_data.test.js` enforces these totals, bin continuity,
job-share arithmetic, quantile values, and the pre-change fixed-50 baseline.

## Received-file checksums

The advisor-supplied files in the original download location had these SHA-256
checksums:

```text
518cb24b2c1bbf94c476e152c593cc955aeec8196ce107edaca8338ecae1bfff  dpu31_size_target_bins.csv
0c0f57a08b88d9759852672c4a3337235469faba6d0b1f22c376415e2dd21473  dpu31_size_target_quantiles.csv
```

The repository copies preserve every parsed value. Line endings are normalized
to LF by the repository, so byte-level checksums may differ from the received
CRLF files.

## Pre-change reproducible baseline

Before topology-derived sizing, the authoritative JavaScript generator emits
exactly 50 customers for every outage. Evaluating 2,377 such jobs against the
target bins produces:

| Metric | D.P.U. target | Fixed-50 generator |
|---|---:|---:|
| Mean | 128.742 | 50 |
| Median | 16 | 50 |
| 25th percentile | 2 | 50 |
| 90th percentile | 325 | 50 |
| Share in `[32, 64)` | 11.3589% | 100% |
| Total-variation distance across 13 bins | 0 | 0.8864114430 |

At the time this baseline was recorded, the HTML replaced the generator's fixed
50 with a runtime population-per-segment approximation. That retired
post-processing is deliberately not used as the scientific baseline: it was not
emitted by the authoritative model, did not use a complete downstream tree, and
did not conserve unique customer inventory when feeder and lateral service
allocations overlapped. Production v4 scenarios now preserve topology-derived
variable counts end to end.

## Calibration reports

[`dpu31_topology_calibration_report.md`](dpu31_topology_calibration_report.md)
records the reproducible five-seed topology fit and five-seed held-out test.
After the rejected two-account baseline exposed a missing small-job scale, the
model added generic disjoint 1–15-account topology leaf groups. The final fit
passed all predeclared held-out thresholds and its reference settings were
promoted. The report also records the remaining mean and tail differences.

## Usage rule

The 13 `job_share` values are the primary calibration target. Customer shares,
mean, quantiles, and tail concentration are validation outputs. PCAO must not be
included in the calibration objective.
