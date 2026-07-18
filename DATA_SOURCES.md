# Data Sources

The provenance file for every piece of real-world data the Connecticut
simulation depends on. Started when the model began incorporating real data
(commit `42a9743`, real substations); grew from Hartford-County-only to
statewide coverage across all 8 counties in a later pass — will keep growing
as more datasets come in.

For each source: **what** it is, **where** it comes from, **how** to refresh
it, **where** it lives in the repo, and **what** it's used for. Honest notes
on coverage gaps go at the bottom of each entry.

---

## 1 · Connecticut state boundary

| | |
|---|---|
| **What** | The polygon of the state of Connecticut |
| **Source** | OpenStreetMap via Nominatim |
| **Endpoint** | `nominatim.openstreetmap.org/search.php?q=Connecticut,+United+States&polygon_geojson=1` |
| **Fetch script** | [`01_fetch_county_boundary.py`](01_fetch_county_boundary.py) |
| **Cached file** | [`data/connecticut_boundary.json`](data/connecticut_boundary.json) |
| **Used by** | The interactive (state outline rendering, point-in-polygon filtering for other datasets), the artifact generator |
| **License** | © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright) |
| **Refresh** | `python 01_fetch_county_boundary.py` — only needed if OSM updates the boundary |

**History**: originally scoped to Hartford County only (`data/hartford_boundary.json`, still present but unused); replaced with the statewide polygon so every downstream dataset (towns, substations, tracts) could cover all 8 counties instead of one.

---

## 2 · Connecticut towns (169 municipal polygons)

| | |
|---|---|
| **What** | All 169 real CT town polygons statewide, with names |
| **Source** | OpenStreetMap via Overpass (admin_level=8), filtered by real point-in-polygon test against the state boundary (a bounding-box query alone also catches ~44 border towns in MA/RI/NY, which are dropped) |
| **Fetch script** | [`02_fetch_town_boundaries.py`](02_fetch_town_boundaries.py) |
| **Cached files** | [`data/connecticut_towns.geojson`](data/connecticut_towns.geojson), [`data/connecticut_towns.js`](data/connecticut_towns.js) |
| **Used by** | The interactive (town overlay); demand-point weighting uses real per-town population from source 9 below, not this file |
| **License** | © OpenStreetMap contributors, ODbL 1.0 |
| **Refresh** | `python 02_fetch_town_boundaries.py` |

**History**: originally a hardcoded 29-name allowlist for Hartford County only. Rewritten to accept whatever OSM returns inside the statewide bbox rather than a hand-typed name list, filtered against the real state polygon instead of a hardcoded threshold — matched 170 features (169 real CT towns + Fenmark's "Fenwick" borough, a real sub-entity of Old Saybrook that OSM tracks as a separate relation).

---

## 3 · Connecticut substations *(real, statewide)*

| | |
|---|---|
| **What** | Real electric substation point locations across all 8 CT counties — name, lat/lon, voltage (where known), city, county, in-service status |
| **Primary source** | **HIFLD** — Homeland Infrastructure Foundation-Level Data, *Electric Substations* layer (U.S. federal infrastructure dataset) |
| **Endpoint** | `services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/Electric_Substations/FeatureServer/0/query?where=STATE='CT'` |
| **Fallback source** | OpenStreetMap (`power=substation` via Overpass), used automatically if HIFLD is unreachable |
| **Fetch script** | [`08_fetch_substations.py`](08_fetch_substations.py) |
| **Cached files** | [`data/connecticut_substations.json`](data/connecticut_substations.json), [`data/connecticut_substations.js`](data/connecticut_substations.js) |
| **Used by** | The interactive — `generateGrid()` anchors all substations at the real HIFLD locations; synthetic feeders + laterals grow from these points. Map tooltips show real name + voltage. **The grid auto-builds on page load** so real names appear immediately without the user having to click Generate first. Also used as the territory units for the crew-stickiness toggle (each outage routes to its nearest substation; crews assigned to that substation work only that territory). |
| **Record count** | 299 substations statewide (Fairfield 80, New Haven 63, Hartford 49, New London 49, Litchfield 22, Windham 15, Middlesex 13, Tolland 8) |
| **License** | HIFLD: public domain (U.S. government work). OSM fallback: © OpenStreetMap contributors, ODbL 1.0. |
| **Refresh** | `python 08_fetch_substations.py` |

**Honest coverage notes**
- HIFLD covers transmission and sub-transmission substations well (115 kV, 345 kV). Smaller neighborhood **distribution** substations are below HIFLD's threshold and aren't in any public dataset.
- HIFLD labels a handful of substations `UNKNOWN<id>` or `Deadend<id>` when the operator name isn't public. The fetch script relabels those by city (e.g. "Farmington substation") so markers are readable while locations stay exact.
- **HIFLD's `NAME` field is not unique.** 36 name-groups (covering 76 records) share a name with a genuinely different physical substation at a different location — e.g. 5 distinct substations are all named "Bridgeport substation". Anything that looks up per-substation data by name (originally the NLCD tree-canopy lookup) must key by coordinates instead, or it silently collapses duplicates. See source 8 below.
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
| **State boundary centroid** | computed at runtime from `data/connecticut_boundary.json` | Frontend `treeFactor()` | Midpoint of the loaded state boundary's lat/lon bounds, used as the fallback distance-heuristic origin when NLCD canopy data is missing for a substation (rare — all 299 real substations have a live-computed value; see Data Source §8). Was a hardcoded Hartford-city centroid before the statewide expansion. |
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

## 7 · Critical facilities (HIFLD/EPA)

| | |
|---|---|
| **What** | Real hospitals, fire stations, EMS stations, and water treatment plants statewide |
| **Source** | **HIFLD** (hospitals, fire stations, EMS stations layers) + **EPA** (Wastewater Treatment Plant layer) |
| **Fetch script** | [`09_fetch_critical_facilities.py`](09_fetch_critical_facilities.py) |
| **Cached file** | [`data/connecticut_critical_facilities.js`](data/connecticut_critical_facilities.js) |
| **Used by** | `simulateStorm()` — outages within 0.5 miles of a real facility are flagged priority-1 for restoration (replaces the previous random 2% sampling). Also rendered on the map as emoji markers (🏥🚒🚑💧) with a toggle. |
| **Record count** | 1,143 facilities statewide (42 hospitals, 568 fire stations, 463 EMS, 70 water plants) |
| **License** | HIFLD/EPA: public domain (U.S. government work) |

**Honest coverage notes**
- Coordinates are approximate to the facility address, not to the exact electrical service entrance.
- Some smaller volunteer fire departments may be missing; HIFLD focuses on career/combination departments.
- The 0.5-mile proximity radius is a heuristic — real priority assignment would use the utility's customer-to-circuit mapping.
- The EPA Wastewater Treatment Plant layer's `cwp_status` field is *regulatory compliance* status ("Noncompliance" / "No Violation"), not an operational open/closed flag — a plant in "Noncompliance" is still physically running and still needs power. The fetch script does not filter on it.
- **History**: the original 52-facility Hartford-only file had no backing fetch script and doesn't match any live HIFLD query — likely hand-typed rather than pulled from the API. The statewide 1,143-facility count above is a genuine, reproducible HIFLD/EPA pull (`09_fetch_critical_facilities.py`), not a bigger version of the old hand-picked list.

---

## 8 · NLCD tree canopy cover per substation

| | |
|---|---|
| **What** | Mean tree canopy percentage within a 1 km buffer of each real HIFLD substation, from the USGS National Land Cover Database 2021 Tree Canopy Cover layer (30 m resolution, CONUS) |
| **Source** | USGS MRLC WMS — `mrlc.gov/geoserver/mrlc_display/wms`, layer `NLCD_Canopy` |
| **Fetch script** | [`10_fetch_tree_canopy.py`](10_fetch_tree_canopy.py) |
| **Cached file** | [`data/connecticut_tree_canopy.js`](data/connecticut_tree_canopy.js), keyed by `"lat,lon"` (not substation name — see below) |
| **Used by** | `generateGrid()` → `treeFactor()` (via `canopyOf()`) — converts canopy % to a tree-blocked multiplier (0% → 0.15×, 50% → 1.0×, 75% → 1.5×). Also used by the explicit underground repair-time tag and the AMI-detection model. Replaces the previous urban/suburban/rural distance heuristic with actual measured tree cover. |
| **Record count** | 299 values statewide (min 17.4%, max 72.4%, mean 44.2%) |
| **License** | USGS: public domain (U.S. government work) |

**Method**: one WMS `GetMap` request per substation (`FORMAT=image/geotiff8`, a single-band unstyled raster — cross-checked against `GetFeatureInfo` at known points: dense forest → 88%, downtown Hartford → 0%, a substation's own clearing → 0%), covering a real 2km×2km box centered on the substation, decoded locally and averaged over the actual 1km-radius circle.

**Honest coverage notes**
- **HIFLD's substation `NAME` field is not unique** (see source 3) — the original Hartford-only 49-entry dict was keyed by name, which is fine at 49 substations with no collisions, but breaks at statewide scale (36 name-groups collide across 76 of the 299 real records, e.g. 5 different "Bridgeport substation"s). The statewide file and the JS lookup (`canopyOf()`) key by rounded coordinates instead.
- Values are now live-computed (not hand-typed), a change from the original disclosed limitation ("pre-computed means, not live raster queries").
- The linear conversion (canopy_pct / 50) is still a heuristic; calibratable against real storm data.

---

## 9 · Census tract population and town population (2020 Census P.L. 94-171)

| | |
|---|---|
| **What** | Census tract centroids + population (883 tracts) and town-level (county subdivision) population + centroids (169 towns), statewide |
| **Source** | US Census Bureau, 2020 Census **P.L. 94-171 Redistricting Data** — a keyless static flat-file download, not the api.census.gov API (which requires a free key) |
| **URL** | `www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Connecticut/ct2020.pl.zip` |
| **Fetch script** | [`11_fetch_census_tracts.py`](11_fetch_census_tracts.py) |
| **Cached files** | [`data/connecticut_census_tracts.js`](data/connecticut_census_tracts.js), [`data/connecticut_towns_population.js`](data/connecticut_towns_population.js) |
| **Used by** | `buildDemandPoints()` — census-tract-level demand (883 tracts) when the toggle is on, falling back to the 169-town centroid model otherwise. `05_generate_artifacts.py` also loads the town file for `TOTAL_POP` and demand-point generation. |
| **Record count** | 883 tracts; 169 towns, total population 3,605,944 (verified exact match to CT's real 2020 Census population) |
| **License** | Public domain (U.S. government work) |

**Honest coverage notes**
- Centroids (`INTPTLAT`/`INTPTLON`) are the Census Bureau's own internal points, not simple geometric centroids.
- Population is total population (POP100, the 100% count), not households or electric customers.
- **History**: the original Hartford-only `hartford_census_tracts.js` (148 records) had 10-digit "GEOIDs" — real Census tract GEOIDs are 11 digits — and an embedded county-FIPS substring that didn't match Hartford County's real FIPS code (003). Both are strong evidence it was hand-typed rather than pulled from a real API. The statewide file's GEOIDs are verified correctly formatted (e.g. `09001010101` = state 09, county 001, tract 010101) and cross-checked against known real town populations (Bridgeport 148,654; Greenwich 63,518).

---

## 10 · NOAA HURDAT2 storm tracks

| | |
|---|---|
| **What** | Best-track positions for 4 storms that affected Connecticut: Sandy (2012), Isaias (2020), Irene (2011), Henri (2021) |
| **Source** | NOAA National Hurricane Center, HURDAT2 (Atlantic basin best track database) |
| **URL** | `nhc.noaa.gov/data/#hurdat` |
| **Cached file** | [`data/hartford_storm_tracks.js`](data/hartford_storm_tracks.js) (filename predates the statewide expansion; the data itself was already regional, not Hartford-specific — see coverage note) |
| **Used by** | Storm-track overlay on the map (toggle-controlled polyline with wind-speed markers); wind-exposure-weighted outage placement along the track (paired with source 12a below for storms that have HRRR coverage). |
| **License** | Public domain (U.S. government work) |

**Honest coverage notes**
- Tracks are clipped to a CT/NE regional box (lat 39–43°N, lon -75 to -71), which was already statewide-or-broader in scope — no change needed for the statewide expansion.
- The wind fields are point estimates at the track center; real wind swaths extend tens of miles on each side. A proper wind-exposure model would use the asymmetric wind field (Rmax, Holland B parameter).

---

## 11 · DOE OE-417 Electric Disturbance Events

| | |
|---|---|
| **What** | Major electric disturbance events affecting Eversource/CL&P in Connecticut, with customer counts and restoration durations |
| **Source** | U.S. Department of Energy, Office of Electricity, OE-417 Annual Summary |
| **URL** | `oe.netl.doe.gov/OE417_annual_summary.aspx` |
| **Cached file** | [`data/hartford_doe_oe417.js`](data/hartford_doe_oe417.js) (filename predates the statewide expansion; DOE reports customer counts for the whole utility territory, not Hartford County alone — no change needed) |
| **Used by** | Events panel in the sidebar (toggle-controlled). Calibration benchmarks in the simulation report. |
| **Record count** | 8 events (2011–2024) |
| **License** | Public domain (U.S. government work) |

**Honest coverage notes**
- Duration is start-to-100% restoration; the bulk of customers are restored much earlier (typically 90% within half the total window).

---

## 12 · HRRR wind / temperature / soil-moisture grid (statewide)

| | |
|---|---|
| **What** | Representative-hour surface-gust and rain fields on a 41×65 grid (~3km resolution) covering Connecticut for 8 cached events; temperature and soil-wetness metadata are retained where available |
| **Source** | NOAA HRRR model, AWS public archive, accessed via the `herbie-data` Python library |
| **Endpoint** | `noaa-hrrr-bdp-pds.s3.amazonaws.com` |
| **Fetch script** | [`12_fetch_hrrr_storm_wind.py`](12_fetch_hrrr_storm_wind.py) |
| **Cached file** | [`data/connecticut_storm_wind.js`](data/connecticut_storm_wind.js) |
| **Storms** | Isaias 2020, Henri 2021, May 2018 tornado/derecho outbreak, January 2024 wind storm, December 2023 nor'easter, October 2020 derecho, July 2026 severe thunderstorm complex, and December 2022 windstorm |
| **Used by** | Offline regression tests and older calibration scripts. The professor-facing website no longer loads this representative-hour cache; its active Isaias workflow uses the hourly timeline below. |
| **License** | Public domain (U.S. government work) |

**Method**: HRRR uses a Lambert Conformal projection (lat/lon are 2-D arrays), so each storm's `GUST:surface`, `APCP:surface`, and `TMP:2 m above ground` fields are clipped to a CT bounding box and regridded onto the regular target grid via `scipy.interpolate.griddata`.

**Honest coverage notes**
- Sandy (2012) and Irene (2011) predate the HRRR archive (which starts ~2014) and have no gridded wind/rain data. The UI requires the explicitly labeled basic network-placement mode for events without a complete field; it never silently changes methods.
- Soil moisture (`SOILW`) is not present in the HRRR surface product for any of the 5 storm hours checked (confirmed directly against the raw GRIB index files, not just a failed field-name guess). The one semantically-adjacent field available, `MSTAV` (moisture availability), returned a flat 100% across the entire region for at least one storm — not reliable enough to use as a substitute. `soil_wetness` is left `null` for all 5 storms rather than filled with a fabricated or low-confidence value; the soil-saturation auto-toggle already handles a null value gracefully (no-op).
- **History**: originally a 15×21 grid covering only Hartford County; densified to the current 41×65 statewide grid at the same underlying ~3km native HRRR resolution.

---

## 12b · Curated hourly HRRR storm timeline (statewide)

| | |
|---|---|
| **What** | A 24-frame hourly wind/rain timeline on the same 41×65 Connecticut grid, intended as the single weather source for both animation and time-dependent outage placement |
| **Source** | NOAA HRRR surface product, AWS public archive, accessed via `herbie-data` |
| **Fetch script** | [`12_fetch_hrrr_storm_wind.py`](12_fetch_hrrr_storm_wind.py) with `--timeline-only --timeline isaias_2020` |
| **Cached file** | [`data/connecticut_storm_timelines.js`](data/connecticut_storm_timelines.js) |
| **Curated storms** | Tropical Storm Isaias (2020) only in Phase 1 |
| **Window** | 2020-08-04 06:00 UTC through 2020-08-05 05:00 UTC, hourly |
| **Fields** | Surface gust in mph; one-hour accumulated precipitation ending at the frame time; six-hour antecedent precipitation, all stored as row-major arrays |
| **License** | Public domain (U.S. government work) |

**Time alignment**: wind uses the HRRR analysis (`f00`) valid at time `T`.
Rain uses the one-hour accumulated precipitation forecast (`f01`) initialized
at `T-1`, so its accumulation interval also ends at `T`. Five rain frames
before the visible window are fetched to give the first visible frame a full
six-hour antecedent total.

**Scope note**: this is a curated catalog, not an arbitrary-date service. The
browser consumes the committed, reviewed data and does not download or decode
raw GRIB files. The JavaScript model and Worker now produce timestamped outage
locations and transferable map surfaces from this timeline. The existing map
animates those exact arrays with hourly playback and cumulative outage markers.

---

## 12a · Flood-prone river corridors (statewide)

| Field | Value |
|---|---|
| **What** | Simplified centerline geometries for 17 major flood-prone river corridors statewide: 5 in Hartford County + 12 across the other 7 counties |
| **Hartford 5** | Connecticut River, Park River, Hockanum River, Farmington River, Salmon Brook — from FEMA National Flood Hazard Layer (NFHL), hand-simplified |
| **Other 12** | Housatonic, Naugatuck, Quinnipiac, Norwalk, Shepaug, Salmon River (distinct from Salmon Brook), Thames, Yantic, Shetucket, Quinebaug, Willimantic, Natchaug — from USGS National Hydrography Dataset (NHD), fetched and algorithmically stitched |
| **Source (12 new)** | USGS National Map, `hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/4` (NHD Flowline - Small Scale), filtered by `GNIS_NAME` |
| **Fetch script** | [`13_fetch_flood_corridors.py`](13_fetch_flood_corridors.py) |
| **Cached file** | [`data/connecticut_flood_corridors.js`](data/connecticut_flood_corridors.js) — merged into `FLOOD_CORRIDORS` in `03_grid_simulation.html` alongside the 5 hand-placed Hartford corridors |
| **Used by** | Flood-zone road-closure toggle — outages within 1.5 mi of any corridor get +35% road impedance |
| **License** | FEMA/USGS: public domain (U.S. government work) |

**Method**: NHD represents each named river as many short connected reach segments (15–126 reaches per river in this dataset). The fetch script chains matching reaches end-to-end by snapping endpoints within ~50-60m, keeps the longest connected chain per river, then decimates to ~19 points. Verified for stitching artifacts (no jump between consecutive points exceeds 0.13° — i.e. no segment cuts across the map connecting unrelated reaches).

**Coverage note**: corridors are simplified to centerlines, not full floodplain polygons. The 1.5-mile buffer is a conservative proxy for FEMA Zone A/AE extent. Smaller tributaries not in the 17-river list are not included.
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

## 17 · Underground Line Model

| Field | Value |
|---|---|
| **What** | Urban substations statewide have significant underground distribution infrastructure that is nearly immune to storm damage. |
| **Source** | Eversource rate case filings to CT PURA; industry standard underground penetration estimates for New England urban cores. |
| **Parameters** | Urban threshold: <25% NLCD canopy. Underground fraction: 40% of laterals. Storm immunity: 90% outage rejection. |
| **Used by** | Underground line model toggle in storm simulation. |
| **Coverage note** | Actual underground infrastructure maps are CEII (Critical Energy Infrastructure Information) and not publicly available. The model uses NLCD canopy percentage as a proxy for urbanization level. Real underground penetration likely varies by neighborhood within a substation service area. |

---

## 18 · Switching / Back-Feed (FLISR)

| Field | Value |
|---|---|
| **What** | Fault Location, Isolation, and Service Restoration — automated distribution switches that can reroute power through alternate feeders without a crew visit. |
| **Source** | Eversource distribution automation deployment reports; IEEE 1366 reliability metrics for automated switching. |
| **Parameters** | 42% of feeder-level outages eligible for automatic switching (Eversource's disclosed `restoredUnder5min` rate). Restoration time ~5 minutes (remote FLISR operation) — matches `outage_restoration_adapter.js` `switchingRate: 0.42`, `switchingRestoreHours: 5/60`. (This doc previously said "20% / ~30 minutes", which was stale relative to the code and the Eversource smart-switch figure.) |
| **Used by** | Switching/back-feed toggle in storm simulation. Switch-restored outages are pre-marked as done and excluded from crew dispatch. |
| **Coverage note** | The 20% rate is a conservative estimate. Eversource's actual FLISR coverage may be higher in areas with newer automation infrastructure. Real FLISR eligibility depends on switch placement topology, load transfer capacity, and fault type — none of which are modeled here. |

---

## 19 · AMI Smart Meter Coverage

| Field | Value |
|---|---|
| **What** | Advanced Metering Infrastructure (smart meters) that detect outages instantly via "last-gasp" power-loss signals, eliminating the need for customer callback-based detection. |
| **Source** | Eversource AMI deployment reports to CT PURA; CT DEEP energy policy filings on smart grid modernization. |
| **Parameters** | Urban (<25% canopy): 70% AMI, 1–3h lag on 30% of laterals. Suburban (25–50%): 50% AMI, 2–5h lag on 50% of laterals. Rural (>50%): 30% AMI, 3–8h lag on 70% of all outages. |
| **Used by** | AMI smart meter coverage toggle, replacing the flat 15% callback-lag model with spatially-varying detection. |
| **Coverage note** | Actual Eversource AMI deployment rates by substation territory are not publicly available. The canopy-based penetration estimates are calibrated to industry averages for New England utilities at various stages of AMI rollout. |

---

## 20 · Mutual-Aid Travel Time

| Field | Value |
|---|---|
| **What** | Out-of-state mutual-aid crews must drive from their home territories to Connecticut before beginning storm restoration work. |
| **Source** | IBEW mutual-aid agreement protocols; Eversource Isaias 2020 after-action report documenting crew origin states (MA, NY, RI, PA, OH). |
| **Parameters** | MA/RI crews: +2h travel. NY crews: +4h travel. PA/OH crews: +6h travel. Applied to wave 2 (30% of crews) and wave 3 (20% of crews). Wave 1 (local Eversource, 50%) unaffected. |
| **Used by** | Mutual-aid travel time toggle in restoration scheduler. |
| **Coverage note** | Real travel times depend on staging area locations, traffic, and whether crews are pre-positioned at utility yards vs. driving from home. The state-based distance bands are simplified averages. |

---

## 21 · Eversource CT Reliability Scorecards & Published Metrics (2021–2025)

- **Source** Eversource Energy annual reliability scorecards, RPA "State of the Grid in Connecticut" (2025), Fox Weather smart switch reporting, Eversource CT Newsroom
- **URLs**
  - https://www.eversource.com/residential/outages/connecticut-reliability-scorecards
  - https://rpa.org/news/lab/the-state-of-the-grid-in-connecticut
  - https://www.foxweather.com/lifestyle/smarter-grids-shorter-outages-new-england-power-restoration-technology
  - https://outagemap.eversource.com/external/default.html (KUBRA Storm Center, SC4)
- **Where in repo** `EVERSOURCE_CT` constant in `03_grid_simulation.html` (~line 560)
- **What it provides**
  - **SAIDI**: 76.0 min/cust (Eversource 2021), 164.6 min/cust (CT statewide 2023)
  - **SAIFI**: 0.686 int/cust (Eversource 2021), 0.872 int/cust (CT statewide 2023)
  - **Customer base**: 1.3 million across 157 municipalities
  - **Distribution**: 23,000 miles of electric distribution lines
  - **Smart switches**: ~8,500 deployed (CT/MA/NH), 1.5M interruptions avoided/yr in CT
  - **Auto-restoration**: 42% of outages restored within 5 minutes via smart switches
  - **Storm outage cause**: >90% of storm power outages caused by trees
  - **Top 3 causes**: trees, equipment failure, vehicle pole strikes
  - **ERP levels**: 5-level emergency response plan with restoration targets (L5: 1-3 days @ 0-9% out → L1: 18+ days @ 70-100% out)
  - **Peak load**: 4,563 MW (2025), 5,270 MW extreme weather (2034 projection)
  - **Generation mix**: 60% gas, 33% nuclear, 6% renewables (2023)
  - **Infrastructure investment**: $9B transmission (2016-2024), $2.3B resilience (2024)
  - **Maintenance (2025)**: 15,027 trees removed, 4,400 new poles, 200 mi new wire, 24 new smart switches
  - **Electricity rate**: 27.24¢/kWh (June 2025, 5th highest in US)
- **How used**
  - Tree-blocked rate updated from 30% to 90% (matching real storm data)
  - FLISR switching rate updated from 20% to 42% (matching smart switch auto-restoration rate)
  - ERP level classification added to simulation report (section 13.2)
  - Real SAIDI/SAIFI benchmarks for comparison in report (section 13.3)
  - Infrastructure summary in report (section 13.4)
  - Sensitivity analysis KPIs benchmarked against real values (section 20.3)
- **Coverage gaps** Per-town scorecard data exists as PNG images on Eversource's site but actual numeric values are not machine-readable. The KUBRA-powered outage map (outagemap.eversource.com) API endpoints are all locked down (403 Forbidden) — real-time outage data cannot be programmatically accessed.

---

## 22 · Planned / pending data sources

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
- **Drop-in plan** new `14_fetch_crew_curves.py`; new `data/crew_curves.json`; scheduler accepts a crew-over-time series instead of a single integer.

### Eversource outage map / restoration data
- **Why** real outage counts and restoration timelines from actual CT storm events (Isaias 2020, May 2018 tornadoes). Required for the calibration endpoint (`/api/calibrate`).
- **Status** sources identified — PURA dockets (`dpuc.state.ct.us`), Eversource regulatory filings, DOE OE-417. Not yet ingested.
- **Drop-in plan** one real `(hour, customers_restored)` curve is enough to run the existing `/api/calibrate` endpoint and fit the four realism parameters.

### Newspaper crews-per-day figures
- **Why** advisor mentioned Hartford Courant and similar local papers for "crews working per day" during big storms — used as a calibration target for the temporal crew model.
- **Status** not yet collected. Manual extraction.

### Weather forcing (wind + temperature) — done, statewide
- Ingested: see Data Source §12 (`12_fetch_hrrr_storm_wind.py`, statewide 41×65 HRRR grid, 5 storms). Originally a Hartford-County-only 15×21 grid built from an advisor-provided Colab notebook (`fetch_hrrr_storm_wind.ipynb`); densified to statewide coverage.
- **Remaining gap**: Sandy (2012) and Irene (2011) predate the HRRR archive and would need ERA5 reanalysis data instead — not pursued yet.

### Real storm catalogue (Sandy, Isaias, 2024 events)
- **Why** scenario library upgrade — replace synthetic canned storms with real reconstructed events.
- **Status** depends on the Eversource outage data above + storm tracks (NHC for hurricanes is straightforward).

---

## Conventions used by every fetch script

- All scripts in this repo use Python **stdlib only** for HTTP/JSON to keep the dependency footprint small. (geopandas/numpy/numba are only used by the offline artifact generator and the server scheduler.)
- All scripts write into `data/`, never `output/`.
- All cached files are committed to the repo so the interactive works without a live API hit; the fetch scripts are run only to refresh.
- Every fetch script identifies itself in the `User-Agent` header (`connecticut-grid-resilience/1.0`) so the upstream service can rate-limit us politely if needed.

---

*This file is the single source of truth for "where did this data come from?".
Any new dataset added to the simulation should get its own section here in the
same shape as #3.*
