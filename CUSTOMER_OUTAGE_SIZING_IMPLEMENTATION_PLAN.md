# Customer-Outage Sizing Implementation Plan

**Status:** Phases 1–7 complete; topology-derived customer sizing passed held-out calibration
**Prepared for:** Alex Luo
**Advisor:** Dr. Dave Wanik
**Last updated:** 2026-08-18

## Purpose

This document defines how the simulator will assign customer counts to synthetic
outages so that outage size follows electrical topology and can be validated
against the National Grid D.P.U. 24-41 storm-job distribution supplied by Dr.
Dave Wanik.

It is the alignment document for this work. If implementation choices conflict
with it, either the implementation must be changed or this document must be
updated deliberately with the reason recorded.

## Advisor request, translated into requirements

The production outage-placement model must generate job sizes from the synthetic
network rather than assigning one fixed or independently sampled customer count
to every outage.

Required behavior:

1. Put customer load on the synthetic distribution network, with laterals
   serving nearby customers.
2. Define a network outage's size as the number of customers electrically
   downstream of the failed component; compact leaf-group failures use their
   disjoint attached customer load.
3. Make service and lateral failures usually small.
4. Make feeder and backbone failures occasionally affect hundreds or thousands
   of customers.
5. Tune component-class failure weights until the simulated job-size
   distribution resembles `dpu31_size_target_bins.csv`.
6. Use the quantiles and concentration statistics as validation checks.
7. Keep PCAO near 30--40 as a possible emergent result, not a value forced into
   the placement or sizing calculation.

The model must continue to determine outage geography from HRRR weather,
Census-derived exposure, and network lines. Customer sizing is a new downstream
topology calculation; it is not a revision to the Census-to-HRRR allocation.

## Supplied reference targets

### Primary calibration target

`dpu31_size_target_bins.csv` contains 2,377 National Grid storm jobs divided
into 13 size bins. For each bin it gives the number and share of jobs and the
share of all customer interruptions.

The target reconciles to:

- 2,377 jobs
- 306,020 summed customer-job impacts
- 128.742 customers per job on average
- 25.16% of jobs affecting no more than two customers
- 48.80% of jobs below 16 customers
- 7.07% of jobs in the 512-or-more bins producing 62.42% of customer impacts
- 2.99% of jobs in the 1,024-or-more bins producing 39.28% of customer impacts

The 13 job-count shares are the primary quantities to fit. Customer shares,
moments, quantiles, and tail concentration are validation outputs.

### Quantile checklist

`dpu31_size_target_quantiles.csv` supplies these percentile checks:

| Percentile | Customers |
|---:|---:|
| 10th | 1 |
| 25th | 2 |
| 50th | 16 |
| 75th | 80 |
| 90th | 325 |
| 95th | 706.2 |
| 99th | 1,779.64 |
| 99.9th | 2,915.02 |

Interpolated percentile values may be fractional even though individual outage
customer counts must be positive integers.

### Concentration checks

The supplied figure and advisor email give two additional checks:

- The smallest 50% of jobs produce approximately 1.8% of customer
  interruptions.
- The largest 1% of jobs produce approximately 19% of customer interruptions.

### Data currently not supplied

The aggregate targets are sufficient for bin calibration, but the following
referenced raw files are not currently in the repository:

- The original 2,377-row National Grid job list
- `isaias_daily_troublespots`
- `isaias_troublespots`

Their absence does not block the topology-sizing work. It limits independent
reproduction of the supplied aggregates and more granular Isaias analysis.

## Pre-implementation gap recorded at project start

The current repository has three incompatible customer-count stages:

1. `outage_location_model.js` requires `customersPerOutage === 50` and emits
   `popLoss: 50` and `customers: 50`.
2. `outage_restoration_adapter.js` validates and rewrites every outage as 50
   customers.
3. `03_grid_simulation.html` later replaces 50 with an approximate
   population-per-polyline-segment calculation.

The current network records feeder membership but not a complete electrical
tree. Laterals point to parent feeders, but feeder and lateral segments do not
have explicit parent/child relationships, customer load points, or exact
downstream customer sums. Feeder and lateral service allocations also overlap,
so the current geography-derived estimate is a consequence proxy rather than a
conserved inventory of unique customers.

The existing optional hierarchical restoration mode controls restoration
ordering. It does not supply the missing downstream topology for customer
sizing.

## Scope

### In scope

- An explicit rooted feeder/lateral/service topology
- Deterministic placement of Census-derived customer accounts onto that network
- Exact downstream customer totals for failure candidates
- Non-overlapping simultaneously active outage subtrees
- Variable customer counts carried unchanged through placement and restoration
- Calibration of component-class selection weights against the 13 DPU bins
- Statistical diagnostics and UI reporting
- Automated correctness, regression, acceptance, and performance tests
- Documentation and data provenance

### Out of scope for this workstream

- Changing Census-block-to-HRRR allocation
- Changing the land mask or population smoothing defaults
- Treating the synthetic grid as utility GIS topology
- Sampling production job sizes directly from the target bins
- Forcing every scenario's mean to exactly 128.742
- Forcing PCAO to a target value
- Calibrating restoration duration, crew counts, or discovery timing at the
  same time as job size
- Claiming utility-specific circuit accuracy without utility GIS and customer
  connectivity data

## Scientific and engineering principles

1. **Topology produces size.** The selected component identifies a downstream
   subtree; that subtree determines customer impact.
2. **Targets tune component selection, not individual sizes.** DPU data may
   tune feeder/lateral/service susceptibilities but may not overwrite the
   downstream sum.
3. **Customer inventory is conserved.** The network must hold an explicit,
   integer customer inventory derived from Census exposure.
4. **Simultaneous impacts are unique.** A customer may not be counted in two
   active outage jobs in one snapshot.
5. **Placement geography remains authoritative.** Weather, exposure, network
   geometry, and the configured placement objective continue to select where
   failures occur.
6. **Determinism is preserved.** Fixed inputs and a fixed seed must reproduce
   the same topology, candidates, selected locations, and customer sizes.
7. **Calibration and validation are separated.** Multiple seeds will be used
   for fitting and different seeds for validation.
8. **PCAO is reported, never optimized.** It remains an independent emergent
   check.

## Target network representation

Every feeder tree will be oriented away from its substation:

```text
Substation
└── Feeder/backbone segment
    ├── Feeder continuation
    └── Lateral segment
        ├── Lateral continuation
        └── Service/customer load
```

Required stable identifiers and relationships include:

- Substation ID
- Feeder ID
- Lateral ID, when applicable
- Topology segment ID
- Parent segment ID
- Ordered child segment IDs
- Component class: `service`, `lateral`, or `feeder`
- Feeder or lateral chainage
- Direct customer load
- Downstream customer load
- Rooted depth and subtree interval

Feeder polylines are already created from the substation outward. Lateral
polylines are already created from a feeder anchor outward. Grid generation
must preserve the selected feeder anchor index or chainage rather than retaining
only the anchor coordinate.

## Customer allocation design

### Source quantity

Customer load will come only from the existing precomputed Connecticut Census
population grid, converted using the project's statewide population-to-account
ratio. Synthetic uniform-area demand points used to improve geographic network
coverage must not create customer accounts.

### Allocation method

For every populated analysis-grid location:

1. Convert population mass to estimated account mass.
2. Identify nearby lateral segments within the applicable substation territory.
3. Allocate accounts among nearby laterals using a documented deterministic
   distance-based rule.
4. Place the lateral allocation at ordered service/load positions along the
   lateral.
5. Convert fractional allocations to integers using a largest-remainder method.

The final integer network inventory must reconcile exactly to the configured
statewide account total. The calculation must also report allocation distance
diagnostics so a synthetic line far from its assigned load cannot pass silently.

### Compact service representation

The browser does not need to draw or transport one object for every customer.
Service loads may use a compact representation with multiplicities or grouped
terminal records, provided that:

- One- and two-customer failure candidates remain representable.
- Downstream totals remain exact.
- Candidate sampling remains reproducible.
- The representation does not alter customer conservation.

## Downstream customer calculation

After customer loads are attached, a post-order traversal will calculate:

```text
downstreamCustomers(segment)
    = directCustomers(segment)
    + sum(downstreamCustomers(child) for every child segment)
```

An outage candidate's customer count is then:

```text
customers(outage) = downstreamCustomers(failed segment)
```

Expected qualitative results:

- Compact customer-group failure: 1–15 customers
- Terminal lateral failure: small customer count
- Lateral failure nearer its feeder: tens or hundreds
- Feeder/backbone failure: hundreds or thousands

## Non-overlap rule

Selected failures in one simultaneous scenario must form an antichain in the
topology: no accepted failure may be an ancestor or descendant of another
accepted failure.

Each segment will receive a depth-first subtree interval. Two selected subtrees
overlap when one interval contains or intersects the other. The sampler will
reject an overlapping candidate and continue down its deterministic ranked
candidate list.

Required scenario invariant:

```text
sum(outage.customers)
    == unique customers disconnected in the scenario
    == scenario.totalCustomers
```

If a requested outage count exceeds the non-overlapping capacity of the
generated topology, generation must fail with a clear diagnostic rather than
emit zero-size or overlapping jobs.

Multi-day sequential modeling may later permit related upstream and downstream
jobs at different times, but they may not claim the same customers
simultaneously.

## Placement and calibration design

The current segment-keyed exponential-race sampler will remain the basis of
weighted selection. Weather, exposure, line length, and placement mode will
continue to determine geographic candidate weight.

New component-class susceptibility controls will govern the relative frequency
of selecting:

- Service candidates
- Lateral candidates
- Feeder/backbone candidates

The reference configuration must state these parameters explicitly. They must
be validated, exposed as scientific sensitivity controls when appropriate, and
recorded in scenario output.

### Calibration procedure

1. Establish and save the current model's pre-change baseline distribution.
2. Generate the rooted topology and customer allocation without DPU tuning.
3. Measure the topology-only job-size distribution.
4. Run repeated 2,377-job scenarios over a fixed set of calibration seeds.
5. Tune only component-class susceptibility values.
6. Minimize error in the 13 target job-count shares, preferably using
   multinomial deviance or another documented full-distribution loss.
7. Freeze the chosen reference values.
8. Evaluate them on separate validation seeds.
9. Report all secondary statistics without adding them to the fitting objective.

If susceptibility weights alone cannot produce an adequate match, the
implementation must report the structural mismatch by bin. Network or service
granularity may then be reconsidered explicitly; direct sampling of target job
sizes is not an acceptable production fallback.

## Output contract

The scenario schema will be versioned when the fixed-50 contract is removed.
Each outage should carry at least:

```js
{
  componentClass: "service" | "lateral" | "feeder",
  directCustomers: 0,
  downstreamCustomers: 325,
  customers: 325,
  popLoss: 325,
  topologySegmentId: "...",
  parentSegmentId: "..."
}
```

`customers` and `popLoss` must be equal, positive integers. The model output is
authoritative; downstream adapters and UI code must preserve rather than
replace these values.

The scenario summary should include:

- Statewide network customer inventory
- Selected outage count
- Unique customers affected
- Mean and quantiles of outage size
- Target-bin job and customer shares
- Component-class counts
- Overlap rejection count
- Maximum downstream customer count
- Calibration parameter values
- Customer-allocation and sizing method identifiers

## File-level implementation map

### `outage_location_model.js`

- Extend network normalization with topology metadata.
- Build and validate the rooted segment tree.
- Allocate or consume explicit customer load records.
- Calculate post-order downstream totals.
- Add component-class weights.
- Apply the non-overlap rule during deterministic sampling.
- Emit variable customer counts and a versioned scenario contract.
- Compute size-distribution summaries.

This remains the authoritative location and topology-sizing implementation.

### `outage_location_worker.js`

- Add progress stages for customer allocation and topology sizing.
- Transport variable customer totals and sizing diagnostics.
- Keep snapshot and timeline paths behaviorally consistent.
- Preserve cancellation and responsiveness at statewide scale.

### `03_grid_simulation.html`

- Preserve feeder/lateral attachment chainage during grid generation.
- Include topology and load inputs in the Worker payload.
- Remove the `_segPop()` customer approximation.
- Treat model customer counts as authoritative.
- Add target-versus-simulated size diagnostics.
- Display PCAO separately from calibration metrics.

### `outage_restoration_adapter.js`

- Replace the fixed-50 validator with a variable-customer contract.
- Require positive integer and matching `customers`/`popLoss` values.
- Preserve customer counts while adding restoration metadata.
- Continue exact initial-versus-restored customer accounting.

### Restoration schedulers and server

- Confirm browser and server payloads preserve variable counts exactly.
- Ensure customer-priority logic consumes the new sizes.
- Keep scheduling policy outside the placement-size calibration objective.
- Add an optional largest-first benchmark only as a restoration experiment,
  not as a sizing mechanism.

### Tests

Update existing fixed-50 fixtures and add dedicated topology/customer-size test
fixtures. Target-data tests will read the repository copies of the supplied
CSV files.

### Documentation

Update `OUTAGE_LOCATION_MODEL_GUIDE.md`, `README.md`, and `DATA_SOURCES.md` when
the implementation lands. Document the synthetic-topology limitation and every
calibrated parameter.

## Validation outputs

The UI and automated evaluation should report:

- Job share in all 13 target bins
- Customer share in all 13 target bins
- Total-variation or equivalent distribution error
- Mean customer count
- Target quantiles
- Smallest-50% customer share
- Largest-1% customer share
- Service/lateral/feeder job shares
- Unique-customer conservation
- Count of candidate overlap rejections
- Results across calibration and held-out seeds

PCAO must appear in a separate independent-results section. Wanik et al. (2018),
Equation 2 defines PCAO as peak customers affected divided by total storm
outages. Until failure and restoration operate concurrently, the UI may report
only an asterisked provisional value: all generated failures are assumed active
at peak, so PCAO* equals mean customers per job and is not comparable with the
historical approximately-37 value. PCAO never enters the calibration loss.

## Required automated tests

### Topology correctness

- Every non-root segment has exactly one valid parent.
- Every lateral attaches to its declared feeder.
- Every feeder tree is acyclic and rooted at a substation.
- Post-order sums equal manually verified fixture totals.
- Missing parents, duplicate IDs, cycles, and invalid chainage fail clearly.

### Customer conservation

- Customer-account allocation preserves the statewide integer total exactly.
- Every direct and downstream count is a nonnegative integer.
- Every emitted outage count is a positive integer.
- Selected outage totals equal unique affected customers.

### Sampling

- Fixed seeds reproduce identical locations and sizes.
- Candidate-array reordering does not change results.
- No selected outage is an ancestor or descendant of another selected outage.
- Service, lateral, and feeder weighting changes have measurable and
  interpretable effects.

### Integration

- Worker and direct-model outputs agree.
- Snapshot and timeline paths use the same sizing rules.
- The restoration adapter does not alter customer counts.
- Browser and server payload totals match the generated scenario.
- Restoration ends with every outage restored and zero customers remaining.

### Statistical acceptance

- All target bins and quantiles are computed with correct boundary conventions.
- Calibration uses multiple seeds and reports seed-to-seed variability.
- Held-out validation results are saved or printed reproducibly.
- PCAO is absent from the optimization objective.

### Performance

- Customer allocation and downstream aggregation remain practical in the Web
  Worker.
- Large outage-count acceptance and Worker-responsiveness tests continue to
  pass.
- Compact service representation avoids creating excessive browser drawings or
  structured-clone payloads.

## Delivery sequence and gates

### Phase 1: Targets and baseline

**Status:** Complete; road-network calibration and performance reverified on
2026-08-18.

Deliverables:

- Repository copies of the supplied target CSV files in `data/validation/`
- Provenance and integrity documentation in `data/validation/README.md` and
  `DATA_SOURCES.md`
- Reproducible fixed-50 baseline and target-integrity tests in
  `tests/dpu31_size_target_data.test.js`

Gate: target totals and statistics reproduce the supplied values exactly.

### Phase 2: Rooted topology

**Status:** Complete on 2026-08-13.

Deliverables:

- Stable parent/child segment schema
- Feeder/lateral attachment chainage
- Topology validation and unit tests

Gate: every generated network is an acyclic forest rooted at substations.

Implemented as `connecticut_rooted_network_topology_v1` in
`outage_location_model.js`. Generated laterals now carry their feeder anchor
vertex into the Worker input; saved/legacy networks infer and validate the
anchor from the lateral origin. At this phase boundary the public scenario
still used the legacy fixed-50 count; Phases 3–5 subsequently replaced it.

### Phase 3: Customer allocation

**Status:** Complete on 2026-08-13.

Deliverables:

- Census-account allocation to nearby laterals
- Compact service/load representation
- Exact integer customer inventory

Gate: statewide account conservation and allocation-distance diagnostics pass.

Implemented as `connecticut_network_customer_allocation_v1`. The physical
inventory comes from the unsmoothed Census-derived account grid, independent
of optional exposure-smoothing experiments. Positive grid nodes split across up
to eight nearest distinct laterals in the nearest substation territory using
inverse-square distance weights, with an explicit feeder fallback for
territories that have no laterals. Largest-remainder rounding preserves exactly
1,633,000 integer accounts statewide. One compact load-point attachment is
retained per positive grid-node/lateral allocation, avoiding 1.633 million
individual browser objects. Research, hourly-timeline, and Basic Worker paths
publish conservation and allocation-distance diagnostics; Phase 5 carries the
resulting variable counts through restoration.

### Phase 4: Downstream sizing and overlap prevention

**Status:** Complete on 2026-08-13.

Deliverables:

- Post-order downstream sums
- Topology-derived outage sizes
- Non-overlapping selected subtrees

Gate: every scenario passes exact unique-customer accounting.

Implemented as `connecticut_topology_failure_selection_v1`. Network failure
sizes are the exact integer downstream sums produced in Phase 3. Compact
customer-group candidates partition a segment's direct load into disjoint
1–15-account groups and use lazy order statistics, so statewide selection does
not materialize an object for every customer. The calibrated deterministic
cycle is `[1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 5, 8, 12, 15]`; these groups are
generic topology leaf loads, not asserted equipment types. Rooted preorder
intervals reject ancestor/descendant network pairs and any group inside an
already selected network subtree. Tests prove account conservation,
deterministic order-invariant selection, zero customer-subtree overlap, and
exact unique-customer totals. Phase 5 migrated this selector into the public v4
contract.

### Phase 5: End-to-end contract migration

**Status:** Complete on 2026-08-13.

Deliverables:

- Versioned variable-customer scenario schema
- Worker, adapter, UI, browser scheduler, and server compatibility
- Removal of the fixed-50 and `_segPop()` production paths

Gate: restoration returns every generated outage and ends at zero customers.

Implemented with `connecticut_outage_scenario_v4` and
`connecticut_timeline_outage_scenario_v4`. Snapshot, hourly timeline, and Basic
placement all invoke the same topology-sizing selector. Each outage carries
matching positive integer `customers` and `popLoss`, plus direct, downstream,
component-class, and topology identifiers. The Worker transports allocation and
sizing diagnostics; the browser no longer runs `_segPop()` or overwrites model
counts; the restoration adapter preserves variable counts; and the server
requires a positive integer customer count. The full regression suite verifies
exact handoff totals, complete restoration, zero remaining customers, and
off-thread responsiveness on a 100,000-segment test network.

### Phase 6: Calibration and held-out validation

**Status:** Complete; road-network fit accepted on 2026-08-18 and reference settings frozen.

**Acceptance thresholds recorded before tuning:** The mean job-share total
variation distance over held-out seeds must be at most 0.15, no individual
target-bin job-share error may exceed 0.10, and the simulated share of jobs
outside the supplied `[1, 4096)` range must be at most 0.01. The calibration
objective is job-share total variation across all 13 bins. Customer-share
error, mean, quantiles, smallest-half share, largest-1% share, and PCAO remain
secondary outputs and cannot be added to the loss after results are seen.

Deliverables:

- Multi-seed component-weight calibration
- Frozen reference parameters
- Target-versus-simulated bin and tail report

Gate: the full distribution is acceptably close under a tolerance defined and
recorded before final tuning, and failures are reported by bin rather than
hidden by a single average.

The first 60-combination search used five calibration and five held-out seeds.
Its two-account representation failed held-out job-share TV (0.4515) and
maximum-bin-error (0.2156), showing a structural shortage of small jobs. Those
weights were not promoted.

The follow-up added generic 1–15-account topology leaf groups and spread each
lateral's customer allocation over its standardized segments. That fit was
valid for the deterministic synthetic calibration network, but became stale
when the website adopted the road-snapped grid. The calibration harness now
reconstructs the production road network exactly rather than silently testing
different geometry.

The road-network rerun contains 299 substations, 1,749 feeders, 8,137 laterals,
and 185,571 candidates at a 0.075 km maximum candidate length. The final
40-combination search reused the same calibration seeds, held-out seeds,
fitting objective, and acceptance limits. Its accepted reference settings are
feeder 0.003, lateral 1.00, and small-group 0.80. On held-out seeds it achieved
job-share TV 0.1397, maximum bin error 0.0786, and overflow job share 0.00025,
passing every frozen limit. Mean size (125.17 versus 128.74) and largest-1%
concentration (14.54% versus approximately 19%) remain reported differences,
not hidden or added to the objective after fitting. The complete saved report
is `data/validation/dpu31_topology_calibration_report.md`.

### Phase 7: UI, documentation, and performance

**Status:** Complete on 2026-08-13.

Deliverables:

- Customer-size validation panel
- Updated model guide, README, and data provenance
- Passing full test suite and performance checks

Gate: reviewers can trace every displayed customer count to topology and every
target statistic to a supplied source file.

Implemented with a generated-scenario validation panel that reports all 13
target-versus-simulated job shares, job-share total variation, mean, median,
largest-1% customer concentration, and overflow. PCAO* appears in a separate
independent-output notice with its numerator, denominator, current time-basis
limitation, and explicit warning that it is not comparable with approximately
37. It is not part of the pass/fail calculation. Model,
data-source, calibration-report, and alignment documentation now use the same
v4 terminology. The full 89-test suite passes, including exact restoration
accounting, exact cached-versus-uncached timeline equivalence, optimized-versus-
generic midpoint integration, and the 100,000-segment off-thread performance
case. The validated 0.075 km candidate length was retained. A production
browser check reduced the first Isaias run from approximately 27 seconds to
3.2 seconds and an identical rerun to 41 milliseconds through exact midpoint
reuse and layered in-memory Worker caching.

## Separate Isaias follow-up

The Isaias forwarded email describes a second model-validation problem and
must be implemented after customer sizing is stable.

Required temporal distinctions:

- `occurredAt`: physical failure time
- `reportedAt`: OMS discovery/report time
- `restoredAt`: repair completion time

The temporal model should reproduce the supplied daily quantities:

- 21,381 total trouble spots
- 21,381 total repaired spots
- 33.0% of eventual jobs known on August 4
- 73.35% known by August 8
- Peak backlog of 10,143 on August 7
- Peak daily repairs of 4,123 on August 9

It should not initialize all Isaias jobs at landfall or use one constant daily
repair rate. Crew shifts, discovery, repairs, remaining jobs, and customers
still out are separate time series.

This follow-up must not be used to retune the customer-size topology. It answers
when jobs become visible and are cleared; the present work answers how many
customers each job affects.

## Definition of done

This workstream is complete only when all of the following are true:

1. The production model no longer assigns or assumes 50 customers per outage.
2. The HTML no longer manufactures customer sizes after model generation.
3. Every outage size is an exact downstream topology sum.
4. Simultaneously selected outage customer sets do not overlap.
5. Customer inventory and restoration accounting reconcile exactly.
6. The simulated 13-bin distribution has been calibrated and evaluated on
   held-out seeds.
7. Mean, quantiles, tail concentration, and component-class mix are reported.
8. PCAO is reported independently and is not forced.
9. Tests, performance checks, documentation, and provenance are complete.
10. Limitations of synthetic topology and aggregate-only target data are stated
    plainly.

## Change-control checklist

Before making a customer-sizing change, answer:

1. Does this preserve topology-derived sizes?
2. Does this preserve exact customer inventory?
3. Can it create ancestor/descendant overlap?
4. Does it change outage geography or only customer sizing?
5. Is a target statistic being used for calibration or only validation?
6. Could the change force PCAO directly or indirectly?
7. Are fixed-seed determinism and Worker performance preserved?
8. Which tests and documentation must change with it?

If those questions cannot be answered, the change is not ready to merge.
