// 30_reconstruct_july4_timeline.js
// Adds a RECONSTRUCTED hourly timeline for the July 4, 2026 CT severe-thunderstorm complex to
// data/connecticut_storm_timelines.js as "ct_july2026_severe_tstorm" (the id used by the storm
// track + calibration preset), so it becomes selectable in 03_grid_simulation.html's weather model.
//
// It is a RECONSTRUCTION, not archived hourly HRRR:
//   - envelope  = the real HRRR peak-gust field for july2026 (data/connecticut_storm_wind.js)
//                 x 1.7 convective gust factor (reconciles the ~40 mph sustained grid with the
//                 SPC-measured 58-65 kt / 67-75 mph gusts; peak ~68 mph, localized NW->central).
//   - evolution = a NW->SE squall-line sweep over the storm evening (front moves W->E), timed to
//                 the NOAA SPC report cluster (damage ~7-10 pm ET). Each cell reaches its real peak
//                 as the front passes its longitude, so the peak field is conserved as the envelope.
//   - rain      = the light real peak-rain field (July 4 was wind/convective-driven, not rain).
// Idempotent: aborts if the entry already exists. Run from the repo root:  node 30_reconstruct_july4_timeline.js
const fs = require("fs"), path = require("path");
const DIR = __dirname;

global.window = {}; require(path.join(DIR, "data", "connecticut_storm_wind.js")); const W = global.window.CONNECTICUT_STORM_WIND;
global.window = {}; require(path.join(DIR, "data", "connecticut_storm_timelines.js")); const T = global.window.CONNECTICUT_STORM_TIMELINES;

const grid = T.grid, LATS = grid.lats, LONS = grid.lons, NLAT = LATS.length, NLON = LONS.length, NCELL = NLAT * NLON;
const jw = W.storms.july2026, PW = jw.peak_wind_mph, PR = jw.peak_rain_in;   // [NLAT][NLON]
const GUST = 1.7, AMBIENT = 0.22, LON_SIGMA = 0.55, RAIN_FR = 0.6;

const times = ["2026-07-04T22:00:00Z","2026-07-04T23:00:00Z","2026-07-05T00:00:00Z","2026-07-05T01:00:00Z",
               "2026-07-05T02:00:00Z","2026-07-05T03:00:00Z","2026-07-05T04:00:00Z","2026-07-05T05:00:00Z"];
const NF = times.length;
const frontLon = i => -74.1 + (i / (NF - 1)) * (-71.5 - (-74.1));   // W -> E across CT over the evening
const r1 = x => Math.round(x * 10) / 10, r3 = x => Math.round(x * 1000) / 1000;

const rainHist = [], frames = [];
for (let f = 0; f < NF; f++) {
  const fl = frontLon(f);
  const gust = new Array(NCELL), rain1 = new Array(NCELL), rain6 = new Array(NCELL);
  for (let r = 0; r < NLAT; r++) for (let c = 0; c < NLON; c++) {
    const idx = r * NLON + c;
    const w = Math.exp(-0.5 * Math.pow((LONS[c] - fl) / LON_SIGMA, 2));   // front proximity 0..1
    gust[idx] = r1(PW[r][c] * GUST * (AMBIENT + (1 - AMBIENT) * w));
    rain1[idx] = r3(PR[r][c] * w * RAIN_FR);
  }
  rainHist.push(rain1);
  for (let i = 0; i < NCELL; i++) { let s = 0; for (let k = Math.max(0, f - 5); k <= f; k++) s += rainHist[k][i]; rain6[i] = r3(s); }
  let sw = 0, mw = 0, mwi = 0, sr1 = 0, mr1 = 0, sr6 = 0, mr6 = 0;
  for (let i = 0; i < NCELL; i++) { sw += gust[i]; if (gust[i] > mw) { mw = gust[i]; mwi = i; } sr1 += rain1[i]; if (rain1[i] > mr1) mr1 = rain1[i]; sr6 += rain6[i]; if (rain6[i] > mr6) mr6 = rain6[i]; }
  frames.push({ valid_time: times[f], wind_gust_mph: gust, rain_1h_in: rain1, rain_6h_in: rain6,
    summary: { mean_wind_mph: r1(sw / NCELL), max_wind_mph: r1(mw), max_wind_lat: LATS[Math.floor(mwi / NLON)], max_wind_lon: LONS[mwi % NLON],
      mean_rain_1h_in: r3(sr1 / NCELL), max_rain_1h_in: r3(mr1), mean_rain_6h_in: r3(sr6 / NCELL), max_rain_6h_in: r3(mr6) } });
}

const storm = {
  storm_id: "ct_july2026_severe_tstorm", name: "July 4, 2026 Severe Thunderstorms",
  source: "RECONSTRUCTED (not archived hourly HRRR): envelope = real HRRR peak-gust field (connecticut_storm_wind.js july2026) x1.7 convective gust factor; hourly NW->SE squall-line sweep timed to NOAA SPC reports (damage ~7-10pm ET).",
  model: "HRRR peak field x gust factor + reconstructed front passage", product: "reconstructed_hourly_gust",
  precip_type: "rain", avg_temp_f: jw.avg_temp_f, precipitation_type: "rain",
  start_time: times[0], end_time: times[NF - 1], interval_minutes: 60,
  timezone_note: "valid_time in UTC; local storm evening was Saturday July 4, 2026 ET (UTC-4).",
  rain_alignment: "reconstructed; July 4 was wind/convective-driven, rain was light", antecedent_rain_hours: 6,
  reconstructed: true, frames
};

const file = path.join(DIR, "data", "connecticut_storm_timelines.js");
let txt = fs.readFileSync(file, "utf8");
if (txt.includes('"ct_july2026_severe_tstorm"')) { console.log("ct_july2026_severe_tstorm already present -- nothing to do."); process.exit(0); }
const anchor = '"storms":{', at = txt.indexOf(anchor);
if (at < 0) { console.error("could not find storms object anchor"); process.exit(1); }
txt = txt.slice(0, at + anchor.length) + '"ct_july2026_severe_tstorm":' + JSON.stringify(storm) + ',' + txt.slice(at + anchor.length);
fs.writeFileSync(file, txt);
let gmax = 0; for (const fr of frames) { const m = Math.max(...fr.wind_gust_mph); if (m > gmax) gmax = m; }
console.log(`inserted ct_july2026_severe_tstorm (${NF} frames, peak gust ${gmax.toFixed(1)} mph) into data/connecticut_storm_timelines.js`);
