/*
 * Connecticut weather- and customer-weighted outage-location model.
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

  const SCHEMA_VERSION = 1;
  const POPULATION_TO_CUSTOMER_RATIO = 1633000 / 3605944;
  const EARTH_RADIUS_KM = 6371.0088;

  const DEFAULT_CONFIG = Object.freeze({
    stormId: "isaias_2020",
    seed: 42,
    nOutages: 2000,
    customersPerOutage: 50,
    windThresholdMph: 35,
    windExcessScaleMph: 25,
    windExponent: 2,
    rainCoefficient: 0.5,
    rainReferenceIn: 1,
    rainScoreCap: 2,
    exposureExponent: 1,
    customerSmoothingKm: 6,
    ruralBaselineFraction: 0.02,
    gaussianBandwidthKm: 10,
    feederSusceptibility: 1,
    lateralSusceptibility: 1.25,
  });

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
    feeder_susceptibility: "feederSusceptibility",
    lateral_susceptibility: "lateralSusceptibility",
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
      if (!Object.prototype.hasOwnProperty.call(DEFAULT_CONFIG, normalizedKey)) {
        throw new InputValidationError(`unknown configuration field: ${key}`);
      }
      normalized[normalizedKey] = value;
    }
    const config = { ...DEFAULT_CONFIG, ...normalized };
    if (typeof config.stormId !== "string" || !config.stormId.trim()) {
      throw new InputValidationError("stormId must not be empty");
    }
    integer(config.seed, "seed");
    integer(config.nOutages, "nOutages", 1);
    integer(config.customersPerOutage, "customersPerOutage", 1);
    if (config.customersPerOutage !== 50) {
      throw new InputValidationError("version-one outages must represent exactly 50 customers");
    }
    for (const key of ["windThresholdMph", "rainCoefficient", "ruralBaselineFraction"]) {
      if (finiteNumber(config[key], key) < 0) {
        throw new InputValidationError(`${key} must be >= 0`);
      }
    }
    for (const key of [
      "windExcessScaleMph", "windExponent", "rainReferenceIn", "rainScoreCap",
      "exposureExponent", "customerSmoothingKm", "gaussianBandwidthKm",
      "feederSusceptibility", "lateralSusceptibility",
    ]) {
      if (finiteNumber(config[key], key) <= 0) {
        throw new InputValidationError(`${key} must be > 0`);
      }
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

  function normalizeCensusTracts(tracts) {
    if (!Array.isArray(tracts) || !tracts.length) {
      throw new InputValidationError("censusTracts must be a non-empty array");
    }
    return tracts.map((tract, index) => {
      if (!tract || typeof tract !== "object") {
        throw new InputValidationError(`censusTracts[${index}] must be an object`);
      }
      const population = finiteNumber(tract.pop ?? tract.population, `censusTracts[${index}].pop`);
      const latitude = finiteNumber(tract.lat ?? tract.latitude, `censusTracts[${index}].lat`);
      const longitude = finiteNumber(tract.lon ?? tract.longitude, `censusTracts[${index}].lon`);
      if (population < 0) throw new InputValidationError(`censusTracts[${index}].pop must be >= 0`);
      if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
        throw new InputValidationError(`censusTracts[${index}] is outside valid longitude/latitude bounds`);
      }
      return { geoid: String(tract.geoid ?? tract.GEOID ?? index), population, latitude, longitude };
    });
  }

  function rasterizeCustomerAccounts(censusTracts, latitudes, longitudes, mask) {
    const tracts = normalizeCensusTracts(censusTracts);
    const rows = latitudes.length;
    const columns = longitudes.length;
    const grid = Array.from({ length: rows }, () => Array(columns).fill(0));
    for (const tract of tracts) {
      const [row0, row1, rowFraction] = bracketingIndices(latitudes, tract.latitude);
      const [column0, column1, columnFraction] = bracketingIndices(longitudes, tract.longitude);
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
        const [row, column] = nearestValidCell(mask, latitudes, longitudes, tract.latitude, tract.longitude);
        candidates.clear();
        candidates.set(row * columns + column, 1);
        totalWeight = 1;
      }
      const accounts = tract.population * POPULATION_TO_CUSTOMER_RATIO;
      for (const [key, weight] of candidates) {
        const row = Math.floor(key / columns);
        const column = key % columns;
        grid[row][column] += accounts * weight / totalWeight;
      }
    }
    return grid;
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

  function gridTotal(grid) {
    let total = 0;
    for (const row of grid) for (const value of row) total += value;
    return total;
  }

  function boundaryAwareGaussianSmooth(values, mask, options) {
    const smoothingKm = finiteNumber(options.smoothingKm, "smoothingKm");
    const latitudeCellKm = finiteNumber(options.latitudeCellKm, "latitudeCellKm");
    const longitudeCellKm = finiteNumber(options.longitudeCellKm, "longitudeCellKm");
    const preserveTotal = options.preserveTotal !== false;
    if (smoothingKm <= 0 || latitudeCellKm <= 0 || longitudeCellKm <= 0) {
      throw new InputValidationError("smoothing and grid-cell spacing must be positive");
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

  function buildCustomerExposureSurface(boundary, censusTracts, latitudes, longitudes, options = {}) {
    const smoothingKm = options.smoothingKm ?? DEFAULT_CONFIG.customerSmoothingKm;
    const ruralBaselineFraction = options.ruralBaselineFraction ?? DEFAULT_CONFIG.ruralBaselineFraction;
    if (finiteNumber(ruralBaselineFraction, "ruralBaselineFraction") < 0) {
      throw new InputValidationError("ruralBaselineFraction must be >= 0");
    }
    const lats = validateCoordinates(latitudes, "latitudes");
    const lons = validateCoordinates(longitudes, "longitudes");
    const mask = buildConnecticutMask(boundary, lats, lons);
    const rawCustomerAccounts = rasterizeCustomerAccounts(censusTracts, lats, lons, mask);
    const spacing = gridCellSpacingKm(lats, lons);
    const smoothedCustomerAccounts = boundaryAwareGaussianSmooth(rawCustomerAccounts, mask, {
      smoothingKm, ...spacing,
    });
    const total = gridTotal(rawCustomerAccounts);
    const validCellCount = mask.reduce((sum, row) => sum + row.filter(Boolean).length, 0);
    if (!validCellCount || total <= 0) throw new InputValidationError("customer surface has no in-state customer accounts");
    const baseline = ruralBaselineFraction * total / validCellCount;
    if (baseline) {
      for (let row = 0; row < mask.length; row += 1) {
        for (let column = 0; column < mask[0].length; column += 1) {
          if (mask[row][column]) smoothedCustomerAccounts[row][column] += baseline;
        }
      }
    }
    const rescale = total / gridTotal(smoothedCustomerAccounts);
    for (let row = 0; row < mask.length; row += 1) {
      for (let column = 0; column < mask[0].length; column += 1) smoothedCustomerAccounts[row][column] *= rescale;
    }
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_customer_exposure_v1",
      latitudes: lats,
      longitudes: lons,
      connecticutMask: mask,
      rawCustomerAccounts,
      smoothedCustomerAccounts,
      totalCustomerAccounts: total,
      smoothingKm,
      ruralBaselineFraction,
      ...spacing,
      summary: { rawTotal: gridTotal(rawCustomerAccounts), smoothedTotal: gridTotal(smoothedCustomerAccounts), validCellCount },
    };
  }

  function weatherSeverityScore(windMph, rainInPerHour, options = {}) {
    const wind = finiteNumber(windMph, "windMph");
    const rain = finiteNumber(rainInPerHour, "rainInPerHour");
    const threshold = options.windThresholdMph ?? DEFAULT_CONFIG.windThresholdMph;
    const scale = options.windExcessScaleMph ?? DEFAULT_CONFIG.windExcessScaleMph;
    const exponent = options.windExponent ?? DEFAULT_CONFIG.windExponent;
    const rainReference = options.rainReferenceIn ?? DEFAULT_CONFIG.rainReferenceIn;
    const coefficient = options.rainCoefficient ?? DEFAULT_CONFIG.rainCoefficient;
    const rainCap = options.rainScoreCap ?? DEFAULT_CONFIG.rainScoreCap;
    if (wind < 0 || wind > 250) throw new InputValidationError("windMph must be within [0, 250]");
    if (rain < 0 || rain > 15) throw new InputValidationError("rainInPerHour must be within [0, 15]");
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
      wind: validateGrid(storm.peakWindMph ?? storm.peak_wind_mph, latitudes.length, longitudes.length, "peakWindMph", [0, 250]),
      rain: validateGrid(storm.peakRainIn ?? storm.peak_rain_in, latitudes.length, longitudes.length, "peakRainIn", [0, 15]),
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
    const windMph = [], rainInPerHour = [], windDamageScore = [], rainAmplification = [], weatherSeverity = [];
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
      windMph.push(windRow); rainInPerHour.push(rainRow); windDamageScore.push(damageRow);
      rainAmplification.push(amplificationRow); weatherSeverity.push(severityRow);
    }
    const flatSeverity = weatherSeverity.flat();
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_weather_severity_v1",
      stormId: normalized.stormId,
      stormName: normalized.name,
      stormDate: normalized.date,
      precipitationType: normalized.precipitationType,
      latitudes, longitudes, connecticutMask, windMph, rainInPerHour,
      windDamageScore, rainAmplification, weatherSeverity,
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
    if (weatherSurface.latitudes.length !== rows || weatherSurface.longitudes.length !== columns) {
      throw new InputValidationError("customer and weather surface shapes must match");
    }
    const validCellCount = customerSurface.summary.validCellCount;
    const meanExposure = customerSurface.summary.smoothedTotal / validCellCount;
    const relativeCustomerExposure = mask.map((row, rowIndex) => row.map((inside, columnIndex) =>
      inside ? customerSurface.smoothedCustomerAccounts[rowIndex][columnIndex] / meanExposure : 0));
    const rawImpact = mask.map((row, rowIndex) => row.map((inside, columnIndex) => inside
      ? weatherSurface.weatherSeverity[rowIndex][columnIndex]
        * relativeCustomerExposure[rowIndex][columnIndex] ** exposureExponent
      : 0));
    const smoothedImpact = boundaryAwareGaussianSmooth(rawImpact, mask, {
      smoothingKm: gaussianBandwidthKm,
      latitudeCellKm: customerSurface.latitudeCellKm,
      longitudeCellKm: customerSurface.longitudeCellKm,
    });
    const smoothedTotal = gridTotal(smoothedImpact);
    const samplingProbability = mask.map((row, rowIndex) => row.map((inside, columnIndex) =>
      inside ? smoothedImpact[rowIndex][columnIndex] / smoothedTotal : 0));
    const rawTotal = gridTotal(rawImpact);
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_combined_impact_v1",
      stormId: weatherSurface.stormId,
      latitudes: customerSurface.latitudes,
      longitudes: customerSurface.longitudes,
      connecticutMask: mask,
      relativeCustomerExposure,
      weatherSeverity: weatherSurface.weatherSeverity,
      rawImpact,
      smoothedImpact,
      samplingProbability,
      exposureExponent,
      gaussianBandwidthKm,
      meanCustomerAccountsPerValidCell: meanExposure,
      summary: {
        rawTotal,
        smoothedTotal,
        probabilityTotal: gridTotal(samplingProbability),
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

  function bilinearGridValue(latitudes, longitudes, values, latitude, longitude) {
    if (!Array.isArray(values) || values.length !== latitudes.length
      || !Array.isArray(values[0]) || values[0].length !== longitudes.length) {
      throw new InputValidationError("bilinear grid shape does not match coordinates");
    }
    const [row0, row1, rowFraction] = bracketingIndices(latitudes, latitude);
    const [column0, column1, columnFraction] = bracketingIndices(longitudes, longitude);
    const lower = values[row0][column0] * (1 - columnFraction) + values[row0][column1] * columnFraction;
    const upper = values[row1][column0] * (1 - columnFraction) + values[row1][column1] * columnFraction;
    return lower * (1 - rowFraction) + upper * rowFraction;
  }

  function normalizeNetwork(network) {
    if (!network || !Array.isArray(network.feeders) || !Array.isArray(network.laterals)) {
      throw new InputValidationError("network must contain feeders and laterals arrays");
    }
    const feeders = network.feeders.map((feeder, fi) => ({
      fi,
      feederId: integer(feeder.feederId ?? feeder.feeder_id ?? fi, `feeders[${fi}].feederId`, 0),
      subId: integer(feeder.subId ?? feeder.sub_id ?? feeder.subIdx ?? 0, `feeders[${fi}].subId`, 0),
      coordinates: (feeder.coordinates || feeder.pts || []).map((point, index) =>
        feeder.coordinates
          ? assertCoordinate(point, `feeders[${fi}].coordinates[${index}]`)
          : assertCoordinate([point[1], point[0]], `feeders[${fi}].pts[${index}]`)),
    }));
    if (Array.isArray(network.substations) && network.substations.length) {
      const substationIds = new Set(network.substations.map((substation, index) =>
        integer(substation.subId ?? substation.sub_id ?? index, `substations[${index}].subId`, 0)));
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
      return {
        li,
        lateralId: integer(lateral.lateralId ?? lateral.lateral_id ?? li, `laterals[${li}].lateralId`, 0),
        feeder,
        coordinates: (lateral.coordinates || lateral.pts || []).map((point, index) =>
          lateral.coordinates
            ? assertCoordinate(point, `laterals[${li}].coordinates[${index}]`)
            : assertCoordinate([point[1], point[0]], `laterals[${li}].pts[${index}]`)),
      };
    });
    for (const [label, lines] of [["feeder", feeders], ["lateral", laterals]]) {
      for (const line of lines) {
        if (line.coordinates.length < 2) throw new InputValidationError(`${label} ${line.fi ?? line.li} needs at least two points`);
      }
    }
    return { feeders, laterals };
  }

  function buildWeightedNetworkSegments(network, customerSurface, weatherSurface, impactSurface, options = {}) {
    const feederSusceptibility = options.feederSusceptibility ?? DEFAULT_CONFIG.feederSusceptibility;
    const lateralSusceptibility = options.lateralSusceptibility ?? DEFAULT_CONFIG.lateralSusceptibility;
    if (feederSusceptibility <= 0 || lateralSusceptibility <= 0) {
      throw new InputValidationError("network susceptibility factors must be positive");
    }
    const normalized = normalizeNetwork(network);
    const { latitudes, longitudes } = impactSurface;
    const interpolationGrids = [
      weatherSurface.windMph,
      weatherSurface.rainInPerHour,
      customerSurface.smoothedCustomerAccounts,
      impactSurface.relativeCustomerExposure,
      impactSurface.weatherSeverity,
      impactSurface.rawImpact,
      impactSurface.smoothedImpact,
    ];
    if (interpolationGrids.some((grid) => !Array.isArray(grid)
      || grid.length !== latitudes.length
      || grid.some((row) => !Array.isArray(row) || row.length !== longitudes.length))) {
      throw new InputValidationError("network weighting surfaces must share one grid");
    }
    const segments = [];
    function addLine(kind, line, feeder, coordinates, susceptibility) {
      for (let segmentIndex = 0; segmentIndex < coordinates.length - 1; segmentIndex += 1) {
        const start = coordinates[segmentIndex];
        const end = coordinates[segmentIndex + 1];
        const lengthKm = haversineKm(start, end);
        if (lengthKm <= 0) continue;
        const midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
        const latitude = midpoint[1], longitude = midpoint[0];
        const smoothedImpact = bilinearGridValue(latitudes, longitudes, impactSurface.smoothedImpact, latitude, longitude);
        const weight = smoothedImpact * lengthKm * susceptibility;
        if (weight <= 0 || !Number.isFinite(weight)) continue;
        const lineId = kind === "feeder" ? feeder.feederId : line.lateralId;
        segments.push({
          segmentId: `${kind}:${lineId}:${segmentIndex}`,
          networkKind: kind,
          fi: feeder.fi,
          li: kind === "lateral" ? line.li : null,
          segmentIndex,
          feederId: feeder.feederId,
          lateralId: kind === "lateral" ? line.lateralId : null,
          subId: feeder.subId,
          start, end, midpoint, lengthKm,
          localWindMph: bilinearGridValue(latitudes, longitudes, weatherSurface.windMph, latitude, longitude),
          localRainIn: bilinearGridValue(latitudes, longitudes, weatherSurface.rainInPerHour, latitude, longitude),
          customerExposure: bilinearGridValue(latitudes, longitudes, customerSurface.smoothedCustomerAccounts, latitude, longitude),
          relativeCustomerExposure: bilinearGridValue(latitudes, longitudes, impactSurface.relativeCustomerExposure, latitude, longitude),
          localWeatherSeverity: bilinearGridValue(latitudes, longitudes, impactSurface.weatherSeverity, latitude, longitude),
          rawImpact: bilinearGridValue(latitudes, longitudes, impactSurface.rawImpact, latitude, longitude),
          smoothedImpact, susceptibility, weight,
        });
      }
    }
    for (const feeder of normalized.feeders) addLine("feeder", feeder, feeder, feeder.coordinates, feederSusceptibility);
    for (const lateral of normalized.laterals) addLine("lateral", lateral, lateral.feeder, lateral.coordinates, lateralSusceptibility);
    if (!segments.length) throw new InputValidationError("network has no positive-weight segments");
    return segments;
  }

  function buildBasicNetworkSegments(network, options = {}) {
    const feederSusceptibility = options.feederSusceptibility ?? DEFAULT_CONFIG.feederSusceptibility;
    const lateralSusceptibility = options.lateralSusceptibility ?? DEFAULT_CONFIG.lateralSusceptibility;
    if (feederSusceptibility <= 0 || lateralSusceptibility <= 0) {
      throw new InputValidationError("network susceptibility factors must be positive");
    }
    const normalized = normalizeNetwork(network);
    const segments = [];
    function addLine(kind, line, feeder, coordinates, susceptibility) {
      for (let segmentIndex = 0; segmentIndex < coordinates.length - 1; segmentIndex += 1) {
        const start = coordinates[segmentIndex];
        const end = coordinates[segmentIndex + 1];
        const lengthKm = haversineKm(start, end);
        if (lengthKm <= 0) continue;
        const lineId = kind === "feeder" ? feeder.feederId : line.lateralId;
        segments.push({
          segmentId: `basic:${kind}:${lineId}:${segmentIndex}`,
          networkKind: kind,
          fi: feeder.fi,
          li: kind === "lateral" ? line.li : null,
          segmentIndex,
          feederId: feeder.feederId,
          lateralId: kind === "lateral" ? line.lateralId : null,
          subId: feeder.subId,
          start,
          end,
          midpoint: [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
          lengthKm,
          localWindMph: null,
          localRainIn: null,
          customerExposure: null,
          relativeCustomerExposure: null,
          localWeatherSeverity: null,
          rawImpact: null,
          smoothedImpact: null,
          susceptibility,
          weight: lengthKm * susceptibility,
        });
      }
    }
    for (const feeder of normalized.feeders) addLine("feeder", feeder, feeder, feeder.coordinates, feederSusceptibility);
    for (const lateral of normalized.laterals) addLine("lateral", lateral, lateral.feeder, lateral.coordinates, lateralSusceptibility);
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

  function sampleOutageScenario(weightedSegments, configInput = {}, inputs = {}, boundary = null) {
    const config = validateConfig(configInput);
    if (!Array.isArray(weightedSegments) || weightedSegments.length < config.nOutages) {
      throw new InputValidationError(`only ${weightedSegments?.length || 0} positive-weight network segments are available for ${config.nOutages} unique outages`);
    }
    const totalWeight = weightedSegments.reduce((sum, segment) => sum + finiteNumber(segment.weight, "segment.weight"), 0);
    if (totalWeight <= 0) throw new InputValidationError("network sampling weight must be positive");
    const boundaryRings = boundary ? extractBoundaryRings(boundary) : null;
    const random = mulberry32(config.seed);
    const selected = weightedSegments.map((segment, index) => ({
      key: Math.log(Math.max(random(), Number.MIN_VALUE)) / segment.weight,
      index,
    })).sort((a, b) => b.key - a.key || b.index - a.index).slice(0, config.nOutages);
    const outages = selected.map(({ index }) => {
      const segment = weightedSegments[index];
      let position=random(),lon,lat,inside=!boundaryRings;
      for (let attempt=0;attempt<32;attempt++){
        lon=segment.start[0]+(segment.end[0]-segment.start[0])*position;
        lat=segment.start[1]+(segment.end[1]-segment.start[1])*position;
        inside=!boundaryRings||pointInBoundary(boundaryRings,lat,lon);
        if (inside) break;
        position=random();
      }
      if (!inside){
        for (const fallback of [0.5,0,1,0.25,0.75]){
          lon=segment.start[0]+(segment.end[0]-segment.start[0])*fallback;
          lat=segment.start[1]+(segment.end[1]-segment.start[1])*fallback;
          if (pointInBoundary(boundaryRings,lat,lon)){inside=true;break;}
        }
      }
      if (!inside){
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
        popLoss: config.customersPerOutage,
        customers: config.customersPerOutage,
        critical: false,
        priority: 0,
        tree_blocked: -1,
        networkSegmentId: segment.segmentId,
        networkKind: segment.networkKind,
        lateralId: segment.lateralId,
        localWindMph: segment.localWindMph,
        localRainIn: segment.localRainIn,
        customerExposure: segment.customerExposure,
        relativeCustomerExposure: segment.relativeCustomerExposure,
        localWeatherSeverity: segment.localWeatherSeverity,
        rawImpact: segment.rawImpact,
        smoothedImpact: segment.smoothedImpact,
        segmentLengthKm: segment.lengthKm,
        susceptibility: segment.susceptibility,
        samplingWeight: segment.weight / totalWeight,
      };
    });
    return {
      schemaVersion: SCHEMA_VERSION,
      schema: "connecticut_outage_scenario_v1",
      scenarioId: `${config.stormId}_seed${config.seed}`,
      config,
      inputs: { ...inputs },
      outages,
      totalCustomers: outages.length * config.customersPerOutage,
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
      input.boundary, input.censusTracts, weather.latitudes, weather.longitudes,
      { smoothingKm: config.customerSmoothingKm, ruralBaselineFraction: config.ruralBaselineFraction },
    );
    const weatherSurface = buildWeatherSeveritySurface(input.weather, customerSurface.connecticutMask, config);
    const impactSurface = buildCombinedImpactSurface(customerSurface, weatherSurface, config);
    const weightedSegments = buildWeightedNetworkSegments(input.network, customerSurface, weatherSurface, impactSurface, config);
    const scenario = sampleOutageScenario(weightedSegments, config, input.inputs || {}, input.boundary);
    const feederOutages = scenario.outages.filter((outage) => outage.is_feeder === 1).length;
    return {
      ...scenario,
      surfaces: { customer: customerSurface, weather: weatherSurface, impact: impactSurface },
      summary: {
        candidateSegments: weightedSegments.length,
        feederCandidateSegments: weightedSegments.filter((segment) => segment.networkKind === "feeder").length,
        lateralCandidateSegments: weightedSegments.filter((segment) => segment.networkKind === "lateral").length,
        sampledOutages: scenario.outages.length,
        uniqueSampledSegments: new Set(scenario.outages.map((outage) => outage.networkSegmentId)).size,
        feederOutages,
        lateralOutages: scenario.outages.length - feederOutages,
        representedCustomers: scenario.totalCustomers,
        totalSegmentWeight: weightedSegments.reduce((sum, segment) => sum + segment.weight, 0),
      },
    };
  }

  return Object.freeze({
    SCHEMA_VERSION,
    POPULATION_TO_CUSTOMER_RATIO,
    DEFAULT_CONFIG,
    InputValidationError,
    validateConfig,
    extractBoundaryRings,
    pointInBoundary,
    buildConnecticutMask,
    rasterizeCustomerAccounts,
    boundaryAwareGaussianSmooth,
    buildCustomerExposureSurface,
    weatherSeverityScore,
    normalizeWeather,
    buildWeatherSeveritySurface,
    buildCombinedImpactSurface,
    haversineKm,
    bilinearGridValue,
    normalizeNetwork,
    buildWeightedNetworkSegments,
    buildBasicNetworkSegments,
    mulberry32,
    sampleOutageScenario,
    generateOutageScenario,
  });
});
