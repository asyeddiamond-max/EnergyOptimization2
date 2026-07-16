"use strict";

function neighborInside(model, boundary, latitude, longitude, directionOffset) {
  const directions = [
    [1, 0], [0, 1], [-1, 0], [0, -1],
    [1, 1], [-1, 1], [-1, -1], [1, -1],
  ];
  for (const delta of [0.001, 0.0005, 0.0002, 0.0001]) {
    for (let index = 0; index < directions.length; index += 1) {
      const direction = directions[(index + directionOffset) % directions.length];
      const candidate = [
        longitude + direction[0] * delta,
        latitude + direction[1] * delta,
      ];
      if (model.pointInBoundary(boundary, candidate[1], candidate[0])) return candidate;
    }
  }
  throw new Error(`could not construct an in-boundary test segment near ${latitude},${longitude}`);
}

function buildReviewNetwork(model, boundary, weatherGrid) {
  const centers = [];
  for (const latitude of weatherGrid.lats) {
    for (const longitude of weatherGrid.lons) {
      if (model.pointInBoundary(boundary, latitude, longitude)) centers.push([longitude, latitude]);
    }
  }
  if (centers.length < 1000) throw new Error("expected at least 1,000 in-state weather-grid centers");

  const substations = centers.slice(0, 16).map(([lon, lat], subId) => ({
    sub_id: subId,
    name: `Test substation ${subId}`,
    lat,
    lon,
  }));
  const feeders = [];
  const laterals = [];
  centers.forEach(([lon, lat], index) => {
    const center = [lon, lat];
    feeders.push({
      feeder_id: index,
      sub_id: index % substations.length,
      coordinates: [center, neighborInside(model, boundary, lat, lon, 0)],
    });
    laterals.push({
      lateral_id: index,
      feeder_id: index,
      coordinates: [center, neighborInside(model, boundary, lat, lon, 1)],
    });
  });
  return { substations, feeders, laterals };
}

function expandLine(coordinates, segmentCount) {
  const [start, end] = coordinates;
  return Array.from({ length: segmentCount + 1 }, (_, index) =>
    (index % 2 === 0 ? [...start] : [...end]));
}

function buildPerformanceNetwork(model, boundary, weatherGrid, segmentCount = 40) {
  const network = buildReviewNetwork(model, boundary, weatherGrid);
  return {
    substations: network.substations,
    feeders: network.feeders.map((feeder) => ({
      ...feeder,
      coordinates: expandLine(feeder.coordinates, segmentCount),
    })),
    laterals: network.laterals.map((lateral) => ({
      ...lateral,
      coordinates: expandLine(lateral.coordinates, segmentCount),
    })),
  };
}

module.exports = { buildReviewNetwork, buildPerformanceNetwork };
