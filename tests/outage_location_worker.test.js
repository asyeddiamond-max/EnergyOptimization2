"use strict";

/*
 * Author: Alex Luo (@alexl1239) -- original design and implementation,
 *   feature/outage-location-simulator.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { Worker } = require("node:worker_threads");
const model = require("../outage_location_model.js");
const {
  buildPerformanceNetwork,
  buildReviewNetwork,
} = require("./helpers/outage_location_test_network.js");

const ROOT = path.resolve(__dirname, "..");
const WORKER_PATH = path.join(ROOT, "outage_location_worker.js");
const PROTOCOL = "connecticut_outage_worker_v1";
const fixture = JSON.parse(fs.readFileSync(
  path.join(__dirname, "fixtures", "outage_location_reference_v1.json"), "utf8",
));

function request(runId, input) {
  return { protocol: PROTOCOL, version: 1, type: "generate", runId, input };
}

function cancel(runId) {
  return { protocol: PROTOCOL, version: 1, type: "cancel", runId };
}

function smallInput(seed = 17) {
  const source = fixture.small_deterministic_reference.input;
  return {
    config: { ...source.config, seed },
    boundary: source.boundary,
    censusTracts: source.census_tracts,
    weather: source.weather,
    network: source.network,
    inputs: { fixture: "small-worker" },
  };
}

function fullInput() {
  const config = fixture.full_isaias_reference.config;
  const boundary = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_boundary.json"), "utf8"));
  const censusTracts = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_census_tracts.json"), "utf8"));
  const weatherText = fs.readFileSync(path.join(ROOT, "data", "connecticut_storm_wind.js"), "utf8");
  const weatherData = JSON.parse(weatherText.slice(weatherText.indexOf("=") + 1).trim().replace(/;$/, ""));
  const network = buildPerformanceNetwork(model, boundary, weatherData.grid);
  return {
    config,
    boundary,
    censusTracts,
    weather: {
      grid: weatherData.grid,
      storm: { storm_id: config.storm_id, ...weatherData.storms[config.storm_id] },
    },
    network,
    inputs: { fixture: "full-worker" },
  };
}

function timelineInput() {
  const boundary = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_boundary.json"), "utf8"));
  const censusTracts = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "connecticut_census_tracts.json"), "utf8"));
  const timelineText = fs.readFileSync(
    path.join(ROOT, "data", "connecticut_storm_timelines.js"),
    "utf8",
  );
  const timelineData = JSON.parse(
    timelineText.slice(timelineText.indexOf("=") + 1).trim().replace(/;$/, ""),
  );
  return {
    mode: "timeline",
    config: model.DEFAULT_CONFIG,
    boundary,
    censusTracts,
    weatherTimeline: {
      grid: timelineData.grid,
      storm: timelineData.storms.isaias_2020,
    },
    network: buildReviewNetwork(model, boundary, timelineData.grid),
    inputs: { fixture: "timeline-worker" },
  };
}

function createWorker() {
  return new Worker(WORKER_PATH);
}

function waitFor(worker, predicate, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error(`Timed out after ${timeoutMs}ms waiting for Worker message`));
    }, timeoutMs);
    const onMessage = (message) => {
      if (!predicate(message)) return;
      cleanup();
      resolve(message);
    };
    const onError = (error) => {
      cleanup();
      reject(error);
    };
    function cleanup() {
      clearTimeout(timer);
      worker.off("message", onMessage);
      worker.off("error", onError);
    }
    worker.on("message", onMessage);
    worker.on("error", onError);
  });
}

test("Worker announces its versioned capabilities", async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  const ready = await waitFor(worker, (message) => message.type === "ready");
  assert.equal(ready.protocol, PROTOCOL);
  assert.equal(ready.version, 1);
  assert.equal(ready.capabilities.progress, true);
  assert.equal(ready.capabilities.transferableSurfaces, true);
  assert.equal(ready.capabilities.timelineWeather, true);
});

test("Worker answers an explicit startup status handshake", async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  const readyPromise = waitFor(
    worker,
    (message) => message.type === "ready" && message.runId === "startup-test",
  );
  worker.postMessage({ protocol: PROTOCOL, version: 1, type: "status", runId: "startup-test" });
  const ready = await readyPromise;
  assert.equal(ready.capabilities.progress, true);
  assert.equal(ready.capabilities.transferableSurfaces, true);
});

test("Worker reports real stages and returns typed surfaces plus restoration-compatible outages", async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  const stages = [];
  worker.on("message", (message) => {
    if (message.type === "progress" && message.runId === "small") stages.push(message.stage);
  });
  worker.postMessage(request("small", smallInput()));
  const message = await waitFor(worker, (value) => value.type === "result" && value.runId === "small");
  const { result } = message;
  assert.deepEqual(stages, [
    "validation", "customer-exposure", "weather-severity", "impact-smoothing",
    "network-weighting", "sampling", "serialization", "complete",
  ]);
  assert.equal(result.outages.length, 3);
  assert.equal(result.totalCustomers, 150);
  assert.equal(result.summary.uniqueSampledSegments, 3);
  assert.ok(result.outages.every((outage) => outage.popLoss === 50));
  assert.ok(result.surfaces.mask instanceof Uint8Array);
  assert.ok(result.surfaces.smoothedImpact instanceof Float64Array);
  assert.deepEqual([result.surfaces.rows, result.surfaces.columns], [3, 3]);
  assert.equal(result.surfaces.smoothedImpact.length, 9);
  assert.ok(result.summary.timingsMs["network-weighting"] >= 0);
});

test("Worker returns 24 transferable Isaias frames and 2,000 timestamped outages", { timeout: 30000 }, async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  const stages = [];
  worker.on("message", (message) => {
    if (message.type === "progress" && message.runId === "timeline") stages.push(message.stage);
  });
  worker.postMessage(request("timeline", timelineInput()));
  const message = await waitFor(
    worker,
    (value) => value.type === "result" && value.runId === "timeline",
    30000,
  );
  const { result } = message;
  assert.deepEqual(stages, [
    "timeline-validation", "timeline-modeling", "timeline-serialization", "complete",
  ]);
  assert.equal(result.summary.placementModel, "curated_hourly_timeline_v1");
  assert.equal(result.outages.length, 2000);
  assert.equal(result.totalCustomers, 100000);
  assert.equal(result.summary.uniqueSampledSegments, 2000);
  assert.ok(result.outages.every((outage) => typeof outage.occurredAt === "string"));
  assert.equal(result.surfaces.mode, "timeline");
  assert.equal(result.surfaces.timeline.frames.length, 24);
  assert.ok(result.surfaces.timeline.frames[0].windGustMph instanceof Float32Array);
  assert.ok(result.surfaces.timeline.frames[0].rain1hIn instanceof Float32Array);
  assert.ok(result.surfaces.timeline.frames[0].rain6hIn instanceof Float32Array);
  assert.ok(result.surfaces.timeline.frames[0].smoothedImpact instanceof Float32Array);
  assert.equal(result.surfaces.timeline.frames[0].windGustMph.length, 41 * 65);
});

test("Worker returns human-readable validation errors with the failing stage", async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  const input = smallInput();
  input.config = { ...input.config, customers_per_outage: 49 };
  worker.postMessage(request("bad-input", input));
  const message = await waitFor(worker, (value) => value.type === "error" && value.runId === "bad-input");
  assert.equal(message.error.name, "InputValidationError");
  assert.equal(message.error.stage, "validation");
  assert.match(message.error.message, /exactly 50 customers/);

  worker.postMessage({ ...request("wrong-version", smallInput()), version: 2 });
  const protocolError = await waitFor(
    worker,
    (value) => value.type === "error" && value.runId === "wrong-version",
  );
  assert.equal(protocolError.error.stage, "message-validation");
  assert.match(protocolError.error.message, /version 1/);
});

test("Worker cancellation stops a run at the next stage boundary", async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  worker.on("message", (message) => {
    if (message.type === "progress" && message.runId === "cancel-me") {
      worker.postMessage(cancel("cancel-me"));
    }
  });
  worker.postMessage(request("cancel-me", smallInput()));
  const message = await waitFor(worker, (value) => value.type === "cancelled" && value.runId === "cancel-me");
  assert.equal(message.reason, "cancelled");
  assert.notEqual(message.stage, "not-active");
});

test("explicit basic mode succeeds without weather surfaces and labels itself clearly", async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  const input = smallInput();
  input.mode = "basic";
  delete input.boundary;
  delete input.censusTracts;
  delete input.weather;
  worker.postMessage(request("basic", input));
  const message = await waitFor(worker, (value) => value.type === "result" && value.runId === "basic");
  assert.equal(message.result.summary.placementModel, "basic_network_v1");
  assert.equal(message.result.surfaces, null);
  assert.equal(message.result.outages.length, 3);
  assert.equal(message.result.totalCustomers, 150);
});

test("a newer request supersedes an older run without leaking a stale result", async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  const messages = [];
  let replacementSent = false;
  worker.on("message", (message) => {
    messages.push(message);
    if (!replacementSent && message.type === "progress" && message.runId === "old") {
      replacementSent = true;
      worker.postMessage(request("new", smallInput(18)));
    }
  });
  worker.postMessage(request("old", smallInput(17)));
  const replacement = await waitFor(worker, (value) => value.type === "result" && value.runId === "new");
  assert.equal(replacement.result.config.seed, 18);
  assert.ok(messages.some((message) => message.type === "cancelled"
    && message.runId === "old" && message.reason === "superseded"));
  assert.ok(!messages.some((message) => message.type === "result" && message.runId === "old"));
});

test("full Isaias generation runs off-thread on a 100k-segment test network", { timeout: 120000 }, async (t) => {
  const worker = createWorker();
  t.after(() => worker.terminate());
  await waitFor(worker, (message) => message.type === "ready");
  let mainThreadTicks = 0;
  const ticker = setInterval(() => { mainThreadTicks += 1; }, 5);
  t.after(() => clearInterval(ticker));
  worker.postMessage(request("full-isaias", fullInput()));
  const message = await waitFor(
    worker,
    (value) => value.type === "result" && value.runId === "full-isaias",
    120000,
  );
  clearInterval(ticker);
  assert.ok(mainThreadTicks >= 10, `expected responsive main-thread ticks, received ${mainThreadTicks}`);
  assert.ok(message.result.summary.candidateSegments >= 100000);
  assert.equal(message.result.summary.sampledOutages, 2000);
  assert.equal(message.result.summary.uniqueSampledSegments, 2000);
  assert.equal(message.result.summary.representedCustomers, 100000);
  assert.equal(
    message.result.summary.surface.validConnecticutCells,
    fixture.full_isaias_reference.expected.valid_connecticut_cells,
  );
  assert.equal(message.result.surfaces.mask.length, 41 * 65);
  assert.equal(message.result.surfaces.smoothedImpact.length, 41 * 65);
});
