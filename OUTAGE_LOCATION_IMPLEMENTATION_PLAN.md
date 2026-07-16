# Weather- and Customer-Weighted Outage Location Generator

> **Historical implementation record:** The Python phases below were completed
> as scientific validation work, but the Python-authoritative deployment
> architecture is superseded by
> `OUTAGE_LOCATION_WEB_MIGRATION_PLAN.md`. Phase W6 removed the Python
> production files after browser parity and end-to-end validation passed. This
> document is retained only as a record of the initial scientific work.

## Purpose

This document is not an active implementation plan. The final architecture and
completed acceptance record live in `OUTAGE_LOCATION_WEB_MIGRATION_PLAN.md`.

The feature will generate one reproducible set of approximately realistic outage locations for Connecticut. These locations will be passed into the existing restoration simulator.

The first milestone is **one complete 2,000-location scenario**, not a Monte Carlo ensemble.

## Problem statement

Given a Connecticut storm's wind and rain fields and a representation of customer exposure, generate 2,000 plausible outage locations that:

- are more likely where damaging weather is severe;
- are more likely where more electric customers are exposed;
- lie on the modeled distribution network;
- retain feeder, lateral, and substation relationships needed by restoration;
- each initially represent exactly 50 customers without power;
- are reproducible from a saved configuration and random seed; and
- can be consumed by the existing restoration scheduler without manual editing.

## Fixed design decisions

These decisions describe the superseded Python phase and are preserved for
historical context only.

1. **One authoritative outage generator**
   - The scientific outage-generation model will be implemented in Python.
   - Its weather, exposure, smoothing, and sampling equations will not be duplicated in `03_grid_simulation.html`.
   - The current browser outage placement is legacy behavior and will not be extended into a second version of this model.

2. **Single scenario before Monte Carlo**
   - Version one generates one scenario for one storm and one seed.
   - Monte Carlo orchestration and distributional uncertainty are deferred until the single-run pipeline is validated.

3. **Network-constrained locations**
   - Outages will be sampled on feeder/lateral segments rather than sampled freely and snapped afterward.
   - The existing simulator network should be reused or exported in machine-readable form. A competing distribution-grid generator should not be introduced solely for this feature.

4. **Exactly 2,000 outage locations**
   - The initial default is 2,000 outage jobs.
   - The count remains configurable for testing and later experiments.

5. **Exactly 50 customers per outage in version one**
   - The default scenario represents 100,000 customers without power.
   - A variable customer-impact distribution is deferred.

6. **Wind is the primary weather driver**
   - Wind damage will use a nonlinear, threshold-aware transformation.
   - Rain will initially amplify wind/tree-related risk rather than independently dominate outage placement.
   - Physical units and explicit thresholds are preferred over event-specific min-max normalization.

7. **Customer exposure affects probability, not customers per job**
   - Census-derived customer density will influence where an outage is likely.
   - Every selected outage will still represent 50 customers in version one.

8. **Gaussian smoothing occurs before sampling**
   - The combined weather-and-exposure impact surface will be smoothed before it is evaluated on network segments.
   - Raw and smoothed surfaces will both be retained.
   - Smoothing must be Connecticut-boundary-aware to avoid probability bleeding outside the state.

9. **Explainability and reproducibility are required outputs**
   - Each outage will retain its local wind, rain, exposure, smoothed impact, and final sampling weight.
   - Each run will save its seed, parameters, input identifiers, and output totals.

10. **EAGLE-I is out of scope for this milestone**
    - No EAGLE-I acquisition, calibration, or validation work is required.
    - Validation against observed outages can be added later when appropriate access and data are available.

## Intended architecture

```text
Connecticut boundary       Census/customer data       HRRR wind and rain
          |                         |                         |
          |                         v                         v
          |               Customer exposure grid     Weather severity grid
          |                         |                         |
          +-------------------------+-------------------------+
                                    |
                                    v
                          Combined impact surface
                                    |
                                    v
                     Boundary-aware Gaussian smoothing
                                    |
                                    v
                  Interpolate impact onto network segments
                                    |
                                    v
                   Seeded sample of 2,000 outage points
                                    |
                                    v
               Add restoration and explainability metadata
                                    |
                                    v
                 JSON / CSV / GeoJSON / diagnostic figures
                                    |
                                    v
                       Existing restoration scheduler
```

## Proposed files

Names may be adjusted to fit the repository, but responsibilities should remain separated.

- `outage_location_model.py`
  - Pure, importable modeling functions.
  - No notebook-only commands and no UI logic.
- `22_generate_outage_locations.py`
  - Command-line entry point for generating one scenario.
- `tests/test_outage_location_model.py`
  - Determinism, geography, probability, count, and schema tests.
- `output/outage_scenarios/<scenario_id>/`
  - Generated scenario and diagnostics.
- Existing files should be modified only where necessary for network export/import or restoration integration.

## Input contract

### Required data

- Connecticut boundary polygon.
- Census-tract population or customer exposure data.
- HRRR grid coordinates.
- HRRR peak gust field in mph.
- HRRR rain field with its accumulation period documented.
- Modeled feeder/lateral network segments.
- Substation ownership or association for each segment.

### Required configuration

- Storm identifier.
- Random seed.
- Number of outage locations; default `2000`.
- Customers per outage; default `50`.
- Wind damage threshold.
- Wind nonlinearity exponent.
- Rain amplification coefficient.
- Customer exposure exponent.
- Gaussian bandwidth.
- Any feeder-versus-lateral susceptibility factors.

## Output contract

The main scenario JSON must contain run metadata and an `outages` list compatible with the backend `Outage` model.

Minimum outage fields:

```json
{
  "lat": 41.62,
  "lon": -72.71,
  "customers": 50,
  "critical": false,
  "feeder_id": 123,
  "is_feeder": 0,
  "priority": 0,
  "sub_id": 27,
  "tree_blocked": -1
}
```

Additional explainability fields should include:

- local wind in mph;
- local rain in the documented accumulation unit;
- local customer exposure;
- raw combined impact;
- Gaussian-smoothed impact;
- segment length;
- final segment sampling weight; and
- network segment identifier.

Each run should produce:

- `scenario.json` for restoration;
- `outages.csv` for tabular analysis;
- `outages.geojson` for mapping;
- `run_metadata.json` for complete reproducibility;
- `impact_surface.png` showing model components; and
- `sampled_outages.png` showing the final 2,000 points.

## Modeling outline

### Customer exposure

1. Load the 883 Connecticut census tracts.
2. Convert population to estimated customer accounts using the repository's existing population-to-customer ratio.
3. Place tract demand on the weather grid.
4. Smooth centroid-based demand into a continuous density surface.
5. Apply the Connecticut mask.
6. Include a small, documented rural baseline so rural failures are possible but less likely.

### Weather severity

The initial conceptual form is:

```text
wind_damage = max(0, wind_mph - wind_threshold) ** wind_exponent
weather_severity = wind_damage * (1 + rain_coefficient * rain_score)
```

Exact defaults must be documented and kept configurable. Wind and rain input units must be checked before calculation.

### Combined impact

The initial conceptual form is:

```text
raw_impact = weather_severity * customer_exposure ** exposure_exponent
smoothed_impact = boundary_aware_gaussian(raw_impact, sigma)
```

The implementation must preserve both surfaces.

### Segment sampling

1. Interpolate `smoothed_impact` at each feeder/lateral segment.
2. Calculate a sampling weight using impact and physical segment length.
3. Apply any documented feeder/lateral susceptibility factor.
4. Normalize valid segment weights.
5. Select 2,000 segments using a seeded random number generator.
6. Select a seeded position along each chosen segment.
7. Avoid duplicate selection of the same small segment where sufficient eligible segments exist.

## Implementation phases

### Phase 1 — Contract and network access

Status: **complete**

- [x] Define typed configuration and output schemas.
- [x] Determine the least invasive way to expose the existing network to Python.
- [x] Load boundary, census, HRRR, substations, and network segments.
- [x] Validate feeder/lateral/substation associations.
- [x] Add initial unit tests for loaders and schemas.

Implementation note: `03_grid_simulation.html` now exports its exact in-memory
network as versioned `connecticut_network_v1` JSON. IDs are zero-based to match
the restoration backend, coordinates use GeoJSON longitude/latitude order, and
`outage_location_model.py` validates that feeders begin at their owning
substations and laterals begin on their declared parent feeders. This preserves
one existing network generator while giving the authoritative Python outage
model a stable input contract.

Exit criterion: Python can load the Connecticut inputs and the same network relationships needed by restoration.

### Phase 2 — Customer-exposure surface

Status: **complete**

- [x] Convert census population to estimated customer accounts.
- [x] Rasterize demand to the common grid.
- [x] Smooth centroid-based demand.
- [x] Add and document the rural baseline.
- [x] Mask to Connecticut.
- [x] Produce customer-exposure diagnostics.
- [x] Test totals, bounds, and major population centers.

Implementation note: the 883 tract centroids are bilinearly allocated to the
41 x 65 HRRR grid, with border weights renormalized per tract so the raw grid
conserves all 1,633,000 estimated Connecticut customer accounts. A 6 km
mask-normalized Gaussian smooth removes centroid/grid spikes, a rural floor of
2% of mean cell exposure keeps every in-state cell possible, and the result is
rescaled to the same statewide total. The command
`python3 22_generate_outage_locations.py` reproduces the JSON, metadata, and
side-by-side raw/smoothed PNG diagnostic.

Exit criterion: The customer surface is geographically plausible and its estimated total is conserved within a documented tolerance.

### Phase 3 — Weather-severity surface

Status: **complete**

- [x] Load and validate wind and rain fields.
- [x] Implement threshold-aware nonlinear wind damage.
- [x] Implement rain amplification.
- [x] Preserve component grids.
- [x] Produce weather diagnostics.
- [x] Test monotonicity, missing data, and units.

Implementation note: the dimensionless wind score is
`max(0, (wind_mph - 35) / 25) ** 2`. One inch of one-hour rain adds 50%
amplification, capped at a rain score of 2 (a maximum 2x multiplier), and rain
does not create severity below the wind threshold. Diagnostics use fixed
physical scales rather than per-event normalization. The default Isaias HRRR
field produces a broad, plausible Connecticut footprint. The cached May 2018
field peaks at only 38.5 mph and therefore produces only three above-threshold
cells; this is recorded as an HRRR input-resolution/cached-data limitation, not
hidden by lowering the threshold or scaling that event to an artificial maximum.

Exit criterion: The severity surface follows the known storm footprint and does not exaggerate mild weather through relative normalization.

### Phase 4 — Combined and Gaussian-smoothed impact

Status: **complete**

- [x] Combine weather severity and customer exposure.
- [x] Implement boundary-aware Gaussian smoothing.
- [x] Retain raw and smoothed surfaces.
- [x] Normalize valid probabilities.
- [x] Produce side-by-side diagnostics.
- [x] Test nonnegativity, finite values, masking, and approximate mass preservation.

Implementation note: smoothed customer accounts are divided by the mean valid
Connecticut grid-cell exposure to form an interpretable dimensionless exposure
factor. Raw impact is `weather_severity * relative_exposure ** exponent`, with
an initial exponent of 1. A 10 km mask-normalized Gaussian smooth creates the
final impact surface, is rescaled to preserve raw impact mass, and is normalized
to exactly one for sampling. For default Isaias, raw and smoothed impact both
sum to 378.883427; smoothing expands positive support from 1,232 to all 1,576
in-state grid cells while leaving every out-of-state cell at zero.

Exit criterion: The surface visibly and numerically favors locations where damaging weather and customer exposure overlap.

### Phase 5 — Sample 2,000 network outages

Status: **complete**

- [x] Interpolate smoothed impact onto network segments.
- [x] Include physical segment length in weights.
- [x] Perform deterministic seeded sampling.
- [x] Place points on selected segments.
- [x] Assign exactly 50 customers per point.
- [x] Attach restoration and explainability metadata.
- [x] Export JSON, CSV, GeoJSON, metadata, and maps.
- [x] Test count, total customers, geography, network validity, and reproducibility.

Implementation note: the exact browser-generated seed-42/five-feeder network is
stored as `data/connecticut_network_seed42_f5.json.gz` (299 substations, 2,772
feeders, and 16,546 laterals). Its polylines expand to 110,789 positive-weight
atomic segments. Each segment weight is `smoothed_impact * length_km *
susceptibility`, with initial factors of 1.0 for feeders and 1.25 for laterals.
Efraimidis-Spirakis weighted sampling without replacement selects 2,000 unique
segments reproducibly, then places one seeded point along each segment. The
default Isaias seed-42 run produces exactly 2,000 in-state network points and
100,000 represented customers, with valid zero-based feeder/substation parent
relationships and matching JSON, CSV, GeoJSON, metadata, and PNG outputs.

Exit criterion: One seed produces exactly 2,000 valid network outage locations representing exactly 100,000 customers.

### Phase 6 — Restoration integration

Status: **complete**

- [x] Submit the generated scenario to the existing scheduler.
- [x] Confirm `sub_id`, hierarchy, priority, and specialization fields behave correctly.
- [x] Verify scheduler input/output customer totals.
- [x] Generate the restoration curve and final runtime summary.
- [x] Document a one-command reproducible workflow.

Implementation note: `outage_restoration_integration.py` adapts the generated
scenario to the existing `07_server.py` `ScheduleRequest` contract and calls
the same schedule endpoint function used by the FastAPI backend. It requires
the Numba backend rather than silently accepting the NumPy fallback because
the latter does not implement hierarchical energization. The initial run uses
450 crews, the rounded scale-equivalent of the simulator's 4,500-crew/20,450-
outage Isaias calibration. Realistic mode and feeder hierarchy are enabled;
crew specialization, tiered priority, customer-weighted dispatch, and crew
stickiness are available as CLI options but default off so the first result
isolates the new outage-location input. All generated points have normal
priority and leave `tree_blocked=-1`, allowing the existing backend to assign
tree status only when specialization is explicitly enabled.

The adapter explicitly prevents specialization and hierarchy from being
enabled together. The existing backend partitions tree and line outages into
independent sub-schedulers before applying feeder gating, which can otherwise
energize a lateral before a parent-feeder fault in the other partition clears.
Specialization is verified with `--crew-specialization --no-hierarchical`, and
hierarchy is verified in the default run. Repairing that upstream composition
behavior is restoration-model work and is outside this location-feature
milestone; the guard prevents a silently invalid result in the meantime.

The default scenario is accepted without editing and returns all 2,000 jobs.
It preserves exactly 100,000 input/restored customers and reaches complete
restoration at 96.0 simulated hours. The command writes
`restoration_result.json`, `restoration_curve.csv`, and
`restoration_curve.png`, and adds the scheduler settings, runtime, milestones,
and customer checks to `run_metadata.json`. Automated integration tests also
confirm that lateral energization cannot precede the sampled parent feeder's
clear time.

After installing `requirements.txt` in `.venv`, the reproducible one-command
workflow is:

```text
.venv/bin/python 22_generate_outage_locations.py
```

Exit criterion: A generated scenario is accepted by the restoration simulator without manual editing and produces a complete restoration result.

### Deferred phase — Monte Carlo and kernel comparison

Status: **deferred**

- Repeat location sampling with multiple seeds.
- Compare Gaussian and exponential smoothing.
- Add uncertainty in coefficients or customers per outage only after justification.
- Report spatial and restoration-time distributions.

## Cross-phase acceptance criteria

The first milestone is complete only when all of the following are true:

- [x] One command generates a complete scenario.
- [x] The scenario contains exactly 2,000 outage points.
- [x] The scenario represents exactly 100,000 customers.
- [x] All points lie inside Connecticut and on valid network segments.
- [x] Each point has feeder and substation metadata needed by restoration.
- [x] A fixed configuration and seed reproduce byte-equivalent core outage data.
- [x] Weather and customer exposure both measurably influence placement.
- [x] Raw and smoothed impact surfaces are saved.
- [x] Model parameters and data identifiers are saved with the run.
- [x] The existing restoration scheduler accepts the scenario.
- [x] Automated tests pass.
- [x] No second implementation of the scientific generator is added to the browser.

## Validation and review gates

Before proceeding beyond each surface-building phase, inspect the generated maps:

1. **After Phase 2:** verify the customer surface resembles Connecticut settlement patterns.
2. **After Phase 3:** verify the weather surface resembles the selected storm footprint.
3. **After Phase 4:** verify high impact occurs where weather and exposure overlap.
4. **After Phase 5:** verify sampled outages visually follow the impact surface without implausible snapping or border artifacts.
5. **After Phase 6:** verify customer totals and restoration metadata remain consistent through scheduling.

If a review gate fails, correct that phase rather than compensating with later sampling or restoration parameters.

## Explicit non-goals for the first milestone

- EAGLE-I acquisition or validation.
- Monte Carlo ensembles.
- Exponential-kernel comparison.
- Variable customers per outage.
- Fitting parameters to observed outage data.
- Replacing the restoration scheduler.
- Building a second distribution network.
- Duplicating the Python model in JavaScript.
- Turning the reference HRRR GIF notebook/script into production code.

## Change-control notes

When implementation reveals that an agreed decision must change:

1. Record the reason in this document.
2. Update the affected fixed decision, phase tasks, and acceptance criteria.
3. Note whether existing generated scenarios must be regenerated.
4. Obtain project-owner agreement before making a material modeling change.

Implementation progress should be recorded by updating phase status and checkboxes in this document as work is completed.
