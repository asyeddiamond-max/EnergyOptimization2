"use strict";

/*
 * Author: Alex Luo (@alexl1239) -- original design and implementation,
 *   feature/outage-location-simulator.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");

function loadTimelineData() {
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, "data", "connecticut_storm_timelines.js"), "utf8"),
    context,
  );
  return context.window.CONNECTICUT_STORM_TIMELINES;
}

test("curated Isaias timeline has a complete hourly Connecticut weather cube", () => {
  const data = loadTimelineData();
  const storm = data.storms.isaias_2020;
  const cellCount = data.grid.n_lat * data.grid.n_lon;

  assert.equal(data.schema_version, 1);
  assert.equal(storm.storm_id, "isaias_2020");
  assert.equal(data.grid.n_lat, 41);
  assert.equal(data.grid.n_lon, 65);
  assert.equal(storm.start_time, "2020-08-04T06:00:00Z");
  assert.equal(storm.end_time, "2020-08-05T05:00:00Z");
  assert.equal(storm.interval_minutes, 60);
  assert.equal(storm.antecedent_rain_hours, 6);
  assert.equal(storm.frames.length, 24);

  storm.frames.forEach((frame, index) => {
    assert.equal(frame.wind_gust_mph.length, cellCount);
    assert.equal(frame.rain_1h_in.length, cellCount);
    assert.equal(frame.rain_6h_in.length, cellCount);
    assert.ok(frame.wind_gust_mph.every(Number.isFinite));
    assert.ok(frame.rain_1h_in.every((value) => Number.isFinite(value) && value >= 0));
    assert.ok(frame.rain_6h_in.every((value) => Number.isFinite(value) && value >= 0));
    if (index > 0) {
      const previous = Date.parse(storm.frames[index - 1].valid_time);
      assert.equal(Date.parse(frame.valid_time) - previous, 60 * 60 * 1000);
    }
  });
});

test("six-hour rain agrees with the aligned hourly fields after the pre-window period", () => {
  const { storms } = loadTimelineData();
  const frames = storms.isaias_2020.frames;
  for (let frameIndex = 5; frameIndex < frames.length; frameIndex += 1) {
    for (let cell = 0; cell < frames[frameIndex].rain_6h_in.length; cell += 1) {
      let expected = 0;
      for (let offset = 0; offset < 6; offset += 1) {
        expected += frames[frameIndex - offset].rain_1h_in[cell];
      }
      assert.ok(Math.abs(frames[frameIndex].rain_6h_in[cell] - expected) <= 0.004);
    }
  }
});

test("Isaias frames contain a moving, damaging wind footprint rather than a repeated snapshot", () => {
  const frames = loadTimelineData().storms.isaias_2020.frames;
  const byTime = Object.fromEntries(frames.map((frame) => [frame.valid_time, frame.summary]));

  assert.ok(byTime["2020-08-04T06:00:00Z"].max_wind_mph < 20);
  assert.ok(byTime["2020-08-04T19:00:00Z"].max_wind_mph >= 60);
  assert.ok(byTime["2020-08-05T05:00:00Z"].max_wind_mph < 30);
  assert.ok(
    byTime["2020-08-04T21:00:00Z"].max_wind_lon
      > byTime["2020-08-04T17:00:00Z"].max_wind_lon + 1,
  );
  assert.notDeepEqual(frames[0].wind_gust_mph, frames[13].wind_gust_mph);
});
