"use strict";

/*
 * Author: Alex Luo (@alexl1239) -- original design and implementation,
 *   feature/outage-location-simulator.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const model = require("../outage_location_model.js");
const { buildReviewNetwork } = require("./helpers/outage_location_test_network.js");

const ROOT = path.resolve(__dirname, "..");

function loadInputs(stormId = "isaias_2020") {
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "data", "connecticut_storm_timelines.js"), "utf8"),
    context,
  );
  const data = context.window.CONNECTICUT_STORM_TIMELINES;
  const boundary = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_boundary.json"), "utf8"));
  const populationGrid = JSON.parse(
    fs.readFileSync(path.join(ROOT, "data", "connecticut_census_population_grid.json"), "utf8"),
  );
  return {
    config: { ...model.DEFAULT_CONFIG, stormId },
    boundary,
    populationGrid,
    weatherTimeline: { grid: data.grid, storm: data.storms[stormId] },
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

  assert.equal(result.schemaVersion, 4);
  assert.equal(result.schema, "connecticut_timeline_outage_scenario_v4");
  assert.equal(
    result.summary.placementModel,
    "impact_weighted_curated_hourly_timeline_v4_topology_sized",
  );
  assert.equal(result.summary.placementMode, "impact_weighted");
  assert.equal(result.summary.timelineFrames, 24);
  assert.equal(result.outages.length, 2000);
  assert.equal(
    result.totalCustomers,
    result.outages.reduce((sum, outage) => sum + outage.customers, 0),
  );
  assert.equal(result.methodology.networkTopology.customerLoadsAssigned, true);
  assert.equal(result.methodology.networkTopology.overlappingOutagePreventionApplied, true);
  assert.equal(result.customerAllocation.summary.targetIntegerCustomerAccounts, 1633000);
  assert.equal(result.customerAllocation.summary.allocatedCustomerAccounts, 1633000);
  assert.equal(result.customerAllocation.summary.rootDownstreamCustomerAccounts, 1633000);
  assert.equal(result.summary.uniqueSampledSegments, 2000);
  assert.equal(new Set(result.outages.map((outage) => outage.networkSegmentId)).size, 2000);
  assert.equal(result.summary.frameOutageCounts.reduce((sum, count) => sum + count, 0), 2000);
  assert.ok(result.outages.every(
    (outage) => Number.isInteger(outage.customers)
      && outage.customers > 0
      && outage.popLoss === outage.customers,
  ));
  assert.ok(result.outages.every(
    (outage) => Number.isInteger(outage.networkDirectCustomerAccounts)
      && Number.isInteger(outage.networkDownstreamCustomerAccounts),
  ));
  assert.ok(result.outages.every((outage) => validTimes.has(outage.occurredAt)));
  assert.ok(result.outages.every((outage) => outage.localRain1hIn >= 0 && outage.localRain6hIn >= 0));
  assert.ok(result.outages.every((outage) =>
    model.pointInBoundary(input.boundary, outage.lat, outage.lon)));
  assert.equal(result.summary.firstOccurrence, "2020-08-04T17:00:00Z");
  assert.equal(result.summary.lastOccurrence, "2020-08-05T00:00:00Z");
});

test("December 2022 timeline produces topology-sized outages from its own 42 weather frames", () => {
  const input = loadInputs("dec2022");
  const result = model.generateTimelineOutageScenario({
    ...input,
    config: { ...input.config, nOutages: 500 },
  });
  const validTimes = new Set(input.weatherTimeline.storm.frames.map((frame) => frame.valid_time));

  assert.equal(result.summary.timelineFrames, 42);
  assert.equal(result.outages.length, 500);
  assert.equal(result.summary.frameOutageCounts.reduce((sum, count) => sum + count, 0), 500);
  assert.equal(new Set(result.outages.map((outage) => outage.networkSegmentId)).size, 500);
  assert.equal(
    result.totalCustomers,
    result.outages.reduce((sum, outage) => sum + outage.customers, 0),
  );
  assert.ok(result.outages.every((outage) =>
    validTimes.has(outage.occurredAt)
      && Number.isInteger(outage.customers)
      && outage.customers > 0));
  assert.equal(result.summary.firstOccurrence, "2022-12-23T01:00:00Z");
  assert.equal(result.summary.lastOccurrence, "2022-12-24T01:00:00Z");
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

test("failure-oriented timeline mode excludes Census exposure from placement weights", () => {
  const input = loadInputs();
  const failure = model.generateTimelineOutageScenario({
    ...input,
    config: { ...input.config, placementMode: "failure_oriented", nOutages: 100 },
  });
  const impact = model.generateTimelineOutageScenario({
    ...input,
    config: { ...input.config, placementMode: "impact_weighted", nOutages: 100 },
  });
  assert.equal(
    failure.summary.placementModel,
    "failure_oriented_curated_hourly_timeline_v4_topology_sized",
  );
  assert.equal(failure.methodology.placementMode, "failure_oriented");
  assert.equal(failure.summary.totalSegmentWeight, failure.summary.totalFailureOrientedWeight);
  assert.ok(failure.outages.every(
    (outage) => outage.placementMode === "failure_oriented"
      && outage.failureOrientedWeight >= 0
      && outage.impactPriorityWeight >= 0,
  ));
  assert.notDeepEqual(
    failure.outages.map((outage) => outage.networkSegmentId),
    impact.outages.map((outage) => outage.networkSegmentId),
  );
});

test("hourly timeline remains comparable to but meaningfully differs from the old peak-hour snapshot", () => {
  const input = loadInputs();
  const timeline = model.generateTimelineOutageScenario(input);
  const snapshot = model.generateOutageScenario({
    config: { ...input.config, stormId: "isaias_2020" },
    boundary: input.boundary,
    populationGrid: input.populationGrid,
    weather: loadSnapshotWeather(),
    network: input.network,
  });
  const snapshotIds = new Set(snapshot.outages.map((outage) => outage.networkSegmentId));
  const overlap = timeline.outages.filter((outage) => snapshotIds.has(outage.networkSegmentId)).length;

  assert.equal(snapshot.outages.length, 2000);
  assert.equal(timeline.outages.length, 2000);
  assert.equal(snapshot.totalCustomers, snapshot.sizeSummary.totalCustomers);
  assert.equal(timeline.totalCustomers, timeline.sizeSummary.totalCustomers);
  assert.ok(snapshot.outages.every((outage) => outage.occurredAt == null));
  assert.ok(timeline.outages.every((outage) => outage.occurredAt != null));
  const overlapFraction = overlap / timeline.outages.length;
  assert.ok(
    overlapFraction > 0.2 && overlapFraction < 0.99,
    `expected comparable but distinct failure sets, observed overlap ${overlapFraction}`,
  );
});
