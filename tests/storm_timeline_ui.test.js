"use strict";

/*
 * Author: Alex Luo (@alexl1239) -- original design and implementation,
 *   feature/outage-location-simulator.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const html = fs.readFileSync(
  path.resolve(__dirname, "..", "03_grid_simulation.html"),
  "utf8",
);

test("existing simulation page loads the curated timeline and exposes compact playback controls", () => {
  assert.match(html, /data\/connecticut_storm_timelines\.js/);
  assert.doesNotMatch(html, /<script src="\.\/data\/connecticut_storm_wind\.js"><\/script>/);
  assert.match(html, /id="stormPlayback"/);
  assert.match(html, /id="timelinePlayPause"/);
  assert.match(html, /id="timelineSlider"/);
  assert.match(html, /id="timelineTimestamp"/);
  assert.doesNotMatch(html, /type="date"[^>]*storm/i);
});

test("restoration handoff uses the complete accumulated timeline and reports zero remaining customers", () => {
  assert.match(html, /id="restorationHandoffNote"/);
  assert.match(html, /id="restorationContractSummary"/);
  assert.match(html, /function prepareTimelineForRestoration\(\)/);
  assert.match(html, /setTimelineFrame\(frames\.length-1\)/);
  assert.match(html, /const N=storm\.outages\.length/);
  assert.match(html, /remainingCustomers!==0/);
  assert.match(html, /starts after storm passage/);
});

test("research UI sends the curated timeline to the existing Worker", () => {
  assert.match(html, /mode:'timeline'/);
  assert.match(html, /weatherTimeline:\{/);
  assert.match(html, /CONNECTICUT_STORM_TIMELINES/);
  assert.match(html, /outage_location_worker\.js\?v=4/);
  assert.match(html, /outage_location_model\.js\?v=4/);
  assert.match(html, /id="modelRiskObjective"/);
  assert.match(html, /value="failure_oriented"/);
  assert.match(html, /candidateSegmentLengthKm:'modelCandidateLength'/);
  assert.match(html, /lineIntegrationStepKm:'modelIntegrationStep'/);
  assert.doesNotMatch(
    html,
    /CONNECTICUT_CENSUS_TRACTS\s*=\s*window\.CONNECTICUT_CENSUS_TRACTS\.map/,
  );
  assert.doesNotMatch(
    html,
    /CONNECTICUT_TOWNS_POPULATION\s*\|\|\s*\[\]\)\.map\(t\s*=>\s*\(\{\.\.\.t,\s*pop:\s*t\.pop\s*\*\s*POP_TO_CUSTOMER_RATIO/,
  );
  assert.match(html, /TOTAL_POPULATION_PERSONS/);
  assert.match(html, /ESTIMATED_STATEWIDE_CUSTOMER_ACCOUNTS/);
});

test("model tuning tab exposes sensitivity controls with delayed, accessible explanations", () => {
  assert.match(html, /id="outageModelAdvanced"/);
  assert.match(html, /<summary>Model tuning<\/summary>/);
  assert.match(html, /const MODEL_CONTROL_HELP = Object\.freeze/);
  assert.match(html, /function installModelTuningHelp\(\)/);
  assert.match(html, /installModelTuningHelp\(\)/);
  assert.match(html, /transition:opacity \.12s ease \.45s/);
  assert.match(html, /control\.setAttribute\('aria-description',help\)/);
  assert.match(html, /label\.tabIndex=0/);
  for (const id of [
    "modelWindThreshold",
    "modelWindScale",
    "modelWindExponent",
    "modelRainCoefficient",
    "modelRainCap",
    "modelExposureExponent",
    "modelCustomerSmoothing",
    "modelRuralBaseline",
    "modelGaussianBandwidth",
    "modelCandidateLength",
    "modelIntegrationStep",
    "modelFeederSusceptibility",
    "modelLateralSusceptibility",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
    assert.match(html, new RegExp(`${id}:\\s*`));
  }
  assert.match(
    html,
    /changing only this global scale does not change placement probabilities/,
  );
  assert.match(html, /the neutral paper default is one/);
});

test("map playback offers model-aligned weather and impact surfaces", () => {
  for (const value of [
    "windGustMph", "rain1hIn", "rain6hIn", "weatherSeverity", "rawImpact", "smoothedImpact",
  ]) {
    assert.match(html, new RegExp(`<option value="${value}">`));
  }
  assert.match(html, /Weather \/ impact overlay/);
  assert.match(html, /outage\.stormFrameIndex<=currentTimelineFrameIndex/);
});
