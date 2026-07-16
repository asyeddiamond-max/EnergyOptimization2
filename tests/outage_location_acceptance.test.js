"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const model = require("../outage_location_model.js");
const { buildReviewNetwork } = require("./helpers/outage_location_test_network.js");
const ROOT = path.resolve(__dirname, "..");
const fixture = JSON.parse(fs.readFileSync(
  path.join(__dirname, "fixtures", "outage_location_reference_v1.json"), "utf8",
));

let cachedFullInputs = null;
function loadFullInputs() {
  if (cachedFullInputs) return cachedFullInputs;
  const boundary = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_boundary.json"), "utf8"));
  const censusTracts = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_census_tracts.json"), "utf8"));
  const weatherText = fs.readFileSync(path.join(ROOT, "data", "connecticut_storm_wind.js"), "utf8");
  const weatherData = JSON.parse(weatherText.slice(weatherText.indexOf("=") + 1).trim().replace(/;$/, ""));
  const network = buildReviewNetwork(model, boundary, weatherData.grid);
  cachedFullInputs = { boundary, censusTracts, weatherData, network };
  return cachedFullInputs;
}

function weatherFor(weatherData, stormId) {
  return {
    grid: weatherData.grid,
    storm: { storm_id: stormId, ...weatherData.storms[stormId] },
  };
}

function flatSum(values) {
  return values.flat().reduce((sum, value) => sum + value, 0);
}

function arraysDiffer(left, right, tolerance = 1e-12) {
  return left.flat().some((value, index) => Math.abs(value - right.flat()[index]) > tolerance);
}

function smallScenario(configOverrides = {}, weatherTransform = (weather) => weather) {
  const source = fixture.small_deterministic_reference.input;
  const weather = weatherTransform(structuredClone(source.weather));
  return model.generateOutageScenario({
    config: { ...source.config, ...configOverrides },
    boundary: source.boundary,
    censusTracts: source.census_tracts,
    weather,
    network: source.network,
  });
}

test("scientific controls and seed have measurable, interpretable effects", () => {
  const baseline = smallScenario();
  const strongerWeather = smallScenario({}, (weather) => {
    weather.storm.peak_wind_mph = weather.storm.peak_wind_mph
      .map((row) => row.map((value) => value + 5));
    return weather;
  });
  const noRainAmplification = smallScenario({ rain_coefficient: 0 });
  const higherThreshold = smallScenario({ wind_threshold_mph: 40 });
  const strongerExposure = smallScenario({ exposure_exponent: 2 });
  const widerGaussian = smallScenario({ gaussian_bandwidth_km: 25 });
  const differentSeed = smallScenario({ seed: 18 });

  assert.ok(flatSum(strongerWeather.surfaces.weather.weatherSeverity)
    > flatSum(baseline.surfaces.weather.weatherSeverity));
  assert.ok(flatSum(noRainAmplification.surfaces.weather.weatherSeverity)
    < flatSum(baseline.surfaces.weather.weatherSeverity));
  assert.ok(flatSum(higherThreshold.surfaces.weather.weatherSeverity)
    < flatSum(baseline.surfaces.weather.weatherSeverity));
  assert.ok(arraysDiffer(
    strongerExposure.surfaces.impact.samplingProbability,
    baseline.surfaces.impact.samplingProbability,
  ));
  assert.ok(arraysDiffer(
    widerGaussian.surfaces.impact.smoothedImpact,
    baseline.surfaces.impact.smoothedImpact,
  ));
  assert.notDeepEqual(differentSeed.outages, baseline.outages);
});

test("default Isaias output satisfies exact geography, uniqueness, network, and customer contracts", { timeout: 120000 }, () => {
  const { boundary, censusTracts, weatherData, network } = loadFullInputs();
  const config = { ...model.DEFAULT_CONFIG, stormId: "isaias_2020" };
  const weather = weatherFor(weatherData, config.stormId);
  const result = model.generateOutageScenario({ config, boundary, censusTracts, weather, network });
  const normalizedNetwork = model.normalizeNetwork(network);

  assert.equal(result.outages.length, 2000);
  assert.equal(result.totalCustomers, 100000);
  assert.equal(new Set(result.outages.map((outage) => outage.networkSegmentId)).size, 2000);
  assert.equal(new Set(result.outages.map((outage) => `${outage.lat},${outage.lon}`)).size, 2000);
  result.outages.forEach((outage) => {
    assert.equal(outage.popLoss, 50);
    assert.equal(outage.customers, 50);
    assert.equal(model.pointInBoundary(boundary, outage.lat, outage.lon), true);
    assert.ok(outage.fi >= 0 && outage.fi < normalizedNetwork.feeders.length);
    assert.equal(outage.feeder_id, outage.fi);
    assert.ok(outage.sub_id >= 0 && outage.sub_id < network.substations.length);
    if (outage.kind === "l") {
      assert.ok(outage.li >= 0 && outage.li < normalizedNetwork.laterals.length);
      assert.equal(normalizedNetwork.laterals[outage.li].feeder.fi, outage.fi);
      assert.equal(normalizedNetwork.laterals[outage.li].feeder.feederId, outage.feeder_id);
    } else {
      assert.equal(outage.kind, "f");
      assert.equal(outage.is_feeder, 1);
    }
  });
});

test("every complete HRRR storm is validated under the default scientific threshold", { timeout: 120000 }, () => {
  const { boundary, censusTracts, weatherData, network } = loadFullInputs();
  const expectedDefaultNoDamage = new Set(["july2026"]);
  const observedDefaultNoDamage = new Set();

  for (const stormId of Object.keys(weatherData.storms)) {
    const weather = weatherFor(weatherData, stormId);
    const config = { ...model.DEFAULT_CONFIG, stormId, nOutages: 50 };
    try {
      const result = model.generateOutageScenario({ config, boundary, censusTracts, weather, network });
      assert.equal(result.outages.length, 50, stormId);
      assert.equal(result.totalCustomers, 2500, stormId);
      assert.ok(result.outages.every((outage) => outage.popLoss === 50), stormId);
    } catch (error) {
      assert.match(error.message, /no positive in-state mass/, stormId);
      observedDefaultNoDamage.add(stormId);
    }
  }
  assert.deepEqual(observedDefaultNoDamage, expectedDefaultNoDamage);

  const lowerThresholdResult = model.generateOutageScenario({
    config: { ...model.DEFAULT_CONFIG, stormId: "july2026", nOutages: 50, windThresholdMph: 20 },
    boundary,
    censusTracts,
    weather: weatherFor(weatherData, "july2026"),
    network,
  });
  assert.equal(lowerThresholdResult.outages.length, 50);
  assert.equal(lowerThresholdResult.totalCustomers, 2500);
});
