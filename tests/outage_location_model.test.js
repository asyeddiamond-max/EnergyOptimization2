"use strict";

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

test("configuration has frozen defaults and rejects invalid version-one inputs", () => {
  assert.equal(model.DEFAULT_CONFIG.nOutages, 2000);
  assert.equal(model.DEFAULT_CONFIG.customersPerOutage, 50);
  assert.equal(model.validateConfig({ n_outages: 3 }).nOutages, 3);
  assert.throws(() => model.validateConfig({ customersPerOutage: 49 }), model.InputValidationError);
  assert.throws(() => model.validateConfig({ gaussianBandwidthKm: 0 }), model.InputValidationError);
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
  compareGrid(customer.rawCustomerAccounts, expected.raw_customer_accounts);
  compareGrid(customer.smoothedCustomerAccounts, expected.smoothed_customer_accounts);
  tolerance(customer.summary.rawTotal, expected.summary.raw_total);
  tolerance(customer.summary.smoothedTotal, expected.summary.smoothed_total);
  assert.equal(customer.summary.validCellCount, 9);
  assert.ok(customer.smoothedCustomerAccounts.flat().every((value) => value > 0));
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
  compareGrid(severity.rainInPerHour, expected.rain_in_per_hour);
  compareGrid(severity.windDamageScore, expected.wind_damage_score);
  compareGrid(severity.rainAmplification, expected.rain_amplification);
  compareGrid(severity.weatherSeverity, expected.weather_severity);
  assert.equal(severity.summary.positiveSeverityCells, expected.summary.positive_severity_cells);
  tolerance(severity.summary.maximumSeverity, expected.summary.maximum_severity);
});

test("combined impact and boundary-aware Gaussian surface match Python", () => {
  const { impact } = smallSurfaces();
  const expected = small.expected.impact_surface;
  compareGrid(impact.relativeCustomerExposure, expected.relative_customer_exposure);
  compareGrid(impact.rawImpact, expected.raw_impact);
  compareGrid(impact.smoothedImpact, expected.smoothed_impact);
  compareGrid(impact.samplingProbability, expected.sampling_probability);
  tolerance(impact.summary.rawTotal, expected.summary.raw_total);
  tolerance(impact.summary.smoothedTotal, expected.summary.smoothed_total);
  tolerance(impact.summary.probabilityTotal, 1);
});

test("network expansion produces the eight expected weighted atomic segments", () => {
  const { config, customer, severity, impact } = smallSurfaces();
  const segments = model.buildWeightedNetworkSegments(small.input.network, customer, severity, impact, config);
  assert.equal(segments.length, small.expected.weighted_segments.length);
  segments.forEach((segment, index) => {
    const expected = small.expected.weighted_segments[index];
    assert.equal(segment.segmentId, expected.segment_id);
    assert.equal(segment.networkKind, expected.network_kind);
    assert.equal(segment.feederId, expected.feeder_id);
    assert.equal(segment.lateralId, expected.lateral_id);
    assert.equal(segment.subId, expected.sub_id);
    for (const [actualKey, expectedKey] of [
      ["lengthKm", "length_km"], ["localWindMph", "local_wind_mph"],
      ["localRainIn", "local_rain_in"], ["customerExposure", "customer_exposure"],
      ["relativeCustomerExposure", "relative_customer_exposure"],
      ["localWeatherSeverity", "local_weather_severity"], ["rawImpact", "raw_impact"],
      ["smoothedImpact", "smoothed_impact"], ["susceptibility", "susceptibility"],
      ["weight", "weight"],
    ]) tolerance(segment[actualKey], expected[expectedKey], 3e-12);
  });
});

test("Mulberry32 sampling is deterministic, unique, and restoration-compatible", () => {
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
  assert.equal(first.totalCustomers, 150);
  assert.equal(new Set(first.outages.map((outage) => outage.networkSegmentId)).size, 3);
  first.outages.forEach((outage) => {
    assert.equal(outage.popLoss, 50);
    assert.equal(outage.customers, 50);
    assert.ok(Number.isInteger(outage.fi));
    assert.ok(outage.kind === "f" || Number.isInteger(outage.li));
    assert.ok(outage.is_feeder === 0 || outage.is_feeder === 1);
    assert.equal(outage.sub_id, 0);
  });
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
  assert.equal(segments.length, 8);
  assert.ok(segments.every((segment) => segment.segmentId.startsWith("basic:")
    && segment.weight > 0 && segment.localWeatherSeverity === null));
  const scenario = model.sampleOutageScenario(segments, small.input.config);
  assert.equal(scenario.outages.length, 3);
  assert.equal(scenario.totalCustomers, 150);
  assert.ok(scenario.outages.every((outage) => outage.localWeatherSeverity === null));
});

test("full default Isaias component surfaces match the frozen W0 reference", { timeout: 120000 }, () => {
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
