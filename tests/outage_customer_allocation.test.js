"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const model = require("../outage_location_model.js");

const ROOT = path.resolve(__dirname, "..");

function allocationNetwork(includeLaterals = true) {
  return {
    substations: [{ sub_id: 7, lat: 41.0, lon: -72.8 }],
    feeders: [{
      feeder_id: 10,
      sub_id: 7,
      coordinates: [[-72.8, 41.0], [-72.79, 41.0], [-72.78, 41.0]],
    }],
    laterals: includeLaterals ? [{
      lateral_id: 20,
      feeder_id: 10,
      feeder_anchor_vertex_index: 1,
      coordinates: [[-72.79, 41.0], [-72.79, 41.01]],
    }, {
      lateral_id: 21,
      feeder_id: 10,
      feeder_anchor_vertex_index: 2,
      coordinates: [[-72.78, 41.0], [-72.775, 41.01]],
    }] : [],
  };
}

function smallCustomerSurface() {
  return {
    latitudes: [41.002, 41.008],
    longitudes: [-72.789, -72.776],
    connecticutMask: [[true, true], [true, true]],
    rawCustomerAccounts: [[1.2, 2.8], [3.4, 2.6]],
    // Physical inventory must come from the raw grid, regardless of an
    // optional exposure-smoothing experiment.
    smoothedCustomerAccounts: [[999, 999], [999, 999]],
    totalCustomerAccounts: 10,
  };
}

function assertDownstreamRecurrence(allocation) {
  const byId = new Map(allocation.segments.map((segment) => [segment.segmentId, segment]));
  for (const segment of allocation.segments) {
    const childCustomers = segment.childSegmentIds.reduce(
      (sum, childId) => sum + byId.get(childId).downstreamCustomerAccounts,
      0,
    );
    const childLoadPoints = segment.childSegmentIds.reduce(
      (sum, childId) => sum + byId.get(childId).downstreamLoadPointCount,
      0,
    );
    assert.equal(
      segment.downstreamCustomerAccounts,
      segment.directCustomerAccounts + childCustomers,
    );
    assert.equal(
      segment.downstreamLoadPointCount,
      segment.directLoadPointCount + childLoadPoints,
    );
  }
}

test("customer allocation conserves integer inventory and computes exact downstream sums", () => {
  const topology = model.buildRootedNetworkTopology(allocationNetwork(), {
    candidateSegmentLengthKm: 0.6,
  });
  const allocation = model.allocateCustomerAccountsToTopology(
    topology,
    smallCustomerSurface(),
  );

  assert.equal(allocation.schema, "connecticut_network_customer_allocation_v1");
  assert.equal(allocation.allocationVersion, model.CUSTOMER_ALLOCATION_VERSION);
  assert.equal(allocation.summary.estimatedCustomerAccounts, 10);
  assert.equal(allocation.summary.targetIntegerCustomerAccounts, 10);
  assert.equal(allocation.summary.allocatedCustomerAccounts, 10);
  assert.equal(allocation.summary.rootDownstreamCustomerAccounts, 10);
  assert.equal(allocation.summary.feederFallbackCustomerAccounts, 0);
  assert.equal(allocation.summary.lateralCustomerAccounts, 10);
  assert.equal(allocation.serviceRepresentation.virtualCustomerAccounts, 10);
  assert.equal(allocation.serviceRepresentation.individualServiceObjectsMaterialized, false);
  assert.equal(
    allocation.loadPoints.reduce((sum, loadPoint) => sum + loadPoint.customerAccounts, 0),
    10,
  );
  assert.ok(allocation.loadPoints.every(
    (loadPoint) => Number.isInteger(loadPoint.customerAccounts)
      && loadPoint.customerAccounts > 0
      && loadPoint.attachedComponentClass === "lateral",
  ));
  assertDownstreamRecurrence(allocation);
});

test("territories without laterals use an explicit feeder fallback", () => {
  const topology = model.buildRootedNetworkTopology(allocationNetwork(false), {
    candidateSegmentLengthKm: 0.6,
  });
  const allocation = model.allocateCustomerAccountsToTopology(
    topology,
    smallCustomerSurface(),
  );
  assert.equal(allocation.summary.lateralCustomerAccounts, 0);
  assert.equal(allocation.summary.feederFallbackCustomerAccounts, 10);
  assert.ok(allocation.loadPoints.every(
    (loadPoint) => loadPoint.attachedComponentClass === "feeder",
  ));
  assertDownstreamRecurrence(allocation);
});

test("customer allocation rejects positive inventory outside the Connecticut mask", () => {
  const topology = model.buildRootedNetworkTopology(allocationNetwork());
  const surface = smallCustomerSurface();
  surface.connecticutMask[0][0] = false;
  assert.throws(
    () => model.allocateCustomerAccountsToTopology(topology, surface),
    /positive outside Connecticut/,
  );
});

test("production Census grid integerizes to exactly 1,633,000 customer accounts", () => {
  const stored = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "connecticut_census_population_grid.json"),
    "utf8",
  ));
  const boundary = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "connecticut_land_boundary.json"),
    "utf8",
  ));
  const customerSurface = model.buildCustomerExposureSurface(
    boundary,
    stored,
    stored.grid.latitudes,
    stored.grid.longitudes,
    { smoothingKm: 0, ruralBaselineFraction: 0 },
  );
  const topology = model.buildRootedNetworkTopology(allocationNetwork(), {
    candidateSegmentLengthKm: 0.6,
  });
  const allocation = model.allocateCustomerAccountsToTopology(
    topology,
    customerSurface,
  );

  assert.equal(allocation.summary.targetIntegerCustomerAccounts, 1633000);
  assert.equal(allocation.summary.allocatedCustomerAccounts, 1633000);
  assert.equal(allocation.summary.rootDownstreamCustomerAccounts, 1633000);
  assert.equal(
    allocation.segments.reduce(
      (sum, segment) => sum + segment.directCustomerAccounts,
      0,
    ),
    1633000,
  );
  assertDownstreamRecurrence(allocation);
});
