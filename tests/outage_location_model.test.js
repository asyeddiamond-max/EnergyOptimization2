"use strict";

/*
 * Author: Alex Luo (@alexl1239) -- original design and implementation,
 *   feature/outage-location-simulator.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const model = require("../outage_location_model.js");

const ROOT = path.resolve(__dirname, "..");
const fixture = JSON.parse(fs.readFileSync(
  path.join(__dirname, "fixtures", "outage_location_reference_v1.json"), "utf8",
));
const small = fixture.small_deterministic_reference;
const tolerance = (actual, expected, relative = 2e-12, absolute = 2e-12) => {
  const difference = Math.abs(actual - expected);
  assert.ok(
    difference <= Math.max(absolute, Math.abs(expected) * relative),
    `${actual} differs from ${expected} by ${difference}`,
  );
};
function compareGrid(actual, expected, relative = 2e-12) {
  assert.equal(actual.length, expected.length);
  for (let row = 0; row < expected.length; row += 1) {
    assert.equal(actual[row].length, expected[row].length);
    for (let column = 0; column < expected[row].length; column += 1) {
      tolerance(actual[row][column], expected[row][column], relative);
    }
  }
}
function pythonConfigToJs(config) {
  return model.validateConfig(config);
}
function smallSurfaces() {
  const input = small.input;
  const config = pythonConfigToJs(input.config);
  const weather = model.normalizeWeather(input.weather);
  const customer = model.buildCustomerExposureSurface(
    input.boundary, input.census_tracts, weather.latitudes, weather.longitudes,
    { smoothingKm: config.customerSmoothingKm, ruralBaselineFraction: config.ruralBaselineFraction },
  );
  const severity = model.buildWeatherSeveritySurface(input.weather, customer.connecticutMask, config);
  const impact = model.buildCombinedImpactSurface(customer, severity, config);
  return { config, customer, severity, impact };
}

test("configuration has frozen defaults and rejects invalid inputs", () => {
  assert.equal(model.DEFAULT_CONFIG.nOutages, 2000);
  assert.equal(model.DEFAULT_CONFIG.customersPerOutage, undefined);
  assert.equal(model.DEFAULT_CONFIG.customerSmoothingKm, 0);
  assert.equal(model.DEFAULT_CONFIG.ruralBaselineFraction, 0);
  assert.equal(model.DEFAULT_CONFIG.placementMode, "impact_weighted");
  assert.equal(model.DEFAULT_CONFIG.candidateSegmentLengthKm, 0.25);
  assert.equal(model.DEFAULT_CONFIG.lineIntegrationStepKm, 0.25);
  assert.equal(model.DEFAULT_CONFIG.lateralSusceptibility, 1);
  assert.equal(model.DEFAULT_CONFIG.feederSusceptibility, 0.1);
  assert.equal(model.DEFAULT_CONFIG.serviceFailureWeight, 0.75);
  assert.equal(model.DEFAULT_CONFIG.serviceGroupMaximumCustomers, 15);
  assert.equal(model.validateConfig({ n_outages: 3 }).nOutages, 3);
  assert.throws(() => model.validateConfig({ customersPerOutage: 49 }), model.InputValidationError);
  assert.throws(() => model.validateConfig({ gaussianBandwidthKm: 0 }), model.InputValidationError);
  assert.equal(model.validateConfig({ customerSmoothingKm: 0 }).customerSmoothingKm, 0);
  assert.throws(() => model.validateConfig({ customerSmoothingKm: -0.1 }), model.InputValidationError);
  assert.throws(() => model.validateConfig({ placementMode: "probability" }), model.InputValidationError);
  assert.throws(() => model.validateConfig({ typoBandwidthKm: 10 }), model.InputValidationError);
});

test("boundary masking treats edges as inside and holes with even/odd semantics", () => {
  const polygonWithHole = {
    type: "Polygon",
    coordinates: [
      [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
      [[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]],
    ],
  };
  assert.equal(model.pointInBoundary(polygonWithHole, 0, 2), true);
  assert.equal(model.pointInBoundary(polygonWithHole, 2, 2), false);
  assert.equal(model.pointInBoundary(polygonWithHole, 3.5, 3.5), true);
  assert.equal(model.pointInBoundary(polygonWithHole, 5, 5), false);
});

test("small customer allocation, Gaussian smoothing, rural floor, and conservation match Python", () => {
  const { customer } = smallSurfaces();
  const expected = small.expected.customer_surface;
  assert.deepEqual(customer.connecticutMask, expected.connecticut_mask);
  tolerance(
    customer.totalCustomerAccounts,
    customer.totalPopulationPersons * model.POPULATION_TO_CUSTOMER_RATIO,
  );
  tolerance(customer.summary.rawPopulationTotal, customer.totalPopulationPersons);
  tolerance(customer.summary.smoothedPopulationTotal, customer.totalPopulationPersons);
  compareGrid(customer.rawCustomerAccounts, expected.raw_customer_accounts);
  compareGrid(customer.smoothedCustomerAccounts, expected.smoothed_customer_accounts);
  tolerance(customer.summary.rawTotal, expected.summary.raw_total);
  tolerance(customer.summary.smoothedTotal, expected.summary.smoothed_total);
  assert.equal(customer.summary.validCellCount, 9);
  assert.ok(customer.smoothedCustomerAccounts.flat().every((value) => value > 0));
  assert.equal(customer.spatialMethod.coordinateReferenceSystem, "EPSG:4326");
  assert.equal(customer.spatialMethod.smoothing.standardDeviationKm, small.input.config.customer_smoothing_km);
  assert.match(customer.spatialMethod.populationAllocation, /bilinear/);
});

test("zero population smoothing is an exact mass-preserving identity", () => {
  const input = small.input;
  const weather = model.normalizeWeather(input.weather);
  const customer = model.buildCustomerExposureSurface(
    input.boundary,
    input.census_tracts,
    weather.latitudes,
    weather.longitudes,
    { smoothingKm: 0, ruralBaselineFraction: 0 },
  );
  compareGrid(customer.smoothedPopulationPersons, customer.rawPopulationPersons);
  tolerance(customer.summary.rawPopulationTotal, customer.summary.smoothedPopulationTotal);
  assert.equal(customer.spatialMethod.smoothing.applied, false);
  assert.equal(customer.spatialMethod.smoothing.kernel, "none");
});

test("production block grid exactly reproduces runtime bilinear allocation", { timeout: 120000 }, () => {
  const blocks = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "connecticut_census_blocks.json"), "utf8",
  ));
  const stored = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "connecticut_census_population_grid.json"), "utf8",
  ));
  const { rows, columns, latitudes, longitudes } = stored.grid;
  const mask = Array.from({ length: rows }, (_, row) =>
    stored.connecticutMask.slice(row * columns, (row + 1) * columns).map(Boolean));
  const expected = Array.from({ length: rows }, (_, row) =>
    stored.populationPersons.slice(row * columns, (row + 1) * columns));
  const rerasterized = model.rasterizePopulationPersons(blocks, latitudes, longitudes, mask);
  const boundary = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "connecticut_land_boundary.json"), "utf8",
  ));
  const customer = model.buildCustomerExposureSurface(
    boundary, stored, latitudes, longitudes, { smoothingKm: 0, ruralBaselineFraction: 0 },
  );

  assert.equal(blocks.length, 49926);
  assert.equal(stored.source.populatedBlockCount, 42008);
  assert.equal(stored.source.zeroPopulationBlockCount, 7918);
  assert.equal(stored.source.totalPopulationPersons, 3605944);
  assert.equal(new Set(blocks.map((block) => block.geoid)).size, blocks.length);
  assert.ok(blocks.every((block) => /^09\d{13}$/.test(block.geoid)));
  tolerance(rerasterized.flat().reduce((sum, value) => sum + value, 0), 3605944, 1e-12, 1e-6);
  compareGrid(rerasterized, expected, 1e-12);
  tolerance(customer.summary.rawPopulationTotal, 3605944, 1e-12, 1e-6);
  assert.equal(customer.summary.validCellCount, stored.connecticutMask.reduce((a, b) => a + b, 0));
  assert.equal(customer.spatialMethod.sourceGeography, "Census block");
  assert.equal(customer.spatialMethod.boundarySource, "data/connecticut_land_boundary.json");
  assert.throws(
    () => model.buildCustomerExposureSurface(
      boundary,
      { ...stored, source: { ...stored.source, totalPopulationPersons: 3605945 } },
      latitudes,
      longitudes,
      { smoothingKm: 0, ruralBaselineFraction: 0 },
    ),
    /total does not match/,
  );
});

test("wind threshold and rain amplification preserve all weather components", () => {
  assert.deepEqual(model.weatherSeverityScore(35, 2), {
    windDamage: 0,
    rainAmplification: 2,
    weatherSeverity: 0,
  });
  const { severity } = smallSurfaces();
  const expected = small.expected.weather_surface;
  compareGrid(severity.windMph, expected.wind_mph);
  assert.equal(severity.rainInputKind, "one_hour_accumulation");
  assert.equal(severity.rainAccumulationIn, severity.rainInPerHour);
  compareGrid(severity.rainInPerHour, expected.rain_in_per_hour);
  compareGrid(severity.windDamageScore, expected.wind_damage_score);
  compareGrid(severity.rainAmplification, expected.rain_amplification);
  compareGrid(severity.weatherSeverity, expected.weather_severity);
  assert.equal(severity.summary.positiveSeverityCells, expected.summary.positive_severity_cells);
  tolerance(severity.summary.maximumSeverity, expected.summary.maximum_severity);
});

test("combined impact and boundary-aware Gaussian surface match Python", () => {
  const { severity, impact } = smallSurfaces();
  const expected = small.expected.impact_surface;
  compareGrid(impact.relativeCustomerExposure, expected.relative_customer_exposure);
  compareGrid(impact.rawImpact, expected.raw_impact);
  compareGrid(impact.smoothedImpact, expected.smoothed_impact);
  assert.equal(impact.normalizedImpactScore, impact.samplingProbability);
  assert.equal(impact.hazardIndex, severity.weatherSeverity);
  assert.equal(impact.relativeCustomerConsequenceIndex, impact.relativeCustomerExposure);
  assert.equal(impact.smoothedImpactPriorityScore, impact.smoothedImpact);
  assert.match(impact.interpretation.hazardIndex, /not a calibrated/);
  compareGrid(impact.samplingProbability, expected.sampling_probability);
  tolerance(impact.summary.rawTotal, expected.summary.raw_total);
  tolerance(impact.summary.smoothedTotal, expected.summary.smoothed_total);
  tolerance(impact.summary.normalizedScoreTotal, 1);
  tolerance(impact.summary.probabilityTotal, 1);
});

test("combined impact rejects equal-shaped surfaces on different coordinates", () => {
  const { config, customer, severity } = smallSurfaces();
  const shiftedWeather = {
    ...severity,
    latitudes: severity.latitudes.map((value, index) => index === 0 ? value + 1e-6 : value),
  };
  assert.throws(
    () => model.buildCombinedImpactSurface(customer, shiftedWeather, config),
    /grid coordinates must match exactly/,
  );
});

test("network expansion standardizes candidate length and line-integrates separated scores", () => {
  const { config, customer, severity, impact } = smallSurfaces();
  const segments = model.buildWeightedNetworkSegments(small.input.network, customer, severity, impact, config);
  assert.ok(segments.length > small.expected.weighted_segments.length);
  assert.equal(new Set(segments.map((segment) => segment.segmentId)).size, segments.length);
  segments.forEach((segment) => {
    assert.ok(segment.lengthKm <= config.candidateSegmentLengthKm + 1e-9);
    assert.ok(segment.integrationSampleCount >= 1);
    assert.equal(segment.integrationMethod, "composite_midpoint_rule_along_polyline");
    assert.equal(segment.placementMode, "impact_weighted");
    tolerance(segment.weight, segment.impactPriorityWeight);
    assert.ok(segment.failureOrientedWeight >= 0);
    assert.ok(segment.customerConsequenceIndex >= 0);
    assert.ok(segment.pathCoordinates.length >= 2);
  });
});

test("segment-keyed sampling is deterministic, order-invariant, unique, and restoration-compatible", () => {
  const input = small.input;
  const first = model.generateOutageScenario({
    config: input.config,
    boundary: input.boundary,
    censusTracts: input.census_tracts,
    weather: input.weather,
    network: input.network,
  });
  const second = model.generateOutageScenario({
    config: input.config,
    boundary: input.boundary,
    censusTracts: input.census_tracts,
    weather: input.weather,
    network: input.network,
  });
  assert.deepEqual(first.outages, second.outages);
  assert.equal(first.outages.length, 3);
  assert.equal(first.schemaVersion, 4);
  assert.equal(first.schema, "connecticut_outage_scenario_v4");
  assert.equal(
    first.totalCustomers,
    first.outages.reduce((sum, outage) => sum + outage.customers, 0),
  );
  assert.equal(first.methodology.networkTopology.customerLoadsAssigned, true);
  assert.equal(first.methodology.networkTopology.overlappingOutagePreventionApplied, true);
  assert.equal(
    first.customerAllocation.summary.allocatedCustomerAccounts,
    first.customerAllocation.summary.targetIntegerCustomerAccounts,
  );
  assert.equal(
    first.samplingDesign.algorithm,
    "segment_keyed_exponential_random_key_without_replacement",
  );
  assert.equal(first.samplingDesign.stableUnderCandidateReordering, true);
  assert.equal(first.samplingDesign.overlappingCustomerSubtrees, 0);
  const { config, customer, severity, impact } = smallSurfaces();
  const segments = model.buildWeightedNetworkSegments(
    small.input.network, customer, severity, impact, config,
  );
  const forward = model.sampleOutageScenario(segments, config);
  const reversed = model.sampleOutageScenario(segments.slice().reverse(), config);
  assert.deepEqual(reversed.outages, forward.outages);
  assert.equal(new Set(first.outages.map((outage) => outage.networkSegmentId)).size, 3);
  first.outages.forEach((outage) => {
    assert.ok(Number.isInteger(outage.customers) && outage.customers > 0);
    assert.equal(outage.popLoss, outage.customers);
    assert.equal(outage.downstreamCustomers, outage.customers);
    assert.ok(Number.isInteger(outage.fi));
    assert.ok(outage.kind === "f" || Number.isInteger(outage.li));
    assert.ok(outage.is_feeder === 0 || outage.is_feeder === 1);
    assert.equal(outage.sub_id, 0);
    assert.ok(Number.isInteger(outage.networkDirectCustomerAccounts));
    assert.ok(Number.isInteger(outage.networkDownstreamCustomerAccounts));
  });
});

test("uniform population scaling leaves relative exposure and sampled geography invariant", () => {
  const source = small.input;
  const run = (factor) => model.generateOutageScenario({
    config: source.config,
    boundary: source.boundary,
    censusTracts: source.census_tracts.map((tract) => ({ ...tract, pop: tract.pop * factor })),
    weather: source.weather,
    network: source.network,
  });
  const baseline = run(1);
  for (const factor of [model.POPULATION_TO_CUSTOMER_RATIO, 7.25]) {
    const scaled = run(factor);
    compareGrid(
      scaled.surfaces.impact.relativeCustomerExposure,
      baseline.surfaces.impact.relativeCustomerExposure,
      2e-12,
    );
    assert.deepEqual(
      scaled.outages.map((outage) => [
        outage.networkSegmentId, outage.lat, outage.lon,
      ]),
      baseline.outages.map((outage) => [
        outage.networkSegmentId, outage.lat, outage.lon,
      ]),
    );
  }
});

test("wind exceedance scale changes score magnitude but cancels from conditional geography", () => {
  const source = small.input;
  const run = (windExcessScaleMph) => model.generateOutageScenario({
    config: { ...source.config, windExcessScaleMph },
    boundary: source.boundary,
    censusTracts: source.census_tracts,
    weather: source.weather,
    network: source.network,
  });
  const reference = run(25);
  for (const scale of [20, 30]) {
    const candidate = run(scale);
    compareGrid(
      candidate.surfaces.impact.normalizedImpactPriorityScore,
      reference.surfaces.impact.normalizedImpactPriorityScore,
      3e-12,
    );
    assert.deepEqual(
      candidate.outages.map((outage) => [
        outage.networkSegmentId, outage.lat, outage.lon,
      ]),
      reference.outages.map((outage) => [
        outage.networkSegmentId, outage.lat, outage.lon,
      ]),
    );
    assert.notEqual(
      candidate.summary.totalSegmentWeight,
      reference.summary.totalSegmentWeight,
    );
  }
});

test("live website pts arrays are accepted without coordinate reversal errors", () => {
  const normalized = model.normalizeNetwork({
    feeders: [{ subIdx: 2, pts: [[41.0, -72.8], [41.1, -72.7]] }],
    laterals: [{ feederIdx: 0, pts: [[41.1, -72.7], [41.2, -72.6]] }],
  });
  assert.deepEqual(normalized.feeders[0].coordinates[0], [-72.8, 41.0]);
  assert.deepEqual(normalized.laterals[0].coordinates[1], [-72.6, 41.2]);
  assert.equal(normalized.feeders[0].subId, 2);
});

test("explicit basic fallback uses network length without weather or customer claims", () => {
  const segments = model.buildBasicNetworkSegments(small.input.network, small.input.config);
  assert.ok(segments.length > 8);
  assert.ok(segments.every((segment) => segment.segmentId.startsWith("basic:")
    && segment.weight > 0 && segment.localWeatherSeverity === null
    && segment.lengthKm <= model.DEFAULT_CONFIG.candidateSegmentLengthKm + 1e-9));
  const scenario = model.sampleOutageScenario(segments, small.input.config);
  assert.equal(scenario.outages.length, 3);
  assert.equal(scenario.totalCustomers, 150);
  assert.ok(scenario.outages.every((outage) => outage.localWeatherSeverity === null));
  assert.equal(scenario.methodology.placementMode, "network_length_only");
});

test("candidate construction and line integrals are invariant to redundant polyline vertices", () => {
  const original = {
    feeders: [{
      feederId: 0,
      subId: 0,
      coordinates: [[-72.9, 41.4], [-72.87, 41.42], [-72.84, 41.41]],
    }],
    laterals: [],
  };
  const first = original.feeders[0].coordinates[0];
  const second = original.feeders[0].coordinates[1];
  const subdivided = structuredClone(original);
  subdivided.feeders[0].coordinates.splice(1, 0, [
    (first[0] + second[0]) / 2,
    (first[1] + second[1]) / 2,
  ]);
  const options = { candidateSegmentLengthKm: 0.75 };
  const left = model.buildBasicNetworkSegments(original, options);
  const right = model.buildBasicNetworkSegments(subdivided, options);
  assert.deepEqual(left.map((segment) => segment.segmentId), right.map((segment) => segment.segmentId));
  tolerance(
    left.reduce((sum, segment) => sum + segment.weight, 0),
    right.reduce((sum, segment) => sum + segment.weight, 0),
    2e-8,
  );

  const latitudes = [41.3, 41.4, 41.5];
  const longitudes = [-73.0, -72.9, -72.8];
  const values = latitudes.map((latitude) =>
    longitudes.map((longitude) => 2 * latitude + 3 * longitude + 300));
  const coarse = model.integrateGridAlongPath(
    latitudes, longitudes, values, original.feeders[0].coordinates, 0.5,
  );
  const fine = model.integrateGridAlongPath(
    latitudes, longitudes, values, subdivided.feeders[0].coordinates, 0.125,
  );
  tolerance(coarse.integral, fine.integral, 3e-7);
});

test("failure-oriented and impact-weighted objectives are explicit and use different weights", () => {
  const { config, customer, severity, impact } = smallSurfaces();
  const impactSegments = model.buildWeightedNetworkSegments(
    small.input.network,
    customer,
    severity,
    impact,
    { ...config, placementMode: "impact_weighted" },
  );
  const failureSegments = model.buildWeightedNetworkSegments(
    small.input.network,
    customer,
    severity,
    impact,
    { ...config, placementMode: "failure_oriented" },
  );
  const impactById = new Map(impactSegments.map((segment) => [segment.segmentId, segment]));
  for (const failure of failureSegments) {
    const candidate = impactById.get(failure.segmentId);
    if (!candidate) continue;
    tolerance(failure.weight, failure.failureOrientedWeight);
    tolerance(candidate.weight, candidate.impactPriorityWeight);
  }
  assert.ok(failureSegments.some((failure) => {
    const candidate = impactById.get(failure.segmentId);
    return candidate && Math.abs(failure.weight - candidate.weight) > 1e-8;
  }));
});

test("full Isaias component surfaces match the frozen legacy W0 reference", { timeout: 120000 }, () => {
  const expected = fixture.full_isaias_reference.expected;
  const boundaryRaw = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_boundary.json"), "utf8"));
  const censusRaw = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_census_tracts.json"), "utf8"));
  const weatherText = fs.readFileSync(path.join(ROOT, "data", "connecticut_storm_wind.js"), "utf8");
  const weatherPayload = JSON.parse(weatherText.slice(weatherText.indexOf("=") + 1).trim().replace(/;$/, ""));
  const config = model.validateConfig(fixture.full_isaias_reference.config);
  const weather = {
    grid: weatherPayload.grid,
    storm: { storm_id: config.stormId, ...weatherPayload.storms[config.stormId] },
  };
  const normalizedWeather = model.normalizeWeather(weather);
  const customer = model.buildCustomerExposureSurface(
    boundaryRaw, censusRaw, normalizedWeather.latitudes, normalizedWeather.longitudes,
    { smoothingKm: config.customerSmoothingKm, ruralBaselineFraction: config.ruralBaselineFraction },
  );
  const severity = model.buildWeatherSeveritySurface(weather, customer.connecticutMask, config);
  const impact = model.buildCombinedImpactSurface(customer, severity, config);
  assert.equal(censusRaw.length, expected.census_tracts);
  assert.equal(customer.summary.validCellCount, expected.valid_connecticut_cells);
  tolerance(customer.summary.rawTotal, expected.raw_customer_total, 5e-11, 1e-7);
  tolerance(customer.summary.smoothedTotal, expected.smoothed_customer_total, 5e-11, 1e-7);
  assert.equal(severity.summary.positiveSeverityCells, expected.positive_weather_severity_cells);
  tolerance(severity.summary.maximumSeverity, expected.maximum_weather_severity, 5e-11);
  tolerance(impact.summary.rawTotal, expected.raw_impact_total, 5e-11);
  tolerance(impact.summary.smoothedTotal, expected.smoothed_impact_total, 5e-11);
  assert.equal(impact.summary.rawPositiveCells, expected.raw_impact_positive_cells);
  assert.equal(impact.summary.smoothedPositiveCells, expected.smoothed_impact_positive_cells);
});
