# Outage-Location Model: Code and Math Guide

This is an implementation map for reviewers and maintainers. It is deliberately
shorter than a paper methods section: it identifies the equations, assumptions,
tuning controls, and authoritative code without making validation claims.

## Where to start

| Question | Authoritative location |
|---|---|
| What are the reference defaults? | `DEFAULT_CONFIG` in [`outage_location_model.js`](outage_location_model.js) |
| Where are values validated? | `validateConfig` in [`outage_location_model.js`](outage_location_model.js) |
| How is Census exposure constructed? | [`11_fetch_census_population.py`](11_fetch_census_population.py), [`11_build_census_population_grid.js`](11_build_census_population_grid.js), then `buildCustomerExposureSurface` in [`outage_location_model.js`](outage_location_model.js) |
| What is the wind/rain equation? | `weatherSeverityScore` and `buildWeatherSeveritySurface` in [`outage_location_model.js`](outage_location_model.js) |
| How are hazard and customer consequence combined? | `buildCombinedImpactSurface` in [`outage_location_model.js`](outage_location_model.js) |
| How are network lines discretized and integrated? | `standardizeLineSegments`, `integrateNamedGridsAlongPath`, and `buildWeightedNetworkSegments` in [`outage_location_model.js`](outage_location_model.js) |
| How are unique locations sampled? | `sampleOutageScenario` and `sampleTimelineOutageScenario` in [`outage_location_model.js`](outage_location_model.js) |
| How does the UI map fields to model keys? | `MODEL_PARAMETER_INPUTS` in [`03_grid_simulation.html`](03_grid_simulation.html) |
| Where are the hover explanations? | `MODEL_CONTROL_HELP` in [`03_grid_simulation.html`](03_grid_simulation.html) |
| How does work move off the main browser thread? | [`outage_location_worker.js`](outage_location_worker.js) |
| What verifies the implementation? | [`tests/outage_location_model.test.js`](tests/outage_location_model.test.js), [`tests/outage_location_timeline.test.js`](tests/outage_location_timeline.test.js), and [`tests/outage_location_acceptance.test.js`](tests/outage_location_acceptance.test.js) |

`outage_location_model.js` is the sole authoritative implementation of the
outage-location mathematics. The HTML reads values and displays results; the
Worker transports inputs, progress, and outputs.

## Calculation chain

At grid location `x` and storm-frame time `t`, the relative hazard score is

```text
wind_damage(x,t)
    = [max(0, v(x,t) - v₀) / sᵥ]ᵖ

rain_amplification(x,t)
    = 1 + α × min(r₆(x,t) / r₀, r_max)

H(x,t) = wind_damage(x,t) × rain_amplification(x,t)
```

Here `v` is HRRR gust speed and `r₆` is the rolling six-hour HRRR
precipitation accumulation. This is a dimensionless relative stress score, not
an absolute component-failure probability.

For Census block `b`, let `P_b` be its 2020 population and let its Census
internal point fall between four HRRR grid nodes. The latitude and longitude
fractions give ordinary bilinear weights `w_bj`. After discarding nodes outside
the Connecticut land mask, the remaining weights are renormalized:

```text
raw population at node j = Σ over blocks b [P_b × w_bj / Σ valid k w_bk]
```

Thus each block contributes exactly `P_b` people and the grid total remains
3,605,944. This deterministic, storm-independent calculation is cached as a
41×65 grid. The raw block records remain available for auditing but are not
sent to the browser Worker.

Optional boundary-corrected Gaussian population smoothing can be applied after
allocation. The reference configuration uses zero additional population
smoothing: bilinear allocation already spreads each observation among nearby
nodes, blocks are much finer than the approximately 3 km target grid, and no
empirical evidence supports adding another bandwidth. Estimated customer
accounts are persons multiplied by the statewide population-to-customer ratio.
The relative consequence index is

```text
       estimated accounts at x
C(x) = ───────────────────────────────────────────────
       mean estimated accounts over all in-state cells
```

The unsmoothed impact-priority score is `H(x,t) × C(x)ᑫ`. A second
boundary-corrected Gaussian kernel produces `I(x,t)`, the spatially
regularized impact-priority surface.

Every feeder and lateral polyline is divided by chainage into candidates no
longer than the configured candidate length. Composite midpoint quadrature
integrates the selected surface along candidate `s`:

```text
failure weight:  W_failure(s,t) = λₛ × ∫ along s H(x,t) dx
impact weight:   W_impact(s,t)  = λₛ × ∫ along s I(x,t) dx
```

`λₛ` is the feeder or lateral susceptibility multiplier. The chosen
placement objective determines which weight is sampled. Sampling is without
replacement using deterministic segment-keyed exponential random keys, so a
fixed seed is reproducible and candidate-array reordering cannot perturb
unrelated random keys.

## Tuning controls

These are sensitivity controls, not fitted coefficients. The paper reference
configuration is the frozen `DEFAULT_CONFIG`.

| UI label | Configuration key | Reference value | Role |
|---|---|---:|---|
| Research placement objective | `placementMode` | `impact_weighted` | Selects impact-priority or failure-oriented segment weights |
| Wind threshold | `windThresholdMph` | 35 mph | Assigns zero wind damage at or below the threshold |
| Wind exceedance scale | `windExcessScaleMph` | 25 mph | Dimensional scale applied before the wind exponent |
| Wind exponent | `windExponent` | 2 | Controls concentration toward extreme gusts |
| Rain amplification | `rainCoefficient` | 0.5 | Controls spatial rain amplification; zero disables it |
| Rain-score cap | `rainScoreCap` | 2 | Caps the precipitation term |
| Exposure exponent | `exposureExponent` | 1 | Controls customer-consequence weighting in impact mode |
| Population smoothing | `customerSmoothingKm` | 0 km | Optional Gaussian standard deviation after block-to-grid allocation; zero disables it |
| Rural baseline fraction | `ruralBaselineFraction` | 0 | Optional synthetic uniform exposure for sensitivity analysis |
| Impact bandwidth | `gaussianBandwidthKm` | 10 km | Standard deviation for impact-surface regularization |
| Candidate length | `candidateSegmentLengthKm` | 1 km | Maximum length of a without-replacement network candidate |
| Line-integration step | `lineIntegrationStepKm` | 0.25 km | Maximum midpoint-quadrature spacing |
| Feeder susceptibility | `feederSusceptibility` | 1 | Relative feeder candidate multiplier |
| Lateral susceptibility | `lateralSusceptibility` | 1 | Relative lateral candidate multiplier |

The separate **Placement method** UI selector chooses the research model or the
explicit basic network-length fallback. It is orchestration state rather than a
scientific coefficient.

With a fixed outage count, changing `windExcessScaleMph` alone multiplies every
positive hazard weight by the same constant. That factor cancels when location
weights are normalized, so the scale changes score magnitude but not sampled
geography. It is exposed because it appears in the formula, but it is not an
independently identifiable spatial tuning parameter under this sampling design.

## Resolution and data-granularity handling

- HRRR wind and precipitation define the common approximately 3 km analysis
  grid and hourly timeline.
- All 49,926 Connecticut Census blocks are represented by Census internal
  points and mapped to that grid before any weather/customer combination;
  42,008 blocks have positive population.
- The production asset is an unsmoothed grid generated by the same
  `rasterizePopulationPersons` function used in tests. A regression test
  rerasterizes all blocks and requires cell-by-cell agreement.
- The land-only Connecticut mask prevents population or impact mass from
  being assigned to the state's maritime jurisdiction. The broader legal
  outline remains available for map display.
- Optional population smoothing and the separate 10 km impact smoother use
  normalized boundary convolution, so invalid cells do not dilute valid ones.
- Population is conserved exactly during allocation and is rescaled to its
  pre-smoothing total whenever optional smoothing is enabled.
- Bilinear interpolation evaluates grid surfaces along network polylines.
- Candidate length controls the sampling unit; integration step controls the
  numerical quadrature within that unit. They are intentionally separate.

### Population-bandwidth sensitivity

The block-derived reference surface was compared with optional Gaussian
standard deviations of 1.5, 3, and 6 km. Relative to zero smoothing, the
in-state surface correlations were 0.989, 0.899, and 0.758; top-decile-cell
Jaccard overlaps were 0.857, 0.634, and 0.467. Across ten fixed-seed Isaias
runs with 200 sampled outages, mean location-set overlaps were 0.9975, 0.991,
and 0.9675. All variants preserved 3,605,944 people. These results show that
6 km materially changes the exposure surface despite only modestly changing
the conditional sample, so the unfitted reference is zero and nonzero values
remain explicit sensitivity scenarios.

The NOAA storm-track layer is visualization only. Events without a complete
reviewed HRRR timeline require the explicitly labeled basic placement method;
the UI does not silently substitute algorithms.

## Changing or adding a control

1. Change the authoritative reference value in `DEFAULT_CONFIG`.
2. Update validation in `validateConfig` if the valid domain changes.
3. Add the HTML input and map it through `MODEL_PARAMETER_INPUTS`.
4. Add one concise entry to `MODEL_CONTROL_HELP`.
5. Add or update a sensitivity test showing the expected mathematical effect.
6. Run `npm test`.

Do not duplicate default values in the HTML. `resetOutageModelDefaults` reads
them from `OutageLocationModel.DEFAULT_CONFIG`, which keeps the UI, Worker, and
tests aligned.
