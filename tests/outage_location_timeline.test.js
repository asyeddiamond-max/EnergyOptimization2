"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const model = require("../outage_location_model.js");
const { buildReviewNetwork } = require("./helpers/outage_location_test_network.js");

const ROOT = path.resolve(__dirname, "..");

function loadInputs() {
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "data", "connecticut_storm_timelines.js"), "utf8"),
    context,
  );
  const data = context.window.CONNECTICUT_STORM_TIMELINES;
  const boundary = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_boundary.json"), "utf8"));
  const censusTracts = JSON.parse(
    fs.readFileSync(path.join(ROOT, "data", "connecticut_census_tracts.json"), "utf8"),
  );
  return {
    config: model.DEFAULT_CONFIG,
    boundary,
    censusTracts,
    weatherTimeline: { grid: data.grid, storm: data.storms.isaias_2020 },
    network: buildReviewNetwork(model, boundary, data.grid),
  };
}

function loadSnapshotWeather() {
  const text = fs.readFileSync(path.join(ROOT, "data", "connecticut_storm_wind.js"), "utf8");
  const payload = JSON.parse(text.slice(text.indexOf("=") + 1).trim().replace(/;$/, ""));
  return {
    grid: payload.grid,
    storm: { storm_id: "isaias_2020", ...payload.storms.isaias_2020 },
  };
}

test("timeline normalization rejects timestamps that do not match the declared interval", () => {
  const input = loadInputs().weatherTimeline;
  const broken = {
    grid: input.grid,
    storm: {
      ...input.storm,
      frames: input.storm.frames.slice(0, 2).map((frame) => ({ ...frame })),
    },
  };
  broken.storm.frames[1].valid_time = "2020-08-04T07:30:00Z";
  assert.throws(() => model.normalizeWeatherTimeline(broken), /timestamps must match/);
});

test("full Isaias timeline produces exactly 2,000 unique timestamped outages", () => {
  const input = loadInputs();
  const result = model.generateTimelineOutageScenario(input);
  const validTimes = new Set(result.surfaces.timeline.frames.map((frame) => frame.validTime));

  assert.equal(result.schema, "connecticut_timeline_outage_scenario_v1");
  assert.equal(result.summary.placementModel, "curated_hourly_timeline_v1");
  assert.equal(result.summary.timelineFrames, 24);
  assert.equal(result.outages.length, 2000);
  assert.equal(result.totalCustomers, 100000);
  assert.equal(result.summary.uniqueSampledSegments, 2000);
  assert.equal(new Set(result.outages.map((outage) => outage.networkSegmentId)).size, 2000);
  assert.equal(result.summary.frameOutageCounts.reduce((sum, count) => sum + count, 0), 2000);
  assert.ok(result.outages.every((outage) => outage.customers === 50 && outage.popLoss === 50));
  assert.ok(result.outages.every((outage) => validTimes.has(outage.occurredAt)));
  assert.ok(result.outages.every((outage) => outage.localRain1hIn >= 0 && outage.localRain6hIn >= 0));
  assert.ok(result.outages.every((outage) =>
    model.pointInBoundary(input.boundary, outage.lat, outage.lon)));
  assert.equal(result.summary.firstOccurrence, "2020-08-04T17:00:00Z");
  assert.equal(result.summary.lastOccurrence, "2020-08-05T00:00:00Z");
});

test("timestamped outage footprint follows Isaias from west toward east", () => {
  const result = model.generateTimelineOutageScenario(loadInputs());
  const meanLongitude = (time) => {
    const outages = result.outages.filter((outage) => outage.occurredAt === time);
    assert.ok(outages.length > 0, `expected outages at ${time}`);
    return outages.reduce((sum, outage) => sum + outage.lon, 0) / outages.length;
  };
  const longitude17z = meanLongitude("2020-08-04T17:00:00Z");
  const longitude21z = meanLongitude("2020-08-04T21:00:00Z");
  assert.ok(longitude21z > longitude17z + 0.5);
});

test("timeline generation is deterministic for a fixed seed", () => {
  const input = loadInputs();
  const first = model.generateTimelineOutageScenario({
    ...input,
    config: { ...input.config, nOutages: 100 },
  });
  const second = model.generateTimelineOutageScenario({
    ...input,
    config: { ...input.config, nOutages: 100 },
  });
  assert.deepEqual(
    first.outages.map((outage) => [outage.networkSegmentId, outage.lat, outage.lon, outage.occurredAt]),
    second.outages.map((outage) => [outage.networkSegmentId, outage.lat, outage.lon, outage.occurredAt]),
  );
});

test("hourly timeline remains comparable to but meaningfully differs from the old peak-hour snapshot", () => {
  const input = loadInputs();
  const timeline = model.generateTimelineOutageScenario(input);
  const snapshot = model.generateOutageScenario({
    config: { ...input.config, stormId: "isaias_2020" },
    boundary: input.boundary,
    censusTracts: input.censusTracts,
    weather: loadSnapshotWeather(),
    network: input.network,
  });
  const snapshotIds = new Set(snapshot.outages.map((outage) => outage.networkSegmentId));
  const overlap = timeline.outages.filter((outage) => snapshotIds.has(outage.networkSegmentId)).length;

  assert.equal(snapshot.outages.length, 2000);
  assert.equal(timeline.outages.length, 2000);
  assert.equal(snapshot.totalCustomers, 100000);
  assert.equal(timeline.totalCustomers, 100000);
  assert.ok(snapshot.outages.every((outage) => outage.occurredAt == null));
  assert.ok(timeline.outages.every((outage) => outage.occurredAt != null));
  assert.equal(overlap, 1613);
  assert.ok(overlap > 0 && overlap < timeline.outages.length);
});
