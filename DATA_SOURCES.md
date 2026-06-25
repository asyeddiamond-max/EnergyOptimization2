# Data Sources

The provenance file for every piece of real-world data the Hartford County
simulation depends on. Started when the model began incorporating real data
(commit `42a9743`, real substations); will grow as more datasets come in.

For each source: **what** it is, **where** it comes from, **how** to refresh
it, **where** it lives in the repo, and **what** it's used for. Honest notes
on coverage gaps go at the bottom of each entry.

---

## 1 · Hartford County boundary

| | |
|---|---|
| **What** | The polygon of Hartford County, Connecticut |
| **Source** | OpenStreetMap via Nominatim |
| **Endpoint** | `nominatim.openstreetmap.org/search.php?q=Hartford+County,+Connecticut&polygon_geojson=1` |
| **Fetch script** | [`01_fetch_county_boundary.py`](01_fetch_county_boundary.py) |
| **Cached file** | [`data/hartford_boundary.json`](data/hartford_boundary.json) |
| **Used by** | The interactive (county outline rendering, point-in-polygon filtering for other datasets), the artifact generator |
| **License** | © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright) |
| **Refresh** | `python 01_fetch_county_boundary.py` — only needed if OSM updates the boundary |

---

## 2 · Hartford County towns (29 municipal polygons)

| | |
|---|---|
| **What** | The 29 town polygons inside Hartford County, with names + populations |
| **Source** | OpenStreetMap via Overpass (admin_level=8) |
| **Fetch script** | [`02_fetch_town_boundaries.py`](02_fetch_town_boundaries.py) |
| **Cached files** | [`data/hartford_towns.geojson`](data/hartford_towns.geojson), [`data/hartford_towns.js`](data/hartford_towns.js) |
| **Used by** | The interactive (town overlay), demand-point weighting in the synthetic grid generator |
| **License** | © OpenStreetMap contributors, ODbL 1.0 |
| **Refresh** | `python 02_fetch_town_boundaries.py` |

---

## 3 · Hartford County substations *(real, as of commit `140931c`)*

| | |
|---|---|
| **What** | Real electric substation point locations in Hartford County — name, lat/lon, voltage (where known), city, in-service status |
| **Primary source** | **HIFLD** — Homeland Infrastructure Foundation-Level Data, *Electric Substations* layer (U.S. federal infrastructure dataset) |
| **Endpoint** | `services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/Electric_Substations/FeatureServer/0/query?where=STATE='CT' AND COUNTY='HARTFORD'` |
| **Fallback source** | OpenStreetMap (`power=substation` via Overpass), used automatically if HIFLD is unreachable |
| **Fetch script** | [`08_fetch_substations.py`](08_fetch_substations.py) |
| **Cached files** | [`data/hartford_substations.json`](data/hartford_substations.json), [`data/hartford_substations.js`](data/hartford_substations.js) |
| **Used by** | The interactive — `generateGrid()` anchors all substations at the real HIFLD locations; synthetic feeders + laterals grow from these points. Map tooltips show real name + voltage. **The grid auto-builds on page load** (commit `be09088`) so real names appear immediately without the user having to click Generate first. Also used as the territory units for the crew-stickiness toggle (each outage routes to its nearest substation; crews assigned to that substation work only that territory). |
| **Record count** | 49 substations inside the county (as of last fetch) |
| **License** | HIFLD: public domain (U.S. government work). OSM fallback: © OpenStreetMap contributors, ODbL 1.0. |
| **Refresh** | `python 08_fetch_substations.py` |

**Honest coverage notes**
- HIFLD covers transmission and sub-transmission substations well (115 kV, 345 kV). Smaller neighborhood **distribution** substations are below HIFLD's threshold and aren't in any public dataset.
- HIFLD labels a handful of substations `UNKNOWN<id>` or `Deadend<id>` when the operator name isn't public. The fetch script relabels those by city (e.g. "Farmington substation") so markers are readable while locations stay exact.
- A more complete view would require an **ISO New England** or **Eversource GIS** export (currently being pursued via the advisor). The fetch script is straightforward to repoint when that data arrives.

---

## 4 · Eversource Tropical Storm Isaias 2020 — crews-per-day baseline

| | |
|---|---|
| **What** | Documented Connecticut crew deployment ramp during the response to Tropical Storm Isaias (August 4–14, 2020). |
| **Source** | News coverage and Eversource public statements, primarily CT Mirror and NBC Connecticut |
| **Cached file** | *Not a cached JSON file yet — facts are encoded as comments / calibration anchors in the model and in this document.* |
| **Used by** | Reality-check baseline for the temporal crew model (mutual-aid waves + ramp). Sanity-checks the `crew_stickiness` partition and the line/tree split. |
| **License** | News articles, treated as primary-source reporting; cited but not redistributed. |

**Documented numbers**
- **Peak customers without power:** 632,632.
- **Damaged wire:** 500+ miles needing replacement.
- **Crews-over-time:**
  - Aug 5 (day 1 after storm passed): 504 line crews + 235 tree crews = **739 total**.
  - Aug 9 (day 5): 2,500 line crews + 780 tree crews = **3,280 total**.
  - Aug 10 (day 6): 4,500+ crews & support staff.
- **Shift length:** 18-hour days reported.
- **Total restoration window:** ~11 days (vs. 11 for Sandy 2012, 12 for Irene 2011).
- **Line-vs-tree ratio:** ~76% line / 24% tree by day 5 — confirms the simulator's default 80/20 crew-specialization split is in the right neighbourhood.

**Honest notes**
- These are news-reported numbers, not a formal dataset. Eversource's own PURA filing (CT docket `20-08-11`) would be the authoritative source — that's the calibration target listed in `ROADMAP.md`.
- The model currently treats crews as a fixed count throughout the storm. The temporal crew model in `ROADMAP.md` (Track 3, "crews as a time series") would replace that with a Wanik-style ramp curve fit to these numbers.

---

## 5 · Wanik et al. 2015 — baseline outage rates

| | |
|---|---|
| **What** | Quantitative anchors for normal-day vs. storm-day outage counts in the Eversource Connecticut service territory. |
| **Source** | Wanik, D. W. et al. (2015). *Storm outage modeling for an electric distribution network in Northeastern USA.* Natural Hazards 79(2), 1359–1384. |
| **Reachable copy** | [hartman.byu.edu/docs/files/WanikAnagnostouHartmanFredianiAstitha_StormDamage.pdf](https://hartman.byu.edu/docs/files/WanikAnagnostouHartmanFredianiAstitha_StormDamage.pdf) |
| **Used by** | Calibration anchors and sanity-check ranges in `ROADMAP.md` and the research-context document. |

**Documented numbers**
- **Normal day, low wind:** ~40 outages per day (median).
- **Major storm (Sandy 2012, Irene 2011):** >15,000 outages per event — more than an entire year's worth of normal-day outages in a single storm.
- **Storms studied:** Storm Irene 2011, Hurricane Sandy 2012, Nemo blizzard 2013.
- **Geographic scope:** Eversource's Connecticut service territory.

**Honest notes**
- This paper is about **predicting outages from weather**, *not* about crew deployment or restoration time. The advisor's mention of "the 10-year-old David Wanik paper" likely refers to this paper as the data backbone, with crew data coming from other sources (news, PURA filings). I read the PDF in full to verify.
- Future work would point `/api/calibrate` at the Wanik group's per-storm outage curves to fit our model's outage-count behaviour, alongside the news-derived crew ramp.

---

## 6 · Industry-standard parameter anchors *(as of commit `be09088`)*

These aren't fetched datasets but **real-world anchors** baked into the model
when we added the latest realism factors. Tracked here so they're attributable
when reviewers ask "where did that number come from?" and so a future calibration
pass against PURA data has a paper trail of what was hardcoded vs. what was
fit.

| Anchor | Value | Where | Source / rationale |
|---|---|---|---|
| **Hartford downtown centroid** | (41.7637, -72.6851) | Frontend `treeFactor()` | Geographic centroid of Hartford city used as fallback when NLCD canopy data is missing for a substation. Standard map lookup. |
| **NLCD tree canopy** | 8%–72% per substation | Frontend `treeFactor()` | USGS NLCD 2021 tree canopy cover (30 m). Converted to a multiplier via `canopy_pct / 50` (so 50% canopy = 1.0× baseline). Falls back to the urban/suburban/rural distance heuristic if NLCD data is missing. See Data Source §8. |
| **Vegetation trim cycle** | 4 years | Frontend `TRIM_CYCLE_YEARS` | Industry-standard distribution-feeder trim rotation. Eversource and most U.S. utilities trim primary feeders on a 4-year cycle (some 5-year for laterals). Per-feeder trim age uniformly drawn from [0, 4 yr]. |
| **Trim-age effect** | 0.6× (fresh) → 1.6× (overdue) | Frontend `trimAgeMult()` | Linear ramp on tree-blocked rate as the trim ages. Reflects the well-documented relationship between time-since-trim and outage rate (Guikema et al. 2006a, cited in Wanik 2015). Slope is heuristic; calibratable. |
| **Base tree-blocked rate** | 0.30 (30%) | Frontend storm builder | Per-outage probability before the substation × trim-age multipliers. Matches the original tree_blocked_rate default. Adjusted by the soil_saturation toggle (+30%). |
| **Soil-saturation multipliers** | road +25%, tree-blocked rate +30% | Server `schedule` endpoint | When the soil_saturation toggle is on. Heuristic; the magnitudes match qualitative findings from wet-soil tree-fall studies but should be tuned against real wet-storm event data. |
| **Pre-storm staging** | assessment_delay → 0 (from 12 h) | Server `schedule` endpoint | When the pre_storm_staging toggle is on. Models the documented Eversource practice of pre-positioning crews for forecastable events; verified to cut ~24 h off restoration at typical scales (matches the workday-clamp rollover of the 12 h assessment phase). |
| **Multi-day storm drag** | +6 h staging delay, +15% road impedance | Server `schedule` endpoint | When the storm_drag toggle is on AND the storm is "big" (storm_duration > 12 h or > 5000 outages). Joint slowdown captures crew fatigue + out-of-town unfamiliarity + resource exhaustion + triple-time-pay paradox. Calibratable as one parameter. |

**Honest notes on these anchors**
- Several of these multipliers are heuristic, not fit. The point of having them
  exposed as parameters is so the calibration framework (`/api/calibrate`) can
  tune them against real PURA event data when it arrives — at which point the
  "Source / rationale" column gets updated with the calibrated value and a
  reference to the storm used.
- The 4-year vegetation trim cycle and the urban-rural gradient idea are
  well-documented in the CT-specific literature; the *exact* multiplier values
  are the heuristic part.
- All of these reduce to two model-level knobs (`road_multiplier`,
  `assessment_delay`, plus the per-outage `tree_blocked` flag), which is why
  they compose cleanly with every other realism toggle.

---

## 7 · Critical facilities (HIFLD)

| | |
|---|---|
| **What** | Real hospitals, fire stations, EMS stations, and water treatment plants in Hartford County |
| **Source** | **HIFLD** — Homeland Infrastructure Foundation-Level Data (hospitals, fire stations, EMS stations layers) |
| **Cached file** | [`data/hartford_critical_facilities.js`](data/hartford_critical_facilities.js) |
| **Used by** | `simulateStorm()` — outages within 0.5 miles of a real facility are flagged priority-1 for restoration (replaces the previous random 2% sampling). Also rendered on the map as emoji markers (🏥🚒🚑💧) with a toggle. |
| **Record count** | 52 facilities (9 hospitals, 32 fire stations, 3 EMS, 8 water plants) |
| **License** | HIFLD: public domain (U.S. government work) |

**Honest coverage notes**
- Coordinates are approximate to the facility address, not to the exact electrical service entrance.
- Some smaller volunteer fire departments may be missing; HIFLD focuses on career/combination departments.
- The 0.5-mile proximity radius is a heuristic — real priority assignment would use the utility's customer-to-circuit mapping.

---

## 8 · NLCD tree canopy cover per substation

| | |
|---|---|
| **What** | Mean tree canopy percentage within a 1 km buffer of each HIFLD substation, from the USGS National Land Cover Database 2021 Tree Canopy Cover layer (30 m resolution, CONUS) |
| **Source** | USGS MRLC — `mrlc.gov/data/nlcd-2021-usgs-tree-canopy-cover-conus` |
| **Cached in** | Inline `NLCD_CANOPY_BY_SUBSTATION` object in `03_grid_simulation.html` |
| **Used by** | `generateGrid()` → `treeFactor()` — converts canopy % to a tree-blocked multiplier (0% → 0.15×, 50% → 1.0×, 75% → 1.5×). Replaces the previous urban/suburban/rural distance heuristic with actual measured tree cover. |
| **License** | USGS: public domain (U.S. government work) |

**Honest coverage notes**
- Values are pre-computed means, not live raster queries. A future improvement would be a fetch script that clips the NLCD GeoTIFF to each substation's Voronoi polygon for a more precise per-territory canopy fraction.
- The linear conversion (canopy_pct / 50) is a heuristic; calibratable against real storm data.

---

## 9 · Census tract population (2020 Decennial Census)

| | |
|---|---|
| **What** | Census tract centroids with 2020 population for Hartford County (~196 tracts) |
| **Source** | US Census Bureau, 2020 Decennial Census, Table P1; centroids from TIGER/Line shapefiles |
| **URL** | `data.census.gov` + `census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html` |
| **Cached file** | [`data/hartford_census_tracts.js`](data/hartford_census_tracts.js) |
| **Used by** | `buildDemandPoints()` — replaces the 29-town centroid demand model with ~196 tract centroids for ~5× finer spatial granularity in customer-count assignment. Toggle-controlled. |
| **License** | Public domain (U.S. government work) |

**Honest coverage notes**
- Centroids are geometric centroids of TIGER tract polygons, not population-weighted centroids.
- Population is total population, not households or electric customers. Electric customer count would be more precise but isn't publicly available at tract level for Eversource.

---

## 10 · NOAA HURDAT2 storm tracks

| | |
|---|---|
| **What** | Best-track positions for 4 storms that affected Hartford County: Sandy (2012), Isaias (2020), Irene (2011), Henri (2021) |
| **Source** | NOAA National Hurricane Center, HURDAT2 (Atlantic basin best track database) |
| **URL** | `nhc.noaa.gov/data/#hurdat` |
| **Cached file** | [`data/hartford_storm_tracks.js`](data/hartford_storm_tracks.js) |
| **Used by** | Storm-track overlay on the map (toggle-controlled polyline with wind-speed markers). Future: wind-exposure-weighted outage placement along the track. |
| **License** | Public domain (U.S. government work) |

**Honest coverage notes**
- Tracks are clipped to the CT/NE region (lat 39–43°N). Full tracks extend much further south.
- The wind fields are point estimates at the track center; real wind swaths extend tens of miles on each side. A proper wind-exposure model would use the asymmetric wind field (Rmax, Holland B parameter).

---

## 11 · DOE OE-417 Electric Disturbance Events

| | |
|---|---|
| **What** | Major electric disturbance events affecting Eversource/CL&P in Connecticut, with customer counts and restoration durations |
| **Source** | U.S. Department of Energy, Office of Electricity, OE-417 Annual Summary |
| **URL** | `oe.netl.doe.gov/OE417_annual_summary.aspx` |
| **Cached file** | [`data/hartford_doe_oe417.js`](data/hartford_doe_oe417.js) |
| **Used by** | Events panel in the sidebar (toggle-controlled). Calibration benchmarks in the simulation report. Future: direct comparison of simulated vs. actual restoration curves. |
| **Record count** | 8 events (2011–2024) |
| **License** | Public domain (U.S. government work) |

**Honest coverage notes**
- OE-417 reports statewide customer counts, not Hartford County alone. Hartford County is roughly 30–40% of Eversource CT's service territory.
- Duration is start-to-100% restoration; the bulk of customers are restored much earlier (typically 90% within half the total window).

---

## 12 · FEMA Flood Zone Corridors (Hartford County)

| Field | Value |
|---|---|
| **What** | Simplified centerline geometries for major flood-prone river corridors in Hartford County |
| **Source** | FEMA National Flood Hazard Layer (NFHL), simplified to 5 major corridors |
| **URL** | https://www.fema.gov/flood-maps/national-flood-hazard-layer |
| **Format** | Inline JS constant (`FLOOD_CORRIDORS`), 5 polylines with lat/lon points |
| **Corridors** | Connecticut River, Park River, Hockanum River, Farmington River, Salmon Brook |
| **Used by** | Flood-zone road-closure toggle — outages within 1.5 mi of a corridor get +35% road impedance |
| **Coverage note** | Corridors are simplified to centerlines, not full floodplain polygons. The 1.5-mile buffer is a conservative proxy for FEMA Zone A/AE extent. Smaller tributaries (e.g., Podunk River, Mattabesset River) are not included. |
| **Calibration anchor** | CT DOT road-closure records during Irene (2011) and Sandy (2012) confirm major road closures along these corridors |

---

## 13 · Equipment Shortage Model

| Field | Value |
|---|---|
| **What** | Progressive repair-time penalty during major events (5,000+ outages) |
| **Source** | Eversource Isaias 2020 after-action report; CT PURA Docket No. 20-08-03 |
| **Model** | After 60% of repairs complete, each subsequent repair takes up to 40% longer due to transformer/pole/conductor supply depletion |
| **Used by** | Equipment shortage toggle in the restoration scheduler |
| **Calibration anchor** | Eversource reported equipment staging delays in the final restoration phase of Isaias, particularly for distribution transformers which had to be sourced from regional warehouses |

---

## 14 · Customer Callback Lag Model

| Field | Value |
|---|---|
| **What** | Discovery delay for outages on rural laterals not covered by SCADA/smart meters |
| **Source** | CT PURA testimony on Eversource outage detection capabilities; industry literature on outage management systems |
| **Model** | ~15% of lateral outages in high-canopy (rural) areas get 2–8 hours of additional discovery delay |
| **Used by** | Customer callback lag toggle — adds discovery delay before crews are dispatched |
| **Coverage note** | The 15% figure is a conservative estimate. Actual callback-dependent detection varies by utility AMI (Advanced Metering Infrastructure) deployment. Eversource CT had partial AMI rollout as of 2020. |

---

## 15 · Crew Time-Series Ramp (Isaias 2020 PURA data)

| Field | Value |
|---|---|
| **What** | Logistic crew-mobilization curve calibrated to real daily crew counts from Tropical Storm Isaias |
| **Source** | CT PURA Docket No. 20-08-03; CT Mirror (2020-08-05, 2020-09-15); NBC Connecticut (2020-08-07) |
| **URLs** | https://portal.ct.gov/-/media/PURA/1-Final-Decision--PURA-Issues-Ruling-on-Utilities-Preparation-for-Response-to-Tropical-Storm-Isaias.pdf, https://ctmirror.org/2020/08/05/lamont-says-it-will-take-days-to-recover-power/ |
| **Data points** | Day 1: 504 line + 235 tree = 739 crews (~16% of peak); Day 5: 2,500 line + 780 tree = 3,280 (~73%); Peak: 4,500+ |
| **Model** | Logistic function: crews(t) = M / (1 + e^(-0.06 × (t - 72h))), where M = slider crew count |
| **Used by** | Crew time-series ramp toggle — replaces instantaneous deployment with gradual mobilization |
| **Coverage note** | Ramp is calibrated to Isaias (a major event with 632K customers affected). Smaller storms ramp faster because fewer mutual-aid crews are needed. The model applies the same ramp shape regardless of storm size — a simplification. |

---

## 16 · Crew Fatigue & Overtime Productivity Model

| Field | Value |
|---|---|
| **What** | Progressive repair-time penalty from crew fatigue during extended 16-hour shift operations |
| **Sources** | Circadian workforce studies (circadian.com/blog/excessive-overtime); SHRM Overtime Toolkit (shrm.org); IBEW Outside Construction contract provisions (ibew1245.com); powerlinemanjobs.com storm pay analysis |
| **Key findings** | 10% increase in overtime → 2.4% productivity decrease (U.S. manufacturing); accident risk triples after 16 hours continuous work; storm crews earn $5,000–$12,000/week gross at double-time ($100+/hr) on 16-hour shifts |
| **Model** | After day 2 of continuous deployment, repair times increase 5% per additional day (capped at +30% by day 8). Non-critical repairs get an additional 8% penalty after day 4, modeling the behavioral incentive where double/triple-time pay reduces urgency on non-emergency work |
| **Used by** | Crew fatigue & overtime decline toggle |
| **Behavioral note** | The overtime pay incentive is a real phenomenon discussed in utility labor economics. IBEW contracts guarantee double-time for storm hours. When a journeyman lineman earns $100+/hr on double-time 16-hour shifts, the economic incentive structure can reduce urgency on non-critical repairs. This is the "behavioral/social science" dimension the advisor flagged. |

---

## 17 · Planned / pending data sources

These are tracked in [`ROADMAP.md`](ROADMAP.md) and listed here so future-you
(or a reviewer) can see what's not yet integrated. Each one is gated on data
acquisition, not on engineering.

### ISO New England substation dataset
- **Why** the advisor specifically asked for this; expected to be more complete than HIFLD for the bulk system and may include sub-transmission detail.
- **Status** awaiting the advisor's pointer to the dataset.
- **Drop-in plan** repoint `08_fetch_substations.py` at the ISO-NE endpoint or load a provided file from `data/`.

### Real crew counts / crews-over-time
- **Why** the David Wanik ~10-year-old CT crews-over-time paper models statewide crew counts ramping over storm days, back-calculated to county. This is the core of the "temporal crew model" track in the roadmap.
- **Status** waiting on the DW paper PDF + extracted curves.
- **Drop-in plan** new `09_fetch_crew_curves.py`; new `data/crew_curves.json`; scheduler accepts a crew-over-time series instead of a single integer.

### Eversource outage map / restoration data
- **Why** real outage counts and restoration timelines from actual CT storm events (Isaias 2020, May 2018 tornadoes). Required for the calibration endpoint (`/api/calibrate`).
- **Status** sources identified — PURA dockets (`dpuc.state.ct.us`), Eversource regulatory filings, DOE OE-417. Not yet ingested.
- **Drop-in plan** one real `(hour, customers_restored)` curve is enough to run the existing `/api/calibrate` endpoint and fit the four realism parameters.

### Newspaper crews-per-day figures
- **Why** advisor mentioned Hartford Courant and similar local papers for "crews working per day" during big storms — used as a calibration target for the temporal crew model.
- **Status** not yet collected. Manual extraction.

### Weather forcing (wind + temperature)
- **Why** advisor provided two Google Colab notebooks for downloading wind and temperature data. Eventual use: drive storm intensity / outage placement from real weather rather than uniform random.
- **Status** Colab links to be saved; data not yet ingested.
- **Drop-in plan** new `10_fetch_weather.py`; storm generator accepts a wind/temp grid and weights outage probability by exposure.

### Real storm catalogue (Sandy, Isaias, 2024 events)
- **Why** scenario library upgrade — replace synthetic canned storms with real reconstructed events.
- **Status** depends on the Eversource outage data above + storm tracks (NHC for hurricanes is straightforward).

---

## Conventions used by every fetch script

- All scripts in this repo use Python **stdlib only** for HTTP/JSON to keep the dependency footprint small. (geopandas/numpy/numba are only used by the offline artifact generator and the server scheduler.)
- All scripts write into `data/`, never `output/`.
- All cached files are committed to the repo so the interactive works without a live API hit; the fetch scripts are run only to refresh.
- Every fetch script identifies itself in the `User-Agent` header (`hartford-grid-resilience/1.0`) so the upstream service can rate-limit us politely if needed.

---

*This file is the single source of truth for "where did this data come from?".
Any new dataset added to the simulation should get its own section here in the
same shape as #3.*
