"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const model = require("../outage_location_model.js");

function rootedFixture() {
  return {
    substations: [{ sub_id: 7, lat: 41.0, lon: -72.8 }],
    feeders: [{
      feeder_id: 10,
      sub_id: 7,
      coordinates: [[-72.8, 41.0], [-72.79, 41.0], [-72.78, 41.0]],
    }],
    laterals: [{
      lateral_id: 20,
      feeder_id: 10,
      feeder_anchor_vertex_index: 1,
      coordinates: [[-72.79, 41.0], [-72.79, 41.005], [-72.79, 41.01]],
    }, {
      lateral_id: 21,
      feeder_id: 10,
      feeder_anchor_vertex_index: 2,
      coordinates: [[-72.78, 41.0], [-72.775, 41.004]],
    }],
  };
}

function topologySignature(topology) {
  return topology.segments.map((segment) => ({
    segmentId: segment.segmentId,
    parentSegmentId: segment.parentSegmentId,
    childSegmentIds: segment.childSegmentIds,
    topologyRootId: segment.topologyRootId,
    topologyDepth: segment.topologyDepth,
    subtreeStart: segment.subtreeStart,
    subtreeEnd: segment.subtreeEnd,
  })).sort((left, right) => left.segmentId.localeCompare(right.segmentId));
}

test("rooted topology attaches ordered lateral chains to their feeder chainage", () => {
  const topology = model.buildRootedNetworkTopology(rootedFixture(), {
    candidateSegmentLengthKm: 0.6,
  });
  assert.equal(topology.schema, "connecticut_rooted_network_topology_v1");
  assert.equal(topology.topologyVersion, model.NETWORK_TOPOLOGY_VERSION);
  assert.equal(topology.roots.length, 1);
  assert.equal(topology.summary.explicitLateralAttachments, 2);
  assert.equal(topology.summary.inferredLateralAttachments, 0);
  assert.ok(topology.summary.feederSegments >= 2);
  assert.ok(topology.summary.lateralSegments >= 2);

  const byId = new Map(topology.segments.map((segment) => [segment.segmentId, segment]));
  const root = byId.get(topology.roots[0]);
  assert.equal(root.networkKind, "feeder");
  assert.equal(root.parentSegmentId, null);
  assert.equal(root.topologyDepth, 0);
  assert.equal(root.subtreeStart, 0);
  assert.equal(root.subtreeEnd, topology.segments.length - 1);

  for (const segment of topology.segments) {
    assert.equal(segment.topologyRootId, root.segmentId);
    assert.ok(Number.isInteger(segment.subtreeStart));
    assert.ok(Number.isInteger(segment.subtreeEnd));
    assert.ok(segment.subtreeStart <= segment.subtreeEnd);
    if (segment.parentSegmentId === null) continue;
    const parent = byId.get(segment.parentSegmentId);
    assert.ok(parent, `${segment.segmentId} parent exists`);
    assert.ok(parent.childSegmentIds.includes(segment.segmentId));
    assert.equal(segment.topologyDepth, parent.topologyDepth + 1);
    assert.ok(parent.subtreeStart < segment.subtreeStart);
    assert.ok(parent.subtreeEnd >= segment.subtreeEnd);
    assert.equal(parent.feederId, segment.feederId);
    assert.equal(parent.subId, segment.subId);
  }

  for (const lateralId of [20, 21]) {
    const first = byId.get(`lateral:${lateralId}:0`);
    const parent = byId.get(first.parentSegmentId);
    assert.equal(parent.networkKind, "feeder");
    assert.ok(first.feederAnchorChainageKm <= parent.endChainageKm + 1e-9);
    assert.equal(first.feederAttachmentDistanceKm, 0);
  }
});

test("legacy networks infer exact lateral attachment from the lateral origin", () => {
  const network = rootedFixture();
  delete network.laterals[0].feeder_anchor_vertex_index;
  const normalized = model.normalizeNetwork(network);
  const lateral = normalized.laterals.find((candidate) => candidate.lateralId === 20);
  assert.equal(lateral.attachmentMethod, "inferred_from_lateral_origin");
  assert.ok(lateral.feederAttachmentDistanceKm < 1e-9);
  assert.ok(lateral.feederAnchorChainageKm > 0);
});

test("explicit lateral anchors fail closed when geometry is disconnected", () => {
  const network = rootedFixture();
  network.laterals[0].coordinates[0] = [-72.75, 41.03];
  assert.throws(
    () => model.buildRootedNetworkTopology(network),
    /origin is .* km from its feeder anchor/,
  );

  const inconsistent = rootedFixture();
  inconsistent.laterals[0].feeder_anchor_chainage_km = 0;
  assert.throws(
    () => model.buildRootedNetworkTopology(inconsistent),
    /anchor vertex and chainage disagree/,
  );
});

test("topology validation rejects empty and zero-length network lines cleanly", () => {
  const emptyFeeder = rootedFixture();
  emptyFeeder.feeders[0].coordinates = [];
  assert.throws(() => model.normalizeNetwork(emptyFeeder), /feeder 0 needs at least two points/);

  const zeroLateral = rootedFixture();
  zeroLateral.laterals[0].coordinates = [
    [-72.79, 41.0],
    [-72.79, 41.0],
  ];
  assert.throws(() => model.normalizeNetwork(zeroLateral), /lateral 0 must have positive length/);
});

test("topology intervals and links are stable under lateral array reordering", () => {
  const forwardNetwork = rootedFixture();
  const reversedNetwork = rootedFixture();
  reversedNetwork.laterals.reverse();
  const forward = model.buildRootedNetworkTopology(forwardNetwork, {
    candidateSegmentLengthKm: 0.6,
  });
  const reversed = model.buildRootedNetworkTopology(reversedNetwork, {
    candidateSegmentLengthKm: 0.6,
  });
  assert.deepEqual(topologySignature(reversed), topologySignature(forward));
});

test("basic-placement segment prefixes preserve a closed rooted topology", () => {
  const segments = model.buildBasicNetworkSegments(rootedFixture(), {
    candidateSegmentLengthKm: 0.6,
  });
  const byId = new Map(segments.map((segment) => [segment.segmentId, segment]));
  for (const segment of segments) {
    assert.match(segment.segmentId, /^basic:/);
    assert.match(segment.topologyRootId, /^basic:/);
    assert.ok(byId.has(segment.topologyRootId));
    if (segment.parentSegmentId !== null) assert.ok(byId.has(segment.parentSegmentId));
    for (const childId of segment.childSegmentIds) assert.ok(byId.has(childId));
  }
});
