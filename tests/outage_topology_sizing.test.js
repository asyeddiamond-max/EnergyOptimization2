"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const model = require("../outage_location_model.js");

function segment(fields) {
  return {
    segmentId: fields.segmentId,
    componentClass: fields.componentClass || "lateral",
    networkKind: fields.componentClass || "lateral",
    feederId: fields.feederId ?? 0,
    lateralId: fields.lateralId ?? 0,
    subId: fields.subId ?? 0,
    topologyRootId: fields.topologyRootId,
    subtreeStart: fields.subtreeStart,
    subtreeEnd: fields.subtreeEnd,
    directCustomerAccounts: fields.directCustomerAccounts,
    downstreamCustomerAccounts: fields.downstreamCustomerAccounts,
    weight: fields.weight,
  };
}

function assertNoOverlap(selection) {
  const failures = selection.selectedFailures;
  for (let leftIndex = 0; leftIndex < failures.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < failures.length; rightIndex += 1) {
      const left = failures[leftIndex];
      const right = failures[rightIndex];
      if (left.topologyRootId !== right.topologyRootId) continue;
      if (left.failureType === "network" && right.failureType === "network") {
        assert.ok(
          left.subtreeEnd < right.subtreeStart || right.subtreeEnd < left.subtreeStart,
          `${left.failureId} and ${right.failureId} overlap`,
        );
      } else {
        const network = left.failureType === "network" ? left : right;
        const service = left.failureType === "service" ? left : right;
        assert.ok(
          service.attachmentSubtreePoint < network.subtreeStart
            || service.attachmentSubtreePoint > network.subtreeEnd,
          `${network.failureId} contains ${service.failureId}`,
        );
      }
    }
  }
}

test("network failures use downstream sums and reject overlapping rooted subtrees", () => {
  const segments = [
    segment({
      segmentId: "feeder:0:0",
      componentClass: "feeder",
      topologyRootId: "feeder:0:0",
      subtreeStart: 0,
      subtreeEnd: 1,
      directCustomerAccounts: 0,
      downstreamCustomerAccounts: 10,
      weight: 1e9,
    }),
    segment({
      segmentId: "lateral:0:0",
      topologyRootId: "feeder:0:0",
      subtreeStart: 1,
      subtreeEnd: 1,
      directCustomerAccounts: 10,
      downstreamCustomerAccounts: 10,
      weight: 1e8,
    }),
    segment({
      segmentId: "feeder:1:0",
      componentClass: "feeder",
      feederId: 1,
      lateralId: null,
      subId: 1,
      topologyRootId: "feeder:1:0",
      subtreeStart: 2,
      subtreeEnd: 2,
      directCustomerAccounts: 5,
      downstreamCustomerAccounts: 5,
      weight: 1e-9,
    }),
  ];
  const selection = model.selectNonOverlappingTopologyFailures(
    segments,
    { nOutages: 2, seed: 42 },
    { serviceFailureWeight: 0 },
  );

  assert.equal(selection.selectedFailures.length, 2);
  assert.deepEqual(
    selection.selectedFailures.map((failure) => failure.networkSegmentId),
    ["feeder:0:0", "feeder:1:0"],
  );
  assert.deepEqual(
    selection.selectedFailures.map((failure) => failure.customerAccounts),
    [10, 5],
  );
  assert.equal(selection.totalCustomers, 15);
  assert.ok(selection.summary.rejectedForCustomerOverlap >= 1);
  assert.equal(selection.summary.overlappingCustomerSubtrees, 0);
  assertNoOverlap(selection);
});

test("virtual customer-load groups stay compact while producing unique 1-15-account jobs", () => {
  const segments = [segment({
    segmentId: "lateral:99:0",
    topologyRootId: "feeder:99:0",
    subtreeStart: 1,
    subtreeEnd: 1,
    directCustomerAccounts: 1633000,
    downstreamCustomerAccounts: 1633000,
    weight: 1,
  })];
  const selection = model.selectNonOverlappingTopologyFailures(
    segments,
    { nOutages: 100, seed: 17 },
    { serviceFailureWeight: 1e12 },
  );

  assert.equal(selection.summary.virtualServiceCandidateCount, 431361);
  assert.equal(selection.summary.selectedServiceFailures, 100);
  assert.equal(selection.summary.selectedNetworkFailures, 0);
  assert.ok(selection.selectedFailures.every(
    (failure) => failure.failureType === "service"
      && failure.customerAccounts >= 1
      && failure.customerAccounts <= 15,
  ));
  assert.ok(selection.selectedFailures.some((failure) => failure.customerAccounts > 2));
  assert.ok(selection.summary.lazilyGeneratedServiceCandidates <= 101);
  assert.ok(
    selection.summary.lazilyGeneratedServiceCandidates
      < selection.summary.virtualServiceCandidateCount / 1000,
  );
  assert.equal(
    new Set(selection.selectedFailures.map((failure) => failure.failureId)).size,
    100,
  );
  assertNoOverlap(selection);
});

test("one complete customer-load grouping cycle conserves every direct account", () => {
  const segments = [segment({
    segmentId: "lateral:100:0",
    topologyRootId: "feeder:100:0",
    subtreeStart: 1,
    subtreeEnd: 1,
    directCustomerAccounts: 53,
    downstreamCustomerAccounts: 53,
    weight: 1,
  })];
  const selection = model.selectNonOverlappingTopologyFailures(
    segments,
    { nOutages: 14, seed: 29 },
    { serviceFailureWeight: 1e12 },
  );

  assert.equal(selection.summary.virtualServiceCandidateCount, 14);
  assert.equal(selection.summary.selectedServiceFailures, 14);
  assert.equal(selection.totalCustomers, 53);
  assert.deepEqual(
    selection.selectedFailures
      .map((failure) => failure.customerAccounts)
      .sort((left, right) => left - right),
    [1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 5, 8, 12, 15],
  );
  assertNoOverlap(selection);
});

test("topology failure selection is invariant to weighted-segment ordering", () => {
  const segments = [
    segment({
      segmentId: "lateral:1:0",
      topologyRootId: "feeder:1:0",
      subtreeStart: 1,
      subtreeEnd: 1,
      directCustomerAccounts: 200,
      downstreamCustomerAccounts: 200,
      weight: 2,
    }),
    segment({
      segmentId: "lateral:2:0",
      feederId: 2,
      lateralId: 2,
      subId: 2,
      topologyRootId: "feeder:2:0",
      subtreeStart: 3,
      subtreeEnd: 3,
      directCustomerAccounts: 300,
      downstreamCustomerAccounts: 300,
      weight: 3,
    }),
  ];
  const config = { nOutages: 20, seed: 91 };
  const sizing = { serviceFailureWeight: 1000 };
  const forward = model.selectNonOverlappingTopologyFailures(segments, config, sizing);
  const reversed = model.selectNonOverlappingTopologyFailures(
    [...segments].reverse(),
    config,
    sizing,
  );
  assert.deepEqual(reversed.selectedFailures, forward.selectedFailures);
  assert.deepEqual(reversed.summary, forward.summary);
  assertNoOverlap(forward);
});

test("sizing options reject unsupported values instead of silently changing the model", () => {
  assert.throws(
    () => model.validateCustomerSizingConfig({ serviceGroupMaximumCustomers: 3 }),
    /currently supports the calibrated value 15/,
  );
  assert.throws(
    () => model.validateCustomerSizingConfig({ serviceFailureWeight: -1 }),
    /must be >= 0/,
  );
  assert.throws(
    () => model.validateCustomerSizingConfig({ typoWeight: 1 }),
    /unknown customer sizing option/,
  );
});

test("DPU evaluator uses the supplied half-open bins and excludes PCAO from its objective", () => {
  const fixedFifty = Array.from({ length: 2377 }, (_, index) => ({
    customers: 50,
    popLoss: 50,
    componentClass: index % 2 ? "lateral" : "feeder",
  }));
  const comparison = model.evaluateDpu31SizeDistribution(fixedFifty);
  assert.equal(comparison.targetJobs, 2377);
  assert.equal(comparison.targetCustomers, 306020);
  assert.equal(comparison.bins.length, 13);
  assert.equal(comparison.bins[6].lo, 32);
  assert.equal(comparison.bins[6].hi, 64);
  assert.equal(comparison.bins[6].jobs, 2377);
  assert.equal(comparison.overflow.jobs, 0);
  assert.ok(
    Math.abs(comparison.metrics.totalVariationJobShare - 0.8864114429953723)
      < 1e-12,
  );
  assert.equal(comparison.calibrationObjectiveIncludesPcao, false);
});

test("provisional PCAO is transparent about the current post-storm restoration basis", () => {
  const outages = [1, 2, 6].map((customers, index) => ({
    customers,
    popLoss: customers,
    componentClass: index === 0 ? "service" : "lateral",
  }));
  const pcao = model.calculateProvisionalPcao(outages);
  assert.equal(pcao.peakCustomersAffected, 9);
  assert.equal(pcao.totalStormOutages, 3);
  assert.equal(pcao.value, 3);
  assert.equal(pcao.provisional, true);
  assert.equal(pcao.historicalComparisonValid, false);
  assert.equal(pcao.calibrationObjectiveIncludesPcao, false);
  assert.match(pcao.limitation, /equals mean customers per job/);
});
