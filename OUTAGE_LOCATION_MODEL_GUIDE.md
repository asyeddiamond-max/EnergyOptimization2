# Outage-Location Model: Code and Math Guide

This is an implementation map for reviewers and maintainers. It is deliberately
shorter than a paper methods section: it identifies the equations, assumptions,
tuning controls, and authoritative code without making validation claims.

## Where to start

| Question | Authoritative location |
|---|---|
| What are the reference defaults? | `DEFAULT_CONFIG` in [`outage_location_model.js`](outage_location_model.js) |
| Where are values validated? | `validateConfig` in [`outage_location_model.js`](outage_location_model.js) |
| How is Census exposure constructed? | `buildCustomerExposureSurface` in [`outage_location_model.js`](outage_location_model.js) |
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

Census tract population is bilinearly allocated from tract internal points to
the approximately 3 km HRRR analysis grid. It is then smoothed with a
Connecticut-boundary-corrected Gaussian kernel and rescaled to conserve its
in-state total. Estimated customer accounts are persons multiplied by the
statewide population-to-customer ratio. The relative consequence index is

```text
       smoothed estimated accounts at x
C(x) = ───────────────────────────────────────────────
       mean smoothed accounts over all in-state cells
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
| Customer smoothing | `customerSmoothingKm` | 6 km | Standard deviation for the Census exposure kernel |
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
- Census tract observations are mapped to that grid before any
  weather/customer combination.
- Both Gaussian smoothers are boundary-corrected so out-of-state cells do not
  dilute Connecticut values.
- The customer surface is rescaled after smoothing to preserve its in-state
  total.
- Bilinear interpolation evaluates grid surfaces along network polylines.
- Candidate length controls the sampling unit; integration step controls the
  numerical quadrature within that unit. They are intentionally separate.

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
