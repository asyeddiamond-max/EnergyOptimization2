/*
 * Connecticut weather- and customer-weighted outage-location model.
 *
 * Author: Alex Luo (@alexl1239) -- original design and implementation,
 *   feature/outage-location-simulator.
 *
 * This dependency-free module is intentionally usable in three environments:
 * a browser page, a Web Worker, and Node's test runner. It contains no DOM,
 * Leaflet, file-system, or network access. Coordinates at the public boundary
 * and weather interfaces are longitude/latitude GeoJSON values; the live grid
 * simulator's `{pts: [[lat, lon], ...]}` network shape is also accepted.
 */
(function exposeOutageLocationModel(root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  if (root) root.OutageLocationModel = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildModule() {
  "use strict";

  const SCHEMA_VERSION = 3;
  const OUTAGE_SCENARIO_VERSION = 4;
  const LEGACY_CUSTOMERS_PER_OUTAGE = 50;
  const POPULATION_TO_CUSTOMER_RATIO = 1633000 / 3605944;
  const EARTH_RADIUS_KM = 6371.0088;
  const NETWORK_TOPOLOGY_VERSION = 1;
  const CUSTOMER_ALLOCATION_VERSION = 1;
  const LATERAL_ATTACHMENT_TOLERANCE_KM = 0.05;
  const CUSTOMER_ALLOCATION_NEARBY_LATERALS = 8;
  const CUSTOMER_ALLOCATION_DISTANCE_FLOOR_KM = 0.25;

  const DEFAULT_CONFIG = Object.freeze({
    stormId: "isaias_2020",
    seed: 42,
    nOutages: 2000,
    windThresholdMph: 35,
    windExcessScaleMph: 25,
    windExponent: 2,
    rainCoefficient: 0.5,
    rainReferenceIn: 1,
    rainScoreCap: 2,
    exposureExponent: 1,
    // Population-surface regularization on the approximately 3 km analysis
    // grid. Zero is valid and means that bilinear allocation is the only
    // spatial spreading applied before exposure normalization.
    customerSmoothingKm: 0,
    // No synthetic uniform exposure is added by default. A nonzero value
    // remains available for sensitivity experiments, but requires an explicit
    // scenario choice.
    ruralBaselineFraction: 0,
    // Prespecified impact-surface regularization, retained with explicit
    // sensitivity results rather than represented as a calibrated constant.
    gaussianBandwidthKm: 10,
    placementMode: "impact_weighted",
    candidateSegmentLengthKm: 0.075,
    lineIntegrationStepKm: 0.25,
    // Component weights frozen by the 2026-08-18 D.P.U. 24-41 calibration
    // against the production road-snapped network.
    feederSusceptibility: 0.003,
    lateralSusceptibility: 1,
    serviceFailureWeight: 0.8,
    serviceGroupMaximumCustomers: 15,
  });

  // A compact, deterministic partition of direct lateral load. The pattern is
  // repeated as needed, with a segment-keyed starting point for the final
  // partial cycle. It supplies the small-load resolution missing between an
  // individual account and a whole lateral subtree without sampling a job size
  // from the DPU target during a simulation run.
  const CUSTOMER_LOAD_GROUP_PATTERN = Object.freeze([
    1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 5, 8, 12, 15,
  ]);

  const DEFAULT_CUSTOMER_SIZING_CONFIG = Object.freeze({
    // Relative total failure mass for compact customer groups attached to each
    // customer-bearing segment. Frozen by the D.P.U. 24-41 calibration.
    serviceFailureWeight: 0.8,
    // Direct accounts are partitioned into disjoint small load groups. This is
    // a generic network-resolution layer; it does not assert an equipment or
    // damage type for each group.
    serviceGroupMaximumCustomers: 15,
  });

  const DPU31_SIZE_TARGET = Object.freeze([
    [1, 2, 0.2170803533866218, 0.001686164302986733],
    [2, 3, 0.0344972654606647, 0.0005359126854453957],
    [3, 5, 0.06226335717290703, 0.0017155741454806875],
    [5, 8, 0.06436684896928901, 0.002940984249395464],
    [8, 16, 0.10980227177114009, 0.009460166002222077],
    [16, 32, 0.11695414387883887, 0.02059669302659957],
    [32, 64, 0.11358855700462768, 0.04032742957976603],
    [64, 128, 0.09676062263357173, 0.06828311875040848],
    [128, 256, 0.06184265881363063, 0.08714789883014182],
    [256, 512, 0.052166596550273454, 0.14307561597281224],
    [512, 1024, 0.04080774084981069, 0.23145872818770016],
    [1024, 2048, 0.023979806478754733, 0.26758381805110776],
    [2048, 4096, 0.005889777029869584, 0.1251878962159336],
  ].map(([lo, hi, jobShare, customerShare]) => Object.freeze({
    lo, hi, jobShare, customerShare,
  })));

  class InputValidationError extends Error {
    constructor(message) {
      super(message);
      this.name = "InputValidationError";
    }
  }

  const CONFIG_ALIASES = Object.freeze({
    storm_id: "stormId",
    n_outages: "nOutages",
    customers_per_outage: "customersPerOutage",
    wind_threshold_mph: "windThresholdMph",
    wind_excess_scale_mph: "windExcessScaleMph",
    wind_exponent: "windExponent",
    rain_coefficient: "rainCoefficient",
    rain_reference_in: "rainReferenceIn",
    rain_score_cap: "rainScoreCap",
    exposure_exponent: "exposureExponent",
    customer_smoothing_km: "customerSmoothingKm",
    rural_baseline_fraction: "ruralBaselineFraction",
    gaussian_bandwidth_km: "gaussianBandwidthKm",
    placement_mode: "placementMode",
    candidate_segment_length_km: "candidateSegmentLengthKm",
    line_integration_step_km: "lineIntegrationStepKm",
    feeder_susceptibility: "feederSusceptibility",
    lateral_susceptibility: "lateralSusceptibility",
    service_failure_weight: "serviceFailureWeight",
    service_group_maximum_customers: "serviceGroupMaximumCustomers",
  });

  function finiteNumber(value, label) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new InputValidationError(`${label} must be a finite number`);
    }
    return value;
  }

  function integer(value, label, minimum) {
    if (!Number.isInteger(value)) {
      throw new InputValidationError(`${label} must be an integer`);
    }
    if (minimum !== undefined && value < minimum) {
      throw new InputValidationError(`${label} must be >= ${minimum}`);
    }
    return value;
  }

  function validateConfig(input = {}) {
    if (!input || typeof input !== "object" || Array.isArray(input)) {
      throw new InputValidationError("config must be an object");
    }
    const normalized = {};
    for (const [key, value] of Object.entries(input)) {
      const normalizedKey = CONFIG_ALIASES[key] || key;
      if (normalizedKey === "customersPerOutage") {
        if (value !== LEGACY_CUSTOMERS_PER_OUTAGE) {
          throw new InputValidationError(
            "customersPerOutage is a deprecated compatibility field and must be 50 when present; topology sizing determines production counts",
          );
        }
        continue;
      }
      if (!Object.prototype.hasOwnProperty.call(DEFAULT_CONFIG, normalizedKey)) {
        throw new InputValidationError(`unknown configuration field: ${key}`);
      }
      normalized[normalizedKey] = value;
    }
    const config = { ...DEFAULT_CONFIG, ...normalized };
    if (typeof config.stormId !== "string" || !config.stormId.trim()) {
      throw new InputValidationError("stormId must not be empty");
    }
    if (!["failure_oriented", "impact_weighted"].includes(config.placementMode)) {
      throw new InputValidationError(
        "placementMode must be failure_oriented or impact_weighted",
      );
    }
    integer(config.seed, "seed");
    integer(config.nOutages, "nOutages", 1);
    for (const key of ["windThresholdMph", "rainCoefficient", "ruralBaselineFraction"]) {
      if (finiteNumber(config[key], key) < 0) {
        throw new InputValidationError(`${key} must be >= 0`);
      }
    }
    for (const key of [
      "windExcessScaleMph", "windExponent", "rainReferenceIn", "rainScoreCap",
      "exposureExponent", "gaussianBandwidthKm",
      "candidateSegmentLengthKm", "lineIntegrationStepKm",
      "feederSusceptibility", "lateralSusceptibility",
    ]) {
      if (finiteNumber(config[key], key) <= 0) {
        throw new InputValidationError(`${key} must be > 0`);
      }
    }
    if (finiteNumber(config.customerSmoothingKm, "customerSmoothingKm") < 0) {
      throw new InputValidationError("customerSmoothingKm must be >= 0");
    }
    if (finiteNumber(config.serviceFailureWeight, "serviceFailureWeight") < 0) {
      throw new InputValidationError("serviceFailureWeight must be >= 0");
    }
    if (integer(
      config.serviceGroupMaximumCustomers,
      "serviceGroupMaximumCustomers",
      1,
    ) !== 15) {
      throw new InputValidationError(
        "serviceGroupMaximumCustomers currently supports the calibrated value 15",
      );
    }
    if (config.windThresholdMph >= 250) {
      throw new InputValidationError("windThresholdMph must be within [0, 250)");
    }
    return Object.freeze(config);
  }

  function assertCoordinate(point, label) {
    if (!Array.isArray(point) || point.length !== 2) {
      throw new InputValidationError(`${label} must contain [longitude, latitude]`);
    }
    const lon = finiteNumber(point[0], `${label}[0]`);
    const lat = finiteNumber(point[1], `${label}[1]`);
    if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
      throw new InputValidationError(`${label} is outside valid longitude/latitude bounds`);
    }
    return [lon, lat];
  }

  function extractBoundaryRings(boundary) {
    let value = boundary;
    if (Array.isArray(value) && value.length && value[0] && value[0].geojson) {
      value = value[0].geojson;
    }
    if (value && value.type === "Feature") value = value.geometry;
    if (value && value.geojson) value = value.geojson;
    const geometries = value && value.type === "FeatureCollection"
      ? value.features.map((feature) => feature.geometry)
      : value && value.type === "GeometryCollection"
        ? value.geometries
        : [value];
    const rings = [];
    for (const geometry of geometries) {
      if (!geometry || !Array.isArray(geometry.coordinates)) continue;
      const polygonRings = geometry.type === "Polygon"
        ? geometry.coordinates
        : geometry.type === "MultiPolygon"
          ? geometry.coordinates.flat()
          : null;
      if (!polygonRings) continue;
      for (const [ringIndex, ring] of polygonRings.entries()) {
        if (!Array.isArray(ring) || ring.length < 3) {
          throw new InputValidationError(`boundary ring ${ringIndex} must have at least three points`);
        }
        rings.push(ring.map((point, index) => assertCoordinate(point, `boundary ring ${ringIndex} point ${index}`)));
      }
    }
    if (!rings.length) throw new InputValidationError("boundary must contain a Polygon or MultiPolygon");
    return rings;
  }

  function pointOnSegment(lon, lat, a, b, tolerance = 1e-10) {
    const cross = (lon - a[0]) * (b[1] - a[1]) - (lat - a[1]) * (b[0] - a[0]);
    return Math.abs(cross) <= tolerance
      && lon >= Math.min(a[0], b[0]) - tolerance
      && lon <= Math.max(a[0], b[0]) + tolerance
      && lat >= Math.min(a[1], b[1]) - tolerance
      && lat <= Math.max(a[1], b[1]) + tolerance;
  }

  function pointInRing(lon, lat, ring) {
    let inside = false;
    let previous = ring[ring.length - 1];
    for (const current of ring) {
      if (pointOnSegment(lon, lat, previous, current)) return true;
      if ((current[1] > lat) !== (previous[1] > lat)) {
        const intersection = (previous[0] - current[0]) * (lat - current[1])
          / (previous[1] - current[1]) + current[0];
        if (lon < intersection) inside = !inside;
      }
      previous = current;
    }
    return inside;
  }

  function pointInBoundary(boundaryOrRings, latitude, longitude) {
    const rings = Array.isArray(boundaryOrRings)
      && boundaryOrRings.length
      && Array.isArray(boundaryOrRings[0])
      && Array.isArray(boundaryOrRings[0][0])
      ? boundaryOrRings
      : extractBoundaryRings(boundaryOrRings);
    let count = 0;
    for (const ring of rings) if (pointInRing(longitude, latitude, ring)) count += 1;
    return count % 2 === 1;
  }

  function validateCoordinates(values, label) {
    if (!Array.isArray(values) || values.length < 2) {
      throw new InputValidationError(`${label} must contain at least two coordinates`);
    }
    const result = values.map((value, index) => finiteNumber(value, `${label}[${index}]`));
    for (let index = 1; index < result.length; index += 1) {
      if (result[index] <= result[index - 1]) {
        throw new InputValidationError(`${label} must be strictly increasing`);
      }
    }
    return result;
  }

  function buildConnecticutMask(boundary, latitudes, longitudes) {
    const lats = validateCoordinates(latitudes, "latitudes");
    const lons = validateCoordinates(longitudes, "longitudes");
    const rings = extractBoundaryRings(boundary);
    return lats.map((lat) => lons.map((lon) => pointInBoundary(rings, lat, lon)));
  }

  function validateGrid(values, rows, columns, label, bounds) {
    if (!Array.isArray(values) || values.length !== rows
      || values.some((row) => !Array.isArray(row) || row.length !== columns)) {
      throw new InputValidationError(`${label} shape must be ${rows} x ${columns}`);
    }
    return values.map((row, rowIndex) => row.map((value, columnIndex) => {
      const number = finiteNumber(value, `${label}[${rowIndex}][${columnIndex}]`);
      if (bounds && (number < bounds[0] || number > bounds[1])) {
        throw new InputValidationError(`${label}[${rowIndex}][${columnIndex}] must be within [${bounds[0]}, ${bounds[1]}]`);
      }
      return number;
    }));
  }

  function bracketingIndices(values, value) {
    if (value <= values[0]) return [0, 0, 0];
    const last = values.length - 1;
    if (value >= values[last]) return [last, last, 0];
    let low = 0;
    let high = last;
    while (high - low > 1) {
      const middle = (low + high) >> 1;
      if (values[middle] <= value) low = middle;
      else high = middle;
    }
    return [low, high, (value - values[low]) / (values[high] - values[low])];
  }

  function nearestValidCell(mask, latitudes, longitudes, latitude, longitude) {
    let best = null;
    let bestDistance = Infinity;
    const lonScale = Math.cos(latitude * Math.PI / 180);
    for (let row = 0; row < latitudes.length; row += 1) {
      for (let column = 0; column < longitudes.length; column += 1) {
        if (!mask[row][column]) continue;
        const distance = (latitudes[row] - latitude) ** 2
          + ((longitudes[column] - longitude) * lonScale) ** 2;
        if (distance < bestDistance) {
          bestDistance = distance;
          best = [row, column];
        }
      }
    }
    if (!best) throw new InputValidationError("Connecticut mask contains no valid cells");
    return best;
  }

  function normalizePopulationPoints(points) {
    if (!Array.isArray(points) || !points.length) {
      throw new InputValidationError("Census population points must be a non-empty array");
    }
    return points.map((point, index) => {
      if (!point || typeof point !== "object") {
        throw new InputValidationError(`populationPoints[${index}] must be an object`);
      }
      const population = finiteNumber(point.pop ?? point.population, `populationPoints[${index}].pop`);
      const latitude = finiteNumber(point.lat ?? point.latitude, `populationPoints[${index}].lat`);
      const longitude = finiteNumber(point.lon ?? point.longitude, `populationPoints[${index}].lon`);
      if (population < 0) throw new InputValidationError(`populationPoints[${index}].pop must be >= 0`);
      if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
        throw new InputValidationError(`populationPoints[${index}] is outside valid longitude/latitude bounds`);
      }
      return { geoid: String(point.geoid ?? point.GEOID ?? index), population, latitude, longitude };
    });
  }

  function rasterizePopulationPersons(populationPoints, latitudes, longitudes, mask) {
    const points = normalizePopulationPoints(populationPoints);
    const rows = latitudes.length;
    const columns = longitudes.length;
    const grid = Array.from({ length: rows }, () => Array(columns).fill(0));
    for (const point of points) {
      const [row0, row1, rowFraction] = bracketingIndices(latitudes, point.latitude);
      const [column0, column1, columnFraction] = bracketingIndices(longitudes, point.longitude);
      const candidates = new Map();
      for (const [row, rowWeight] of [[row0, 1 - rowFraction], [row1, rowFraction]]) {
        for (const [column, columnWeight] of [[column0, 1 - columnFraction], [column1, columnFraction]]) {
          const weight = rowWeight * columnWeight;
          if (weight > 0 && mask[row][column]) {
            const key = row * columns + column;
            candidates.set(key, (candidates.get(key) || 0) + weight);
          }
        }
      }
      let totalWeight = [...candidates.values()].reduce((sum, value) => sum + value, 0);
      if (totalWeight <= 0) {
        const [row, column] = nearestValidCell(mask, latitudes, longitudes, point.latitude, point.longitude);
        candidates.clear();
        candidates.set(row * columns + column, 1);
        totalWeight = 1;
      }
      for (const [key, weight] of candidates) {
        const row = Math.floor(key / columns);
        const column = key % columns;
        grid[row][column] += point.population * weight / totalWeight;
      }
    }
    return grid;
  }

  function scaleGrid(grid, scalar) {
    return grid.map((row) => row.map((value) => value * scalar));
  }

  function rasterizeCustomerAccounts(populationPoints, latitudes, longitudes, mask) {
    return scaleGrid(
      rasterizePopulationPersons(populationPoints, latitudes, longitudes, mask),
      POPULATION_TO_CUSTOMER_RATIO,
    );
  }

  function gaussianKernel(sigmaCells) {
    if (sigmaCells <= 0) return [1];
    const radius = Math.max(1, Math.ceil(4 * sigmaCells));
    const kernel = [];
    for (let offset = -radius; offset <= radius; offset += 1) {
      kernel.push(Math.exp(-0.5 * (offset / sigmaCells) ** 2));
    }
    const total = kernel.reduce((sum, value) => sum + value, 0);
    return kernel.map((value) => value / total);
  }

  function convolveRows(grid, kernel) {
    const radius = kernel.length >> 1;
    const output = grid.map((row) => Array(row.length).fill(0));
    for (let row = 0; row < grid.length; row += 1) {
      for (let column = 0; column < grid[0].length; column += 1) {
        let value = 0;
        for (let index = 0; index < kernel.length; index += 1) {
          const source = column + index - radius;
          if (source >= 0 && source < grid[0].length) value += grid[row][source] * kernel[index];
        }
        output[row][column] = value;
      }
    }
    return output;
  }

  function convolveColumns(grid, kernel) {
    const radius = kernel.length >> 1;
    const output = grid.map((row) => Array(row.length).fill(0));
    for (let row = 0; row < grid.length; row += 1) {
      for (let column = 0; column < grid[0].length; column += 1) {
        let value = 0;
        for (let index = 0; index < kernel.length; index += 1) {
          const source = row + index - radius;
          if (source >= 0 && source < grid.length) value += grid[source][column] * kernel[index];
        }
        output[row][column] = value;
      }
    }
    return output;
  }

  function separableGaussian(grid, sigmaRows, sigmaColumns) {
    return convolveColumns(convolveRows(grid, gaussianKernel(sigmaColumns)), gaussianKernel(sigmaRows));
  }

  function gridCellSpacingKm(latitudes, longitudes) {
    const latitudeStep = latitudes.slice(1).reduce((sum, value, index) => sum + value - latitudes[index], 0)
      / (latitudes.length - 1);
    const longitudeStep = longitudes.slice(1).reduce((sum, value, index) => sum + value - longitudes[index], 0)
      / (longitudes.length - 1);
    const meanLatitude = latitudes.reduce((sum, value) => sum + value, 0) / latitudes.length;
    return {
      latitudeCellKm: Math.abs(latitudeStep) * 111.195,
      longitudeCellKm: Math.abs(longitudeStep) * 111.195 * Math.cos(meanLatitude * Math.PI / 180),
    };
  }

  function spatialGridMetadata(latitudes, longitudes) {
    const spacing = gridCellSpacingKm(latitudes, longitudes);
    const longitudeScales = latitudes.map(
      (latitude) => 111.195 * Math.cos(latitude * Math.PI / 180),
    );
    const minimumLongitudeScale = Math.min(...longitudeScales);
    const maximumLongitudeScale = Math.max(...longitudeScales);
    return {
      coordinateReferenceSystem: "EPSG:4326",
      coordinateOrder: "[longitude, latitude]",
      gridType: "regular_geographic_grid_nodes",
      gridValuesLocatedAt: "node_centers",
      rows: latitudes.length,
      columns: longitudes.length,
      latitudeCellKm: spacing.latitudeCellKm,
      longitudeCellKmAtMeanLatitude: spacing.longitudeCellKm,
      approximateCellAreaKm2AtMeanLatitude:
        spacing.latitudeCellKm * spacing.longitudeCellKm,
      longitudeKmPerDegreeRange: [minimumLongitudeScale, maximumLongitudeScale],
      distanceApproximation: "spherical Earth, radius 6371.0088 km",
      interpolation: "bilinear in latitude/longitude coordinates",
      boundaryRule: "grid node center inside polygon; polygon edges count as inside",
      boundaryPolygonSemantics: "even-odd rings",
      gridNormalizationMeasure: "equal node weights; population values are mass per node",
    };
  }

  function gridTotal(grid) {
    let total = 0;
    for (const row of grid) for (const value of row) total += value;
    return total;
  }

  function coordinatesMatch(actual, expected) {
    return (Array.isArray(actual) || ArrayBuffer.isView(actual))
      && actual.length === expected.length
      && actual.every((value, index) => Number.isFinite(value)
        && Math.abs(value - expected[index]) <= 1e-12);
  }

  function reshapeFlatGrid(values, rows, columns, label) {
    if (!Array.isArray(values) && !ArrayBuffer.isView(values)) {
      throw new InputValidationError(`${label} must be an array or typed array`);
    }
    if (values.length !== rows * columns) {
      throw new InputValidationError(`${label} must contain exactly ${rows * columns} values`);
    }
    return Array.from({ length: rows }, (_, row) =>
      Array.from(values.slice(row * columns, (row + 1) * columns)));
  }

  function normalizeStoredMask(populationGrid, rows, columns) {
    const stored = populationGrid.connecticutMask
      ?? populationGrid.connecticut_mask
      ?? populationGrid.mask;
    if (stored === undefined) return null;
    let grid;
    if (Array.isArray(stored[0])) {
      if (stored.length !== rows
          || stored.some((row) => !Array.isArray(row) || row.length !== columns)) {
        throw new InputValidationError(
          `populationGrid.connecticutMask shape must be ${rows} x ${columns}`,
        );
      }
      grid = stored;
    } else {
      grid = reshapeFlatGrid(stored, rows, columns, "populationGrid.connecticutMask");
    }
    const mask = grid.map((row) => row.map((value) => {
      if (value !== 0 && value !== 1 && value !== false && value !== true) {
        throw new InputValidationError("populationGrid.connecticutMask values must be Boolean or 0/1");
      }
      return Boolean(value);
    }));
    if (!mask.some((row) => row.some(Boolean))) {
      throw new InputValidationError("populationGrid.connecticutMask contains no in-state nodes");
    }
    return mask;
  }

  function normalizePrecomputedPopulationGrid(populationGrid, latitudes, longitudes, fallbackMask) {
    if (!populationGrid || typeof populationGrid !== "object" || Array.isArray(populationGrid)) {
      throw new InputValidationError("populationGrid must be an object");
    }
    const metadata = populationGrid.grid || populationGrid;
    const sourceLatitudes = metadata.latitudes ?? metadata.lats;
    const sourceLongitudes = metadata.longitudes ?? metadata.lons;
    if (!coordinatesMatch(sourceLatitudes, latitudes)
        || !coordinatesMatch(sourceLongitudes, longitudes)) {
      throw new InputValidationError("populationGrid coordinates must exactly match the weather grid");
    }
    const rows = latitudes.length;
    const columns = longitudes.length;
    const storedMask = normalizeStoredMask(populationGrid, rows, columns);
    const mask = storedMask || fallbackMask;
    const storedValues = populationGrid.populationPersons
      ?? populationGrid.population_persons
      ?? populationGrid.values;
    const values = Array.isArray(storedValues?.[0])
      ? validateGrid(storedValues, rows, columns, "populationGrid.populationPersons")
      : reshapeFlatGrid(storedValues, rows, columns, "populationGrid.populationPersons");
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        const value = finiteNumber(values[row][column], `populationGrid[${row}][${column}]`);
        if (value < 0) throw new InputValidationError("populationGrid values must be nonnegative");
        if (!mask[row][column] && value !== 0) {
          throw new InputValidationError("populationGrid must contain zero population outside its Connecticut mask");
        }
      }
    }
    const actualTotal = gridTotal(values);
    const declaredTotal = populationGrid.source?.totalPopulationPersons;
    if (declaredTotal !== undefined) {
      const expectedTotal = finiteNumber(
        declaredTotal, "populationGrid.source.totalPopulationPersons",
      );
      if (Math.abs(actualTotal - expectedTotal) > 1e-6) {
        throw new InputValidationError(
          "populationGrid total does not match source.totalPopulationPersons",
        );
      }
    }
    return {
      mask,
      values: values.map((row) => row.slice()),
      metadata: populationGrid.source || {},
    };
  }

  function boundaryAwareGaussianSmooth(values, mask, options) {
    const smoothingKm = finiteNumber(options.smoothingKm, "smoothingKm");
    const latitudeCellKm = finiteNumber(options.latitudeCellKm, "latitudeCellKm");
    const longitudeCellKm = finiteNumber(options.longitudeCellKm, "longitudeCellKm");
    const preserveTotal = options.preserveTotal !== false;
    if (smoothingKm < 0 || latitudeCellKm <= 0 || longitudeCellKm <= 0) {
      throw new InputValidationError("smoothing must be nonnegative and grid-cell spacing must be positive");
    }
    const rows = mask.length;
    const columns = mask[0]?.length || 0;
    const grid = validateGrid(values, rows, columns, "Gaussian input");
    let total = 0;
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        if (grid[row][column] < 0) throw new InputValidationError("Gaussian input must be nonnegative");
        if (mask[row][column]) total += grid[row][column];
        else if (grid[row][column] !== 0) throw new InputValidationError("Gaussian input must be zero outside Connecticut");
      }
    }
    if (preserveTotal && total <= 0) throw new InputValidationError("Gaussian input has no positive in-state mass");
    if (smoothingKm === 0) return grid.map((row) => row.slice());
    const maskValues = mask.map((row) => row.map((cell) => cell ? 1 : 0));
    const sigmaRows = smoothingKm / latitudeCellKm;
    const sigmaColumns = smoothingKm / longitudeCellKm;
    const numerator = separableGaussian(grid, sigmaRows, sigmaColumns);
    const denominator = separableGaussian(maskValues, sigmaRows, sigmaColumns);
    const result = mask.map((row, rowIndex) => row.map((cell, columnIndex) =>
      cell && denominator[rowIndex][columnIndex] > 1e-15
        ? numerator[rowIndex][columnIndex] / denominator[rowIndex][columnIndex]
        : 0));
    if (preserveTotal) {
      const scale = total / gridTotal(result);
      for (let row = 0; row < rows; row += 1) {
        for (let column = 0; column < columns; column += 1) result[row][column] *= scale;
      }
    }
    return result;
  }

  function populationSourceFromInput(input) {
    const source = input.populationGrid
      ?? input.population_grid
      ?? input.censusBlocks
      ?? input.census_blocks
      // Compatibility for saved version-2 requests and compact test fixtures.
      ?? input.censusTracts
      ?? input.census_tracts;
    if (source === undefined) {
      throw new InputValidationError("model input requires populationGrid or censusBlocks");
    }
    return source;
  }

  function buildCustomerExposureSurface(boundary, populationSource, latitudes, longitudes, options = {}) {
    const smoothingKm = options.smoothingKm ?? DEFAULT_CONFIG.customerSmoothingKm;
    const ruralBaselineFraction = options.ruralBaselineFraction ?? DEFAULT_CONFIG.ruralBaselineFraction;
    if (finiteNumber(ruralBaselineFraction, "ruralBaselineFraction") < 0) {
      throw new InputValidationError("ruralBaselineFraction must be >= 0");
    }
    const lats = validateCoordinates(latitudes, "latitudes");
    const lons = validateCoordinates(longitudes, "longitudes");
    const boundaryMask = buildConnecticutMask(boundary, lats, lons);
    let mask = boundaryMask;
    let rawPopulationPersons;
    let sourceMetadata;
    let inputRepresentation;
    if (Array.isArray(populationSource)) {
      rawPopulationPersons = rasterizePopulationPersons(populationSource, lats, lons, mask);
      const looksLikeBlocks = populationSource.length > 0
        && populationSource.every((point) => String(point.geoid ?? point.GEOID ?? "").length === 15);
      sourceMetadata = {
        geography: looksLikeBlocks ? "Census block" : "Census population point",
        coordinateRepresentation: "provided point coordinates",
        recordCount: populationSource.length,
      };
      inputRepresentation = "population_points_rasterized_at_runtime";
    } else {
      const normalizedGrid = normalizePrecomputedPopulationGrid(
        populationSource, lats, lons, boundaryMask,
      );
      mask = normalizedGrid.mask;
      rawPopulationPersons = normalizedGrid.values;
      sourceMetadata = normalizedGrid.metadata;
      inputRepresentation = "precomputed_unsmoothed_population_grid";
    }
    const spacing = gridCellSpacingKm(lats, lons);
    const smoothedPopulationPersons = boundaryAwareGaussianSmooth(rawPopulationPersons, mask, {
      smoothingKm, ...spacing,
    });
    const totalPopulationPersons = gridTotal(rawPopulationPersons);
    const validCellCount = mask.reduce((sum, row) => sum + row.filter(Boolean).length, 0);
    if (!validCellCount || totalPopulationPersons <= 0) {
      throw new InputValidationError("population surface has no in-state persons");
    }
    const baseline = ruralBaselineFraction * totalPopulationPersons / validCellCount;
    if (baseline) {
      for (let row = 0; row < mask.length; row += 1) {
        for (let column = 0; column < mask[0].length; column += 1) {
          if (mask[row][column]) smoothedPopulationPersons[row][column] += baseline;
        }
      }
    }
    const rescale = totalPopulationPersons / gridTotal(smoothedPopulationPersons);
    for (let row = 0; row < mask.length; row += 1) {
      for (let column = 0; column < mask[0].length; column += 1) {
        smoothedPopulationPersons[row][column] *= rescale;
      }
    }
    const rawCustomerAccounts = scaleGrid(rawPopulationPersons, POPULATION_TO_CUSTOMER_RATIO);
    const smoothedCustomerAccounts = scaleGrid(
      smoothedPopulationPersons,
      POPULATION_TO_CUSTOMER_RATIO,
    );
    const totalCustomerAccounts = totalPopulationPersons * POPULATION_TO_CUSTOMER_RATIO;
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_customer_exposure_v3",
      sourceQuantity: "census_population_persons",
      accountEstimateMethod: "uniform_statewide_population_ratio",
      populationToCustomerAccountRatio: POPULATION_TO_CUSTOMER_RATIO,
      latitudes: lats,
      longitudes: lons,
      connecticutMask: mask,
      rawPopulationPersons,
      smoothedPopulationPersons,
      totalPopulationPersons,
      rawCustomerAccounts,
      smoothedCustomerAccounts,
      totalCustomerAccounts,
      smoothingKm,
      ruralBaselineFraction,
      ...spacing,
      spatialMethod: {
        ...spatialGridMetadata(lats, lons),
        sourceQuantity: sourceMetadata.dataset
          ? `${sourceMetadata.dataset} population persons`
          : "Census population persons",
        sourceGeography: sourceMetadata.geography || "Census population point",
        sourceCoordinateRepresentation:
          sourceMetadata.coordinateRepresentation || "provided point coordinates",
        boundarySource: sourceMetadata.boundaryMask || "runtime boundary input",
        sourceRecordCount: sourceMetadata.blockCount
          ?? sourceMetadata.recordCount
          ?? null,
        inputRepresentation,
        populationAllocation:
          "bilinear allocation to four surrounding valid nodes, renormalized at boundary; nearest valid node fallback",
        smoothing: {
          applied: smoothingKm > 0,
          kernel: smoothingKm > 0 ? "separable Gaussian" : "none",
          standardDeviationKm: smoothingKm,
          nominalTruncationStandardDeviations: smoothingKm > 0 ? 4 : 0,
          boundaryCorrection: smoothingKm > 0
            ? "normalized convolution by binary in-state node mask"
            : "not applicable",
          massPreservation: smoothingKm > 0
            ? "rescaled to the exact pre-smoothing in-state population total"
            : "identity operation; total unchanged",
        },
        uniformExposureBaselineFraction: ruralBaselineFraction,
        accountConversion:
          `estimated accounts = persons * ${POPULATION_TO_CUSTOMER_RATIO}`,
      },
      summary: {
        rawPopulationTotal: gridTotal(rawPopulationPersons),
        smoothedPopulationTotal: gridTotal(smoothedPopulationPersons),
        rawTotal: gridTotal(rawCustomerAccounts),
        smoothedTotal: gridTotal(smoothedCustomerAccounts),
        validCellCount,
      },
    };
  }

  function weatherSeverityScore(windMph, rainAccumulationIn, options = {}) {
    const wind = finiteNumber(windMph, "windMph");
    const rain = finiteNumber(rainAccumulationIn, "rainAccumulationIn");
    const threshold = options.windThresholdMph ?? DEFAULT_CONFIG.windThresholdMph;
    const scale = options.windExcessScaleMph ?? DEFAULT_CONFIG.windExcessScaleMph;
    const exponent = options.windExponent ?? DEFAULT_CONFIG.windExponent;
    const rainReference = options.rainReferenceIn ?? DEFAULT_CONFIG.rainReferenceIn;
    const coefficient = options.rainCoefficient ?? DEFAULT_CONFIG.rainCoefficient;
    const rainCap = options.rainScoreCap ?? DEFAULT_CONFIG.rainScoreCap;
    if (wind < 0 || wind > 250) throw new InputValidationError("windMph must be within [0, 250]");
    if (rain < 0 || rain > 15) throw new InputValidationError("rainAccumulationIn must be within [0, 15]");
    if (threshold < 0 || threshold >= 250 || scale <= 0 || exponent <= 0
      || rainReference <= 0 || coefficient < 0 || rainCap <= 0) {
      throw new InputValidationError("weather severity parameters are outside their valid ranges");
    }
    const windDamage = (Math.max(0, wind - threshold) / scale) ** exponent;
    const rainAmplification = 1 + coefficient * Math.min(rain / rainReference, rainCap);
    return { windDamage, rainAmplification, weatherSeverity: windDamage * rainAmplification };
  }

  function normalizeWeather(weather) {
    if (!weather || typeof weather !== "object") throw new InputValidationError("weather must be an object");
    const storm = weather.storm || weather;
    const grid = weather.grid || weather;
    const latitudes = validateCoordinates(grid.lats ?? grid.latitudes, "weather.lats");
    const longitudes = validateCoordinates(grid.lons ?? grid.longitudes, "weather.lons");
    return {
      latitudes,
      longitudes,
      stormId: String(storm.stormId ?? storm.storm_id ?? ""),
      name: String(storm.name ?? storm.stormId ?? storm.storm_id ?? ""),
      date: String(storm.date ?? ""),
      precipitationType: String(storm.precipitationType ?? storm.precipitation_type ?? storm.precip_type ?? ""),
      rainInputKind: String(storm.rainInputKind ?? storm.rain_input_kind ?? "one_hour_accumulation"),
      wind: validateGrid(storm.peakWindMph ?? storm.peak_wind_mph, latitudes.length, longitudes.length, "peakWindMph", [0, 250]),
      rain: validateGrid(storm.peakRainIn ?? storm.peak_rain_in, latitudes.length, longitudes.length, "peakRainIn", [0, 15]),
    };
  }

  function normalizeStoredGrid(values, rows, columns, label, bounds) {
    if (Array.isArray(values) && values.length === rows * columns
      && values.every((value) => typeof value === "number")) {
      const nested = Array.from({ length: rows }, (_, row) =>
        values.slice(row * columns, (row + 1) * columns));
      return validateGrid(nested, rows, columns, label, bounds);
    }
    return validateGrid(values, rows, columns, label, bounds);
  }

  function normalizeWeatherTimeline(weatherTimeline) {
    if (!weatherTimeline || typeof weatherTimeline !== "object") {
      throw new InputValidationError("weatherTimeline must be an object");
    }
    const storm = weatherTimeline.storm || weatherTimeline;
    const grid = weatherTimeline.grid || weatherTimeline;
    const latitudes = validateCoordinates(grid.lats ?? grid.latitudes, "weatherTimeline.grid.lats");
    const longitudes = validateCoordinates(grid.lons ?? grid.longitudes, "weatherTimeline.grid.lons");
    const stormId = String(storm.stormId ?? storm.storm_id ?? "");
    if (!stormId) throw new InputValidationError("weatherTimeline stormId must not be empty");
    if (!Array.isArray(storm.frames) || storm.frames.length < 2) {
      throw new InputValidationError("weatherTimeline.frames must contain at least two hourly frames");
    }
    const intervalMinutes = integer(
      storm.intervalMinutes ?? storm.interval_minutes ?? 60,
      "weatherTimeline.intervalMinutes",
      1,
    );
    let previousTime = null;
    const frames = storm.frames.map((frame, index) => {
      if (!frame || typeof frame !== "object") {
        throw new InputValidationError(`weatherTimeline.frames[${index}] must be an object`);
      }
      const validTime = String(frame.validTime ?? frame.valid_time ?? "");
      const epochMs = Date.parse(validTime);
      if (!validTime || !Number.isFinite(epochMs)) {
        throw new InputValidationError(`weatherTimeline.frames[${index}].validTime is invalid`);
      }
      if (previousTime !== null && epochMs - previousTime !== intervalMinutes * 60 * 1000) {
        throw new InputValidationError("weatherTimeline frame timestamps must match intervalMinutes");
      }
      previousTime = epochMs;
      return {
        validTime: new Date(epochMs).toISOString().replace(".000Z", "Z"),
        windGustMph: normalizeStoredGrid(
          frame.windGustMph ?? frame.wind_gust_mph,
          latitudes.length,
          longitudes.length,
          `weatherTimeline.frames[${index}].windGustMph`,
          [0, 250],
        ),
        rain1hIn: normalizeStoredGrid(
          frame.rain1hIn ?? frame.rain_1h_in,
          latitudes.length,
          longitudes.length,
          `weatherTimeline.frames[${index}].rain1hIn`,
          [0, 15],
        ),
        rain6hIn: normalizeStoredGrid(
          frame.rain6hIn ?? frame.rain_6h_in,
          latitudes.length,
          longitudes.length,
          `weatherTimeline.frames[${index}].rain6hIn`,
          [0, 15],
        ),
      };
    });
    return {
      stormId,
      name: String(storm.name ?? stormId),
      precipitationType: String(storm.precipitationType ?? storm.precipitation_type ?? storm.precip_type ?? ""),
      intervalMinutes,
      antecedentRainHours: integer(
        storm.antecedentRainHours ?? storm.antecedent_rain_hours ?? 6,
        "weatherTimeline.antecedentRainHours",
        1,
      ),
      startTime: frames[0].validTime,
      endTime: frames[frames.length - 1].validTime,
      latitudes,
      longitudes,
      frames,
    };
  }

  function buildWeatherSeveritySurface(weather, connecticutMask, options = {}) {
    const normalized = normalizeWeather(weather);
    const { latitudes, longitudes } = normalized;
    if (!Array.isArray(connecticutMask) || connecticutMask.length !== latitudes.length
      || connecticutMask.some((row) => !Array.isArray(row) || row.length !== longitudes.length
        || row.some((cell) => typeof cell !== "boolean"))) {
      throw new InputValidationError(`connecticutMask shape must be ${latitudes.length} x ${longitudes.length} booleans`);
    }
    const windMph = [], rainAccumulationIn = [], windDamageScore = [], rainAmplification = [], weatherSeverity = [];
    for (let row = 0; row < latitudes.length; row += 1) {
      const windRow = [], rainRow = [], damageRow = [], amplificationRow = [], severityRow = [];
      for (let column = 0; column < longitudes.length; column += 1) {
        const components = weatherSeverityScore(normalized.wind[row][column], normalized.rain[row][column], options);
        const inside = Boolean(connecticutMask[row][column]);
        windRow.push(inside ? normalized.wind[row][column] : 0);
        rainRow.push(inside ? normalized.rain[row][column] : 0);
        damageRow.push(inside ? components.windDamage : 0);
        amplificationRow.push(inside ? components.rainAmplification : 0);
        severityRow.push(inside ? components.weatherSeverity : 0);
      }
      windMph.push(windRow); rainAccumulationIn.push(rainRow); windDamageScore.push(damageRow);
      rainAmplification.push(amplificationRow); weatherSeverity.push(severityRow);
    }
    const flatSeverity = weatherSeverity.flat();
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_weather_severity_v2",
      stormId: normalized.stormId,
      stormName: normalized.name,
      stormDate: normalized.date,
      precipitationType: normalized.precipitationType,
      rainInputKind: normalized.rainInputKind,
      latitudes, longitudes, connecticutMask, windMph,
      rainAccumulationIn,
      // Deprecated compatibility alias. The active timeline input is a six-hour
      // accumulation, so "per hour" is not a scientifically correct name.
      rainInPerHour: rainAccumulationIn,
      windDamageScore, rainAmplification, weatherSeverity,
      hazardIndex: weatherSeverity,
      spatialMethod: {
        ...spatialGridMetadata(latitudes, longitudes),
        hazardEquation:
          "max(0, (gust_mph - threshold_mph) / wind_excess_scale_mph)^wind_exponent"
          + " * (1 + rain_coefficient * min(rain_accumulation_in / rain_reference_in, rain_score_cap))",
        hazardInterpretation:
          "dimensionless relative storm stress; not an absolute component-failure probability",
        precipitationInput: normalized.rainInputKind,
      },
      summary: {
        positiveSeverityCells: flatSeverity.filter((value) => value > 0).length,
        maximumSeverity: Math.max(...flatSeverity),
      },
    };
  }

  function buildCombinedImpactSurface(customerSurface, weatherSurface, options = {}) {
    const exposureExponent = options.exposureExponent ?? DEFAULT_CONFIG.exposureExponent;
    const gaussianBandwidthKm = options.gaussianBandwidthKm ?? DEFAULT_CONFIG.gaussianBandwidthKm;
    if (exposureExponent <= 0 || gaussianBandwidthKm <= 0) {
      throw new InputValidationError("exposureExponent and gaussianBandwidthKm must be positive");
    }
    const mask = customerSurface.connecticutMask;
    const rows = customerSurface.latitudes.length;
    const columns = customerSurface.longitudes.length;
    const latitudeCoordinatesMatch = weatherSurface.latitudes.length === rows
      && weatherSurface.latitudes.every(
        (value, index) => value === customerSurface.latitudes[index],
      );
    const longitudeCoordinatesMatch = weatherSurface.longitudes.length === columns
      && weatherSurface.longitudes.every(
        (value, index) => value === customerSurface.longitudes[index],
      );
    if (!latitudeCoordinatesMatch || !longitudeCoordinatesMatch) {
      throw new InputValidationError("customer and weather grid coordinates must match exactly");
    }
    const validCellCount = customerSurface.summary.validCellCount;
    const meanExposure = customerSurface.summary.smoothedTotal / validCellCount;
    const relativeCustomerExposure = mask.map((row, rowIndex) => row.map((inside, columnIndex) =>
      inside ? customerSurface.smoothedCustomerAccounts[rowIndex][columnIndex] / meanExposure : 0));
    const rawImpact = mask.map((row, rowIndex) => row.map((inside, columnIndex) => inside
      ? weatherSurface.weatherSeverity[rowIndex][columnIndex]
        * relativeCustomerExposure[rowIndex][columnIndex] ** exposureExponent
      : 0));
    const rawTotal = gridTotal(rawImpact);
    const allowZeroImpact = options.allowZeroImpact === true;
    let smoothedImpact;
    if (rawTotal > 0) {
      smoothedImpact = boundaryAwareGaussianSmooth(rawImpact, mask, {
        smoothingKm: gaussianBandwidthKm,
        latitudeCellKm: customerSurface.latitudeCellKm,
        longitudeCellKm: customerSurface.longitudeCellKm,
      });
    } else if (allowZeroImpact) {
      smoothedImpact = mask.map((row) => row.map(() => 0));
    } else {
      // Preserve the snapshot model's explicit no-damage error contract.
      smoothedImpact = boundaryAwareGaussianSmooth(rawImpact, mask, {
        smoothingKm: gaussianBandwidthKm,
        latitudeCellKm: customerSurface.latitudeCellKm,
        longitudeCellKm: customerSurface.longitudeCellKm,
      });
    }
    const smoothedTotal = gridTotal(smoothedImpact);
    const normalizedImpactScore = mask.map((row, rowIndex) => row.map((inside, columnIndex) =>
      inside && smoothedTotal > 0 ? smoothedImpact[rowIndex][columnIndex] / smoothedTotal : 0));
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_risk_components_v2",
      stormId: weatherSurface.stormId,
      latitudes: customerSurface.latitudes,
      longitudes: customerSurface.longitudes,
      connecticutMask: mask,
      relativeCustomerExposure,
      relativeCustomerConsequenceIndex: relativeCustomerExposure,
      weatherSeverity: weatherSurface.weatherSeverity,
      hazardIndex: weatherSurface.weatherSeverity,
      rawImpact,
      smoothedImpact,
      normalizedImpactScore,
      rawImpactPriorityScore: rawImpact,
      smoothedImpactPriorityScore: smoothedImpact,
      normalizedImpactPriorityScore: normalizedImpactScore,
      // Deprecated compatibility alias. These normalized cell scores are not
      // marginal inclusion probabilities under fixed-size sampling.
      samplingProbability: normalizedImpactScore,
      exposureExponent,
      gaussianBandwidthKm,
      meanCustomerAccountsPerValidCell: meanExposure,
      interpretation: {
        hazardIndex:
          "dimensionless relative storm stress; not a calibrated failure probability",
        relativeCustomerConsequenceIndex:
          "smoothed estimated customer accounts divided by the in-state grid-node mean",
        impactPriorityScore:
          "hazardIndex * relativeCustomerConsequenceIndex^exposureExponent, then spatially smoothed",
        normalizedImpactPriorityScore:
          "relative grid score summing to one; not a marginal outage inclusion probability",
      },
      spatialMethod: {
        ...spatialGridMetadata(customerSurface.latitudes, customerSurface.longitudes),
        combination:
          "hazard_index * relative_customer_consequence_index^exposure_exponent",
        smoothing: {
          kernel: "separable Gaussian",
          standardDeviationKm: gaussianBandwidthKm,
          nominalTruncationStandardDeviations: 4,
          boundaryCorrection: "normalized convolution by binary in-state node mask",
          massPreservation: "rescaled to preserve the pre-smoothing impact-score sum",
        },
      },
      summary: {
        rawTotal,
        smoothedTotal,
        normalizedScoreTotal: gridTotal(normalizedImpactScore),
        probabilityTotal: gridTotal(normalizedImpactScore),
        rawPositiveCells: rawImpact.flat().filter((value) => value > 0).length,
        smoothedPositiveCells: smoothedImpact.flat().filter((value) => value > 0).length,
      },
    };
  }

  function haversineKm(a, b) {
    const lon1 = a[0] * Math.PI / 180;
    const lat1 = a[1] * Math.PI / 180;
    const lon2 = b[0] * Math.PI / 180;
    const lat2 = b[1] * Math.PI / 180;
    const dlon = lon2 - lon1;
    const dlat = lat2 - lat1;
    const value = Math.sin(dlat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dlon / 2) ** 2;
    return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(value)));
  }

  function bilinearStencil(latitudes, longitudes, latitude, longitude) {
    const [row0, row1, rowFraction] = bracketingIndices(latitudes, latitude);
    const [column0, column1, columnFraction] = bracketingIndices(longitudes, longitude);
    return { row0, row1, rowFraction, column0, column1, columnFraction };
  }

  function bilinearValueFromStencil(values, stencil) {
    const {
      row0, row1, rowFraction, column0, column1, columnFraction,
    } = stencil;
    const lower = values[row0][column0] * (1 - columnFraction)
      + values[row0][column1] * columnFraction;
    const upper = values[row1][column0] * (1 - columnFraction)
      + values[row1][column1] * columnFraction;
    return lower * (1 - rowFraction) + upper * rowFraction;
  }

  function bilinearGridValue(latitudes, longitudes, values, latitude, longitude) {
    if (!Array.isArray(values) || values.length !== latitudes.length
      || !Array.isArray(values[0]) || values[0].length !== longitudes.length) {
      throw new InputValidationError("bilinear grid shape does not match coordinates");
    }
    return bilinearValueFromStencil(
      values,
      bilinearStencil(latitudes, longitudes, latitude, longitude),
    );
  }

  function pathGeometry(coordinates) {
    const cumulativeKm = [0];
    for (let index = 1; index < coordinates.length; index += 1) {
      cumulativeKm.push(
        cumulativeKm[index - 1] + haversineKm(coordinates[index - 1], coordinates[index]),
      );
    }
    return {
      coordinates,
      cumulativeKm,
      lengthKm: cumulativeKm[cumulativeKm.length - 1],
    };
  }

  function nearestPointOnPath(coordinates, point) {
    const geometry = pathGeometry(coordinates);
    let best = null;
    for (let index = 0; index < coordinates.length - 1; index += 1) {
      const start = coordinates[index];
      const end = coordinates[index + 1];
      const referenceLatitude = (start[1] + end[1] + point[1]) / 3 * Math.PI / 180;
      const longitudeKm = 111.320 * Math.max(1e-9, Math.cos(referenceLatitude));
      const latitudeKm = 110.574;
      const dx = (end[0] - start[0]) * longitudeKm;
      const dy = (end[1] - start[1]) * latitudeKm;
      const px = (point[0] - start[0]) * longitudeKm;
      const py = (point[1] - start[1]) * latitudeKm;
      const lengthSquared = dx * dx + dy * dy;
      const fraction = Math.max(0, Math.min(1, lengthSquared > 0
        ? (px * dx + py * dy) / lengthSquared
        : 0));
      const projected = [
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
      ];
      const distanceKm = haversineKm(projected, point);
      const chainageKm = geometry.cumulativeKm[index]
        + (geometry.cumulativeKm[index + 1] - geometry.cumulativeKm[index]) * fraction;
      if (!best || distanceKm < best.distanceKm) {
        best = { projected, distanceKm, chainageKm, sourceSegmentIndex: index };
      }
    }
    return best;
  }

  function pointAlongPath(pathOrCoordinates, fraction) {
    const geometry = Array.isArray(pathOrCoordinates)
      ? pathGeometry(pathOrCoordinates)
      : pathOrCoordinates;
    const boundedFraction = Math.max(0, Math.min(1, fraction));
    if (geometry.lengthKm <= 0) return geometry.coordinates[0].slice();
    const targetKm = boundedFraction * geometry.lengthKm;
    let index = 1;
    while (index < geometry.cumulativeKm.length
      && geometry.cumulativeKm[index] < targetKm) index += 1;
    if (index >= geometry.coordinates.length) {
      return geometry.coordinates[geometry.coordinates.length - 1].slice();
    }
    const startKm = geometry.cumulativeKm[index - 1];
    const endKm = geometry.cumulativeKm[index];
    const localFraction = endKm > startKm ? (targetKm - startKm) / (endKm - startKm) : 0;
    const start = geometry.coordinates[index - 1];
    const end = geometry.coordinates[index];
    return [
      start[0] + (end[0] - start[0]) * localFraction,
      start[1] + (end[1] - start[1]) * localFraction,
    ];
  }

  function subpathByDistance(geometry, startKm, endKm) {
    const startFraction = geometry.lengthKm > 0 ? startKm / geometry.lengthKm : 0;
    const endFraction = geometry.lengthKm > 0 ? endKm / geometry.lengthKm : 1;
    const coordinates = [pointAlongPath(geometry, startFraction)];
    for (let index = 1; index < geometry.coordinates.length - 1; index += 1) {
      const distance = geometry.cumulativeKm[index];
      if (distance > startKm + 1e-12 && distance < endKm - 1e-12) {
        coordinates.push(geometry.coordinates[index].slice());
      }
    }
    coordinates.push(pointAlongPath(geometry, endFraction));
    return coordinates;
  }

  function standardizeLineSegments(coordinates, maximumLengthKm) {
    const maximum = finiteNumber(maximumLengthKm, "candidateSegmentLengthKm");
    if (maximum <= 0) throw new InputValidationError("candidateSegmentLengthKm must be > 0");
    const geometry = pathGeometry(coordinates);
    if (geometry.lengthKm <= 0) return [];
    const count = Math.max(1, Math.ceil(geometry.lengthKm / maximum));
    const intervalKm = geometry.lengthKm / count;
    return Array.from({ length: count }, (_, segmentIndex) => {
      const startKm = intervalKm * segmentIndex;
      const endKm = segmentIndex === count - 1
        ? geometry.lengthKm
        : intervalKm * (segmentIndex + 1);
      const pathCoordinates = subpathByDistance(geometry, startKm, endKm);
      const path = pathGeometry(pathCoordinates);
      return {
        segmentIndex,
        startChainageKm: startKm,
        endChainageKm: endKm,
        pathCoordinates,
        path,
        lengthKm: path.lengthKm,
        start: pathCoordinates[0],
        end: pathCoordinates[pathCoordinates.length - 1],
        midpoint: pointAlongPath(path, 0.5),
      };
    }).filter((segment) => segment.lengthKm > 0);
  }

  function integrateGridAlongPath(
    latitudes,
    longitudes,
    values,
    pathOrCoordinates,
    integrationStepKm,
  ) {
    const stepKm = finiteNumber(integrationStepKm, "lineIntegrationStepKm");
    if (stepKm <= 0) throw new InputValidationError("lineIntegrationStepKm must be > 0");
    const geometry = Array.isArray(pathOrCoordinates)
      ? pathGeometry(pathOrCoordinates)
      : pathOrCoordinates;
    if (geometry.lengthKm <= 0) {
      return { integral: 0, mean: 0, samples: 0 };
    }
    const samples = Math.max(1, Math.ceil(geometry.lengthKm / stepKm));
    let sum = 0;
    for (let index = 0; index < samples; index += 1) {
      const [longitude, latitude] = pointAlongPath(geometry, (index + 0.5) / samples);
      sum += bilinearGridValue(latitudes, longitudes, values, latitude, longitude);
    }
    const mean = sum / samples;
    return { integral: mean * geometry.lengthKm, mean, samples };
  }

  function integrateNamedGridsAlongPath(
    latitudes,
    longitudes,
    namedGrids,
    pathOrCoordinates,
    integrationStepKm,
  ) {
    const stepKm = finiteNumber(integrationStepKm, "lineIntegrationStepKm");
    if (stepKm <= 0) throw new InputValidationError("lineIntegrationStepKm must be > 0");
    const geometry = Array.isArray(pathOrCoordinates)
      ? pathGeometry(pathOrCoordinates)
      : pathOrCoordinates;
    const names = Object.keys(namedGrids);
    const sums = Object.fromEntries(names.map((name) => [name, 0]));
    if (geometry.lengthKm <= 0) {
      return { means: sums, integrals: { ...sums }, samples: 0 };
    }
    const samples = Math.max(1, Math.ceil(geometry.lengthKm / stepKm));
    for (let index = 0; index < samples; index += 1) {
      const [longitude, latitude] = pointAlongPath(geometry, (index + 0.5) / samples);
      const stencil = bilinearStencil(latitudes, longitudes, latitude, longitude);
      for (const name of names) {
        sums[name] += bilinearValueFromStencil(namedGrids[name], stencil);
      }
    }
    const means = Object.fromEntries(
      names.map((name) => [name, sums[name] / samples]),
    );
    const integrals = Object.fromEntries(
      names.map((name) => [name, means[name] * geometry.lengthKm]),
    );
    return { means, integrals, samples };
  }

  function integrateNamedGridsForTopologySegment(
    latitudes,
    longitudes,
    namedGrids,
    segment,
    integrationStepKm,
  ) {
    const stepKm = finiteNumber(integrationStepKm, "lineIntegrationStepKm");
    if (stepKm <= 0) throw new InputValidationError("lineIntegrationStepKm must be > 0");
    // Standardized topology candidates already store the exact along-path
    // midpoint and length used when they were created. At the calibrated
    // 0.075 km candidate length and 0.25 km integration step, midpoint
    // quadrature has exactly one sample. Reusing that sample avoids rebuilding
    // 185k tiny path geometries without changing the numerical method.
    if (segment
        && Array.isArray(segment.midpoint)
        && segment.midpoint.length >= 2
        && Number.isFinite(segment.lengthKm)
        && segment.lengthKm > 0
        && segment.lengthKm <= stepKm + 1e-12) {
      const names = Object.keys(namedGrids);
      const [longitude, latitude] = segment.midpoint;
      const stencil = bilinearStencil(latitudes, longitudes, latitude, longitude);
      const means = Object.fromEntries(names.map((name) => [
        name,
        bilinearValueFromStencil(namedGrids[name], stencil),
      ]));
      const integrals = Object.fromEntries(names.map((name) => [
        name,
        means[name] * segment.lengthKm,
      ]));
      return { means, integrals, samples: 1, stencil };
    }
    return integrateNamedGridsAlongPath(
      latitudes,
      longitudes,
      namedGrids,
      segment.pathCoordinates,
      stepKm,
    );
  }

  function normalizeNetwork(network) {
    if (!network || !Array.isArray(network.feeders) || !Array.isArray(network.laterals)) {
      throw new InputValidationError("network must contain feeders and laterals arrays");
    }
    const substations = Array.isArray(network.substations)
      ? network.substations.map((substation, index) => {
        const subId = integer(
          substation.subId ?? substation.sub_id ?? index,
          `substations[${index}].subId`,
          0,
        );
        const coordinateValue = substation.coordinate ?? substation.coordinates;
        const hasLatitude = substation.lat !== undefined || substation.latitude !== undefined;
        const hasLongitude = substation.lon !== undefined || substation.longitude !== undefined;
        if (hasLatitude !== hasLongitude) {
          throw new InputValidationError(
            `substations[${index}] must provide both latitude and longitude`,
          );
        }
        const coordinate = coordinateValue !== undefined
          ? assertCoordinate(coordinateValue, `substations[${index}].coordinate`)
          : hasLatitude
            ? assertCoordinate([
              substation.lon ?? substation.longitude,
              substation.lat ?? substation.latitude,
            ], `substations[${index}]`)
            : null;
        return {
          subId,
          name: String(substation.name ?? `Substation ${subId}`),
          coordinate,
        };
      })
      : [];
    if (new Set(substations.map((substation) => substation.subId)).size !== substations.length) {
      throw new InputValidationError("substation subId values must be unique");
    }
    const feeders = network.feeders.map((feeder, fi) => {
      const coordinates = (feeder.coordinates || feeder.pts || []).map((point, index) =>
        feeder.coordinates
          ? assertCoordinate(point, `feeders[${fi}].coordinates[${index}]`)
          : assertCoordinate([point[1], point[0]], `feeders[${fi}].pts[${index}]`));
      if (coordinates.length < 2) {
        throw new InputValidationError(`feeder ${fi} needs at least two points`);
      }
      if (pathGeometry(coordinates).lengthKm <= 0) {
        throw new InputValidationError(`feeder ${fi} must have positive length`);
      }
      return {
        fi,
        feederId: integer(feeder.feederId ?? feeder.feeder_id ?? fi, `feeders[${fi}].feederId`, 0),
        subId: integer(feeder.subId ?? feeder.sub_id ?? feeder.subIdx ?? 0, `feeders[${fi}].subId`, 0),
        coordinates,
      };
    });
    if (new Set(feeders.map((feeder) => feeder.feederId)).size !== feeders.length) {
      throw new InputValidationError("feederId values must be unique");
    }
    if (substations.length) {
      const substationIds = new Set(substations.map((substation) => substation.subId));
      for (const feeder of feeders) {
        if (!substationIds.has(feeder.subId)) {
          throw new InputValidationError(`feeder ${feeder.feederId} references missing substation ${feeder.subId}`);
        }
      }
    }
    const feederById = new Map(feeders.map((feeder) => [feeder.feederId, feeder]));
    const laterals = network.laterals.map((lateral, li) => {
      const feederReference = integer(lateral.feederId ?? lateral.feeder_id ?? lateral.feederIdx, `laterals[${li}].feederId`, 0);
      const feeder = feederById.get(feederReference) || feeders[feederReference];
      if (!feeder) throw new InputValidationError(`laterals[${li}] references missing feeder ${feederReference}`);
      const coordinates = (lateral.coordinates || lateral.pts || []).map((point, index) =>
        lateral.coordinates
          ? assertCoordinate(point, `laterals[${li}].coordinates[${index}]`)
          : assertCoordinate([point[1], point[0]], `laterals[${li}].pts[${index}]`));
      if (coordinates.length < 2) {
        throw new InputValidationError(`lateral ${li} needs at least two points`);
      }
      if (pathGeometry(coordinates).lengthKm <= 0) {
        throw new InputValidationError(`lateral ${li} must have positive length`);
      }
      const feederGeometry = pathGeometry(feeder.coordinates);
      const anchorVertexValue = lateral.feederAnchorVertexIndex
        ?? lateral.feeder_anchor_vertex_index
        ?? lateral.feederAnchorIndex
        ?? lateral.feeder_anchor_index;
      const anchorChainageValue = lateral.feederAnchorChainageKm
        ?? lateral.feeder_anchor_chainage_km;
      let feederAnchorVertexIndex = null;
      let feederAnchorChainageKm = null;
      let attachmentMethod;

      if (anchorVertexValue !== undefined && anchorVertexValue !== null) {
        feederAnchorVertexIndex = integer(
          anchorVertexValue,
          `laterals[${li}].feederAnchorVertexIndex`,
          0,
        );
        if (feederAnchorVertexIndex >= feeder.coordinates.length) {
          throw new InputValidationError(
            `laterals[${li}].feederAnchorVertexIndex references a missing feeder vertex`,
          );
        }
        feederAnchorChainageKm = feederGeometry.cumulativeKm[feederAnchorVertexIndex];
        attachmentMethod = "explicit_feeder_vertex";
      }

      if (anchorChainageValue !== undefined && anchorChainageValue !== null) {
        const explicitChainage = finiteNumber(
          anchorChainageValue,
          `laterals[${li}].feederAnchorChainageKm`,
        );
        if (explicitChainage < 0 || explicitChainage > feederGeometry.lengthKm + 1e-9) {
          throw new InputValidationError(
            `laterals[${li}].feederAnchorChainageKm is outside its feeder`,
          );
        }
        if (feederAnchorChainageKm !== null
            && Math.abs(feederAnchorChainageKm - explicitChainage) > 1e-6) {
          throw new InputValidationError(
            `laterals[${li}] feeder anchor vertex and chainage disagree`,
          );
        }
        feederAnchorChainageKm = Math.min(feederGeometry.lengthKm, explicitChainage);
        attachmentMethod = feederAnchorVertexIndex === null
          ? "explicit_feeder_chainage"
          : "explicit_feeder_vertex_and_chainage";
      }

      if (feederAnchorChainageKm === null) {
        const inferred = nearestPointOnPath(feeder.coordinates, coordinates[0]);
        if (!inferred) {
          throw new InputValidationError(`laterals[${li}] cannot attach to a zero-length feeder`);
        }
        feederAnchorChainageKm = inferred.chainageKm;
        attachmentMethod = "inferred_from_lateral_origin";
      }

      const feederAnchorCoordinate = pointAlongPath(
        feederGeometry,
        feederGeometry.lengthKm > 0 ? feederAnchorChainageKm / feederGeometry.lengthKm : 0,
      );
      const feederAttachmentDistanceKm = haversineKm(
        feederAnchorCoordinate,
        coordinates[0],
      );
      if (feederAttachmentDistanceKm > LATERAL_ATTACHMENT_TOLERANCE_KM) {
        throw new InputValidationError(
          `laterals[${li}] origin is ${feederAttachmentDistanceKm.toFixed(3)} km from its feeder anchor`,
        );
      }

      return {
        li,
        lateralId: integer(lateral.lateralId ?? lateral.lateral_id ?? li, `laterals[${li}].lateralId`, 0),
        feeder,
        coordinates,
        feederAnchorVertexIndex,
        feederAnchorChainageKm,
        feederAnchorCoordinate,
        feederAttachmentDistanceKm,
        attachmentMethod,
      };
    });
    if (new Set(laterals.map((lateral) => lateral.lateralId)).size !== laterals.length) {
      throw new InputValidationError("lateralId values must be unique");
    }
    return { substations, feeders, laterals };
  }

  function buildRootedNetworkTopology(network, options = {}) {
    const candidateSegmentLengthKm = options.candidateSegmentLengthKm
      ?? DEFAULT_CONFIG.candidateSegmentLengthKm;
    if (finiteNumber(candidateSegmentLengthKm, "candidateSegmentLengthKm") <= 0) {
      throw new InputValidationError("candidateSegmentLengthKm must be positive");
    }
    const normalized = normalizeNetwork(network);
    const segments = [];
    const feederSegmentsById = new Map();

    function topologySegment(kind, line, feeder, geometry, parentSegmentId) {
      const lineId = kind === "feeder" ? feeder.feederId : line.lateralId;
      const segmentId = `${kind}:${lineId}:${geometry.segmentIndex}`;
      return {
        segmentId,
        topologyVersion: NETWORK_TOPOLOGY_VERSION,
        componentClass: kind,
        networkKind: kind,
        fi: feeder.fi,
        li: kind === "lateral" ? line.li : null,
        segmentIndex: geometry.segmentIndex,
        feederId: feeder.feederId,
        lateralId: kind === "lateral" ? line.lateralId : null,
        subId: feeder.subId,
        parentSegmentId,
        childSegmentIds: [],
        topologyRootId: null,
        topologyDepth: null,
        subtreeStart: null,
        subtreeEnd: null,
        start: geometry.start,
        end: geometry.end,
        midpoint: geometry.midpoint,
        pathCoordinates: geometry.pathCoordinates,
        lengthKm: geometry.lengthKm,
        startChainageKm: geometry.startChainageKm,
        endChainageKm: geometry.endChainageKm,
        feederAnchorChainageKm: kind === "lateral" ? line.feederAnchorChainageKm : null,
        feederAttachmentDistanceKm:
          kind === "lateral" ? line.feederAttachmentDistanceKm : null,
        attachmentMethod: kind === "lateral" ? line.attachmentMethod : null,
      };
    }

    for (const feeder of normalized.feeders) {
      const standardized = standardizeLineSegments(
        feeder.coordinates,
        candidateSegmentLengthKm,
      );
      const feederSegments = standardized.map((geometry, index) =>
        topologySegment(
          "feeder",
          feeder,
          feeder,
          geometry,
          index === 0 ? null : `feeder:${feeder.feederId}:${index - 1}`,
        ));
      if (!feederSegments.length) {
        throw new InputValidationError(`feeder ${feeder.feederId} has no topology segments`);
      }
      feederSegmentsById.set(feeder.feederId, feederSegments);
      segments.push(...feederSegments);
    }

    function feederParentAtChainage(feederSegments, chainageKm) {
      for (const segment of feederSegments) {
        if (chainageKm <= segment.endChainageKm + 1e-9) return segment;
      }
      return feederSegments[feederSegments.length - 1];
    }

    for (const lateral of normalized.laterals) {
      const standardized = standardizeLineSegments(
        lateral.coordinates,
        candidateSegmentLengthKm,
      );
      if (!standardized.length) {
        throw new InputValidationError(`lateral ${lateral.lateralId} has no topology segments`);
      }
      const feederSegments = feederSegmentsById.get(lateral.feeder.feederId);
      const feederParent = feederParentAtChainage(
        feederSegments,
        lateral.feederAnchorChainageKm,
      );
      const lateralSegments = standardized.map((geometry, index) =>
        topologySegment(
          "lateral",
          lateral,
          lateral.feeder,
          geometry,
          index === 0
            ? feederParent.segmentId
            : `lateral:${lateral.lateralId}:${index - 1}`,
        ));
      segments.push(...lateralSegments);
    }

    const segmentById = new Map();
    for (const segment of segments) {
      if (segmentById.has(segment.segmentId)) {
        throw new InputValidationError(`duplicate topology segment ID ${segment.segmentId}`);
      }
      segmentById.set(segment.segmentId, segment);
    }
    for (const segment of segments) {
      if (segment.parentSegmentId === null) continue;
      const parent = segmentById.get(segment.parentSegmentId);
      if (!parent) {
        throw new InputValidationError(
          `topology segment ${segment.segmentId} references missing parent ${segment.parentSegmentId}`,
        );
      }
      if (parent.subId !== segment.subId || parent.feederId !== segment.feederId) {
        throw new InputValidationError(
          `topology segment ${segment.segmentId} crosses feeder or substation ownership`,
        );
      }
      parent.childSegmentIds.push(segment.segmentId);
    }
    for (const segment of segments) segment.childSegmentIds.sort();

    const roots = segments
      .filter((segment) => segment.parentSegmentId === null)
      .map((segment) => segment.segmentId)
      .sort();
    const visited = new Set();
    let preorder = 0;
    let maximumDepth = 0;
    for (const rootId of roots) {
      const stack = [{ segmentId: rootId, depth: 0, exiting: false }];
      while (stack.length) {
        const frame = stack.pop();
        const segment = segmentById.get(frame.segmentId);
        if (frame.exiting) {
          segment.subtreeEnd = preorder - 1;
          continue;
        }
        if (visited.has(frame.segmentId)) {
          throw new InputValidationError(`network topology contains a cycle at ${frame.segmentId}`);
        }
        visited.add(frame.segmentId);
        segment.topologyRootId = rootId;
        segment.topologyDepth = frame.depth;
        segment.subtreeStart = preorder;
        preorder += 1;
        maximumDepth = Math.max(maximumDepth, frame.depth);
        stack.push({ segmentId: frame.segmentId, depth: frame.depth, exiting: true });
        for (let index = segment.childSegmentIds.length - 1; index >= 0; index -= 1) {
          stack.push({
            segmentId: segment.childSegmentIds[index],
            depth: frame.depth + 1,
            exiting: false,
          });
        }
      }
    }
    if (visited.size !== segments.length) {
      throw new InputValidationError(
        `network topology is not a rooted forest: reached ${visited.size} of ${segments.length} segments`,
      );
    }

    const inferredLateralAttachments = normalized.laterals.filter(
      (lateral) => lateral.attachmentMethod === "inferred_from_lateral_origin",
    ).length;
    return {
      schema: "connecticut_rooted_network_topology_v1",
      topologyVersion: NETWORK_TOPOLOGY_VERSION,
      orientation: "feeder and lateral coordinate order is upstream to downstream",
      normalizedNetwork: normalized,
      roots,
      segments,
      summary: {
        roots: roots.length,
        segments: segments.length,
        feederSegments: segments.filter((segment) => segment.networkKind === "feeder").length,
        lateralSegments: segments.filter((segment) => segment.networkKind === "lateral").length,
        maximumDepth,
        explicitLateralAttachments: normalized.laterals.length - inferredLateralAttachments,
        inferredLateralAttachments,
        maximumLateralAttachmentDistanceKm: normalized.laterals.reduce(
          (maximum, lateral) => Math.max(maximum, lateral.feederAttachmentDistanceKm),
          0,
        ),
      },
    };
  }

  function customerTerritoryAnchors(topology) {
    const anchors = [];
    const substationsById = new Map(
      topology.normalizedNetwork.substations.map((substation) => [substation.subId, substation]),
    );
    const rootSegments = topology.roots.map((rootId) =>
      topology.segments.find((segment) => segment.segmentId === rootId));
    const substationIds = [...new Set(
      topology.segments.map((segment) => segment.subId),
    )].sort((left, right) => left - right);
    for (const subId of substationIds) {
      const substation = substationsById.get(subId);
      if (substation && substation.coordinate) {
        anchors.push({ subId, coordinate: substation.coordinate, source: "substation_coordinate" });
        continue;
      }
      const roots = rootSegments
        .filter((segment) => segment.subId === subId)
        .sort((left, right) => left.segmentId.localeCompare(right.segmentId));
      for (const root of roots) {
        anchors.push({
          subId,
          coordinate: root.start,
          source: "feeder_root_fallback",
          rootId: root.segmentId,
        });
      }
    }
    if (!anchors.length) {
      throw new InputValidationError("network topology has no customer-territory anchors");
    }
    return anchors;
  }

  function nearestStableCandidate(candidates, point, idKey, distanceAndPoint) {
    let best = null;
    for (const candidate of candidates) {
      const measured = distanceAndPoint(candidate, point);
      if (!measured || !Number.isFinite(measured.distanceKm)) continue;
      const candidateId = String(candidate[idKey]);
      if (!best
          || measured.distanceKm < best.distanceKm - 1e-12
          || (Math.abs(measured.distanceKm - best.distanceKm) <= 1e-12
            && candidateId < best.candidateId)) {
        best = { candidate, candidateId, ...measured };
      }
    }
    return best;
  }

  function integerizeLoadPoints(loadPoints, targetCustomerAccounts) {
    let floorTotal = 0;
    for (const loadPoint of loadPoints) {
      loadPoint.customerAccounts = Math.floor(loadPoint.estimatedCustomerAccounts);
      loadPoint.roundingRemainder =
        loadPoint.estimatedCustomerAccounts - loadPoint.customerAccounts;
      floorTotal += loadPoint.customerAccounts;
    }
    const remaining = targetCustomerAccounts - floorTotal;
    if (remaining < 0 || remaining > loadPoints.length) {
      throw new InputValidationError(
        `cannot conserve ${targetCustomerAccounts} customer accounts by largest-remainder rounding`,
      );
    }
    const ranked = [...loadPoints].sort((left, right) =>
      right.roundingRemainder - left.roundingRemainder
        || left.sourceRow - right.sourceRow
        || left.sourceColumn - right.sourceColumn
        || left.loadPointId.localeCompare(right.loadPointId));
    for (let index = 0; index < remaining; index += 1) {
      ranked[index].customerAccounts += 1;
    }
  }

  function weightedDistanceQuantile(loadPoints, probability) {
    const ranked = loadPoints
      .filter((loadPoint) => loadPoint.customerAccounts > 0)
      .sort((left, right) => left.allocationDistanceKm - right.allocationDistanceKm
        || left.loadPointId.localeCompare(right.loadPointId));
    const total = ranked.reduce((sum, loadPoint) => sum + loadPoint.customerAccounts, 0);
    const threshold = total * probability;
    let cumulative = 0;
    for (const loadPoint of ranked) {
      cumulative += loadPoint.customerAccounts;
      if (cumulative >= threshold) return loadPoint.allocationDistanceKm;
    }
    return ranked.length ? ranked[ranked.length - 1].allocationDistanceKm : 0;
  }

  function allocateCustomerAccountsToTopology(topology, customerSurface) {
    if (!topology || topology.schema !== "connecticut_rooted_network_topology_v1"
        || !Array.isArray(topology.segments) || !topology.segments.length) {
      throw new InputValidationError("customer allocation requires rooted network topology v1");
    }
    if (!customerSurface || typeof customerSurface !== "object") {
      throw new InputValidationError("customer allocation requires a customer exposure surface");
    }
    const latitudes = validateCoordinates(customerSurface.latitudes, "customer latitudes");
    const longitudes = validateCoordinates(customerSurface.longitudes, "customer longitudes");
    const rows = latitudes.length;
    const columns = longitudes.length;
    const rawCustomerAccounts = validateGrid(
      customerSurface.rawCustomerAccounts,
      rows,
      columns,
      "rawCustomerAccounts",
      [0, Number.MAX_VALUE],
    );
    const mask = customerSurface.connecticutMask;
    if (!Array.isArray(mask) || mask.length !== rows
        || mask.some((row) => !Array.isArray(row) || row.length !== columns
          || row.some((value) => typeof value !== "boolean"))) {
      throw new InputValidationError(`connecticutMask shape must be ${rows} x ${columns}`);
    }
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        if (!mask[row][column] && rawCustomerAccounts[row][column] > 1e-9) {
          throw new InputValidationError(
            `rawCustomerAccounts[${row}][${column}] is positive outside Connecticut`,
          );
        }
      }
    }

    const estimatedCustomerAccounts = gridTotal(rawCustomerAccounts);
    const targetCustomerAccounts = Math.round(estimatedCustomerAccounts);
    if (targetCustomerAccounts <= 0) {
      throw new InputValidationError("customer allocation surface has no customer accounts");
    }
    const anchors = customerTerritoryAnchors(topology);
    const segmentsBySubstation = new Map();
    const lateralSegmentsById = new Map();
    for (const segment of topology.segments) {
      if (!segmentsBySubstation.has(segment.subId)) {
        segmentsBySubstation.set(segment.subId, { lateral: [], feeder: [] });
      }
      segmentsBySubstation.get(segment.subId)[segment.networkKind].push(segment);
      if (segment.networkKind === "lateral") {
        if (!lateralSegmentsById.has(segment.lateralId)) {
          lateralSegmentsById.set(segment.lateralId, []);
        }
        lateralSegmentsById.get(segment.lateralId).push(segment);
      }
    }
    for (const candidates of segmentsBySubstation.values()) {
      candidates.lateral.sort((left, right) => left.segmentId.localeCompare(right.segmentId));
      candidates.feeder.sort((left, right) => left.segmentId.localeCompare(right.segmentId));
    }
    for (const segments of lateralSegmentsById.values()) {
      segments.sort((left, right) => left.segmentIndex - right.segmentIndex);
    }

    const loadPoints = [];
    let sourcePositiveGridNodes = 0;
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        const accounts = rawCustomerAccounts[row][column];
        if (!mask[row][column] || accounts <= 0) continue;
        sourcePositiveGridNodes += 1;
        const coordinate = [longitudes[column], latitudes[row]];
        const territory = nearestStableCandidate(
          anchors,
          coordinate,
          "subId",
          (anchor, point) => ({
            distanceKm: haversineKm(anchor.coordinate, point),
            projected: anchor.coordinate,
          }),
        );
        if (!territory) {
          throw new InputValidationError(`customer grid node ${row},${column} has no territory`);
        }
        const territorySegments = segmentsBySubstation.get(territory.candidate.subId);
        if (!territorySegments) {
          throw new InputValidationError(
            `customer territory ${territory.candidate.subId} has no network segments`,
          );
        }
        const attachments = [];
        if (territorySegments.lateral.length) {
          const nearestByLateral = new Map();
          for (const segment of territorySegments.lateral) {
            const measured = nearestPointOnPath(segment.pathCoordinates, coordinate);
            const prior = nearestByLateral.get(segment.lateralId);
            if (!prior
                || measured.distanceKm < prior.distanceKm - 1e-12
                || (Math.abs(measured.distanceKm - prior.distanceKm) <= 1e-12
                  && segment.segmentId < prior.candidate.segmentId)) {
              nearestByLateral.set(segment.lateralId, {
                candidate: segment,
                candidateId: segment.segmentId,
                ...measured,
              });
            }
          }
          attachments.push(...[...nearestByLateral.values()].sort((left, right) =>
            left.distanceKm - right.distanceKm
              || left.candidateId.localeCompare(right.candidateId)).slice(
            0,
            CUSTOMER_ALLOCATION_NEARBY_LATERALS,
          ));
        } else {
          const feederAttachment = nearestStableCandidate(
            territorySegments.feeder,
            coordinate,
            "segmentId",
            (segment, point) => nearestPointOnPath(segment.pathCoordinates, point),
          );
          if (feederAttachment) attachments.push(feederAttachment);
        }
        if (!attachments.length) {
          throw new InputValidationError(`customer grid node ${row},${column} has no attachment`);
        }
        const inverseDistanceWeights = attachments.map((attachment) =>
          1 / Math.max(
            CUSTOMER_ALLOCATION_DISTANCE_FLOOR_KM,
            attachment.distanceKm,
          ) ** 2);
        const inverseDistanceTotal = inverseDistanceWeights.reduce(
          (sum, value) => sum + value,
          0,
        );
        for (let index = 0; index < attachments.length; index += 1) {
          const attachment = attachments[index];
          const attachmentAccounts=
            accounts * inverseDistanceWeights[index] / inverseDistanceTotal;
          const servingSegments=attachment.candidate.networkKind === "lateral"
            ? lateralSegmentsById.get(attachment.candidate.lateralId)
            : [attachment.candidate];
          const servingLengthKm=servingSegments.reduce(
            (sum, segment) => sum + segment.lengthKm,
            0,
          );
          for (const servingSegment of servingSegments) {
            const measured=servingSegment.segmentId === attachment.candidate.segmentId
              ? attachment
              : nearestPointOnPath(servingSegment.pathCoordinates, coordinate);
            loadPoints.push({
              loadPointId: `grid:${row}:${column}:${servingSegment.segmentId}`,
              sourceRow: row,
              sourceColumn: column,
              latitude: coordinate[1],
              longitude: coordinate[0],
              estimatedCustomerAccounts:
                attachmentAccounts * servingSegment.lengthKm / servingLengthKm,
              customerAccounts: 0,
              roundingRemainder: 0,
              subId: territory.candidate.subId,
              territoryAnchorSource: territory.candidate.source,
              attachedSegmentId: servingSegment.segmentId,
              attachedComponentClass: servingSegment.networkKind,
              attachmentCoordinate: measured.projected,
              allocationDistanceKm: measured.distanceKm,
            });
          }
        }
      }
    }
    if (!loadPoints.length) {
      throw new InputValidationError("customer allocation surface has no positive in-state grid nodes");
    }
    integerizeLoadPoints(loadPoints, targetCustomerAccounts);

    const segments = topology.segments.map((segment) => ({
      ...segment,
      childSegmentIds: [...segment.childSegmentIds],
      directCustomerAccounts: 0,
      downstreamCustomerAccounts: 0,
      directLoadPointCount: 0,
      downstreamLoadPointCount: 0,
    }));
    const segmentById = new Map(segments.map((segment) => [segment.segmentId, segment]));
    for (const loadPoint of loadPoints) {
      if (loadPoint.customerAccounts <= 0) continue;
      const segment = segmentById.get(loadPoint.attachedSegmentId);
      if (!segment) {
        throw new InputValidationError(
          `load point ${loadPoint.loadPointId} references missing segment ${loadPoint.attachedSegmentId}`,
        );
      }
      segment.directCustomerAccounts += loadPoint.customerAccounts;
      segment.directLoadPointCount += 1;
    }
    const postOrder = [...segments].sort((left, right) =>
      right.topologyDepth - left.topologyDepth
        || right.subtreeStart - left.subtreeStart);
    for (const segment of postOrder) {
      segment.downstreamCustomerAccounts += segment.directCustomerAccounts;
      segment.downstreamLoadPointCount += segment.directLoadPointCount;
      if (segment.parentSegmentId !== null) {
        const parent = segmentById.get(segment.parentSegmentId);
        if (!parent) {
          throw new InputValidationError(
            `customer topology segment ${segment.segmentId} has a missing parent`,
          );
        }
        parent.downstreamCustomerAccounts += segment.downstreamCustomerAccounts;
        parent.downstreamLoadPointCount += segment.downstreamLoadPointCount;
      }
    }

    const rootCustomerAccounts = topology.roots.reduce(
      (sum, rootId) => sum + segmentById.get(rootId).downstreamCustomerAccounts,
      0,
    );
    const directCustomerAccounts = segments.reduce(
      (sum, segment) => sum + segment.directCustomerAccounts,
      0,
    );
    if (directCustomerAccounts !== targetCustomerAccounts
        || rootCustomerAccounts !== targetCustomerAccounts) {
      throw new InputValidationError(
        `customer allocation failed conservation: direct=${directCustomerAccounts}, roots=${rootCustomerAccounts}, target=${targetCustomerAccounts}`,
      );
    }
    const materializedLoadPoints = loadPoints.filter(
      (loadPoint) => loadPoint.customerAccounts > 0,
    );
    const weightedDistanceTotal = materializedLoadPoints.reduce(
      (sum, loadPoint) =>
        sum + loadPoint.customerAccounts * loadPoint.allocationDistanceKm,
      0,
    );
    const fallbackCustomerAccounts = materializedLoadPoints.reduce(
      (sum, loadPoint) => sum + (loadPoint.attachedComponentClass === "feeder"
        ? loadPoint.customerAccounts
        : 0),
      0,
    );
    return {
      schema: "connecticut_network_customer_allocation_v1",
      allocationVersion: CUSTOMER_ALLOCATION_VERSION,
      sourceTopologySchema: topology.schema,
      sourceCustomerQuantity: "raw unsmoothed Census-derived customer accounts",
      integerizationMethod: "largest remainder by source grid node",
      territoryMethod: "nearest substation coordinate; feeder-root fallback when unavailable",
      attachmentMethod:
        "inverse-square allocation among up to eight nearest distinct laterals within territory, then length-proportional spreading along each synthetic lateral; feeder fallback when territory has no laterals",
      roots: [...topology.roots],
      segments,
      loadPoints: materializedLoadPoints,
      serviceRepresentation: {
        kind: "integer-multiplicity grid load points",
        materializedLoadPoints: materializedLoadPoints.length,
        virtualCustomerAccounts: targetCustomerAccounts,
        individualServiceObjectsMaterialized: false,
      },
      summary: {
        sourcePositiveGridNodes,
        fractionalNetworkAttachments: loadPoints.length,
        maximumNearbyLateralsPerGridNode: CUSTOMER_ALLOCATION_NEARBY_LATERALS,
        inverseDistanceFloorKm: CUSTOMER_ALLOCATION_DISTANCE_FLOOR_KM,
        materializedLoadPoints: materializedLoadPoints.length,
        estimatedCustomerAccounts,
        targetIntegerCustomerAccounts: targetCustomerAccounts,
        allocatedCustomerAccounts: directCustomerAccounts,
        rootDownstreamCustomerAccounts: rootCustomerAccounts,
        customerBearingSegments: segments.filter(
          (segment) => segment.directCustomerAccounts > 0,
        ).length,
        lateralCustomerAccounts: targetCustomerAccounts - fallbackCustomerAccounts,
        feederFallbackCustomerAccounts: fallbackCustomerAccounts,
        meanCustomerWeightedAllocationDistanceKm:
          weightedDistanceTotal / targetCustomerAccounts,
        p90CustomerWeightedAllocationDistanceKm:
          weightedDistanceQuantile(materializedLoadPoints, 0.9),
        maximumAllocationDistanceKm: materializedLoadPoints.reduce(
          (maximum, loadPoint) => Math.max(maximum, loadPoint.allocationDistanceKm),
          0,
        ),
        territoryAnchors: anchors.length,
        substationCoordinateAnchors: anchors.filter(
          (anchor) => anchor.source === "substation_coordinate",
        ).length,
        feederRootFallbackAnchors: anchors.filter(
          (anchor) => anchor.source === "feeder_root_fallback",
        ).length,
      },
    };
  }

  function buildWeightedNetworkSegments(
    network,
    customerSurface,
    weatherSurface,
    impactSurface,
    options = {},
    topologyOverride = null,
  ) {
    const feederSusceptibility = options.feederSusceptibility ?? DEFAULT_CONFIG.feederSusceptibility;
    const lateralSusceptibility = options.lateralSusceptibility ?? DEFAULT_CONFIG.lateralSusceptibility;
    const candidateSegmentLengthKm = options.candidateSegmentLengthKm
      ?? DEFAULT_CONFIG.candidateSegmentLengthKm;
    const lineIntegrationStepKm = options.lineIntegrationStepKm
      ?? DEFAULT_CONFIG.lineIntegrationStepKm;
    const placementMode = options.placementMode ?? DEFAULT_CONFIG.placementMode;
    if (feederSusceptibility <= 0 || lateralSusceptibility <= 0) {
      throw new InputValidationError("network susceptibility factors must be positive");
    }
    if (candidateSegmentLengthKm <= 0 || lineIntegrationStepKm <= 0) {
      throw new InputValidationError("network segmentation and integration distances must be positive");
    }
    if (!["failure_oriented", "impact_weighted"].includes(placementMode)) {
      throw new InputValidationError("placementMode must be failure_oriented or impact_weighted");
    }
    const topology = topologyOverride
      || buildRootedNetworkTopology(network, { candidateSegmentLengthKm });
    if (!Array.isArray(topology.segments) || !topology.segments.length) {
      throw new InputValidationError("network topology override must contain segments");
    }
    const { latitudes, longitudes } = impactSurface;
    const interpolationGrids = {
      windMph: weatherSurface.windMph,
      rainAccumulationIn: weatherSurface.rainAccumulationIn,
      customerAccounts: customerSurface.smoothedCustomerAccounts,
      relativeCustomerConsequenceIndex: impactSurface.relativeCustomerExposure,
      hazardIndex: impactSurface.weatherSeverity,
      rawImpactPriorityScore: impactSurface.rawImpact,
      smoothedImpactPriorityScore: impactSurface.smoothedImpact,
    };
    if (Object.values(interpolationGrids).some((grid) => !Array.isArray(grid)
      || grid.length !== latitudes.length
      || grid.some((row) => !Array.isArray(row) || row.length !== longitudes.length))) {
      throw new InputValidationError("network weighting surfaces must share one grid");
    }
    const segments = [];
    for (const topologySegment of topology.segments) {
        const susceptibility = topologySegment.networkKind === "feeder"
          ? feederSusceptibility
          : lateralSusceptibility;
        const integrated = integrateNamedGridsForTopologySegment(
          latitudes,
          longitudes,
          interpolationGrids,
          topologySegment,
          lineIntegrationStepKm,
        );
        const failureOrientedWeight = susceptibility * integrated.integrals.hazardIndex;
        const impactPriorityWeight =
          susceptibility * integrated.integrals.smoothedImpactPriorityScore;
        const weight = placementMode === "failure_oriented"
          ? failureOrientedWeight
          : impactPriorityWeight;
        if (weight <= 0 || !Number.isFinite(weight)) continue;
        segments.push({
          ...topologySegment,
          localWindMph: integrated.means.windMph,
          localRainAccumulationIn: integrated.means.rainAccumulationIn,
          localRainInputKind: weatherSurface.rainInputKind,
          localRainIn: integrated.means.rainAccumulationIn,
          customerExposure: integrated.means.customerAccounts,
          relativeCustomerExposure: integrated.means.relativeCustomerConsequenceIndex,
          customerConsequenceIndex: integrated.means.relativeCustomerConsequenceIndex,
          localWeatherSeverity: integrated.means.hazardIndex,
          hazardIndex: integrated.means.hazardIndex,
          rawImpact: integrated.means.rawImpactPriorityScore,
          smoothedImpact: integrated.means.smoothedImpactPriorityScore,
          impactPriorityScore: integrated.means.smoothedImpactPriorityScore,
          integratedHazardScoreKm: integrated.integrals.hazardIndex,
          integratedImpactPriorityScoreKm:
            integrated.integrals.smoothedImpactPriorityScore,
          failureOrientedWeight,
          impactPriorityWeight,
          placementMode,
          susceptibility,
          weight,
          integrationMethod: "composite_midpoint_rule_along_polyline",
          integrationStepKm: lineIntegrationStepKm,
          integrationSampleCount: integrated.samples,
        });
    }
    if (!segments.length) throw new InputValidationError("network has no positive-weight segments");
    return segments;
  }

  function buildBasicNetworkSegments(network, options = {}, topologyOverride = null) {
    const feederSusceptibility = options.feederSusceptibility ?? DEFAULT_CONFIG.feederSusceptibility;
    const lateralSusceptibility = options.lateralSusceptibility ?? DEFAULT_CONFIG.lateralSusceptibility;
    const candidateSegmentLengthKm = options.candidateSegmentLengthKm
      ?? DEFAULT_CONFIG.candidateSegmentLengthKm;
    if (feederSusceptibility <= 0 || lateralSusceptibility <= 0) {
      throw new InputValidationError("network susceptibility factors must be positive");
    }
    if (candidateSegmentLengthKm <= 0) {
      throw new InputValidationError("candidateSegmentLengthKm must be positive");
    }
    const topology = topologyOverride
      || buildRootedNetworkTopology(network, { candidateSegmentLengthKm });
    if (!Array.isArray(topology.segments) || !topology.segments.length) {
      throw new InputValidationError("network topology override must contain segments");
    }
    const segments = topology.segments.map((topologySegment) => {
      const susceptibility = topologySegment.networkKind === "feeder"
        ? feederSusceptibility
        : lateralSusceptibility;
      const prefix = (segmentId) => segmentId === null ? null : `basic:${segmentId}`;
      return {
          ...topologySegment,
          sourceTopologySegmentId: topologySegment.segmentId,
          segmentId: prefix(topologySegment.segmentId),
          parentSegmentId: prefix(topologySegment.parentSegmentId),
          childSegmentIds: topologySegment.childSegmentIds.map(prefix),
          topologyRootId: prefix(topologySegment.topologyRootId),
          localWindMph: null,
          localRainIn: null,
          localRainAccumulationIn: null,
          localRainInputKind: null,
          customerExposure: null,
          relativeCustomerExposure: null,
          localWeatherSeverity: null,
          rawImpact: null,
          smoothedImpact: null,
          hazardIndex: null,
          customerConsequenceIndex: null,
          impactPriorityScore: null,
          failureOrientedWeight: null,
          impactPriorityWeight: null,
          placementMode: "network_length_only",
          susceptibility,
          weight: topologySegment.lengthKm * susceptibility,
      };
    });
    if (!segments.length) throw new InputValidationError("network has no positive-length segments");
    return segments;
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

  function fnv1a32(value) {
    let hash = 0x811C9DC5;
    const text = String(value);
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    hash ^= hash >>> 16;
    hash = Math.imul(hash, 0x7FEB352D);
    hash ^= hash >>> 15;
    hash = Math.imul(hash, 0x846CA68B);
    hash ^= hash >>> 16;
    return hash >>> 0;
  }

  function segmentKeyedUniform(seed, stream, segmentId, counter = 0) {
    const hash = fnv1a32(`${seed}|${stream}|${segmentId}|${counter}`);
    return (hash + 0.5) / 4294967296;
  }

  class MaximumKeyHeap {
    constructor() {
      this.values = [];
    }

    static comesFirst(left, right) {
      return left.selectionKey > right.selectionKey
        || (left.selectionKey === right.selectionKey
          && left.failureId < right.failureId);
    }

    push(value) {
      const values = this.values;
      values.push(value);
      let index = values.length - 1;
      while (index > 0) {
        const parentIndex = Math.floor((index - 1) / 2);
        if (MaximumKeyHeap.comesFirst(values[parentIndex], values[index])) break;
        [values[parentIndex], values[index]] = [values[index], values[parentIndex]];
        index = parentIndex;
      }
    }

    pop() {
      const values = this.values;
      if (!values.length) return null;
      const first = values[0];
      const last = values.pop();
      if (values.length) {
        values[0] = last;
        let index = 0;
        while (true) {
          const leftIndex = index * 2 + 1;
          const rightIndex = leftIndex + 1;
          let bestIndex = index;
          if (leftIndex < values.length
              && MaximumKeyHeap.comesFirst(values[leftIndex], values[bestIndex])) {
            bestIndex = leftIndex;
          }
          if (rightIndex < values.length
              && MaximumKeyHeap.comesFirst(values[rightIndex], values[bestIndex])) {
            bestIndex = rightIndex;
          }
          if (bestIndex === index) break;
          [values[index], values[bestIndex]] = [values[bestIndex], values[index]];
          index = bestIndex;
        }
      }
      return first;
    }

    get size() {
      return this.values.length;
    }
  }

  function validateCustomerSizingConfig(input = {}) {
    if (!input || typeof input !== "object" || Array.isArray(input)) {
      throw new InputValidationError("customer sizing options must be an object");
    }
    for (const key of Object.keys(input)) {
      if (!Object.prototype.hasOwnProperty.call(DEFAULT_CUSTOMER_SIZING_CONFIG, key)) {
        throw new InputValidationError(`unknown customer sizing option: ${key}`);
      }
    }
    const sizing = { ...DEFAULT_CUSTOMER_SIZING_CONFIG, ...input };
    if (finiteNumber(sizing.serviceFailureWeight, "serviceFailureWeight") < 0) {
      throw new InputValidationError("serviceFailureWeight must be >= 0");
    }
    if (integer(
      sizing.serviceGroupMaximumCustomers,
      "serviceGroupMaximumCustomers",
      1,
    ) !== 15) {
      throw new InputValidationError(
        "serviceGroupMaximumCustomers currently supports the calibrated value 15",
      );
    }
    return Object.freeze(sizing);
  }

  function serviceGroupCategories(segment, sizing) {
    const directCustomers = segment.directCustomerAccounts;
    if (!Number.isInteger(directCustomers) || directCustomers <= 0
        || sizing.serviceFailureWeight <= 0) return [];

    const pattern = CUSTOMER_LOAD_GROUP_PATTERN.filter(
      (customerAccounts) => customerAccounts <= sizing.serviceGroupMaximumCustomers,
    );
    const accountsPerCycle = pattern.reduce((sum, value) => sum + value, 0);
    const categoryCounts = new Map();
    const addCategory = (customerAccounts, count = 1) => {
      categoryCounts.set(
        customerAccounts,
        (categoryCounts.get(customerAccounts) || 0) + count,
      );
    };

    // Materialize counts by size, not individual customer groups. Full cycles
    // are handled arithmetically so statewide selection remains compact.
    const fullCycles = Math.floor(directCustomers / accountsPerCycle);
    if (fullCycles > 0) {
      for (const customerAccounts of pattern) {
        addCategory(customerAccounts, fullCycles);
      }
    }
    let remainingCustomers = directCustomers - fullCycles * accountsPerCycle;
    let patternIndex = fnv1a32(
      `customer_load_group_partition|${segment.segmentId}`,
    ) % pattern.length;
    while (remainingCustomers > 0) {
      const customerAccounts = Math.min(
        remainingCustomers,
        pattern[patternIndex],
      );
      addCategory(customerAccounts);
      remainingCustomers -= customerAccounts;
      patternIndex = (patternIndex + 1) % pattern.length;
    }

    const definitions = [...categoryCounts.entries()]
      .map(([customerAccounts, groupCount]) => ({ customerAccounts, groupCount }))
      .sort((left, right) => left.customerAccounts - right.customerAccounts);
    const allocatedCustomers = definitions.reduce(
      (sum, definition) =>
        sum + definition.customerAccounts * definition.groupCount,
      0,
    );
    if (allocatedCustomers !== directCustomers) {
      throw new InputValidationError(
        `customer load groups on ${segment.segmentId} do not conserve direct accounts`,
      );
    }
    const groupCount = definitions.reduce(
      (sum, definition) => sum + definition.groupCount,
      0,
    );
    const perGroupWeight = segment.weight * sizing.serviceFailureWeight / groupCount;
    return [{
      categoryId: `service:${segment.segmentId}`,
      attachmentSegment: segment,
      groupCount,
      remainingGroups: groupCount,
      remainingSizeCounts: new Map(definitions.map((definition) => [
        definition.customerAccounts,
        definition.groupCount,
      ])),
      perGroupWeight,
      currentOrderedUniform: 1,
      generatedGroups: 0,
    }];
  }

  function nextVirtualServiceFailure(category, seed) {
    if (category.remainingGroups <= 0) return null;
    const groupsBeforeSelection = category.remainingGroups;
    const keyedUniform = segmentKeyedUniform(
      seed,
      "virtual_service_order_statistic",
      category.categoryId,
      category.generatedGroups,
    );
    // If N candidate groups have iid U(0,1) keys, their maximum is
    // U^(1/N). Conditional on that maximum, the next order statistic follows
    // the same recurrence on the remaining N-1 groups. This lazily generates
    // only the globally competitive service keys instead of materializing up
    // to 1.633 million customer objects.
    category.currentOrderedUniform *= Math.pow(
      keyedUniform,
      1 / category.remainingGroups,
    );
    let sizeRank = Math.min(
      groupsBeforeSelection - 1,
      Math.floor(segmentKeyedUniform(
        seed,
        "virtual_service_group_permutation",
        category.categoryId,
        category.generatedGroups,
      ) * groupsBeforeSelection),
    );
    let customerAccounts = null;
    for (const [size, count] of category.remainingSizeCounts.entries()) {
      if (sizeRank < count) {
        customerAccounts = size;
        if (count === 1) category.remainingSizeCounts.delete(size);
        else category.remainingSizeCounts.set(size, count - 1);
        break;
      }
      sizeRank -= count;
    }
    if (customerAccounts === null) {
      throw new InputValidationError(
        `customer load group permutation failed for ${category.categoryId}`,
      );
    }
    category.remainingGroups -= 1;
    category.generatedGroups += 1;
    const attachment = category.attachmentSegment;
    return {
      // Keep identity and placement independent of the selected group's size.
      // This preserves the placement model's invariance to uniform population
      // rescaling while customer counts remain a separate sizing output.
      failureId: `${category.categoryId}:rank${category.generatedGroups}`,
      failureType: "service",
      componentClass: "service",
      customerAccounts,
      networkSegmentId: null,
      attachedNetworkSegmentId: attachment.segmentId,
      topologyRootId: attachment.topologyRootId,
      attachmentSubtreePoint: attachment.subtreeStart,
      subtreeStart: null,
      subtreeEnd: null,
      feederId: attachment.feederId,
      lateralId: attachment.lateralId,
      subId: attachment.subId,
      selectionWeight: category.perGroupWeight,
      selectionKey: Math.log(category.currentOrderedUniform) / category.perGroupWeight,
      category,
    };
  }

  function failureOverlapsSelection(candidate, selectedNetworks, selectedServices) {
    if (candidate.failureType === "network") {
      for (const selected of selectedNetworks) {
        if (selected.topologyRootId !== candidate.topologyRootId) continue;
        if (candidate.subtreeStart <= selected.subtreeEnd
            && selected.subtreeStart <= candidate.subtreeEnd) return true;
      }
      for (const selected of selectedServices) {
        if (selected.topologyRootId === candidate.topologyRootId
            && selected.attachmentSubtreePoint >= candidate.subtreeStart
            && selected.attachmentSubtreePoint <= candidate.subtreeEnd) return true;
      }
      return false;
    }
    for (const selected of selectedNetworks) {
      if (selected.topologyRootId === candidate.topologyRootId
          && candidate.attachmentSubtreePoint >= selected.subtreeStart
          && candidate.attachmentSubtreePoint <= selected.subtreeEnd) return true;
    }
    return false;
  }

  function selectNonOverlappingTopologyFailures(
    weightedSegments,
    configInput = {},
    sizingInput = null,
  ) {
    const config = validateConfig(configInput);
    const sizing = validateCustomerSizingConfig(sizingInput || {
      serviceFailureWeight: config.serviceFailureWeight,
      serviceGroupMaximumCustomers: config.serviceGroupMaximumCustomers,
    });
    if (!Array.isArray(weightedSegments) || !weightedSegments.length) {
      throw new InputValidationError("topology failure selection requires weighted segments");
    }
    const orderedSegments = [...weightedSegments].sort(
      (left, right) => left.segmentId.localeCompare(right.segmentId),
    );
    if (new Set(orderedSegments.map((segment) => segment.segmentId)).size
        !== orderedSegments.length) {
      throw new InputValidationError("weighted segment IDs must be unique");
    }

    const heap = new MaximumKeyHeap();
    const serviceCategories = [];
    let networkCandidateCount = 0;
    let virtualServiceCandidateCount = 0;
    let theoreticalSelectionWeight = 0;
    for (const segment of orderedSegments) {
      if (!Number.isFinite(segment.weight) || segment.weight <= 0) continue;
      if (!Number.isInteger(segment.directCustomerAccounts)
          || !Number.isInteger(segment.downstreamCustomerAccounts)
          || segment.directCustomerAccounts < 0
          || segment.downstreamCustomerAccounts < segment.directCustomerAccounts) {
        throw new InputValidationError(
          `segment ${segment.segmentId} lacks valid direct/downstream customer accounts`,
        );
      }
      if (!Number.isInteger(segment.subtreeStart)
          || !Number.isInteger(segment.subtreeEnd)
          || segment.subtreeStart > segment.subtreeEnd
          || typeof segment.topologyRootId !== "string") {
        throw new InputValidationError(
          `segment ${segment.segmentId} lacks valid rooted-subtree metadata`,
        );
      }
      if (segment.downstreamCustomerAccounts > 0) {
        const failureId = `network:${segment.segmentId}`;
        heap.push({
          failureId,
          failureType: "network",
          componentClass: segment.componentClass || segment.networkKind,
          customerAccounts: segment.downstreamCustomerAccounts,
          networkSegmentId: segment.segmentId,
          attachedNetworkSegmentId: null,
          topologyRootId: segment.topologyRootId,
          attachmentSubtreePoint: null,
          subtreeStart: segment.subtreeStart,
          subtreeEnd: segment.subtreeEnd,
          feederId: segment.feederId,
          lateralId: segment.lateralId,
          subId: segment.subId,
          selectionWeight: segment.weight,
          selectionKey: Math.log(segmentKeyedUniform(
            config.seed,
            "topology_failure_selection",
            failureId,
          )) / segment.weight,
          category: null,
        });
        networkCandidateCount += 1;
        theoreticalSelectionWeight += segment.weight;
      }
      for (const category of serviceGroupCategories(segment, sizing)) {
        serviceCategories.push(category);
        virtualServiceCandidateCount += category.groupCount;
        theoreticalSelectionWeight += category.groupCount * category.perGroupWeight;
        const first = nextVirtualServiceFailure(category, config.seed);
        if (first) heap.push(first);
      }
    }
    if (networkCandidateCount + virtualServiceCandidateCount < config.nOutages) {
      throw new InputValidationError(
        `only ${networkCandidateCount + virtualServiceCandidateCount} topology failure candidates are available for ${config.nOutages} outages`,
      );
    }

    const selectedFailures = [];
    const selectedNetworks = [];
    const selectedServices = [];
    let rejectedForCustomerOverlap = 0;
    let discardedOverlappedServiceGroups = 0;
    while (heap.size && selectedFailures.length < config.nOutages) {
      const candidate = heap.pop();
      const overlaps = failureOverlapsSelection(
        candidate,
        selectedNetworks,
        selectedServices,
      );
      if (overlaps) {
        rejectedForCustomerOverlap += 1;
        if (candidate.failureType === "service") {
          // Every remaining virtual group in this category is attached to the
          // same direct-load segment and is blocked by the same selected
          // network subtree, so the category can be discarded in one step.
          discardedOverlappedServiceGroups += candidate.category.remainingGroups;
          candidate.category.remainingGroups = 0;
        }
        continue;
      }
      const { category, ...selected } = candidate;
      selectedFailures.push(selected);
      if (selected.failureType === "network") selectedNetworks.push(selected);
      else selectedServices.push(selected);
      if (category) {
        const next = nextVirtualServiceFailure(category, config.seed);
        if (next) heap.push(next);
      }
    }
    if (selectedFailures.length !== config.nOutages) {
      throw new InputValidationError(
        `overlap-safe selection produced ${selectedFailures.length} of ${config.nOutages} requested outages; adjust component weights or outage count`,
      );
    }

    const uniqueCustomerAccounts = selectedFailures.reduce(
      (sum, failure) => sum + failure.customerAccounts,
      0,
    );
    return {
      schema: "connecticut_topology_failure_selection_v1",
      config,
      customerSizingConfig: sizing,
      selectedFailures,
      totalCustomers: uniqueCustomerAccounts,
      summary: {
        requestedOutages: config.nOutages,
        selectedOutages: selectedFailures.length,
        selectedNetworkFailures: selectedNetworks.length,
        selectedServiceFailures: selectedServices.length,
        networkCandidateCount,
        virtualServiceCandidateCount,
        serviceCategories: serviceCategories.length,
        lazilyGeneratedServiceCandidates: serviceCategories.reduce(
          (sum, category) => sum + category.generatedGroups,
          0,
        ),
        rejectedForCustomerOverlap,
        discardedOverlappedServiceGroups,
        theoreticalSelectionWeight,
        uniqueCustomerAccounts,
        meanCustomersPerOutage: uniqueCustomerAccounts / selectedFailures.length,
        maximumCustomersPerOutage: selectedFailures.reduce(
          (maximum, failure) => Math.max(maximum, failure.customerAccounts),
          0,
        ),
        overlappingCustomerSubtrees: 0,
      },
      methodology: {
        networkFailureSize: "integer downstream customer-account sum",
        serviceFailureSize:
          "disjoint 1-15-account compact customer-load group attached to a lateral segment",
        overlapRule:
          "reject ancestor/descendant network intervals and service groups contained by selected network intervals",
        serviceCandidateMaterialization:
          "lazy per-segment uniform order statistics; individual customer objects are not materialized",
      },
    };
  }

  function segmentPoint(segment, fraction) {
    if (fraction === 0.5 && Array.isArray(segment.midpoint)) {
      return segment.midpoint.slice();
    }
    if (fraction === 0 && Array.isArray(segment.start)) return segment.start.slice();
    if (fraction === 1 && Array.isArray(segment.end)) return segment.end.slice();
    return pointAlongPath(segment.pathCoordinates || [segment.start, segment.end], fraction);
  }

  // A segment can only ever yield an outage if SOME point along it is inside the
  // boundary. Checked at the same fixed fractions the fallback below uses, so a
  // segment that survives this can never fail there.
  function segmentCanPlace(segment, boundaryRings) {
    if (!boundaryRings) return true;
    for (const f of [0.5, 0, 1, 0.25, 0.75]) {
      const [lon, lat] = segmentPoint(segment, f);
      if (pointInBoundary(boundaryRings, lat, lon)) return true;
    }
    return false;
  }

  function sampleOutageScenario(weightedSegments, configInput = {}, inputs = {}, boundary = null) {
    const config = validateConfig(configInput);
    if (!Array.isArray(weightedSegments)) {
      throw new InputValidationError("weightedSegments must be an array");
    }
    const boundaryRings = boundary ? extractBoundaryRings(boundary) : null;

    // Drop un-placeable segments BEFORE sampling instead of throwing after.
    // The live grid generator constrains the network with a coarse 256x256
    // inside-bitmap (~480m x 360m cells), so a handful of segments end up just
    // outside the exact polygon -- measured: 6 of 43,539 laterals for Isaias.
    // Previously ONE such segment being drawn aborted the whole 20,450-outage
    // run ("has no sampled position inside the boundary"). They are candidates
    // that cannot produce a valid point, so the correct place to handle them is
    // the candidate pool, which also keeps the exactly-nOutages contract.
    const placeable = (boundaryRings
      ? weightedSegments.filter((segment) => segmentCanPlace(segment, boundaryRings))
      : weightedSegments.slice()).sort(
      (left, right) => left.segmentId.localeCompare(right.segmentId),
    );
    if (new Set(placeable.map((segment) => segment.segmentId)).size !== placeable.length) {
      throw new InputValidationError("weighted segment IDs must be unique");
    }
    const rejected = weightedSegments.length - placeable.length;
    if (placeable.length < config.nOutages) {
      throw new InputValidationError(`only ${placeable.length} placeable positive-weight network segments are available for ${config.nOutages} unique outages`
        + (rejected ? ` (${rejected} dropped as outside the boundary)` : ""));
    }
    const totalWeight = placeable.reduce((sum, segment) => sum + finiteNumber(segment.weight, "segment.weight"), 0);
    if (totalWeight <= 0) throw new InputValidationError("network sampling weight must be positive");
    const effectivePlacementMode = placeable.every(
      (segment) => segment.placementMode === "network_length_only",
    ) ? "network_length_only" : config.placementMode;
    // Exponential-race/random-key weighted sampling without replacement:
    // K_s = log(U_s) / W_s, U_s ~ Uniform(0, 1); retain the k largest keys.
    // W_s / sum(W) is the first-draw probability, not the final marginal
    // inclusion probability when k > 1. U_s is keyed by seed and stable
    // segment ID, so unrelated candidate insertion or array reordering cannot
    // change a retained segment's random key.
    const selected = placeable.map((segment, index) => ({
      key: Math.log(segmentKeyedUniform(
        config.seed,
        "selection",
        segment.segmentId,
      )) / segment.weight,
      index,
    })).sort((a, b) => b.key - a.key
      || placeable[a.index].segmentId.localeCompare(placeable[b.index].segmentId))
      .slice(0, config.nOutages);
    const outages = selected.map(({ index }) => {
      const segment = placeable[index];
      let position = segmentKeyedUniform(
        config.seed,
        "position",
        segment.segmentId,
      );
      let lon, lat, inside = !boundaryRings;
      for (let attempt=0;attempt<32;attempt++){
        [lon, lat] = segmentPoint(segment, position);
        inside=!boundaryRings||pointInBoundary(boundaryRings,lat,lon);
        if (inside) break;
        position = segmentKeyedUniform(
          config.seed,
          "position",
          segment.segmentId,
          attempt + 1,
        );
      }
      if (!inside){
        for (const fallback of [0.5,0,1,0.25,0.75]){
          [lon, lat] = segmentPoint(segment, fallback);
          if (pointInBoundary(boundaryRings,lat,lon)){inside=true;break;}
        }
      }
      if (!inside){
        // Unreachable: segmentCanPlace() already proved one of these exact
        // fallback fractions is inside. Kept as a genuine invariant check.
        throw new InputValidationError(`selected network segment ${segment.segmentId} has no sampled position inside the boundary`);
      }
      const isFeeder = segment.networkKind === "feeder" ? 1 : 0;
      return {
        lat, lon,
        kind: isFeeder ? "f" : "l",
        fi: segment.fi,
        li: segment.li,
        s: segment.segmentIndex,
        feeder_id: segment.feederId,
        is_feeder: isFeeder,
        sub_id: segment.subId,
        popLoss: LEGACY_CUSTOMERS_PER_OUTAGE,
        customers: LEGACY_CUSTOMERS_PER_OUTAGE,
        critical: false,
        priority: 0,
        tree_blocked: -1,
        networkSegmentId: segment.segmentId,
        networkKind: segment.networkKind,
        componentClass: segment.componentClass || segment.networkKind,
        parentNetworkSegmentId: segment.parentSegmentId ?? null,
        childNetworkSegmentIds: Array.isArray(segment.childSegmentIds)
          ? segment.childSegmentIds.slice()
          : [],
        topologyRootId: segment.topologyRootId ?? segment.segmentId,
        topologyDepth: segment.topologyDepth ?? 0,
        subtreeStart: segment.subtreeStart ?? null,
        subtreeEnd: segment.subtreeEnd ?? null,
        feederAnchorChainageKm: segment.feederAnchorChainageKm ?? null,
        networkDirectCustomerAccounts:
          Number.isInteger(segment.directCustomerAccounts)
            ? segment.directCustomerAccounts
            : null,
        networkDownstreamCustomerAccounts:
          Number.isInteger(segment.downstreamCustomerAccounts)
            ? segment.downstreamCustomerAccounts
            : null,
        lateralId: segment.lateralId,
        localWindMph: segment.localWindMph,
        localRainIn: segment.localRainIn,
        localRainAccumulationIn: segment.localRainAccumulationIn,
        localRainInputKind: segment.localRainInputKind,
        customerExposure: segment.customerExposure,
        relativeCustomerExposure: segment.relativeCustomerExposure,
        localWeatherSeverity: segment.localWeatherSeverity,
        hazardIndex: segment.hazardIndex,
        rawImpact: segment.rawImpact,
        smoothedImpact: segment.smoothedImpact,
        customerConsequenceIndex: segment.customerConsequenceIndex,
        impactPriorityScore: segment.impactPriorityScore,
        failureOrientedWeight: segment.failureOrientedWeight,
        impactPriorityWeight: segment.impactPriorityWeight,
        placementMode: segment.placementMode,
        segmentLengthKm: segment.lengthKm,
        susceptibility: segment.susceptibility,
        normalizedSegmentScore: segment.weight / totalWeight,
        // Deprecated compatibility alias; not a fixed-k inclusion probability.
        samplingWeight: segment.weight / totalWeight,
      };
    });
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_outage_scenario_v3",
      scenarioId: `${config.stormId}_seed${config.seed}`,
      config,
      inputs: { ...inputs },
      outages,
      totalCustomers: outages.length * LEGACY_CUSTOMERS_PER_OUTAGE,
      samplingDesign: {
        algorithm: "segment_keyed_exponential_random_key_without_replacement",
        keyEquation: "log(U_s) / W_s",
        uniformKey: "FNV-1a-derived 32-bit hash of seed, stream, segment ID, and counter",
        stableUnderCandidateReordering: true,
        conditionedOnOutageCount: config.nOutages,
        normalizedScoresAreInclusionProbabilities: false,
      },
      methodology: {
        placementMode: effectivePlacementMode,
        placementInterpretation: effectivePlacementMode === "network_length_only"
          ? "explicit weather-independent network-length fallback"
          : effectivePlacementMode === "failure_oriented"
            ? "conditional failure-oriented synthetic placement"
            : "conditional impact-weighted synthetic placement",
        calibratedAbsoluteFailureProbability: false,
        networkTopology: {
          schema: "connecticut_rooted_network_topology_v1",
          version: NETWORK_TOPOLOGY_VERSION,
          orientation: "feeder and lateral coordinate order is upstream to downstream",
          customerLoadsAssigned: placeable.some(
            (segment) => Number.isInteger(segment.downstreamCustomerAccounts),
          ),
          overlappingOutagePreventionApplied: false,
        },
        candidateSegmentation: {
          method: "equal-chainage subdivision of each feeder/lateral polyline",
          maximumLengthKm: config.candidateSegmentLengthKm,
        },
        lineIntegration: {
          method: "composite midpoint quadrature along polyline chainage",
          maximumStepKm: config.lineIntegrationStepKm,
        },
      },
    };
  }

  function interpolatedQuantile(sortedValues, probability) {
    if (!sortedValues.length) return null;
    if (probability <= 0) return sortedValues[0];
    if (probability >= 1) return sortedValues[sortedValues.length - 1];
    const position = (sortedValues.length - 1) * probability;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    const fraction = position - lower;
    return sortedValues[lower] * (1 - fraction) + sortedValues[upper] * fraction;
  }

  function summarizeOutageSizes(outages) {
    if (!Array.isArray(outages) || !outages.length) {
      throw new InputValidationError("outage-size summary requires at least one outage");
    }
    const sizes = outages.map((outage, index) => {
      if (!Number.isInteger(outage.customers) || outage.customers <= 0
          || outage.popLoss !== outage.customers) {
        throw new InputValidationError(
          `outage ${index} must have matching positive integer customers and popLoss`,
        );
      }
      return outage.customers;
    }).sort((left, right) => left - right);
    const totalCustomers = sizes.reduce((sum, value) => sum + value, 0);
    const classCounts = { service: 0, lateral: 0, feeder: 0 };
    for (const outage of outages) {
      if (!Object.prototype.hasOwnProperty.call(classCounts, outage.componentClass)) {
        throw new InputValidationError(
          `unsupported outage componentClass ${outage.componentClass}`,
        );
      }
      classCounts[outage.componentClass] += 1;
    }
    const smallestHalfCount = Math.floor(sizes.length / 2);
    const largestOnePercentCount = Math.max(1, Math.ceil(sizes.length * 0.01));
    return {
      outageCount: sizes.length,
      totalCustomers,
      meanCustomers: totalCustomers / sizes.length,
      minimumCustomers: sizes[0],
      maximumCustomers: sizes[sizes.length - 1],
      quantiles: {
        p10: interpolatedQuantile(sizes, 0.10),
        p25: interpolatedQuantile(sizes, 0.25),
        p50: interpolatedQuantile(sizes, 0.50),
        p75: interpolatedQuantile(sizes, 0.75),
        p90: interpolatedQuantile(sizes, 0.90),
        p95: interpolatedQuantile(sizes, 0.95),
        p99: interpolatedQuantile(sizes, 0.99),
        p999: interpolatedQuantile(sizes, 0.999),
      },
      componentClassCounts: classCounts,
      smallestHalfCustomerShare: sizes.slice(0, smallestHalfCount).reduce(
        (sum, value) => sum + value,
        0,
      ) / totalCustomers,
      largestOnePercentCustomerShare: sizes.slice(-largestOnePercentCount).reduce(
        (sum, value) => sum + value,
        0,
      ) / totalCustomers,
    };
  }

  function evaluateDpu31SizeDistribution(outages) {
    const summary = summarizeOutageSizes(outages);
    const bins = DPU31_SIZE_TARGET.map((target) => ({
      ...target,
      jobs: 0,
      customers: 0,
    }));
    let overflowJobs = 0;
    let overflowCustomers = 0;
    for (const outage of outages) {
      const bin = bins.find((candidate) =>
        outage.customers >= candidate.lo && outage.customers < candidate.hi);
      if (bin) {
        bin.jobs += 1;
        bin.customers += outage.customers;
      } else {
        overflowJobs += 1;
        overflowCustomers += outage.customers;
      }
    }
    for (const bin of bins) {
      bin.simulatedJobShare = bin.jobs / summary.outageCount;
      bin.simulatedCustomerShare = bin.customers / summary.totalCustomers;
      bin.jobShareError = bin.simulatedJobShare - bin.jobShare;
      bin.customerShareError = bin.simulatedCustomerShare - bin.customerShare;
    }
    const overflowJobShare = overflowJobs / summary.outageCount;
    const overflowCustomerShare = overflowCustomers / summary.totalCustomers;
    const totalVariationJobShare = 0.5 * (
      bins.reduce((sum, bin) => sum + Math.abs(bin.jobShareError), 0)
      + overflowJobShare
    );
    const totalVariationCustomerShare = 0.5 * (
      bins.reduce((sum, bin) => sum + Math.abs(bin.customerShareError), 0)
      + overflowCustomerShare
    );
    return {
      targetId: "dpu_24_41_national_grid_2377_jobs",
      binConvention: "half-open [lo, hi); final target bin is [2048, 4096)",
      targetJobs: 2377,
      targetCustomers: 306020,
      targetMeanCustomers: 128.74211190576358,
      bins,
      overflow: {
        jobs: overflowJobs,
        customers: overflowCustomers,
        jobShare: overflowJobShare,
        customerShare: overflowCustomerShare,
      },
      metrics: {
        totalVariationJobShare,
        totalVariationCustomerShare,
        maximumAbsoluteJobShareError: Math.max(
          overflowJobShare,
          ...bins.map((bin) => Math.abs(bin.jobShareError)),
        ),
        meanCustomerRelativeError:
          summary.meanCustomers / 128.74211190576358 - 1,
      },
      simulated: summary,
      calibrationObjectiveIncludesPcao: false,
    };
  }

  function calculateProvisionalPcao(outages) {
    const summary = summarizeOutageSizes(outages);
    return {
      schema: "connecticut_provisional_pcao_v1",
      value: summary.totalCustomers / summary.outageCount,
      peakCustomersAffected: summary.totalCustomers,
      totalStormOutages: summary.outageCount,
      equation: "peak customers affected / total storm outages",
      source: "Wanik et al. (2018), Equation 2",
      provisional: true,
      historicalComparisonValid: false,
      timeBasis:
        "all generated failures are assumed active at peak because restoration begins after storm passage",
      limitation:
        "under the current workflow PCAO equals mean customers per job; concurrent failure and restoration timing is required for comparison with the historical approximately-37 value",
      calibrationObjectiveIncludesPcao: false,
    };
  }

  function sampleSizedOutageScenario(
    weightedSegments,
    configInput = {},
    inputs = {},
    boundary = null,
  ) {
    const config = validateConfig(configInput);
    if (!Array.isArray(weightedSegments)) {
      throw new InputValidationError("weightedSegments must be an array");
    }
    const boundaryRings = boundary ? extractBoundaryRings(boundary) : null;
    const placeable = boundaryRings
      ? weightedSegments.filter((segment) => segmentCanPlace(segment, boundaryRings))
      : weightedSegments.slice();
    const sizingSelection = selectNonOverlappingTopologyFailures(
      placeable,
      config,
    );
    const sourceSegmentById = new Map(
      placeable.map((segment) => [segment.segmentId, segment]),
    );
    const failureById = new Map();
    const failureSegments = sizingSelection.selectedFailures.map((failure) => {
      const topologySegmentId = failure.networkSegmentId
        || failure.attachedNetworkSegmentId;
      const source = sourceSegmentById.get(topologySegmentId);
      if (!source) {
        throw new InputValidationError(
          `selected failure ${failure.failureId} references missing topology segment ${topologySegmentId}`,
        );
      }
      failureById.set(failure.failureId, { failure, source });
      const service = failure.failureType === "service";
      return {
        ...source,
        segmentId: failure.failureId,
        sourceTopologySegmentId: topologySegmentId,
        networkKind: failure.componentClass,
        componentClass: failure.componentClass,
        parentSegmentId: service ? topologySegmentId : source.parentSegmentId,
        childSegmentIds: service ? [] : source.childSegmentIds,
        directCustomerAccounts: service
          ? failure.customerAccounts
          : source.directCustomerAccounts,
        downstreamCustomerAccounts: failure.customerAccounts,
        weight: failure.selectionWeight,
      };
    });
    const located = sampleOutageScenario(
      failureSegments,
      config,
      inputs,
      boundary,
    );
    const outages = located.outages.map((outage) => {
      const selected = failureById.get(outage.networkSegmentId);
      if (!selected) {
        throw new InputValidationError(
          `located failure ${outage.networkSegmentId} is missing sizing metadata`,
        );
      }
      const { failure, source } = selected;
      const service = failure.failureType === "service";
      return {
        ...outage,
        failureId: failure.failureId,
        componentClass: failure.componentClass,
        networkKind: failure.componentClass,
        topologySegmentId: source.segmentId,
        attachedNetworkSegmentId: service ? source.segmentId : null,
        parentSegmentId: service ? source.segmentId : source.parentSegmentId,
        parentNetworkSegmentId: service ? source.segmentId : source.parentSegmentId,
        childNetworkSegmentIds: service ? [] : [...source.childSegmentIds],
        directCustomers: service
          ? failure.customerAccounts
          : source.directCustomerAccounts,
        downstreamCustomers: failure.customerAccounts,
        customers: failure.customerAccounts,
        popLoss: failure.customerAccounts,
        networkDirectCustomerAccounts: source.directCustomerAccounts,
        networkDownstreamCustomerAccounts: source.downstreamCustomerAccounts,
        subtreeStart: failure.subtreeStart,
        subtreeEnd: failure.subtreeEnd,
        attachmentSubtreePoint: failure.attachmentSubtreePoint,
        sizingSelectionWeight: failure.selectionWeight,
        sizingSelectionKey: failure.selectionKey,
      };
    });
    const sizeSummary = summarizeOutageSizes(outages);
    const dpu31Comparison = evaluateDpu31SizeDistribution(outages);
    const provisionalPcao = calculateProvisionalPcao(outages);
    if (sizeSummary.totalCustomers !== sizingSelection.totalCustomers) {
      throw new InputValidationError(
        `located outage total ${sizeSummary.totalCustomers} does not match sizing selection ${sizingSelection.totalCustomers}`,
      );
    }
    return {
      ...located,
      schemaVersion: OUTAGE_SCENARIO_VERSION,
      schema: "connecticut_outage_scenario_v4",
      outages,
      totalCustomers: sizeSummary.totalCustomers,
      sizeSummary,
      dpu31Comparison,
      provisionalPcao,
      sizingSelection: {
        schema: sizingSelection.schema,
        summary: sizingSelection.summary,
        methodology: sizingSelection.methodology,
      },
      samplingDesign: {
        ...located.samplingDesign,
        topologyFailureSelection: sizingSelection.methodology,
        overlappingCustomerSubtrees: 0,
      },
      methodology: {
        ...located.methodology,
        networkTopology: {
          ...located.methodology.networkTopology,
          customerLoadsAssigned: true,
          overlappingOutagePreventionApplied: true,
        },
        customerSizing: {
          schema: sizingSelection.schema,
          networkFailureSize: sizingSelection.methodology.networkFailureSize,
          serviceFailureSize: sizingSelection.methodology.serviceFailureSize,
          overlapRule: sizingSelection.methodology.overlapRule,
          serviceCandidateMaterialization:
            sizingSelection.methodology.serviceCandidateMaterialization,
          serviceFailureWeight: config.serviceFailureWeight,
          serviceGroupMaximumCustomers: config.serviceGroupMaximumCustomers,
        },
      },
    };
  }

  function generateOutageScenario(input) {
    if (!input || typeof input !== "object") throw new InputValidationError("model input must be an object");
    const config = validateConfig(input.config);
    const weather = normalizeWeather(input.weather);
    if (config.stormId !== weather.stormId) {
      throw new InputValidationError(`config stormId ${config.stormId} does not match weather stormId ${weather.stormId}`);
    }
    const customerSurface = buildCustomerExposureSurface(
      input.boundary, populationSourceFromInput(input), weather.latitudes, weather.longitudes,
      { smoothingKm: config.customerSmoothingKm, ruralBaselineFraction: config.ruralBaselineFraction },
    );
    const weatherSurface = buildWeatherSeveritySurface(input.weather, customerSurface.connecticutMask, config);
    const impactSurface = buildCombinedImpactSurface(customerSurface, weatherSurface, config);
    const topology = buildRootedNetworkTopology(input.network, config);
    const customerAllocation = allocateCustomerAccountsToTopology(topology, customerSurface);
    const weightedSegments = buildWeightedNetworkSegments(
      input.network,
      customerSurface,
      weatherSurface,
      impactSurface,
      config,
      customerAllocation,
    );
    const scenario = sampleSizedOutageScenario(
      weightedSegments,
      config,
      input.inputs || {},
      input.boundary,
    );
    const componentClassCounts = scenario.sizeSummary.componentClassCounts;
    return {
      ...scenario,
      surfaces: { customer: customerSurface, weather: weatherSurface, impact: impactSurface },
      customerAllocation: {
        schema: customerAllocation.schema,
        allocationVersion: customerAllocation.allocationVersion,
        sourceCustomerQuantity: customerAllocation.sourceCustomerQuantity,
        serviceRepresentation: customerAllocation.serviceRepresentation,
        summary: customerAllocation.summary,
      },
      summary: {
        placementModel: `${config.placementMode}_snapshot_v4_topology_sized`,
        placementMode: config.placementMode,
        candidateSegments: weightedSegments.length,
        feederCandidateSegments: weightedSegments.filter((segment) => segment.networkKind === "feeder").length,
        lateralCandidateSegments: weightedSegments.filter((segment) => segment.networkKind === "lateral").length,
        sampledOutages: scenario.outages.length,
        uniqueSampledSegments: new Set(scenario.outages.map((outage) => outage.networkSegmentId)).size,
        feederOutages: componentClassCounts.feeder,
        lateralOutages: componentClassCounts.lateral,
        serviceOutages: componentClassCounts.service,
        topologyRoots: new Set(weightedSegments.map((segment) => segment.topologyRootId)).size,
        maximumTopologyDepth: weightedSegments.reduce(
          (maximum, segment) => Math.max(maximum, segment.topologyDepth || 0),
          0,
        ),
        representedCustomers: scenario.totalCustomers,
        uniqueCustomersAffected: scenario.totalCustomers,
        outageSize: scenario.sizeSummary,
        dpu31Comparison: scenario.dpu31Comparison,
        provisionalPcao: scenario.provisionalPcao,
        topologySizing: scenario.sizingSelection.summary,
        customerAllocation: customerAllocation.summary,
        totalSegmentWeight: weightedSegments.reduce((sum, segment) => sum + segment.weight, 0),
        totalFailureOrientedWeight: weightedSegments.reduce(
          (sum, segment) => sum + segment.failureOrientedWeight, 0,
        ),
        totalImpactPriorityWeight: weightedSegments.reduce(
          (sum, segment) => sum + segment.impactPriorityWeight, 0,
        ),
      },
    };
  }

  function timelineFrameWeatherInput(timeline, frame) {
    return {
      grid: { lats: timeline.latitudes, lons: timeline.longitudes },
      storm: {
        stormId: timeline.stormId,
        name: timeline.name,
        date: frame.validTime.slice(0, 10),
        precipitationType: timeline.precipitationType,
        rainInputKind: `antecedent_${timeline.antecedentRainHours}h_accumulation`,
        peakWindMph: frame.windGustMph,
        peakRainIn: frame.rain6hIn,
      },
    };
  }

  function buildTimelineFrameSurfaces(timeline, customerSurface, config) {
    return timeline.frames.map((sourceFrame, frameIndex) => {
      const weather = buildWeatherSeveritySurface(
        timelineFrameWeatherInput(timeline, sourceFrame),
        customerSurface.connecticutMask,
        config,
      );
      const impact = buildCombinedImpactSurface(customerSurface, weather, {
        ...config,
        allowZeroImpact: true,
      });
      return {
        frameIndex,
        validTime: sourceFrame.validTime,
        rain1hIn: sourceFrame.rain1hIn,
        rain6hIn: sourceFrame.rain6hIn,
        weather,
        impact,
      };
    });
  }

  function buildTimelineWeightedSegments(
    network,
    frameSurfaces,
    config,
    topologyOverride = null,
  ) {
    if (!Array.isArray(frameSurfaces) || !frameSurfaces.length) {
      throw new InputValidationError("frameSurfaces must contain at least one frame");
    }
    const latitudes = frameSurfaces[0].impact.latitudes;
    const longitudes = frameSurfaces[0].impact.longitudes;
    const removeBasicPrefix = (segmentId) => segmentId === null
      ? null
      : segmentId.replace(/^basic:/, "");
    const segments = buildBasicNetworkSegments(network, config, topologyOverride).map((segment) => ({
      ...segment,
      segmentId: removeBasicPrefix(segment.segmentId),
      parentSegmentId: removeBasicPrefix(segment.parentSegmentId),
      childSegmentIds: segment.childSegmentIds.map(removeBasicPrefix),
      topologyRootId: removeBasicPrefix(segment.topologyRootId),
      placementMode: config.placementMode,
      failureOrientedWeight: 0,
      impactPriorityWeight: 0,
      weight: 0,
    }));
    // Line integration is linear. Sum the hourly grids first, then integrate
    // each network candidate once. This is mathematically equivalent to the
    // former frame × segment loop while avoiding millions of repeated path and
    // interpolation setup operations on the production road network.
    const summedHazardIndex = latitudes.map((_, rowIndex) =>
      longitudes.map((__, columnIndex) => frameSurfaces.reduce(
        (sum, frame) => sum + frame.weather.weatherSeverity[rowIndex][columnIndex],
        0,
      )));
    const summedImpactPriorityScore = latitudes.map((_, rowIndex) =>
      longitudes.map((__, columnIndex) => frameSurfaces.reduce(
        (sum, frame) => sum + frame.impact.smoothedImpact[rowIndex][columnIndex],
        0,
      )));
    for (const segment of segments) {
      const integrated = integrateNamedGridsForTopologySegment(
        latitudes,
        longitudes,
        {
          hazardIndex: summedHazardIndex,
          impactPriorityScore: summedImpactPriorityScore,
        },
        segment,
        config.lineIntegrationStepKm,
      );
      segment.failureOrientedWeight =
        integrated.integrals.hazardIndex * segment.susceptibility;
      segment.impactPriorityWeight =
        integrated.integrals.impactPriorityScore * segment.susceptibility;
    }
    for (const segment of segments) {
      segment.weight = config.placementMode === "failure_oriented"
        ? segment.failureOrientedWeight
        : segment.impactPriorityWeight;
      segment.integrationMethod = "composite_midpoint_rule_along_polyline";
      segment.integrationStepKm = config.lineIntegrationStepKm;
      segment.integrationSampleCount = Math.max(
        1,
        Math.ceil(segment.lengthKm / config.lineIntegrationStepKm),
      );
    }
    const positiveSegments = segments.filter((segment) => segment.weight > 0 && Number.isFinite(segment.weight));
    if (!positiveSegments.length) {
      throw new InputValidationError(
        "storm timeline has no positive network score at the configured threshold",
      );
    }
    return positiveSegments;
  }

  function sampleTimelineOutageScenario(
    weightedSegments,
    frameSurfaces,
    customerSurface,
    configInput = {},
    inputs = {},
    boundary = null,
  ) {
    const config = validateConfig(configInput);
    const baseScenario = sampleSizedOutageScenario(
      weightedSegments,
      config,
      inputs,
      boundary,
    );
    const segmentById = new Map(weightedSegments.map((segment) => [segment.segmentId, segment]));
    const latitudes = customerSurface.latitudes;
    const longitudes = customerSurface.longitudes;
    const frameOutageCounts = Array(frameSurfaces.length).fill(0);

    const outages = baseScenario.outages.map((outage) => {
      const segment = segmentById.get(outage.topologySegmentId);
      if (!segment) throw new InputValidationError(`missing timeline segment ${outage.topologySegmentId}`);
      const frameWeights = frameSurfaces.map((frame) => {
        const grid = config.placementMode === "failure_oriented"
          ? frame.weather.weatherSeverity
          : frame.impact.smoothedImpact;
        const integrated = integrateNamedGridsForTopologySegment(
          latitudes,
          longitudes,
          { selectedScore: grid },
          segment,
          config.lineIntegrationStepKm,
        );
        return Math.max(0, integrated.integrals.selectedScore * segment.susceptibility);
      });
      const totalFrameWeight = frameWeights.reduce((sum, value) => sum + value, 0);
      if (totalFrameWeight <= 0) {
        throw new InputValidationError(`timeline segment ${segment.segmentId} has no positive frame weight`);
      }
      const target = segmentKeyedUniform(
        config.seed,
        "occurrence_frame",
        outage.failureId,
      ) * totalFrameWeight;
      let cumulative = 0;
      let selectedFrameIndex = frameWeights.length - 1;
      for (let frameIndex = 0; frameIndex < frameWeights.length; frameIndex += 1) {
        cumulative += frameWeights[frameIndex];
        if (target <= cumulative) {
          selectedFrameIndex = frameIndex;
          break;
        }
      }
      const frame = frameSurfaces[selectedFrameIndex];
      const latitude = outage.lat;
      const longitude = outage.lon;
      const localHazard = bilinearGridValue(
        latitudes, longitudes, frame.weather.weatherSeverity, latitude, longitude,
      );
      const localConsequence = bilinearGridValue(
        latitudes, longitudes, frame.impact.relativeCustomerExposure, latitude, longitude,
      );
      const localImpactPriority = bilinearGridValue(
        latitudes, longitudes, frame.impact.smoothedImpact, latitude, longitude,
      );
      frameOutageCounts[selectedFrameIndex] += 1;
      return {
        ...outage,
        occurredAt: frame.validTime,
        stormFrameIndex: selectedFrameIndex,
        localWindMph: bilinearGridValue(latitudes, longitudes, frame.weather.windMph, latitude, longitude),
        localRain1hIn: bilinearGridValue(latitudes, longitudes, frame.rain1hIn, latitude, longitude),
        localRain6hIn: bilinearGridValue(latitudes, longitudes, frame.rain6hIn, latitude, longitude),
        localRainIn: bilinearGridValue(latitudes, longitudes, frame.rain6hIn, latitude, longitude),
        customerExposure: bilinearGridValue(
          latitudes, longitudes, customerSurface.smoothedCustomerAccounts, latitude, longitude,
        ),
        relativeCustomerExposure: bilinearGridValue(
          latitudes, longitudes, frame.impact.relativeCustomerExposure, latitude, longitude,
        ),
        customerConsequenceIndex: localConsequence,
        localWeatherSeverity: localHazard,
        hazardIndex: localHazard,
        rawImpact: bilinearGridValue(latitudes, longitudes, frame.impact.rawImpact, latitude, longitude),
        smoothedImpact: localImpactPriority,
        impactPriorityScore: localImpactPriority,
        conditionalFrameWeightShare: frameWeights[selectedFrameIndex] / totalFrameWeight,
        // Deprecated compatibility alias.
        frameSamplingWeight: frameWeights[selectedFrameIndex] / totalFrameWeight,
      };
    });

    return {
      ...baseScenario,
      schemaVersion: OUTAGE_SCENARIO_VERSION,
      schema: "connecticut_timeline_outage_scenario_v4",
      scenarioId: `${config.stormId}_timeline_seed${config.seed}`,
      outages,
      frameOutageCounts,
    };
  }

  function prepareTimelineOutageScenario(input) {
    if (!input || typeof input !== "object") throw new InputValidationError("model input must be an object");
    const config = validateConfig(input.config);
    const timeline = normalizeWeatherTimeline(input.weatherTimeline ?? input.weather_timeline);
    if (config.stormId !== timeline.stormId) {
      throw new InputValidationError(
        `config stormId ${config.stormId} does not match timeline stormId ${timeline.stormId}`,
      );
    }
    const customerSurface = buildCustomerExposureSurface(
      input.boundary,
      populationSourceFromInput(input),
      timeline.latitudes,
      timeline.longitudes,
      { smoothingKm: config.customerSmoothingKm, ruralBaselineFraction: config.ruralBaselineFraction },
    );
    const topology = buildRootedNetworkTopology(input.network, config);
    const customerAllocation = allocateCustomerAccountsToTopology(topology, customerSurface);
    const frameSurfaces = buildTimelineFrameSurfaces(timeline, customerSurface, config);
    const weightedSegments = buildTimelineWeightedSegments(
      input.network,
      frameSurfaces,
      config,
      customerAllocation,
    );
    return {
      config,
      timeline,
      customerSurface,
      customerAllocation,
      frameSurfaces,
      weightedSegments,
    };
  }

  function buildTimelineOutageScenarioFromPrepared(input, prepared) {
    if (!input || typeof input !== "object") throw new InputValidationError("model input must be an object");
    if (!prepared || typeof prepared !== "object") {
      throw new InputValidationError("prepared timeline model inputs must be an object");
    }
    const config = validateConfig(input.config);
    const {
      timeline,
      customerSurface,
      customerAllocation,
      frameSurfaces,
      weightedSegments,
    } = prepared;
    if (!timeline || config.stormId !== timeline.stormId) {
      throw new InputValidationError("prepared timeline does not match the requested storm");
    }
    if (!customerSurface || !customerAllocation
        || !Array.isArray(frameSurfaces) || !frameSurfaces.length
        || !Array.isArray(weightedSegments) || !weightedSegments.length) {
      throw new InputValidationError("prepared timeline inputs are incomplete");
    }
    const scenario = sampleTimelineOutageScenario(
      weightedSegments,
      frameSurfaces,
      customerSurface,
      config,
      {
        ...(input.inputs || {}),
        weatherMode: "curated_hourly_timeline",
        timelineStart: timeline.startTime,
        timelineEnd: timeline.endTime,
        antecedentRainHours: timeline.antecedentRainHours,
      },
      input.boundary,
    );
    const componentClassCounts = scenario.sizeSummary.componentClassCounts;
    const activeFrameCount = scenario.frameOutageCounts.filter((count) => count > 0).length;
    return {
      ...scenario,
      customerAllocation: {
        schema: customerAllocation.schema,
        allocationVersion: customerAllocation.allocationVersion,
        sourceCustomerQuantity: customerAllocation.sourceCustomerQuantity,
        serviceRepresentation: customerAllocation.serviceRepresentation,
        summary: customerAllocation.summary,
      },
      surfaces: {
        customer: customerSurface,
        timeline: {
          stormId: timeline.stormId,
          stormName: timeline.name,
          startTime: timeline.startTime,
          endTime: timeline.endTime,
          intervalMinutes: timeline.intervalMinutes,
          antecedentRainHours: timeline.antecedentRainHours,
          rainInputKind: `antecedent_${timeline.antecedentRainHours}h_accumulation`,
          frames: frameSurfaces,
        },
      },
      summary: {
        placementModel: `${config.placementMode}_curated_hourly_timeline_v4_topology_sized`,
        placementMode: config.placementMode,
        candidateSegments: weightedSegments.length,
        feederCandidateSegments: weightedSegments.filter(
          (segment) => segment.networkKind === "feeder",
        ).length,
        lateralCandidateSegments: weightedSegments.filter(
          (segment) => segment.networkKind === "lateral",
        ).length,
        sampledOutages: scenario.outages.length,
        uniqueSampledSegments: new Set(scenario.outages.map((outage) => outage.networkSegmentId)).size,
        feederOutages: componentClassCounts.feeder,
        lateralOutages: componentClassCounts.lateral,
        serviceOutages: componentClassCounts.service,
        topologyRoots: new Set(weightedSegments.map((segment) => segment.topologyRootId)).size,
        maximumTopologyDepth: weightedSegments.reduce(
          (maximum, segment) => Math.max(maximum, segment.topologyDepth || 0),
          0,
        ),
        representedCustomers: scenario.totalCustomers,
        uniqueCustomersAffected: scenario.totalCustomers,
        outageSize: scenario.sizeSummary,
        dpu31Comparison: scenario.dpu31Comparison,
        provisionalPcao: scenario.provisionalPcao,
        topologySizing: scenario.sizingSelection.summary,
        customerAllocation: customerAllocation.summary,
        totalSegmentWeight: weightedSegments.reduce((sum, segment) => sum + segment.weight, 0),
        totalFailureOrientedWeight: weightedSegments.reduce(
          (sum, segment) => sum + segment.failureOrientedWeight, 0,
        ),
        totalImpactPriorityWeight: weightedSegments.reduce(
          (sum, segment) => sum + segment.impactPriorityWeight, 0,
        ),
        timelineFrames: frameSurfaces.length,
        activeOutageFrames: activeFrameCount,
        frameOutageCounts: scenario.frameOutageCounts.slice(),
        firstOccurrence: scenario.outages.reduce(
          (earliest, outage) => !earliest || outage.occurredAt < earliest ? outage.occurredAt : earliest,
          null,
        ),
        lastOccurrence: scenario.outages.reduce(
          (latest, outage) => !latest || outage.occurredAt > latest ? outage.occurredAt : latest,
          null,
        ),
      },
    };
  }

  function generateTimelineOutageScenario(input) {
    return buildTimelineOutageScenarioFromPrepared(
      input,
      prepareTimelineOutageScenario(input),
    );
  }

  return Object.freeze({
    SCHEMA_VERSION,
    OUTAGE_SCENARIO_VERSION,
    LEGACY_CUSTOMERS_PER_OUTAGE,
    POPULATION_TO_CUSTOMER_RATIO,
    NETWORK_TOPOLOGY_VERSION,
    CUSTOMER_ALLOCATION_VERSION,
    DEFAULT_CUSTOMER_SIZING_CONFIG,
    DPU31_SIZE_TARGET,
    DEFAULT_CONFIG,
    InputValidationError,
    validateConfig,
    extractBoundaryRings,
    pointInBoundary,
    buildConnecticutMask,
    rasterizePopulationPersons,
    rasterizeCustomerAccounts,
    boundaryAwareGaussianSmooth,
    spatialGridMetadata,
    populationSourceFromInput,
    buildCustomerExposureSurface,
    weatherSeverityScore,
    normalizeWeather,
    normalizeWeatherTimeline,
    buildWeatherSeveritySurface,
    buildCombinedImpactSurface,
    haversineKm,
    bilinearGridValue,
    pointAlongPath,
    standardizeLineSegments,
    integrateGridAlongPath,
    normalizeNetwork,
    buildRootedNetworkTopology,
    allocateCustomerAccountsToTopology,
    buildWeightedNetworkSegments,
    buildBasicNetworkSegments,
    mulberry32,
    segmentKeyedUniform,
    validateCustomerSizingConfig,
    selectNonOverlappingTopologyFailures,
    sampleOutageScenario,
    sampleSizedOutageScenario,
    summarizeOutageSizes,
    evaluateDpu31SizeDistribution,
    calculateProvisionalPcao,
    buildTimelineFrameSurfaces,
    buildTimelineWeightedSegments,
    sampleTimelineOutageScenario,
    prepareTimelineOutageScenario,
    buildTimelineOutageScenarioFromPrepared,
    generateOutageScenario,
    generateTimelineOutageScenario,
  });
});
