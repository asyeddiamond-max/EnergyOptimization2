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
  assert.ok(data.grid.lats.every((value, index, values) =>
    Number.isFinite(value) && (index === 0 || value > values[index - 1])));
  assert.ok(data.grid.lons.every((value, index, values) =>
    Number.isFinite(value) && (index === 0 || value > values[index - 1])));

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

test("curated December 2022 timeline follows the same reviewed hourly weather contract", () => {
  const data = loadTimelineData();
  const storm = data.storms.dec2022;
  const cellCount = data.grid.n_lat * data.grid.n_lon;

  assert.ok(Object.keys(data.storms).includes("isaias_2020"));
  assert.ok(Object.keys(data.storms).includes("dec2022"));
  assert.equal(storm.storm_id, "dec2022");
  assert.equal(storm.start_time, "2022-12-22T18:00:00Z");
  assert.equal(storm.end_time, "2022-12-24T11:00:00Z");
  assert.equal(storm.interval_minutes, 60);
  assert.equal(storm.antecedent_rain_hours, 6);
  assert.equal(storm.frames.length, 42);
  assert.deepEqual(JSON.parse(JSON.stringify(storm.observed_reference)), {
    event_id: "2022122218",
    source: "Eversource OPM event curves supplied by Dr. Dave Wanik",
    n_jobs: 3899,
    sum_customer_job_impacts: 207731,
    peak_customers_out: 188737,
    peak_open_jobs: 3034,
    curve_start: "2022-12-23T00:00:00",
    curve_end: "2022-12-26T16:00:00",
  });

  storm.frames.forEach((frame, index) => {
    assert.equal(frame.wind_gust_mph.length, cellCount);
    assert.equal(frame.rain_1h_in.length, cellCount);
    assert.equal(frame.rain_6h_in.length, cellCount);
    assert.ok(frame.wind_gust_mph.every(Number.isFinite));
    assert.ok(frame.rain_1h_in.every((value) => Number.isFinite(value) && value >= 0));
    assert.ok(frame.rain_6h_in.every((value) => Number.isFinite(value) && value >= 0));
    if (index > 0) {
      assert.equal(
        Date.parse(frame.valid_time) - Date.parse(storm.frames[index - 1].valid_time),
        60 * 60 * 1000,
      );
    }
  });
});

test("first visible frame contains real antecedent rain rather than zero padding", () => {
  const first = loadTimelineData().storms.isaias_2020.frames[0];
  const preWindowContributionCells = first.rain_6h_in.reduce(
    (count, value, index) => count + (value > first.rain_1h_in[index] + 0.004 ? 1 : 0),
    0,
  );
  assert.ok(preWindowContributionCells > 0);
  const generator = fs.readFileSync(path.join(ROOT, "12_fetch_hrrr_storm_wind.py"), "utf8");
  assert.match(generator, /Actual HRRR f01 APCP fields are fetched/);
  assert.match(generator, /not zero-padded/);
});

test("six-hour rain agrees with aligned hourly fields for every reviewed storm", () => {
  const { storms } = loadTimelineData();
  for (const storm of Object.values(storms)) {
    const { frames } = storm;
    for (let frameIndex = 5; frameIndex < frames.length; frameIndex += 1) {
      for (let cell = 0; cell < frames[frameIndex].rain_6h_in.length; cell += 1) {
        let expected = 0;
        for (let offset = 0; offset < 6; offset += 1) {
          expected += frames[frameIndex - offset].rain_1h_in[cell];
        }
        assert.ok(Math.abs(frames[frameIndex].rain_6h_in[cell] - expected) <= 0.004);
      }
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

test("December 2022 captures approach, damaging passage, heavy rain, and departure", () => {
  const frames = loadTimelineData().storms.dec2022.frames;
  const peak = frames.reduce((highest, frame) =>
    frame.summary.max_wind_mph > highest.summary.max_wind_mph ? frame : highest);

  assert.equal(peak.valid_time, "2022-12-23T11:00:00Z");
  assert.ok(peak.summary.max_wind_mph >= 70 && peak.summary.max_wind_mph <= 80);
  assert.ok(Math.max(...frames.map((frame) => frame.summary.max_rain_6h_in)) >= 2);
  assert.ok(frames[0].summary.max_wind_mph < 30);
  assert.ok(frames.at(-1).summary.max_wind_mph < 40);
  assert.notDeepEqual(frames[0].wind_gust_mph, peak.wind_gust_mph);
});

test("timeline generator preserves reviewed storms and supports reproducible all-storm builds", () => {
  const generator = fs.readFileSync(path.join(ROOT, "12_fetch_hrrr_storm_wind.py"), "utf8");
  assert.match(generator, /def _read_existing_timeline_data\(\):/);
  assert.match(generator, /choices=\["all", \*sorted\(CURATED_TIMELINES\)\]/);
  assert.match(generator, /if key not in CURATED_TIMELINES/);
  assert.match(generator, /\*\*external_storms/);
});
