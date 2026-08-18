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

test("reviewed storms populate dynamically and December 2022 uses its observed event preset", () => {
  assert.match(html, /for \(const \[id,data\] of Object\.entries\(weather\)\)/);
  assert.match(html, /selectedWeatherStorm\?\.name\|\|'storm'/);
  assert.doesNotMatch(html, /hourly Isaias frames/);
  assert.match(
    html,
    /dec2022:\s+\{outages: 3899,\s+crews: 1100, realH: 88,\s+label: "Dec 2022 Windstorm"\}/,
  );
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
  assert.match(html, /const anchoredLateralPts=bd>1e-16/);
  assert.match(html, /pts:anchoredLateralPts/);
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

test("customer-size validation plots National Grid target against the current simulation", () => {
  assert.match(html, /id="modelSizeComparisonChart"/);
  assert.match(html, /Share of outage jobs by customer count/);
  assert.match(html, /National Grid target/);
  assert.match(html, /Current simulation/);
  assert.match(html, /function renderOutageSizeComparisonChart\(comparison\)/);
  assert.match(html, /target:bin\.jobShare/);
  assert.match(html, /simulated:bin\.simulatedJobShare/);
  assert.match(html, /comparison\.overflow\.jobShare/);
  assert.match(html, /renderOutageSizeComparisonChart\(comparison\)/);
  assert.match(html, /role="img" aria-labelledby="\$\{idPrefix\}Title \$\{idPrefix\}Description"/);
  assert.match(html, /Paired vertical bars compare target and simulated job shares/);
  assert.match(html, /transform="rotate\(52/);
  assert.match(html, /Share of jobs/);
  assert.match(html, /Customers affected by the job/);
});

test("customer-size charts open together in a full-screen accessible review", () => {
  assert.match(html, /customer_size_quantile_references\.js/);
  assert.match(html, /id="viewCustomerSizeCharts"[^>]*disabled>View charts/);
  assert.match(html, /id="customerSizeChartsOverlay"[^>]*aria-hidden="true"/);
  assert.match(html, /role="dialog" aria-modal="true"/);
  assert.match(html, /id="fullSizeBinChart"/);
  assert.match(html, /id="fullSizeQuantileChart"/);
  assert.match(html, /function customerSizeQuantileSvg\(result,idPrefix\)/);
  assert.match(html, /interpolatedCustomerQuantile\(sortedCustomers,percentile\)/);
  assert.match(html, /Customers affected per job \(log scale\)/);
  assert.match(html, /const percentiles=national\.map\(point=>point\.percentile\)/);
  assert.match(html, /Both series are evaluated at the same eight percentile checkpoints/);
  assert.doesNotMatch(html, /Four-major-event range/);
  assert.doesNotMatch(html, /Range across Dave's four major events/);
  assert.match(html, /function openCustomerSizeCharts\(\)/);
  assert.match(html, /function closeCustomerSizeCharts\(\)/);
  assert.match(html, /event\.key==='Escape'/);
  assert.match(html, /currentCustomerSizeChartResult=result/);
  assert.match(html, /viewCustomerSizeCharts'\)\.disabled=false/);
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

test("the map starts with a clean review view and only grid lines enabled", () => {
  assert.match(html, /towns:false,territories:false,gridLines:true,substations:false/);
  assert.match(html, /criticalFacilities:false,stormTrack:false/);
  assert.match(html, /data-map-layer="gridLines" checked/);
  for (const layer of ["substations", "territories", "towns", "criticalFacilities", "stormTrack"]) {
    assert.match(html, new RegExp(`data-map-layer="${layer}">`));
  }
  assert.doesNotMatch(html, /id="showCriticalFacilities" checked/);
  assert.doesNotMatch(html, /id="showStormTrack" checked/);
});

test("simulated outage markers distinguish service, lateral, and feeder without priority rings", () => {
  assert.match(html, /id='outageTypeLegend'/);
  assert.match(html, /Simulated outage type/);
  assert.match(html, /Service \/ small customer group/);
  assert.match(html, /Lateral branch/);
  assert.match(html, /Feeder \/ backbone/);
  assert.match(html, /componentPoints=\{service:\[\],lateral:\[\],feeder:\[\]\}/);
  assert.match(html, /outage\.componentClass/);
  assert.match(html, /componentPoints\.service[\s\S]*marker:'x',radius:2\.0/);
  assert.match(html, /componentPoints\.lateral[\s\S]*marker:'x',radius:2\.8/);
  assert.match(html, /componentPoints\.feeder[\s\S]*marker:'x',radius:4\.1/);
  assert.doesNotMatch(html, /Yellow rings mark outages/);
  assert.doesNotMatch(html, /outage-symbol critical/);
  assert.doesNotMatch(html, /marker:'ring'/);
  assert.doesNotMatch(html, /_criticalCloud/);
  assert.match(html, /window\._outageLegendMode='simulated'/);
  assert.match(html, /L\.control\(\{position:'bottomright'\}\)/);
  assert.match(html, /aria-label="Hide outage type key"/);
  assert.doesNotMatch(html, /data-map-layer="outageLegend"/);
});

test("batched outage markers support fast hover and pinned click details", () => {
  assert.match(html, /const OUTAGE_INSPECTION_CELL_DEG=0\.01/);
  assert.match(html, /function rebuildOutageInspectionIndex\(outages\)/);
  assert.match(html, /function nearestInspectableOutage\(latlng,radiusPx\)/);
  assert.match(html, /requestAnimationFrame\(\(\)=>/);
  assert.match(html, /map\.on\('mousemove'/);
  assert.match(html, /map\.on\('click'/);
  assert.match(html, /model-estimated \$\{customerLabel\} affected/);
  assert.match(html, /outageInspectionComponentLabel\(outage\.componentClass\)/);
  assert.match(html, /formatTimelineTimestamp\(outage\.occurredAt\)/);
  assert.match(html, /Click to keep these details open/);
  assert.match(html, /rebuildOutageInspectionIndex\(outages\)/);
  assert.doesNotMatch(html, /for \(const outage of outages\)[\s\S]{0,300}L\.marker\(\[outage\.lat/);
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
