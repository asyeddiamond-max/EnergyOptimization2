"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const adapter = require("../outage_restoration_adapter.js");

function fixtureOutages() {
  return [
    { lat: 41.70, lon: -72.70, kind: "f", fi: 0, li: null, feeder_id: 0, sub_id: 0, popLoss: 50, customers: 50 },
    { lat: 41.71, lon: -72.69, kind: "l", fi: 0, li: 0, feeder_id: 0, sub_id: 0, popLoss: 50, customers: 50 },
    { lat: 41.90, lon: -72.30, kind: "l", fi: 1, li: 1, feeder_id: 1, sub_id: 1, popLoss: 50, customers: 50 },
  ];
}

const context = {
  seed: 42,
  realistic: true,
  substations: [
    { lat: 41.70, lon: -72.70, canopyPercent: 10, treeFactor: 0.4 },
    { lat: 41.90, lon: -72.30, canopyPercent: 65, treeFactor: 1.5 },
  ],
  feeders: [
    { subIdx: 0, trimAge: 0 },
    { subIdx: 1, trimAge: 4 },
  ],
  laterals: [
    { feederIdx: 0 },
    { feederIdx: 1 },
  ],
  criticalFacilities: [{ lat: 41.70, lon: -72.70 }],
  floodCorridors: [{ pts: [[41.69, -72.70], [41.72, -72.70]] }],
  callbackEnabled: true,
  amiEnabled: true,
  switchingEnabled: true,
  undergroundEnabled: true,
};

test("metadata enrichment is deterministic and never changes placement or customer totals", () => {
  const input = fixtureOutages();
  const first = adapter.enrichOutages(input, context);
  const second = adapter.enrichOutages(input, context);
  assert.deepEqual(first, second);
  assert.equal(first.contract.representedCustomers, 150);
  assert.equal(first.summary.placementUnchanged, true);
  first.outages.forEach((outage, index) => {
    assert.equal(outage.lat, input[index].lat);
    assert.equal(outage.lon, input[index].lon);
    assert.equal(outage.popLoss, 50);
    assert.equal(outage.customers, 50);
  });
  assert.equal(first.outages[0].critical, true);
  assert.equal(first.outages[0].near_flood_zone, true);
});

test("downstream toggles use independent random streams and cannot perturb other metadata", () => {
  const baseline = adapter.enrichOutages(fixtureOutages(), context);
  const noSwitching = adapter.enrichOutages(fixtureOutages(), { ...context, switchingEnabled: false });
  for (let index = 0; index < baseline.outages.length; index += 1) {
    const a = baseline.outages[index];
    const b = noSwitching.outages[index];
    assert.equal(a.critical, b.critical);
    assert.equal(a.tree_blocked, b.tree_blocked);
    assert.equal(a.callback_lag_h, b.callback_lag_h);
    assert.equal(a.underground, b.underground);
  }
});

test("switching and underground tags preserve the fixed initial contract", () => {
  const result = adapter.enrichOutages(fixtureOutages(), {
    ...context,
    criticalFacilities: [],
    config: {
      switchingRate: 1,
      undergroundLateralRate: 1,
      criticalFallbackRate: 0,
    },
  });
  assert.equal(result.outages[0].switch_restored, true);
  assert.equal(result.outages[1].underground, true);
  assert.equal(result.outages[1].underground_repair_multiplier, 1.35);
  assert.equal(result.outages.reduce((sum, outage) => sum + outage.popLoss, 0), 150);
});

test("restoration summary includes automatic switching jobs and proves a zero endpoint", () => {
  const outages = fixtureOutages();
  const automaticJobs = [{ outageIdx: 0, o: outages[0], etaFinish: 5 / 60 }];
  const crews = [{ jobs: [
    { outageIdx: 1, o: outages[1], etaFinish: 2 },
    { outageIdx: 2, o: outages[2], etaFinish: 4 },
  ] }];
  const summary = adapter.summarizeRestorationJobs(outages, crews, automaticJobs);
  assert.deepEqual(summary, {
    inputOutages: 3,
    restoredOutages: 3,
    inputCustomers: 150,
    restoredCustomers: 150,
    remainingCustomers: 0,
    lastCompletionHour: 4,
    complete: true,
  });
});

test("contract validation rejects any variable-customer generated outage", () => {
  const outages = fixtureOutages();
  outages[1].popLoss = 49;
  assert.throws(() => adapter.validateInitialScenario(outages, 149, 50), adapter.ContractError);
});
