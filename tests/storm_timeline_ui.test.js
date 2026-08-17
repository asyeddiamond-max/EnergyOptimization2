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
  assert.match(html, /data\/connecticut_census_population_grid\.js/);
  assert.match(html, /populationGrid:window\.CONNECTICUT_CENSUS_POPULATION_GRID/);
  assert.doesNotMatch(html, /script src="\.\/data\/connecticut_census_blocks/);
  assert.match(html, /outage_location_worker\.js\?v=7/);
  assert.match(html, /outage_location_model\.js\?v=9/);
  assert.match(html, /id="modelRiskObjective"/);
  assert.match(html, /value="failure_oriented"/);
  assert.match(html, /candidateSegmentLengthKm:'modelCandidateLength'/);
  assert.match(html, /lineIntegrationStepKm:'modelIntegrationStep'/);
  assert.doesNotMatch(
    html,
    /CONNECTICUT_CENSUS_BLOCKS\s*=\s*window\.CONNECTICUT_CENSUS_BLOCKS\.map/,
  );
  assert.doesNotMatch(
    html,
    /CONNECTICUT_TOWNS_POPULATION\s*\|\|\s*\[\]\)\.map\(t\s*=>\s*\(\{\.\.\.t,\s*pop:\s*t\.pop\s*\*\s*POP_TO_CUSTOMER_RATIO/,
  );
  assert.match(html, /TOTAL_POPULATION_PERSONS/);
  assert.match(html, /ESTIMATED_STATEWIDE_CUSTOMER_ACCOUNTS/);
  assert.match(html, /feederAnchorVertexIndex=1\+Math\.floor/);
  assert.match(html, /feeder_anchor_vertex_index:lateral\.feederAnchorVertexIndex/);
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
    "modelServiceFailureWeight",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
    assert.match(html, new RegExp(`${id}:\\s*`));
  }
  assert.match(
    html,
    /changing only this global scale does not change placement probabilities/,
  );
  assert.match(html, /paper default was fitted to the regulatory job-size bins/);
});

test("generated-scenario UI reports DPU size-bin error and keeps PCAO outside calibration", () => {
  for (const id of [
    "modelSizeValidation",
    "modelSizeTv",
    "modelSizeMean",
    "modelSizeMedian",
    "modelSizeTopOne",
    "modelSizeValidationBins",
    "modelPcaoIndependent",
    "modelPcaoValue",
    "modelPcaoFormula",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /function renderOutageSizeValidation\(result\)/);
  assert.match(html, /result\?\.dpu31Comparison/);
  assert.match(html, /Formal acceptance still uses held-out seeds/);
  assert.match(html, /PCAO\* —/);
  assert.match(html, /Current-workflow demonstration only/);
  assert.match(html, /not comparable with the historical ≈37 value/);
  assert.match(html, /never used for calibration/);
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

test("simulated outage markers distinguish service, lateral, feeder, and critical-facility status", () => {
  assert.match(html, /id='outageTypeLegend'/);
  assert.match(html, /Simulated outage type/);
  assert.match(html, /Service \/ small customer group/);
  assert.match(html, /Lateral branch/);
  assert.match(html, /Feeder \/ backbone/);
  assert.match(html, /Near a critical facility/);
  assert.match(html, /componentPoints=\{service:\[\],lateral:\[\],feeder:\[\]\}/);
  assert.match(html, /outage\.componentClass/);
  assert.match(html, /componentPoints\.service[\s\S]*marker:'x',radius:2\.0/);
  assert.match(html, /componentPoints\.lateral[\s\S]*marker:'x',radius:2\.8/);
  assert.match(html, /componentPoints\.feeder[\s\S]*marker:'x',radius:4\.1/);
  assert.match(html, /marker:'ring'/);
  assert.match(html, /Facility-location dots:/);
  assert.match(html, /window\._outageLegendMode='simulated'/);
  assert.match(html, /L\.control\(\{position:'bottomright'\}\)/);
  assert.match(html, /aria-label="Hide outage type key"/);
  assert.doesNotMatch(html, /data-map-layer="outageLegend"/);
});

test("critical-facility visibility is explained separately from placement and size calibration", () => {
  assert.match(html, /id="showCriticalFacilities"/);
  assert.match(html, /This checkbox only changes the map display/);
  assert.match(html, /criticalFacilities:window\.CONNECTICUT_CRITICAL_FACILITIES\|\|\[\]/);
});

test("outage-location control is exact by number and logarithmic by slider", () => {
  assert.match(html, /id="oCountInput"[^>]*value="2000"/);
  assert.match(html, /id="oSlider" min="0" max="1000"/);
  assert.match(html, /function outageSliderPosition\(count\)/);
  assert.match(html, /function outageCountAtSliderPosition\(position\)/);
  assert.match(html, /Math\.pow\(OUTAGE_COUNT_MAX\/OUTAGE_COUNT_MIN,fraction\)/);
  assert.match(html, /nOutages:requestedOutageCount\(\)/);
  assert.match(html, /Customers affected is calculated from the network/);
  assert.match(html, /\$\{outages\.length\.toLocaleString\(\)\} locations/);
  assert.doesNotMatch(html, /nOutages:Number\(oS\.value\)/);
});

test("a size-distribution miss is presented as a calibration warning, not a runtime failure", () => {
  assert.match(html, /size-validation-status\.warn/);
  assert.match(html, /Calibration warning: the simulation ran/);
  assert.match(html, /This does not block the demo/);
  assert.match(html, /this scenario's customer sizes are outside the validation limits/);
});
