# Browser-First Outage Location Model Migration and UI Integration

## Status and authority

Status: **complete — Phases W0 through W6 implemented and validated**

This document is the source of truth for migrating the weather- and
customer-weighted outage-location feature into the browser application. It
supersedes the Python-authoritative deployment decision in
`OUTAGE_LOCATION_IMPLEMENTATION_PLAN.md`.

The completed Python work served as temporary reference and validation
material. Phase W6 removed it after the browser model passed the parity and
end-to-end gates below; the frozen JSON fixture remains as archival evidence.

## Product outcome

A professor should be able to open `03_grid_simulation.html` or the hosted
GitHub Pages site and, without installing Python, starting a server, importing
JSON, or downloading files:

1. choose a supported storm;
2. change the random seed and outage-location model controls;
3. generate a reproducible set of network-constrained outages;
4. inspect the weather, customer-exposure, and combined-impact surfaces;
5. see the generated outage locations and totals on the map;
6. run the existing restoration simulator; and
7. inspect the restoration curve and summary.

The default scientific scenario remains 2,000 outage locations with exactly
50 customers per location, representing 100,000 customers without power.

## Fixed architecture decisions

### 1. One production implementation

- The authoritative production outage-location model will be
  `outage_location_model.js`.
- The website and automated JavaScript tests will execute that same file.
- Scientific equations must not be duplicated inside
  `03_grid_simulation.html`, the Web Worker, or the Python backend.
- The Worker is orchestration only: receive inputs, call the model, return
  progress/results.

### 2. Browser-first and server-independent generation

- Outage generation must work on GitHub Pages without the FastAPI server.
- The optional server may still be used by the existing restoration planner,
  but it is not required to generate or view the outage scenario.
- No user-facing JSON import/export step is part of the normal review flow.

### 3. Reuse the live in-memory distribution network

- The model will consume the `substations`, `feeders`, and `laterals` already
  created by `generateGrid()`.
- It will not generate a second network and will not require a separately
  downloaded network JSON file.
- Feeder, lateral, and substation indices must continue to match the existing
  restoration payload contract.

### 4. Run expensive work off the main thread

- Customer-surface construction, Gaussian smoothing, evaluation of roughly
  110,000 atomic network segments, and seeded sampling will run in
  `outage_location_worker.js`.
- The page must remain responsive, show real progress by stage, and allow a
  newer generation request to supersede an older one safely.
- If Web Workers are unavailable, the UI should show a clear unsupported
  message rather than freeze during a large synchronous fallback.

### 5. Preserve the validated version-one scientific model

Initial browser defaults remain:

- wind threshold: 35 mph;
- wind exceedance scale: 25 mph;
- wind exponent: 2;
- rain amplification: 50% per inch/hour;
- rain-score cap: 2;
- customer exposure exponent: 1;
- tract-centroid smoothing: 6 km;
- rural baseline: 2% of statewide mean exposure;
- final boundary-aware Gaussian bandwidth: 10 km;
- feeder susceptibility: 1.0;
- lateral susceptibility: 1.25;
- customers per outage: exactly 50.

The formulas remain:

```text
wind_damage = max(0, (wind_mph - 35) / 25) ^ 2
rain_amplification = 1 + 0.5 * min(rain_in_per_hour / 1.0, 2)
weather_severity = wind_damage * rain_amplification

relative_exposure = smoothed_customer_accounts / mean_in_state_exposure
raw_impact = weather_severity * relative_exposure ^ exposure_exponent
smoothed_impact = boundary_aware_gaussian(raw_impact, 10 km)

segment_weight = smoothed_impact_at_midpoint
                 * segment_length_km
                 * feeder_or_lateral_susceptibility
```

### 6. Do not retain two weather-driven placement algorithms

- The current HRRR `wind²` segment weighting and HURDAT2 Gaussian track-decay
  placement inside `simulateStorm()` will be removed after the new model is
  integrated.
- The storm-track overlay may remain for visualization.
- A storm with no usable HRRR wind-and-rain field may use an explicitly labeled
  **basic placement fallback**, but the UI must not describe that fallback as
  the weather/customer model.
- The UI must never silently switch modeling methods.

### 7. Separate outage generation from restoration realism

- The outage-location model owns location probability and assigns 50 customers
  to every generated outage.
- Existing restoration metadata such as critical-facility proximity,
  `sub_id`, `tree_blocked`, flood proximity, and callback lag may be attached
  after generation, provided they do not move the sampled point or change its
  initial 50-customer value.
- Existing storm-generation effects that currently remove candidates or set
  `popLoss` to zero (notably underground immunity and switching/back-feed)
  must not silently alter the scientific generator's count or customer-total
  contract. Their interaction will be made explicit in the UI and tested.
- Restoration continues to consume the existing `storm.outages` structure.

### 8. Delay cleanup until parity is proven

- Do not delete the Python reference before the JavaScript core, browser
  workflow, and restoration handoff pass their gates.
- Once those gates pass, remove the superseded Python production feature and
  its generated-only network/output artifacts in the same migration branch.
- Git history is the archive; redundant production code will not be kept “just
  in case.”
- `wind_rain_visualizer.py` is user-provided HRRR reference material and is not
  part of this cleanup.

## Exact integration points in the current website

### Existing code to reuse

- `generateGrid()` supplies the in-memory `substations`, `feeders`, and
  `laterals` arrays.
- `window.CONNECTICUT_CENSUS_TRACTS` supplies 883 tract populations and
  centroids.
- `window.CONNECTICUT_STORM_WIND` supplies the 41 × 65 HRRR coordinate grid and
  per-storm wind/rain fields.
- The boundary loaded by `loadBoundary()` supplies the Connecticut mask.
- `PointCloudLayer` remains the high-performance outage renderer.
- `storm.outages` remains the handoff to `planRestoration()`,
  `buildServerPayload()`, reports, exports, and the optional server scheduler.
- Existing storm and seed selectors remain the primary controls.

### Existing code to replace or revise

- Replace the placement portion of `simulateStorm()` with a call to the new
  Worker.
- Remove the existing `getHrrrWindMph()` duplicate after interpolation lives in
  the model module.
- Remove the current wind-field checkbox and its `wind²`/track-decay placement
  branches after the new UI is active.
- Remove the Python-only “Export network for Python outage model” control once
  browser generation uses the live network directly.
- Revise the `REAL_STORM_PRESETS` change handler. In research-model mode,
  choosing Isaias or another storm selects weather data but must not silently
  replace the user's requested outage count with the historical calibration
  count (for example, 20,450 for Isaias). Historical outage/crew presets should
  be a separate explicit action.
- Revise reset, storm-change, report, and status paths so model diagnostics and
  overlays never show stale results.

## Proposed files

- `outage_location_model.js`
  - Pure scientific functions with no DOM, Leaflet, network requests, or UI
    state.
  - Loads in browsers, Web Workers, and Node tests without separate copies.
- `outage_location_worker.js`
  - Worker message validation, cancellation/run IDs, progress events, typed
    array preparation, and calls into `outage_location_model.js`.
- `tests/outage_location_model.test.js`
  - Node standard-library unit and integration tests against the exact browser
    model.
- `package.json`
  - Minimal dependency-free `npm test` script if the repository does not
    already have a JavaScript test runner.
- `03_grid_simulation.html`
  - Controls, Worker orchestration, result mapping, diagnostic overlay, and
    existing restoration handoff only.

Files removed only after the cleanup gate:

- `outage_location_model.py`;
- `outage_restoration_integration.py`;
- `22_generate_outage_locations.py`;
- `tests/test_outage_location_model.py` and its Python-only package marker;
- `data/connecticut_network_seed42_f5.json.gz`;
- generated `output/outage_scenarios/` artifacts that are no longer part of
  the browser product; and
- the Python-only network export button/function in
  `03_grid_simulation.html`.

The broader server, data-fetching scripts, and `requirements.txt` remain
because they serve other existing project capabilities.

## Browser model contracts

### Model input

```text
config
  stormId, seed, nOutages, customersPerOutage
  windThresholdMph, windExcessScaleMph, windExponent
  rainReferenceIn, rainCoefficient, rainScoreCap
  customerSmoothingKm, ruralBaselineFraction, exposureExponent
  gaussianBandwidthKm
  feederSusceptibility, lateralSusceptibility

boundary
  Connecticut GeoJSON Polygon/MultiPolygon

censusTracts
  [{ geoid, pop, lat, lon }, ...]

weather
  { lats, lons, peak_wind_mph, peak_rain_in, units }

network
  substations, feeders, laterals using current in-memory indices
```

### Model output

```text
outages[]
  lat, lon
  kind, fi, li
  feeder_id, is_feeder, sub_id
  popLoss = 50
  local wind, rain, exposure, raw impact, smoothed impact
  segment length, susceptibility, normalized sampling weight

surfaces
  mask, customer exposure, weather severity
  raw impact, smoothed impact, probability

summary
  storm, seed, parameters
  candidate/sample counts
  feeder/lateral counts
  represented customers
  component totals and maxima
  generation-stage timings
```

Restoration-only metadata will be attached by a separate website adapter so
the scientific model remains testable and independent of UI realism toggles.

## Phase W0 frozen reference

The migration reference is
`tests/fixtures/outage_location_reference_v1.json`. It is generated by
`tests/build_outage_location_reference_fixture.py` and contains:

- the exact Python formulas and version-one defaults;
- SHA-256 identities for the boundary, census, weather, and network inputs;
- full default Isaias aggregate expectations;
- seven geographically distributed 41 × 65 surface checkpoints, including
  masked and in-state cells;
- a Python-only sampled-outage hash retained for archival traceability, not
  cross-language PRNG parity; and
- a complete, hand-auditable 3 × 3 boundary/census/weather/network fixture
  with expected component surfaces, eight weighted segments, and a three-point
  Python reference sample.

Default Isaias expectations frozen in W0 include:

- 883 census tracts and 1,633,000 estimated customer accounts;
- 41 × 65 grid with 1,576 valid Connecticut cells;
- 1,232 positive raw weather/impact cells and 1,576 positive smoothed cells;
- raw and smoothed impact total `378.88342686647`;
- 299 substations, 2,772 feeders, and 16,546 laterals;
- 110,789 positive-weight atomic segments;
- 29,603 feeder and 81,186 lateral candidate segments;
- feeder sampling-weight share `0.3891588381803497`; and
- 2,000 unique sampled segments, 777 feeder outages, 1,223 lateral outages,
  and exactly 100,000 represented customers.

JavaScript must match deterministic scientific surfaces and aggregate
contracts within documented numeric tolerance. Individual Python-sampled
coordinates are not required to match because the website will standardize on
its existing Mulberry32 generator; JavaScript determinism is tested against
itself after the port.

## Phase W0 current website mutation audit

| Current location | Current mutation | Effect on the new contract | Migration disposition |
|---|---|---|---|
| `oSlider` | Directly sets requested outage count | Intended user control | Keep; default becomes 2,000 in research mode |
| `REAL_STORM_PRESETS` storm-change handler | Silently replaces outage and crew sliders | Selecting Isaias changes 2,000 to 20,450 | Separate weather selection from an explicit historical-preset action |
| `seedInput` + `generateGrid()` | Changes synthetic feeder/lateral topology as well as storm realization | Same weather settings can have a different eligible network | Keep and document; scenario identity includes grid seed and feeders/substation |
| `fSlider` + `generateGrid()` | Changes network density and candidate segments | Valid, intentional network input change | Keep; invalidate any generated storm and surfaces |
| `windFieldWeighting` | Turns old weather placement on/off | Competing weather-driven generator | Remove and replace with explicit research/basic model selector |
| `getHrrrWindMph()` + HRRR `wind²` branch | Uses wind alone with a 0.05 floor | Does not match threshold/rain/customer/Gaussian model | Replace with authoritative module |
| HURDAT2 track-decay branch | Uses track distance and wind factor | Second weather-like placement method | Remove as a generator; retain track visualization only |
| `realisticMode` `popMultiplier` | Changes every outage from full segment load to half segment load | Produces variable customers instead of exactly 50 | Do not apply to research-model `popLoss` |
| Underground-line rejection in `simulateStorm()` | Rejects selected urban lateral candidates and retries | Changes scientific placement distribution | Do not apply after research sampling; model separately only after explicit scope change |
| Fenwick-tree exhaustion rebuild | Allows repeated segments when requested count exceeds candidates | Breaks uniqueness guarantee | Research model fails clearly when unique candidates are insufficient |
| Shared `rnd` stream in `simulateStorm()` | Placement, point position, tree status, critical fallback, switching, and AMI/callback draws share one stream | Toggling downstream realism can change later outage locations | Use a model-only PRNG stream; use separate deterministic streams for metadata |
| Critical-facility/fallback assignment | Sets `critical`; fallback consumes shared randomness | Metadata is valid, but must not perturb placement | Attach after sampling with a separate stream |
| Tree-blocked assignment | Sets `tree_blocked` and consumes shared randomness | Metadata is valid, but must not perturb placement | Attach after sampling with a separate stream |
| Flood-proximity assignment | Sets `near_flood_zone` | Metadata only | Keep in post-generation adapter |
| AMI/callback assignment | Sets `callback_lag_h` and consumes shared randomness | Metadata only, but currently perturbs later placement | Keep in post-generation adapter with a separate stream |
| Switching/back-feed draw | Marks some feeder outages `switch_restored` | Changes downstream queue and customers | Model as restoration behavior without changing the frozen initial 2,000 × 50 scenario |
| Post-loop switching block | Sets selected outages' `popLoss` to zero | Violates exact initial customer total | Remove from scientific scenario construction |
| `Math.min(totalCust, TOTAL_POP)` | Caps summed outage customers | Can hide an inconsistent per-outage total | Research total is exact `count × 50`; validate rather than cap |
| Real storm-report wind override | Replaces local `wind_mph` near reports | Affects repair severity metadata, not current placement | Keep separate from the frozen HRRR placement input and label clearly |
| `buildServerPayload()` priority mapping | Assigns make-safe tier to every 33rd outage | Changes dispatch order only | Keep in restoration adapter; test schema and totals |
| `loadLiveOutages()` | Replaces simulated storm with real current incidents and variable customers | Separate product mode | Preserve; exclude from research-generator contracts |

The audit establishes a strict boundary: the scientific model returns fixed
locations and 50-customer values; restoration metadata enrichment may not feed
randomness or mutations back into those results.

## UI design

### Primary controls

Reuse or clearly group these existing controls under **Storm outage model**:

- storm event;
- random seed;
- outage count, default 2,000; and
- a visible statement that each outage represents 50 customers.

Replace the current wind-field checkbox with an explicit placement selector:

- **Weather + customer exposure** — the research feature;
- **Basic placement (no complete HRRR field)** — explicit fallback only.

The research option is enabled only when the selected storm has valid wind and
rain arrays matching the HRRR grid. Unsupported storms show the missing input
and require the user to deliberately select the basic fallback.

Selecting a storm changes the weather field and displayed storm metadata. It
does not silently change the scientific outage count, customers per outage, or
other model parameters. Historical restoration calibration presets remain
available only through a separately labeled user action.

### Advanced scientific controls

Place these in a collapsed **Outage model parameters** panel:

- wind threshold;
- wind exponent;
- rain amplification;
- customer-exposure exponent;
- customer smoothing;
- rural baseline;
- final Gaussian bandwidth; and
- feeder/lateral susceptibility.

Include a **Reset scientific defaults** action. Changing a parameter marks the
current storm result stale until the user regenerates it.

### Review output

After generation, display without downloads:

- 2,000-point map layer;
- represented-customer total;
- feeder/lateral split;
- selected storm and seed;
- concise formula/parameter summary;
- generation runtime;
- a toggleable Leaflet raster overlay for customer exposure, weather
  severity, raw impact, and Gaussian-smoothed impact; and
- a legend whose scale does not normalize mild storms to appear severe.

The existing **Plan restoration** button then operates on the generated
`storm.outages`, and the existing restoration curve/report UI remains the
review surface for the downstream result.

## Migration phases

### Phase W0 — Freeze reference behavior

Status: **complete**

- [x] Record the Python default configuration and model equations as a golden
  reference fixture.
- [x] Save small deterministic fixtures for boundary, census, weather, and
  network calculations that are practical to inspect in tests.
- [x] Record default Isaias aggregate expectations: grid mask count, exposure
  total, raw/smoothed impact totals, positive support, 2,000/100,000 totals,
  and feeder/lateral validity.
- [x] Identify every current UI behavior that mutates outage count,
  `popLoss`, or placement after selection.

Implementation note: the 30 KB reference fixture is intentionally small enough
to review and load in Node tests. Its regeneration script recomputes the full
pipeline from current source inputs; automated tests fail if a source file,
formula, default, checkpoint, aggregate, network relationship, or deterministic
Python reference sample changes before the JavaScript parity gate is updated
deliberately.

Exit criterion: parity can be evaluated without running or preserving two
production implementations indefinitely.

### Phase W1 — Build the pure JavaScript model

Status: **complete**

- [x] Implement validated configuration and input contracts.
- [x] Implement boundary masking and interpolation.
- [x] Implement customer allocation, smoothing, rural floor, and conservation.
- [x] Implement wind/rain severity and component preservation.
- [x] Implement boundary-aware Gaussian impact smoothing.
- [x] Expand the browser network into atomic weighted segments.
- [x] Implement deterministic seeded sampling without replacement.
- [x] Return restoration-compatible identifiers and explainability fields.
- [x] Add Node tests for each scientific component.

Implementation note: `outage_location_model.js` is a dependency-free UMD
module shared by browser, Worker, and Node environments. It accepts both the
migration fixture's GeoJSON `[longitude, latitude]` polylines and the live
website's `{pts: [[latitude, longitude], ...]}` arrays. The W1 Node suite
checks the hand-auditable 3 × 3 reference component-by-component and rebuilds
the full default Isaias case: 1,576 in-state cells, 110,789 positive-weight
atomic segments, and 2,000 unique 50-customer outages. Cross-language surface
values and aggregate weights match the W0 reference within explicit floating-
point tolerances; browser sampling is deterministic under the existing
Mulberry32 generator rather than Python's unrelated PRNG stream.

Exit criterion: Node executes one dependency-free JavaScript module that
satisfies the scientific contracts and aggregate reference tolerances.

### Phase W2 — Add Web Worker execution

Status: **complete**

- [x] Define versioned request, progress, result, cancellation, and error
  messages.
- [x] Keep all expensive surface/segment work off the main thread.
- [x] Report real progress for exposure, weather, smoothing, weighting, and
  sampling stages.
- [x] Ignore stale results from superseded runs.
- [x] Verify errors are human-readable in the page rather than only in the
  console.

Implementation note: `outage_location_worker.js` uses the versioned
`connecticut_outage_worker_v1` protocol in both browser Web Workers and Node
worker threads. It yields between validated scientific stages so cancellation
and newer run IDs can be processed, while each expensive calculation remains
off the caller thread. Diagnostic grids are flattened into transferable
`Float64Array`/`Uint8Array` buffers for the future map UI. Worker results include
per-stage timings and the full restoration-compatible outage array; errors
include a readable message and failing stage. The actual-worker test suite
covers readiness, progress, typed transport, errors, cancellation,
supersession, and a responsive full Isaias generation.

Exit criterion: a full default generation completes without blocking map
interaction or control input.

### Phase W3 — Integrate controls, map, and diagnostics

Status: **complete**

- [x] Replace the legacy weather-placement control with the explicit model
  selector.
- [x] Add advanced scientific controls and reset-to-default behavior.
- [x] Validate supported storms dynamically from their wind/rain arrays.
- [x] Separate storm weather selection from the existing automatic historical
  outage/crew preset mutation.
- [x] Convert the live in-memory network to the Worker input contract.
- [x] Convert Worker output to `storm.outages` without changing location or
  50-customer values.
- [x] Reuse `PointCloudLayer` for outage rendering.
- [x] Add component surface overlays, fixed scales, legend, summary, loading,
  empty, stale, and error states.
- [x] Ensure storm/seed/grid changes invalidate old results and overlays.

Implementation note: `03_grid_simulation.html` now exposes the browser model as
the primary storm-generation workflow. It discovers complete HRRR storms from
the loaded data, requires an explicitly labeled network-length fallback for
unsupported historical events, and keeps historical outage/crew calibration
behind a separate button. The collapsed parameter panel reads defaults from
the authoritative JavaScript model. Worker results are validated at exactly
50 customers per point, adapted directly into `storm.outages`, rendered with
the existing point cloud, and paired with fixed-scale customer, weather, raw-
impact, and Gaussian-impact overlays. Browser verification covered default
Isaias, Henri, unsupported Sandy, the explicit basic fallback, surface
switching, stale parameter changes, default reset, explicit historical
presets, and a clean console.

Exit criterion: a professor can generate and inspect different supported
storms and parameter choices entirely through the website.

### Phase W4 — Restoration and feature-interaction integration

Status: **complete**

- [x] Attach critical, territory, tree, flood, and callback metadata in one
  explicit adapter after scientific sampling.
- [x] Confirm local restoration accepts the generated outage objects.
- [x] Confirm `buildServerPayload()` produces valid feeder, lateral,
  substation, priority, and tree fields.
- [x] Resolve hierarchy/specialization UI compatibility rather than allowing
  the known invalid combination silently.
- [x] Define and test how underground immunity and switching/back-feed interact
  with the required 2,000 × 50 initial scenario.
- [x] Verify customer totals before scheduling, through scheduling, and at the
  restoration curve endpoint.
- [x] Verify reports and exports identify the weather/customer placement model
  and include its parameters.

Implementation note: `outage_restoration_adapter.js` is the single
post-sampling enrichment boundary. Independent seeded streams attach critical,
tree, flood, callback/AMI, switching, underground, feeder, and territory data
without moving a point or changing its 50-customer value. Switching is an
explicit five-minute restoration event included in the initial curve total;
underground failures remain in the sample and receive a local 1.35× repair-time
modifier. The local scheduler now asserts a complete one-job-per-outage,
customer-conserving plan before rendering, and the curve independently rejects
any customer-total mismatch. Review-sized scenarios use a faster linear
nearest-job scan and the explicit callback metadata instead of double-counting
the older random discovery ramp. The server payload validates parent feeder,
substation, tree, specialization/hierarchy, and customer-total contracts; UI
behavior that the current server does not implement is routed transparently to
the browser planner. Reports and feature-collection exports include placement
model/configuration, restoration tags, planner source, and accounting totals.
Browser verification covered the default 2,000-point Isaias scenario, 100,000
initial customers, 250 automatic switching jobs, a zero-endpoint restoration
curve, report generation, and both hierarchy/specialization selections. A
second 2,000-point run with browser-only behaviors disabled completed through
the online Python backend in 916 ms; the returned 2,000-job curve retained the
100,000-customer initial total and rendered a zero endpoint.

Exit criterion: the generated browser scenario flows through local and
available-server restoration paths without manual conversion or inconsistent
customer totals.

### Phase W5 — Parity, performance, and professor-flow validation

Status: **complete**

- [x] Compare JavaScript component grids and aggregate metrics with the frozen
  Python reference.
- [x] Test determinism for identical storm/grid/config/seed inputs.
- [x] Test that changing weather, exposure, seed, and smoothing controls causes
  the expected measurable changes.
- [x] Test exact count, exact 50 customers per point, exact total, uniqueness,
  Connecticut geography, and network membership.
- [x] Test Isaias plus every other storm with complete HRRR wind/rain inputs.
- [x] Test unavailable-weather and invalid-input UI behavior.
- [x] Test desktop browser performance and confirm the main thread remains
  responsive throughout generation.
- [x] Test both server-online and server-offline restoration behavior.
- [x] Complete the hosted-site flow: open page → choose storm/controls →
  generate → inspect overlays → plan restoration → inspect curve.
- [x] Check browser console and network panel for errors.

Implementation note: `tests/outage_location_acceptance.test.js` adds control
sensitivity, seed, exact-customer, uniqueness, Connecticut-boundary, network
membership, and all-complete-HRRR-event gates on top of the frozen component
parity tests. The exact geography gate found two Isaias samples on feeder
segments that crossed the western state line; sampling now keeps the selected
network segment but deterministically retries positions along that segment
until the point is inside Connecticut. Seven complete HRRR events generate at
the default 35 mph threshold. The July 2026 field has an in-state maximum of
27.6 mph, so the UI now explains that the current threshold predicts no
positive in-state impact and offers two explicit choices: lower the scientific
threshold (validated at 20 mph) or select basic placement. It no longer fails
after generation begins.

The static-site browser flow was exercised from a clean page load through the
default 2,000-point Isaias scenario, all diagnostic overlays, and restoration.
Browser generation reported about 1 second of calculation time while the
Worker responsiveness test continued to receive main-thread ticks. The
threshold preflight caches the fixed Connecticut weather-grid mask; measured
storm and threshold changes completed in roughly 60–70 ms after page setup.
The offline route restored all 100,000 customers with 300 crews and 250 explicit
automatic-switch jobs, rendered a zero endpoint, and needed no server or file
handling. With browser-only features disabled, the optional hosted backend
returned the 2,000-job plan in 1.09 seconds and preserved the same initial and
zero-endpoint customer totals. Missing-weather, below-threshold, basic-mode,
and invalid-number guidance were exercised through the visible controls. The
browser console contained no warnings or errors after generation, overlay
changes, and both restoration routes.

Exit criterion: the full professor workflow is reliable, reproducible, and
requires no local setup or file handling.

### Phase W6 — Remove redundancy and finalize documentation

Status: **complete**

- [x] Remove the legacy wind²/track-decay weather placement implementation.
- [x] Remove the superseded Python outage-location production files and tests.
- [x] Remove the Python-only exported network artifact and UI control.
- [x] Remove obsolete generated scenario outputs.
- [x] Update README architecture, usage, file layout, formulas, limitations,
  and testing instructions.
- [x] Mark the original Python implementation plan historical/superseded.
- [x] Run all existing repository tests plus the new JavaScript and browser
  integration checks after cleanup.
- [x] Review the final diff to confirm unrelated project behavior and
  user-provided reference material were preserved.

Implementation note: the repository now has one maintained production
generator (`outage_location_model.js`), one orchestration Worker, and one
restoration metadata adapter. The old Python generator/CLI/adapter and their
tests, the exported network file, generated scenario directory, legacy browser
placement function, and network-download UI were removed. JavaScript tests now
build their review and 100,000-segment performance networks deterministically,
so full contract and responsiveness coverage no longer depends on a production
network export. `README.md` and `DATA_SOURCES.md` describe the final browser
architecture and honest limitations; the initial implementation plan and
methodology notebook are labeled historical. The user-provided
`wind_rain_visualizer.py`, weather inputs, statewide restoration server, and
scheduler were preserved.

Final regression: all 25 dependency-free JavaScript tests passed, inline HTML
JavaScript and notebook JSON parsed, and `git diff --check` passed. A clean
static-page browser run generated 2,000 unique outages and exactly 100,000
customers, confirmed the obsolete network-download control was absent, planned
2,000 restoration jobs with 300 crews plus 250 automatic-switch events, and
rendered a zero-customer endpoint with no browser warnings or errors.

Exit criterion: the repository contains one maintained scientific generator,
used directly by the website and its automated tests, with no obsolete Python
production duplicate.

## Automated acceptance matrix

| Area | Required checks |
|---|---|
| Configuration | defaults, validation, reset, stale-result invalidation |
| Customer exposure | 883 tracts, conserved accounts, mask, rural floor, population-center ordering |
| Weather | physical units, threshold, monotonicity, rain amplification, missing arrays |
| Gaussian impact | nonnegative, finite, masked, mass preservation, bandwidth behavior |
| Sampling | deterministic, weighted, without replacement, exact count, on-segment points |
| Restoration schema | `fi`, `li`, `feeder_id`, `is_feeder`, `sub_id`, priority/tree fields |
| Totals | 50 customers each, count × 50 before restoration, zero remaining at completion |
| UI | supported/unsupported storms, progress, errors, overlays, legends, reset, responsive controls |
| Compatibility | local scheduler, server scheduler when available, offline generation |
| Cleanup | no old weather generator, no Python production duplicate, no Python-only network export |

## Definition of done

The migration is complete only when all of the following are true:

- [x] One JavaScript scientific model is the sole maintained outage generator.
- [x] It runs in the website without Python or a backend.
- [x] The professor can change storm, seed, outage count, and scientific model
  parameters through clear controls.
- [x] Generation does not freeze the page.
- [x] The map and diagnostics explain why outages were placed where they were.
- [x] The default produces exactly 2,000 network outages and 100,000 customers.
- [x] The result feeds directly into the existing restoration UI.
- [x] Local and optional-server restoration paths preserve customer totals.
- [x] Automated JavaScript, existing repository, and browser integration tests
  pass.
- [x] The old weather placement and superseded Python production feature are
  removed.
- [x] No user-facing downloads, uploads, or JSON manipulation are required.
- [x] Monte Carlo and exponential-kernel comparison remain separate future
  work unless explicitly added to scope.

## Change control

If implementation reveals a needed change to a scientific equation, customer
contract, fallback policy, or restoration interaction:

1. stop at the current phase gate;
2. record the issue and proposed change in this document;
3. determine whether parity fixtures and previous generated results must
   change; and
4. obtain project-owner agreement before proceeding.
