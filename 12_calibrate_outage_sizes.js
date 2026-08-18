#!/usr/bin/env node
"use strict";

/*
 * Reproducible topology-only calibration against the supplied D.P.U. 24-41
 * job-size bins. The fitting objective is mean job-share total variation over
 * calibration seeds. PCAO and all secondary statistics are excluded.
 */

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const model = require("./outage_location_model.js");

const ROOT = __dirname;
const CALIBRATION_SEEDS = Object.freeze([101, 211, 307, 401, 503]);
const VALIDATION_SEEDS = Object.freeze([1009, 1103, 1201, 1301, 1409]);

function loadWindowAsset(relativePath, property) {
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(ROOT, relativePath), "utf8"), context);
  return context.window[property];
}

function pointInside(boundary, longitude, latitude) {
  return model.pointInBoundary(boundary, latitude, longitude);
}

function movePoint(origin, angle, distanceDegrees) {
  return [
    origin[0] + Math.cos(angle) * distanceDegrees,
    origin[1] + Math.sin(angle) * distanceDegrees,
  ];
}

function nextInsidePoint(boundary, origin, preferredAngle, stepDegrees, inwardAngle) {
  const angleOffsets = [0, Math.PI / 6, -Math.PI / 6, Math.PI / 3, -Math.PI / 3];
  const distances = [1, 0.75, 0.5, 0.25];
  for (const distanceFactor of distances) {
    for (const angleOffset of angleOffsets) {
      const candidate = movePoint(
        origin,
        preferredAngle + angleOffset,
        stepDegrees * distanceFactor,
      );
      if (pointInside(boundary, candidate[0], candidate[1])) return candidate;
    }
    const inward = movePoint(origin, inwardAngle, stepDegrees * distanceFactor);
    if (pointInside(boundary, inward[0], inward[1])) return inward;
  }
  return null;
}

function buildCalibrationNetwork(boundary, substations, options = {}) {
  const seed = options.seed ?? 20260813;
  const feedersPerSubstation = options.feedersPerSubstation ?? 5;
  const lateralsPerFeeder = options.lateralsPerFeeder ?? 6;
  const random = model.mulberry32(seed);
  const stateCenter = [-72.70, 41.60];
  const network = {
    substations: substations.map((substation, subId) => ({
      sub_id: subId,
      name: substation.name,
      lat: substation.lat,
      lon: substation.lon,
    })),
    feeders: [],
    laterals: [],
  };

  for (let subId = 0; subId < substations.length; subId += 1) {
    const substation = substations[subId];
    const root = [substation.lon, substation.lat];
    const inwardAngle = Math.atan2(
      stateCenter[1] - root[1],
      stateCenter[0] - root[0],
    );
    for (let feederOffset = 0; feederOffset < feedersPerSubstation; feederOffset += 1) {
      const feederId = network.feeders.length;
      let angle = feederOffset / feedersPerSubstation * Math.PI * 2
        + (random() - 0.5) * 0.35;
      const coordinates = [root];
      for (let step = 0; step < 10; step += 1) {
        angle += (random() - 0.5) * 0.35;
        const next = nextInsidePoint(
          boundary,
          coordinates[coordinates.length - 1],
          angle,
          0.0045 + random() * 0.003,
          inwardAngle,
        );
        if (!next) break;
        coordinates.push(next);
      }
      if (coordinates.length < 2) {
        const fallback = nextInsidePoint(boundary, root, inwardAngle, 0.001, inwardAngle);
        if (!fallback) continue;
        coordinates.push(fallback);
      }
      network.feeders.push({
        feeder_id: feederId,
        sub_id: subId,
        coordinates,
      });

      for (let lateralOffset = 0; lateralOffset < lateralsPerFeeder; lateralOffset += 1) {
        const anchorIndex = 1 + Math.floor(
          lateralOffset / lateralsPerFeeder * (coordinates.length - 1),
        );
        const boundedAnchorIndex = Math.min(coordinates.length - 1, anchorIndex);
        const anchor = coordinates[boundedAnchorIndex];
        const lateralCoordinates = [anchor];
        let lateralAngle = angle + Math.PI / 2
          + (lateralOffset % 2 ? Math.PI : 0)
          + (random() - 0.5) * 0.8;
        for (let step = 0; step < 4; step += 1) {
          lateralAngle += (random() - 0.5) * 0.6;
          const next = nextInsidePoint(
            boundary,
            lateralCoordinates[lateralCoordinates.length - 1],
            lateralAngle,
            0.0015 + random() * 0.0015,
            inwardAngle,
          );
          if (!next) break;
          lateralCoordinates.push(next);
        }
        if (lateralCoordinates.length < 2) continue;
        network.laterals.push({
          lateral_id: network.laterals.length,
          feeder_id: feederId,
          feeder_anchor_vertex_index: boundedAnchorIndex,
          coordinates: lateralCoordinates,
        });
      }
    }
  }
  return network;
}

/*
 * Rebuild the road-snapped production network using the same deterministic
 * ordering and lateral-to-feeder attachment rule as 03_grid_simulation.html.
 * road_grid.json stores points as [latitude, longitude], so keep them in the
 * `pts` form understood by outage_location_model.js.
 */
function buildRoadCalibrationNetwork(substations, roadGrid) {
  if (!roadGrid || !Array.isArray(roadGrid.subs)) {
    throw new Error("road grid must contain a subs array");
  }
  if (roadGrid.subs.length !== substations.length) {
    throw new Error(
      `road grid has ${roadGrid.subs.length} substations; expected ${substations.length}`,
    );
  }
  const network = {
    substations: substations.map((substation, subId) => ({
      sub_id: subId,
      name: substation.name,
      lat: substation.lat,
      lon: substation.lon,
    })),
    feeders: [],
    laterals: [],
  };

  for (let subId = 0; subId < substations.length; subId += 1) {
    const substation = substations[subId];
    // The road-grid asset is generated from CONNECTICUT_SUBSTATIONS in source
    // order. Match by that stable position because HIFLD names are not unique.
    const entry = roadGrid.subs[subId];
    if (entry?.name !== substation.name) {
      throw new Error(
        `road grid substation ${subId} is ${entry?.name ?? "missing"}; expected ${substation.name}`,
      );
    }
    if (!entry || !Array.isArray(entry.feeders) || !entry.feeders.length) {
      throw new Error(`road grid has no feeders for substation ${substation.name ?? subId}`);
    }

    const substationFeederIds = [];
    for (const points of entry.feeders) {
      const feederId = network.feeders.length;
      substationFeederIds.push(feederId);
      network.feeders.push({
        feeder_id: feederId,
        sub_id: subId,
        pts: points.map((point) => [point[0], point[1]]),
      });
    }

    for (const points of entry.laterals ?? []) {
      const lateralOrigin = points[0];
      let feederId = substationFeederIds[0];
      let feederAnchorVertexIndex = 0;
      let bestDistanceSquared = Infinity;
      for (const candidateFeederId of substationFeederIds) {
        const feederPoints = network.feeders[candidateFeederId].pts;
        for (let vertexIndex = 0; vertexIndex < feederPoints.length; vertexIndex += 1) {
          const point = feederPoints[vertexIndex];
          const distanceSquared = (point[0] - lateralOrigin[0]) ** 2
            + (point[1] - lateralOrigin[1]) ** 2;
          if (distanceSquared < bestDistanceSquared) {
            bestDistanceSquared = distanceSquared;
            feederId = candidateFeederId;
            feederAnchorVertexIndex = vertexIndex;
          }
        }
      }
      const feederAnchor = network.feeders[feederId].pts[feederAnchorVertexIndex];
      const anchoredPoints = bestDistanceSquared > 1e-16
        ? [[feederAnchor[0], feederAnchor[1]], ...points]
        : points;
      network.laterals.push({
        lateral_id: network.laterals.length,
        feeder_id: feederId,
        feeder_anchor_vertex_index: feederAnchorVertexIndex,
        pts: anchoredPoints.map((point) => [point[0], point[1]]),
      });
    }
  }
  return network;
}

function calibrationInputs(options = {}) {
  const candidateSegmentLengthKm = options.candidateSegmentLengthKm
    ?? model.DEFAULT_CONFIG.candidateSegmentLengthKm;
  const boundary = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "connecticut_land_boundary.json"),
    "utf8",
  ));
  const populationGrid = JSON.parse(fs.readFileSync(
    path.join(ROOT, "data", "connecticut_census_population_grid.json"),
    "utf8",
  ));
  const substations = loadWindowAsset(
    "data/connecticut_substations.js",
    "CONNECTICUT_SUBSTATIONS",
  );
  const networkSource = options.networkSource ?? "road_grid";
  const network = networkSource === "road_grid"
    ? buildRoadCalibrationNetwork(
      substations,
      JSON.parse(fs.readFileSync(path.join(ROOT, "data", "road_grid.json"), "utf8")),
    )
    : buildCalibrationNetwork(boundary, substations);
  const customerSurface = model.buildCustomerExposureSurface(
    boundary,
    populationGrid,
    populationGrid.grid.latitudes,
    populationGrid.grid.longitudes,
    { smoothingKm: 0, ruralBaselineFraction: 0 },
  );
  const topology = model.buildRootedNetworkTopology(network, {
    candidateSegmentLengthKm,
  });
  const allocation = model.allocateCustomerAccountsToTopology(topology, customerSurface);
  const neutralSegments = model.buildBasicNetworkSegments(
    network,
    { ...model.DEFAULT_CONFIG, candidateSegmentLengthKm },
    allocation,
  ).map((segment) => ({
    ...segment,
    segmentId: segment.segmentId.replace(/^basic:/, ""),
    parentSegmentId: segment.parentSegmentId?.replace(/^basic:/, "") ?? null,
    childSegmentIds: segment.childSegmentIds.map((id) => id.replace(/^basic:/, "")),
    topologyRootId: segment.topologyRootId.replace(/^basic:/, ""),
  }));
  return { networkSource, network, customerSurface, allocation, neutralSegments };
}

function resultOutages(selection) {
  return selection.selectedFailures.map((failure) => ({
    customers: failure.customerAccounts,
    popLoss: failure.customerAccounts,
    componentClass: failure.componentClass,
  }));
}

function evaluateParameters(neutralSegments, parameters, seeds) {
  const weightedSegments = neutralSegments.map((segment) => ({
    ...segment,
    weight: segment.lengthKm * (segment.networkKind === "feeder"
      ? parameters.feederSusceptibility
      : parameters.lateralSusceptibility),
  }));
  const runs = [];
  for (const seed of seeds) {
    try {
      const selection = model.selectNonOverlappingTopologyFailures(
        weightedSegments,
        {
          ...model.DEFAULT_CONFIG,
          seed,
          nOutages: 2377,
          feederSusceptibility: parameters.feederSusceptibility,
          lateralSusceptibility: parameters.lateralSusceptibility,
          serviceFailureWeight: parameters.serviceFailureWeight,
        },
      );
      const comparison = model.evaluateDpu31SizeDistribution(resultOutages(selection));
      runs.push({ seed, selection, comparison });
    } catch (error) {
      return { parameters, failed: true, error: error.message, runs: [] };
    }
  }
  const mean = (getter) => runs.reduce((sum, run) => sum + getter(run), 0) / runs.length;
  const binJobShares = model.DPU31_SIZE_TARGET.map((_, index) =>
    mean((run) => run.comparison.bins[index].simulatedJobShare));
  return {
    parameters,
    failed: false,
    seeds: [...seeds],
    metrics: {
      meanJobShareTotalVariation: mean(
        (run) => run.comparison.metrics.totalVariationJobShare,
      ),
      meanCustomerShareTotalVariation: mean(
        (run) => run.comparison.metrics.totalVariationCustomerShare,
      ),
      meanMaximumAbsoluteJobShareError: mean(
        (run) => run.comparison.metrics.maximumAbsoluteJobShareError,
      ),
      meanCustomersPerOutage: mean(
        (run) => run.comparison.simulated.meanCustomers,
      ),
      meanOverflowJobShare: mean((run) => run.comparison.overflow.jobShare),
      meanOverflowCustomerShare: mean(
        (run) => run.comparison.overflow.customerShare,
      ),
    },
    binJobShares,
    componentClassCounts: {
      service: mean((run) => run.comparison.simulated.componentClassCounts.service),
      lateral: mean((run) => run.comparison.simulated.componentClassCounts.lateral),
      feeder: mean((run) => run.comparison.simulated.componentClassCounts.feeder),
    },
    secondary: {
      p25: mean((run) => run.comparison.simulated.quantiles.p25),
      p50: mean((run) => run.comparison.simulated.quantiles.p50),
      p90: mean((run) => run.comparison.simulated.quantiles.p90),
      p99: mean((run) => run.comparison.simulated.quantiles.p99),
      largestOnePercentCustomerShare: mean(
        (run) => run.comparison.simulated.largestOnePercentCustomerShare,
      ),
    },
  };
}

function parameterGrid(quick) {
  const feederValues = quick
    ? [0.001, 0.003, 0.01, 0.03]
    : [0.001, 0.002, 0.003, 0.005, 0.01, 0.03, 0.05, 0.1];
  const serviceValues = quick
    ? [0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    : [0.6, 0.65, 0.7, 0.75, 0.8];
  return feederValues.flatMap((feederSusceptibility) => serviceValues.map(
    (serviceFailureWeight) => ({
      feederSusceptibility,
      lateralSusceptibility: 1,
      serviceFailureWeight,
    }),
  ));
}

function runCalibration(options = {}) {
  const quick = options.quick === true;
  const candidateSegmentLengthKm = options.candidateSegmentLengthKm
    ?? model.DEFAULT_CONFIG.candidateSegmentLengthKm;
  const networkSource = options.networkSource ?? "road_grid";
  const inputs = calibrationInputs({ candidateSegmentLengthKm, networkSource });
  const seeds = quick ? CALIBRATION_SEEDS.slice(0, 3) : CALIBRATION_SEEDS;
  const evaluated = parameterGrid(quick).map((parameters) =>
    evaluateParameters(inputs.neutralSegments, parameters, seeds));
  const successful = evaluated.filter((result) => !result.failed).sort(
    (left, right) =>
      left.metrics.meanJobShareTotalVariation - right.metrics.meanJobShareTotalVariation
        || left.metrics.meanCustomerShareTotalVariation
          - right.metrics.meanCustomerShareTotalVariation,
  );
  if (!successful.length) throw new Error("every calibration parameter set failed");
  const bestCalibration = successful[0];
  const heldOut = evaluateParameters(
    inputs.neutralSegments,
    bestCalibration.parameters,
    quick ? VALIDATION_SEEDS.slice(0, 3) : VALIDATION_SEEDS,
  );
  return {
    schema: "dpu31_topology_size_calibration_v1",
    generatedBy: "12_calibrate_outage_sizes.js",
    calibrationObjective: "mean 13-bin job-share total variation; PCAO excluded",
    acceptanceThresholds: {
      heldOutMeanJobShareTotalVariationMaximum: 0.15,
      heldOutMaximumAbsoluteBinJobShareErrorMaximum: 0.10,
      heldOutOverflowJobShareMaximum: 0.01,
    },
    topology: {
      source: inputs.networkSource,
      substations: inputs.network.substations.length,
      feeders: inputs.network.feeders.length,
      laterals: inputs.network.laterals.length,
      candidateSegments: inputs.neutralSegments.length,
      candidateSegmentLengthKm,
      allocatedCustomerAccounts: inputs.allocation.summary.allocatedCustomerAccounts,
    },
    quick,
    searchedParameterSets: evaluated.length,
    failedParameterSets: evaluated.filter((result) => result.failed).length,
    bestCalibration,
    heldOut,
    accepted: !heldOut.failed
      && heldOut.metrics.meanJobShareTotalVariation <= 0.15
      && heldOut.metrics.meanMaximumAbsoluteJobShareError <= 0.10
      && heldOut.metrics.meanOverflowJobShare <= 0.01,
    topFive: successful.slice(0, 5),
  };
}

if (require.main === module) {
  const segmentArgument = process.argv.find((value) => value.startsWith("--segment-km="));
  const networkArgument = process.argv.find((value) => value.startsWith("--network="));
  const result = runCalibration({
    quick: process.argv.includes("--quick"),
    networkSource: networkArgument?.split("=")[1] === "synthetic"
      ? "synthetic"
      : "road_grid",
    candidateSegmentLengthKm: segmentArgument
      ? Number(segmentArgument.split("=")[1])
      : model.DEFAULT_CONFIG.candidateSegmentLengthKm,
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

module.exports = {
  CALIBRATION_SEEDS,
  VALIDATION_SEEDS,
  buildCalibrationNetwork,
  buildRoadCalibrationNetwork,
  calibrationInputs,
  evaluateParameters,
  runCalibration,
};
