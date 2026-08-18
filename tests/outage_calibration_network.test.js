"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const calibration = require("../12_calibrate_outage_sizes.js");
const model = require("../outage_location_model.js");

const ROOT = path.join(__dirname, "..");

function loadSubstations() {
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "data", "connecticut_substations.js"), "utf8"),
    context,
  );
  return context.window.CONNECTICUT_SUBSTATIONS;
}

test("calibration road network matches production ordering and exact lateral anchors", () => {
  const substations = loadSubstations();
  const roadGrid = JSON.parse(
    fs.readFileSync(path.join(ROOT, "data", "road_grid.json"), "utf8"),
  );
  const network = calibration.buildRoadCalibrationNetwork(substations, roadGrid);
  const productionEntries = substations.map((substation, index) => {
    const entry = roadGrid.subs[index];
    assert.equal(entry.name, substation.name);
    return entry;
  });

  assert.equal(network.substations.length, substations.length);
  assert.equal(
    network.feeders.length,
    productionEntries.reduce((sum, entry) => sum + entry.feeders.length, 0),
  );
  assert.equal(
    network.laterals.length,
    productionEntries.reduce((sum, entry) => sum + entry.laterals.length, 0),
  );

  for (const lateral of network.laterals) {
    const feeder = network.feeders[lateral.feeder_id];
    assert.ok(feeder, `lateral ${lateral.lateral_id} feeder exists`);
    const anchor = feeder.pts[lateral.feeder_anchor_vertex_index];
    assert.deepEqual(lateral.pts[0], anchor);
  }

  const normalized = model.normalizeNetwork(network);
  assert.equal(normalized.feeders.length, network.feeders.length);
  assert.equal(normalized.laterals.length, network.laterals.length);
  assert.equal(
    normalized.laterals.filter((lateral) =>
      lateral.attachmentMethod === "explicit_feeder_vertex").length,
    network.laterals.length,
  );
});

test("calibration road network keeps distinct same-named substations by source order", () => {
  const substations = loadSubstations();
  const roadGrid = JSON.parse(
    fs.readFileSync(path.join(ROOT, "data", "road_grid.json"), "utf8"),
  );
  const duplicateName = substations.find((substation, index) =>
    substations.findIndex((candidate) => candidate.name === substation.name) !== index).name;
  const duplicateIndices = substations
    .map((substation, index) => ({ substation, index }))
    .filter(({ substation }) => substation.name === duplicateName)
    .map(({ index }) => index);
  assert.ok(duplicateIndices.length > 1);

  const network = calibration.buildRoadCalibrationNetwork(substations, roadGrid);
  const feederRoots = duplicateIndices.map((subId) => {
    const feeder = network.feeders.find((candidate) => candidate.sub_id === subId);
    assert.ok(feeder, `substation ${subId} has a feeder`);
    return feeder.pts[0];
  });
  assert.equal(new Set(feederRoots.map((point) => point.join(","))).size, feederRoots.length);
});
