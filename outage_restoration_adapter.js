(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.OutageRestorationAdapter = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const METADATA_VERSION = 1;
  const DEFAULTS = Object.freeze({
    customersPerOutage: 50,
    criticalRadiusMi: 0.5,
    criticalFallbackRate: 0.02,
    treeBaseRate: 0.90,
    floodRadiusMi: 1.5,
    switchingRate: 0.42,
    switchingRestoreHours: 5 / 60,
    undergroundUrbanCanopyMax: 25,
    undergroundLateralRate: 0.40,
    undergroundRepairMultiplier: 1.35,
  });

  class ContractError extends Error {
    constructor(message) {
      super(message);
      this.name = "ContractError";
    }
  }

  function mulberry32(seed) {
    let state = seed | 0;
    return function random() {
      state = state + 0x6D2B79F5 | 0;
      let value = Math.imul(state ^ state >>> 15, 1 | state);
      value = value + Math.imul(value ^ value >>> 7, 61 | value) ^ value;
      return ((value ^ value >>> 14) >>> 0) / 4294967296;
    };
  }

  function stream(seed, salt) {
    return mulberry32((Math.imul(seed | 0, salt) + 0x5A17B9D3) | 0);
  }

  function haversineMi(a, b) {
    const toRadians = (degrees) => degrees * Math.PI / 180;
    const dLat = toRadians(b.lat - a.lat);
    const dLon = toRadians(b.lon - a.lon);
    const lat1 = toRadians(a.lat);
    const lat2 = toRadians(b.lat);
    const value = Math.sin(dLat / 2) ** 2
      + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * 3958.8 * Math.asin(Math.sqrt(value));
  }

  function distanceToFloodCorridor(lat, lon, corridors) {
    let minimum = Infinity;
    for (const corridor of corridors || []) {
      const points = corridor.pts || [];
      for (let index = 0; index < points.length - 1; index += 1) {
        const [aLat, aLon] = points[index];
        const [bLat, bLon] = points[index + 1];
        const dx = bLat - aLat;
        const dy = bLon - aLon;
        const lengthSquared = dx * dx + dy * dy;
        const fraction = Math.max(0, Math.min(1, lengthSquared > 0
          ? ((lat - aLat) * dx + (lon - aLon) * dy) / lengthSquared
          : 0));
        const point = { lat: aLat + fraction * dx, lon: aLon + fraction * dy };
        minimum = Math.min(minimum, haversineMi({ lat, lon }, point));
      }
    }
    return minimum;
  }

  function hasNearbyCriticalFacility(outage, facilities, radiusMi) {
    for (const facility of facilities || []) {
      if (haversineMi(outage, facility) <= radiusMi) return true;
    }
    return false;
  }

  function trimAgeMultiplier(age) {
    return 0.6 + 0.25 * age;
  }

  function resolveFeeder(outage, feeders, laterals) {
    const explicit = Number.isInteger(outage.feeder_id) ? outage.feeder_id : outage.feederId;
    if (Number.isInteger(explicit) && explicit >= 0 && feeders[explicit]) return explicit;
    if (outage.kind === "f" && Number.isInteger(outage.fi) && feeders[outage.fi]) return outage.fi;
    if (outage.kind === "l" && Number.isInteger(outage.li) && laterals[outage.li]) {
      const parent = laterals[outage.li].feederIdx ?? laterals[outage.li].feeder_id;
      if (Number.isInteger(parent) && parent >= 0 && feeders[parent]) return parent;
    }
    return -1;
  }

  function resolveSubstation(outage, feederIndex, substations, feeders) {
    const explicit = Number.isInteger(outage.sub_id) ? outage.sub_id : outage.subId;
    if (Number.isInteger(explicit) && explicit >= 0 && substations[explicit]) return explicit;
    if (feederIndex >= 0) {
      const parent = feeders[feederIndex].subIdx ?? feeders[feederIndex].sub_id;
      if (Number.isInteger(parent) && parent >= 0 && substations[parent]) return parent;
    }
    return -1;
  }

  function validateInitialScenario(outages, expectedTotal, customersPerOutage = 50) {
    if (!Array.isArray(outages) || outages.length === 0) {
      throw new ContractError("the generated scenario must contain at least one outage");
    }
    for (let index = 0; index < outages.length; index += 1) {
      const outage = outages[index];
      if (!Number.isFinite(outage.lat) || !Number.isFinite(outage.lon)) {
        throw new ContractError(`outage ${index} has invalid coordinates`);
      }
      if (outage.popLoss !== customersPerOutage || outage.customers !== customersPerOutage) {
        throw new ContractError(`outage ${index} must represent exactly ${customersPerOutage} customers`);
      }
    }
    const representedCustomers = outages.length * customersPerOutage;
    if (expectedTotal != null && expectedTotal !== representedCustomers) {
      throw new ContractError(`scenario total ${expectedTotal} does not equal ${representedCustomers}`);
    }
    return Object.freeze({
      outageCount: outages.length,
      customersPerOutage,
      representedCustomers,
    });
  }

  function enrichOutages(sampledOutages, options = {}) {
    const config = { ...DEFAULTS, ...(options.config || {}) };
    const seed = Number.isInteger(options.seed) ? options.seed : 42;
    const realistic = options.realistic !== false;
    const substations = options.substations || [];
    const feeders = options.feeders || [];
    const laterals = options.laterals || [];
    const facilities = options.criticalFacilities || [];
    const corridors = options.floodCorridors || [];
    const criticalRandom = stream(seed, 7919);
    const treeRandom = stream(seed, 1877);
    const callbackRandom = stream(seed, 3253);
    const switchingRandom = stream(seed, 4217);
    const undergroundRandom = stream(seed, 7331);

    const prepared = sampledOutages.map((outage) => ({
      ...outage,
      popLoss: config.customersPerOutage,
      customers: config.customersPerOutage,
    }));
    const initialContract = validateInitialScenario(
      prepared,
      sampledOutages.length * config.customersPerOutage,
      config.customersPerOutage,
    );

    const counts = {
      critical: 0,
      treeBlocked: 0,
      nearFloodZone: 0,
      callbackDelayed: 0,
      switchRestored: 0,
      underground: 0,
    };

    const outages = prepared.map((outage) => {
      const feederIndex = resolveFeeder(outage, feeders, laterals);
      const substationIndex = resolveSubstation(outage, feederIndex, substations, feeders);
      const substation = substations[substationIndex] || {};
      const canopy = Number.isFinite(substation.canopyPercent) ? substation.canopyPercent : 50;
      const feeder = feeders[feederIndex] || {};
      const trimAge = Number.isFinite(feeder.trimAge) ? feeder.trimAge : 2;
      const treeFactor = Number.isFinite(substation.treeFactor) ? substation.treeFactor : 1;

      let critical = false;
      if (realistic) {
        critical = facilities.length > 0
          ? hasNearbyCriticalFacility(outage, facilities, config.criticalRadiusMi)
          : criticalRandom() < config.criticalFallbackRate;
      }
      const treeProbability = realistic
        ? Math.max(0, Math.min(1, config.treeBaseRate * treeFactor * trimAgeMultiplier(trimAge)))
        : 0;
      const treeBlocked = realistic && treeRandom() < treeProbability ? 1 : 0;
      const nearFloodZone = realistic
        && distanceToFloodCorridor(outage.lat, outage.lon, corridors) <= config.floodRadiusMi;

      let callbackLagHours = 0;
      if (realistic && options.callbackEnabled !== false) {
        if (options.amiEnabled) {
          if (canopy < 25) {
            if (outage.kind === "l" && callbackRandom() < 0.30) callbackLagHours = 1 + callbackRandom() * 2;
          } else if (canopy < 50) {
            if (outage.kind === "l" && callbackRandom() < 0.50) callbackLagHours = 2 + callbackRandom() * 3;
          } else if (callbackRandom() < 0.70) {
            callbackLagHours = 3 + callbackRandom() * 5;
          }
        } else if (outage.kind === "l" && treeFactor > 1 && callbackRandom() < 0.15) {
          callbackLagHours = 2 + callbackRandom() * 6;
        }
      }

      const switchRestored = realistic && options.switchingEnabled === true
        && outage.kind === "f" && !critical && switchingRandom() < config.switchingRate;
      const underground = realistic && options.undergroundEnabled === true
        && outage.kind === "l" && canopy < config.undergroundUrbanCanopyMax
        && undergroundRandom() < config.undergroundLateralRate;

      if (critical) counts.critical += 1;
      if (treeBlocked) counts.treeBlocked += 1;
      if (nearFloodZone) counts.nearFloodZone += 1;
      if (callbackLagHours > 0) counts.callbackDelayed += 1;
      if (switchRestored) counts.switchRestored += 1;
      if (underground) counts.underground += 1;

      return {
        ...outage,
        feeder_id: feederIndex,
        sub_id: substationIndex,
        critical,
        tree_blocked: treeBlocked,
        near_flood_zone: nearFloodZone,
        callback_lag_h: callbackLagHours,
        switch_restored: switchRestored,
        switch_restore_h: switchRestored ? config.switchingRestoreHours : 0,
        underground,
        underground_repair_multiplier: underground ? config.undergroundRepairMultiplier : 1,
        restoration_metadata_version: METADATA_VERSION,
      };
    });

    validateInitialScenario(outages, initialContract.representedCustomers, config.customersPerOutage);
    return {
      outages,
      contract: initialContract,
      summary: Object.freeze({
        metadataVersion: METADATA_VERSION,
        ...counts,
        switchingRestoreHours: config.switchingRestoreHours,
        undergroundRepairMultiplier: config.undergroundRepairMultiplier,
        placementUnchanged: true,
      }),
    };
  }

  function summarizeRestorationJobs(outages, crews, automaticJobs = []) {
    const byCoordinate = new Map();
    outages.forEach((outage, index) => {
      byCoordinate.set(`${outage.lat.toFixed(6)},${outage.lon.toFixed(6)}`, index);
    });
    const jobs = [
      ...automaticJobs,
      ...(crews || []).flatMap((crew) => crew.jobs || []),
    ];
    const seen = new Set();
    let restoredCustomers = 0;
    let lastCompletionHour = 0;
    for (const job of jobs) {
      let outageIndex = Number.isInteger(job.outageIdx) ? job.outageIdx : -1;
      if (outageIndex < 0 && job.o && Number.isFinite(job.o.lat) && Number.isFinite(job.o.lon)) {
        outageIndex = byCoordinate.get(`${job.o.lat.toFixed(6)},${job.o.lon.toFixed(6)}`) ?? -1;
      }
      if (outageIndex < 0 || !outages[outageIndex]) {
        throw new ContractError("a restoration job could not be mapped to its input outage");
      }
      if (seen.has(outageIndex)) throw new ContractError(`outage ${outageIndex} was restored more than once`);
      seen.add(outageIndex);
      restoredCustomers += outages[outageIndex].popLoss;
      lastCompletionHour = Math.max(lastCompletionHour, Number(job.etaFinish) || 0);
    }
    const inputCustomers = outages.reduce((sum, outage) => sum + outage.popLoss, 0);
    return Object.freeze({
      inputOutages: outages.length,
      restoredOutages: seen.size,
      inputCustomers,
      restoredCustomers,
      remainingCustomers: inputCustomers - restoredCustomers,
      lastCompletionHour,
      complete: seen.size === outages.length && restoredCustomers === inputCustomers,
    });
  }

  return Object.freeze({
    METADATA_VERSION,
    DEFAULTS,
    ContractError,
    mulberry32,
    haversineMi,
    distanceToFloodCorridor,
    validateInitialScenario,
    enrichOutages,
    summarizeRestorationJobs,
  });
});
