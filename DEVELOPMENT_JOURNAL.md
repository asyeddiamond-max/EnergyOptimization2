# Hartford County Grid Simulation — Development Journal

A running log of design decisions, additions, and trade-offs made to the simulation. Each entry captures *what* changed, *why* it changed, and the reasoning behind the choice. Updated continuously.

---

## Phase 1 — Foundation: a basic interactive map

**Goal:** Get a working Leaflet-based map of Hartford County into the browser.

**What was built:**
- Leaflet map with OSM tiles
- Hartford County boundary outlined (red)
- Three basemap options (OSM standard, OpenTopoMap, Carto Light)
- Town centroids with click-to-info popups
- Energy load shading overlay (population proxy)

**Key decisions:**
- Used Leaflet over Mapbox or Google Maps: no API keys, self-hostable, smaller bundle
- Pulled county boundary from OpenStreetMap via Nominatim — cached locally so it works offline
- Town centroids and 2020 census populations were hard-coded into a JavaScript array as the starting source of truth

---

## Phase 2 — Isolation of Hartford County

**Goal:** Make the simulation feel like it's about Hartford County specifically, not just "a map with Hartford in it."

**What was built:**
- Polygon mask covering everything *outside* Hartford County so the surrounding region greys out
- Pronounced red boundary line emphasized
- View locked to the county

**Why:** The user (asyeddiamond) wanted the interactive to look like it represented Hartford County as a discrete entity. The mask + bold boundary visually accomplished that.

---

## Phase 3 — Adding the synthetic distribution grid

**Goal:** Place substations across the county and draw a plausible network of feeders and laterals.

**What was built:**
- Weighted k-means substation placement using town centroids as weighted demand points
- Configurable number of substations (slider, 20–300)
- Configurable feeders per substation (slider, 3–10)
- Each substation grows random-walk feeders radiating outward
- Each feeder spawns laterals branching off random midpoints
- Color-coded by substation (feeders share their parent substation's color)

**Key decisions:**
- Network is **synthetic, not real** because real distribution-network topology is Critical Energy/Electric Infrastructure Information (CEII) and not public. The README is explicit about this so viewers aren't misled.
- K-means weighted by `sqrt(pop)` blends population-driven placement with uniform-area coverage so rural towns aren't completely neglected
- Random walks are clipped to the county polygon so the grid stays inside Hartford County

---

## Phase 4 — Storm simulation

**Goal:** Let the user place failures across the network and see how many customers are affected.

**What was built:**
- "Storm outages" slider (50–25,000)
- Each outage placed on a random feeder or lateral segment
- Each segment's customer share is summed to give a "customers without power" estimate
- Color-coded markers (red dots)
- "Sandy-scale" storm sizes supported (25K outage points)

**Key decisions:**
- Storm distribution is uniform over segments (weighted by segment count). Not weighted by actual storm path or population density — that would require real outage data.
- Customer impact per outage is a rough proxy: the affected segment's share of its parent feeder's customer base. This **overestimates** real impact by ~2x because real grids have sectionalizers that isolate small chunks. Realistic mode (added later) halves this.

---

## Phase 5 — Restoration scheduler

**Goal:** Send crews to outages and compute total restoration time.

**What was built:**
- Repair crews slider (1–5,000)
- Greedy nearest-outage scheduler
- Min-heap on crew finish times for O(log M) "next free crew" lookup
- Crew depots placed by k-means clustering of outage locations (when ≤200 crews)
- Numbered repair circles for the first 30 jobs per crew

**Key decisions:**
- **Greedy was chosen over MILP** for performance and simplicity. Greedy is a known baseline that real research uses; MILP would require a solver that doesn't run in the browser.
- The min-heap structure is the right data structure here — pulled from a standard algorithms textbook.
- Color-coding crews matches the existing palette so the visual style stays coherent.

---

## Phase 6 — Optimal crew count recommender

**Goal:** Find the smallest crew count that achieves restoration within 15% of the theoretical floor.

**What was built:**
- "Find optimal crew count" button
- Binary search over M from 1 to upper bound
- Each evaluation runs the scheduler and measures total restoration time
- Returns the smallest M whose result is within 15% of the floor

**Key decisions:**
- Tolerance set to 15% based on industry rules-of-thumb. Lower = closer to optimal but more crews; higher = cheaper but slower.
- Upper bound capped at `max(50, N/10)` — past this, additional crews idle waiting for outages to be discovered.

---

## Phase 7 — Realistic mode toggle

**Goal:** Match restoration times to real Eversource storm reports (~2–7 days for major storms instead of "hours" theoretical floor).

**What was built:**
- "Realistic mode" toggle (yellow callout in sidebar)
- Seven real-world factors layered onto the scheduler:
  1. **12-hour damage assessment delay** before any crew dispatches
  2. **14-hour workday clamp** (6 am–8 pm, then overnight downtime)
  3. **Stochastic repair durations** — log-normal sampler, median 2 h, 90th percentile 6 h
  4. **Damage-assessment ramp** — only 30% of outages visible within an hour of dispatch; rest reveal exponentially over 36 hours
  5. **Mutual-aid waves** — 50% of crews dispatch at hour 12, +30% at hour 36, +20% at hour 60
  6. **Road-network proxy** — actual travel time = haversine × 1.5
  7. **Tier-1 critical facility priority** — ~2% of outages flagged critical, scheduled first
- Sectionalizer model: per-outage customer impact halved

**Why:** Without these, the model produced restoration times of "~12 hours for a major storm" — wildly optimistic compared to Eversource's 2–7-day actuals. The factors above bring it into the right order of magnitude.

**Key decisions:**
- Realistic mode is a *toggle* rather than the only mode so users can compare against the optimistic baseline
- Each factor is documented in the README with the publication or operational source it's based on
- The seven factors map directly to the SCALING document's §4 uncertainty table

---

## Phase 8 — Performance optimizations

**Goal:** Keep the simulation responsive at "max settings" (300 substations, 25K outages, 5K crews).

**Several rounds of optimization were applied:**

**Round 1: Spatial data structures**
- Pre-computed 256×256 inside-county bitmap for O(1) point-in-polygon checks (replaces O(P) ray-casting)
- Typed arrays (Float64Array) for k-means hot loops
- Grid hash for nearest-outage queries: O(log N) instead of O(N)

**Round 2: Rendering**
- Canvas renderer for feeders, laterals, repair dots
- Outage rendering moved to a custom `PointCloudLayer` (single canvas draw vs. 25K Leaflet circleMarkers)
- Numbered repair budget capped at 1,500 (or 500 when M > 500) to avoid DOM blowup

**Round 3: Scheduler core**
- Min-heap for crew finish times: O(log M) "next free crew"
- Visibility-aware grid hash for rolling-horizon nearest-outage lookup
- Sorted discovery list with monotonic "first undone" pointer for O(log N) `nextDiscoveryAfter`
- Ring expansion capped at 100 cells (≈55 km, sufficient for county-wide queries)

**Round 4: Async / responsiveness**
- `planRestoration` made async with chunked yields every 3,000 outage assignments
- Inner `scheduleFast` (used by recommender) also async with yields every 4,000 iterations
- Progress bars under both buttons showing live percentage

**Round 5 (planned, in-progress): Web Worker**
- Move the scheduler entirely off the main thread
- Solves all remaining "page isn't responding" cases
- See in-progress entries below

---

## Phase 9 — Export functionality

**Goal:** Allow scenarios to be exported for downstream GIS analysis.

**What was built:**
- GeoJSON export (one FeatureCollection per layer: substations, feeders, laterals, outages, restoration plan)
- Shapefile export (multi-layer .shp/.shx/.dbf/.prj bundles)
- Manifest file recording seed and all slider positions
- Compatible with QGIS, ArcGIS, geopandas, R `sf`

**Key decisions:**
- Both formats supported because different downstream consumers prefer different formats
- Schema documented in the README so consumers know what columns to expect
- WGS84 (EPSG:4326) coordinate system

---

## Phase 10 — Repository structure and deployment

**Goal:** Make the repo presentable and useful for a research project.

**What was built:**
- Numbered file convention (01, 02, 03, etc.) matching the user's existing repo style
- GitHub Pages deployment so anyone can use the simulation without installing
- README rewritten end-to-end with goals, controls, algorithms, performance notes
- `data/` folder for cached OSM inputs
- `output/` folder for matplotlib PNG artifacts
- `noindex` meta tag so it doesn't appear in Google search

---

## Phase 11 (in progress) — Web Worker for the scheduler

**Goal:** Move all scheduler compute off the main thread so the UI never freezes.

**Why now:** Previous optimizations (async yields, point cloud rendering) keep the UI responsive *most* of the time, but at extreme settings (Sandy-scale + 5K crews + Find optimal crew count) the browser still hits the unresponsive-page dialog. The proper fix is to put scheduling in a Web Worker.

**Status:** Implementation in progress.

---

## Phase — Real-data integration batch (June 2026)

**Goal:** Replace heuristic placeholders throughout the model with real Hartford County data from federal open-data sources, and add a simulation report download.

**What was built:**

1. **Critical facilities from HIFLD** — 52 real hospitals, fire stations, EMS stations, and water treatment plants loaded from `data/hartford_critical_facilities.js`. Outages within 0.5 miles of a real facility are flagged priority-1 for restoration, replacing the previous random 2% sampling. Rendered on the map as clean SVG markers (red cross for hospitals, flame for fire, star-badge for EMS, droplet for water) with a toggleable layer.

2. **NLCD 2021 tree canopy per substation** — Pre-computed mean canopy percentage (from USGS 30m resolution data) within a 1 km buffer of each of the 49 HIFLD substations. Replaces the simple urban/suburban/rural distance heuristic (`< 5km → 0.40×, < 12km → 1.00×, else 1.50×`) with actual measured tree cover (`canopy_pct / 50`, so Hartford downtown at 8% → 0.16×, Hartland at 72% → 1.44×).

3. **Census tract demand model** — ~196 census tract centroids with 2020 populations replace the 29-town centroid demand model for ~5× finer spatial granularity. Toggle-controlled so the user can compare tract-level vs. town-level demand placement.

4. **NOAA HURDAT2 storm tracks** — Best-track data for Sandy (2012), Isaias (2020), Irene (2011), and Henri (2021). Rendered as a dashed polyline overlay with wind-speed markers at each track point. Selectable via dropdown.

5. **DOE OE-417 disturbance events** — 8 real Connecticut outage events (2011–2024) with actual customer counts and restoration durations. Shown in a toggleable panel for quick comparison against simulated results.

6. **Simulation report download** — Generates a detailed text file covering: grid configuration (all 49 substations with NLCD canopy factors), critical facilities inventory, storm damage assessment (per-substation breakdown), restoration milestones (10%–100%), crew summary table, 200-job dispatch log, DOE calibration benchmarks, and full data-source provenance.

7. **Bug fix** — `trimAgeMult()` and `TRIM_CYCLE_YEARS` moved from local scope inside `generateGrid()` to top-level scope, fixing a scoping bug where `simulateStorm()` referenced them but they were only accessible via closure.

**Key decisions:**
- Used SVG symbols instead of emoji for map markers — emojis render differently across platforms and look unprofessional at small sizes.
- Census tract toggle defaults to ON but can be turned off to compare demand granularity.
- DOE OE-417 events are displayed as a reference panel, not yet wired into the calibration endpoint.
- Storm tracks are overlays only — wind-exposure-weighted outage placement is the natural next step.

---

## Phase — Environmental/behavioral realism + report upgrade (June 2026)

**Goal:** Add three new environmental and behavioral realism factors to the restoration scheduler, improve the simulation report with per-town individualized breakdowns, and add a progress bar to the server wake button.

**What was built:**

1. **Flood-zone road closures** — Five major Hartford County river corridors (Connecticut River, Park River, Hockanum River, Farmington River, Salmon Brook) modeled as simplified centerline geometries from FEMA NFHL. Outages within 1.5 miles of a flood corridor get +35% road impedance, simulating the need for crews to take longer detour routes when low-lying roads are impassable. Based on CT DOT road-closure records during Irene (2011) and Sandy (2012).

2. **Equipment/material shortage** — During major events (5,000+ outages), the supply of replacement transformers, poles, and conductor spools runs thin. After 60% of repairs are complete, each subsequent repair takes progressively longer (up to +40% penalty) as crews wait for resupply from regional warehouses. Based on Eversource Isaias after-action reports citing equipment staging delays.

3. **Customer callback lag** — Not all outages are detected by SCADA or smart meters. On rural laterals in high-canopy areas, ~15% of outages are only discovered when a customer calls to report them, adding 2–8 hours of additional discovery delay. Based on CT PURA testimony on Eversource outage detection gaps.

4. **Per-town simulation report** — Section 5 of the download report now includes an individualized breakdown for each of the 29 Hartford County towns: outage counts, customers affected (% of town population), critical-facility outages, tree-blocked %, flood-zone outages, callback-lag count, and full restoration timeline (first repair, 50%, 90%, 100%, avg repair time).

5. **Server wake progress bar** — The "Wake server now" button now shows a visual progress bar with stage-aware labels ("Sending wake signal," "Server is booting," "Almost ready") and a 65-second countdown. Turns green on success, red on timeout.

**Key decisions:**
- Flood corridors are simplified to centerlines rather than full floodplain polygons — accurate enough for the road-impedance model and avoids needing to load large FEMA shapefiles in-browser.
- Equipment shortage only kicks in during major events (5,000+ outages) to avoid penalizing small storms where supply chains are adequate.
- Callback lag is scoped to rural laterals (high tree-factor areas) because urban areas generally have better AMI coverage and faster detection.

---

## Phase — Crew time series, fatigue model, graph flip (June 2026)

**Goal:** Address four specific advisor requests: flip the restoration curve to show "customers without power" (high→low), implement crew time-series ramp from real data, model crew fatigue and overtime economics, and overlay real DOE restoration curves.

**What was built:**

1. **Flipped restoration graph (high→low)** — The inline SVG curve now shows "customers without power" dropping from peak to zero, matching the advisor's request and standard utility reporting conventions. Previously showed "customers restored" rising from zero — the advisor said "turn your graph upside down."

2. **Crew time-series ramp (Isaias model)** — Crews mobilize on a logistic curve calibrated to real PURA Docket 20-08-03 data: ~16% of peak force on day 1 (504 line + 235 tree = 739 crews), ~40% by day 3, ~73% by day 5 (2,500 line + 780 tree = 3,280), full force by day 7 (4,500+). Replaces the old 3-wave model (50%/30%/20%) with a continuous, data-driven ramp. Toggle-controlled so users can compare against instantaneous deployment.

3. **Crew fatigue & overtime productivity decline** — After day 2 of continuous 16-hour shifts, repair times increase 5% per additional day, capped at +30% by day 8. Non-critical repairs get an additional 8% penalty after day 4, modeling the behavioral incentive where IBEW double-time pay ($100+/hr) reduces urgency. Based on Circadian workforce research (10% OT increase → 2.4% productivity loss) and SHRM overtime studies (accident risk triples after 16h continuous work). Addresses the advisor's "behavioral social science" dimension.

4. **Real DOE curve overlay** — The restoration graph now overlays a dashed red curve showing the closest-matching real DOE OE-417 event's restoration trajectory for visual comparison between simulated and actual restoration.

**Key decisions:**
- Logistic ramp (k=0.06, t_mid=72h) was chosen over a step function because real crew mobilization is continuous, not discrete waves.
- Fatigue penalty is conservative (5%/day, max 30%) to avoid overstating the effect. The 8% non-critical penalty is the "behavioral" component the advisor specifically wanted.
- DOE overlay uses a simplified S-curve interpolation since actual hour-by-hour restoration data is not publicly available from PURA filings.

**Data sources:**
- Crew counts: PURA Docket 20-08-03, CT Mirror (2020-08-05), NBC Connecticut
- Crew compensation: IBEW Outside Construction contracts, powerlinemanjobs.com
- Fatigue research: Circadian (circadian.com), SHRM overtime toolkit
- DOE events: DOE OE-417 Electric Disturbance database

---

## Phase — Massively expanded simulation report (June 2026)

**Goal:** Rewrite `generateSimulationReport()` from a ~200-line summary into a ~1,000-line, 19-section comprehensive analysis document that the user described as wanting "the level of depth where one would need multiple servers in order to get this information."

**What was built:**

The report now contains 19 fully-written sections:

1. **Distribution Grid Configuration & Topology** — line miles, density stats, coordinate system, generation seed
2. **Substation-Level Detail** — full table with lat/lon, voltage, feeders, laterals, canopy%, treeFactor, trim age; vulnerability and population rankings
3. **Critical Infrastructure Inventory** — all HIFLD facilities with nearest-substation distances, per-town facility counts
4. **Network Topology Analysis** — feeder/lateral length statistics (mean, std dev, percentiles), per-substation topology table with customers/mile
5. **Storm Damage Assessment** — overall impact, customer-loss distribution with histogram, per-substation damage table, top-5 worst-hit narrative
6. **Spatial Damage Analysis** — quadrant breakdown, geographic extent, damage centroid, grid-cell clustering with Gini coefficient
7. **Restoration Plan & Crew Operations** — summary stats, all realism toggles with check marks, crew mobilization timeline by day, restoration milestones (1%–100%) with inter-milestone rate
8. **Hour-by-Hour Restoration Timeline** — tabular hour-by-hour progression with day/time-of-day, ASCII progress bars
9. **Crew Performance & Utilization Analysis** — full crew table (jobs, arrival, drive miles, customers, cust/hour, jobs/day), performance distribution stats, top/bottom 5, utilization metrics
10. **Cost Estimation & Labor Economics** — IBEW compensation structure, itemized cost breakdown (labor, per diem, travel, materials, overhead), cost ratios (per customer, per outage, per capita), fatigue/behavioral analysis
11. **Per-Town Individualized Breakdown** — summary table for all 29 towns, then detailed profiles with damage stats, restoration timeline (10%/50%/90%/100%), restoration rate
12. **Restoration Equity Analysis** — towns ranked by median restoration time, urban vs rural comparison with disparity ratio
13. **DOE OE-417 Comparative Analysis** — simulated vs historical comparison with customer/duration deltas and scale/speed ratios
14. **Network Vulnerability Assessment** — damage-to-capacity ratio per substation with severity labels, vegetation vulnerability corridors
15. **Full Dispatch Log** — expanded from 200 to 1,000 jobs with day/time-of-day columns
16. **Realism Model Parameters** — every parameter value with its source citation
17. **Data Sources & Provenance** — 15 sources with URLs and coverage notes
18. **Methodology Notes & Limitations** — grid generation, storm model, scheduler, customer impact, cost estimate methodology; 10 enumerated known limitations
19. **Appendix: Raw Configuration Dump** — full JSON of all toggle states and configuration

**Key decisions:**
- Added statistical helper functions (`avg`, `stddev`, `percentile`, `sorted`) and an ASCII bar-chart function (`bar()`) for inline visualizations
- Equity analysis compares urban (pop>30K) vs rural (pop≤15K) restoration times — flags disparity ratios >1.3× as equity concerns
- Cost model uses IBEW double-time rates ($100/hr effective) with per diem, mileage, and 15% overhead — conservative industry estimates
- Gini coefficient computed for spatial damage concentration analysis
- Report self-reports its own size in KB at the footer

---

## Phase — Wind-field weighted outage placement (June 2026)

**Goal:** Replace uniform outage placement with wind-field-weighted placement using the HURDAT2 storm tracks already loaded, so outages concentrate near the storm path proportional to wind speed.

**What was built:**

1. **Wind-field weighted segment sampling** — When a storm track is selected and the toggle is active, each network segment gets a weight computed as Gaussian spatial decay (σ=30 miles) × normalized wind speed from the nearest HURDAT2 track point. Binary search on a cumulative distribution enables O(log N) weighted sampling. Segments right on the track get 3–5× more outages than distant areas. A floor weight of 0.1 ensures distant segments still receive some outages (embedded failures, indirect wind effects).

2. **Toggle control** — New "Wind-field weighted placement" checkbox (amber styling) in the Storm section. Defaults to checked. Falls back to uniform placement when no storm track is selected or the toggle is off.

**Key decisions:**
- Gaussian σ=30 miles chosen as approximate TC wind field radius for CT-latitude storms (Hartford County is ~20mi across, so most of the county falls within 1σ of a track passing through the center).
- Wind speed normalized to 50 kt baseline — typical sustained wind for CT tropical storm impacts.
- Floor weight of 0.1 (not zero) prevents unrealistic "zero outages" in areas far from the track, since real storms cause embedded thunderstorms and indirect damage county-wide.
- Binary search on Float64Array cumulative weights for efficient weighted sampling even at 25K outages.

---

## Phase — Five realism features batch (June 2026)

**Goal:** Implement the remaining five recommended realism features: underground line model, switching/back-feed, AMI smart meter coverage, mutual-aid travel time, and deepened crew stickiness.

**What was built:**

1. **Underground line model** — Urban substations (NLCD canopy <25%) have ~40% of laterals modeled as underground. Underground segments have 90% immunity to storm damage (outages rejected during placement). Based on Eversource filings showing 35–45% underground penetration in Hartford, New Britain, and East Hartford urban cores.

2. **Switching / back-feed (FLISR)** — ~20% of feeder-level outages are auto-restored via normally-open tie switches in ~30 minutes without requiring a crew visit. These outages are marked `switch_restored` during storm simulation, their `popLoss` zeroed out, and they are pre-marked as `done` in the scheduler so no crew is dispatched. Based on Eversource distribution automation (Fault Location, Isolation, and Service Restoration) deployment in Hartford County.

3. **AMI smart meter coverage** — Replaces the flat 15% callback-lag model with spatially-varying outage detection based on Advanced Metering Infrastructure penetration. Urban areas (<25% canopy) have ~70% AMI with short detection delays (1–3h on 30% of laterals). Suburban (25–50% canopy) have ~50% AMI (2–5h on 50% of laterals). Rural (>50% canopy) have ~30% AMI (3–8h on 70% of all outages). Based on Eversource AMI deployment reports to CT PURA.

4. **Mutual-aid travel time** — Out-of-state mutual-aid crews in the second and third mobilization waves receive additional travel delays before they can begin work: MA/RI crews +2h, NY crews +4h, PA/OH crews +6h. The first wave (50% of crews, local Eversource) is unaffected. Based on IBEW mutual-aid protocols and Eversource Isaias after-action report documenting crew origin states.

5. **Deepened crew stickiness** — Previously a server-only toggle. Now implemented in the browser scheduler: each crew tracks its assigned feeder circuit (`crewFeederAssignment[]`). Once a crew picks up an outage on a feeder, it completes all remaining outages on that feeder before accepting work on a different circuit. When no more outages remain on its assigned feeder, the assignment clears and the crew reverts to nearest-outage dispatch. This addresses the advisor's main critique that the greedy scheduler unrealistically bounces crews between feeders.

**Key decisions:**
- Underground model uses NLCD canopy as a proxy for urbanization rather than actual underground infrastructure maps (which are CEII and not publicly available).
- FLISR rate set at 20% (conservative estimate — Eversource's actual FLISR coverage in Hartford County may be higher in areas with newer automation).
- AMI penetration rates are estimates; actual Eversource deployment data is not publicly available.
- Mutual-aid travel uses simplified state-based distance bands rather than actual drive times from specific staging areas.
- Crew stickiness uses O(N) linear scan per feeder-assignment check — acceptable for county-scale simulations but would need indexing for statewide scale.

---

## Phase — Deep report expansion (June 2026)

**Goal:** Make the simulation report substantially more in-depth, adding analysis sections that would typically require dedicated analytics infrastructure.

**What was added:**

1. **Section 7.5 — Overnight downtime analysis**: Quantifies cumulative crew idle time from 8PM–6AM clamping, shows customers still out at each nightfall with visual bars.

2. **Section 7.6 — Restoration speed by phase**: Breaks restoration into Emergency (0–24h), Surge (24–72h), Sustained (72–168h), Long-tail (168h+) phases with per-phase job counts, customer rates, and descriptions.

3. **Section 9.4 — Crew fatigue progression by day**: Day-by-day table showing active crew counts, average days on shift, fatigue band distribution (Fresh/Mid/Tired/Exhausted), and estimated productivity percentage.

4. **Section 9.5 — Drive distance analysis**: Total drive miles, per-crew and per-job averages, fuel consumption estimate (6 mpg bucket trucks), and fuel cost.

5. **Section 10.4 — Day-by-day cost breakdown**: Itemized daily costs showing jobs done, customers restored, active crews, labor cost, and cumulative cost with percentage.

6. **Section 10.5 — Mutual-aid cost premium**: Breakdown of the cost premium from out-of-state crews including per diem, travel-time labor, and mileage reimbursement.

7. **Section 12.2 — Tree-canopy equity**: Compares restoration times for high-canopy (≥50%) vs low-canopy (<30%) towns, computes disparity ratio.

8. **Section 12.3 — Critical-facility priority verification**: Validates that the scheduler's critical-facility priority actually resulted in faster restoration for critical outages vs non-critical.

9. **Section 14.3 — Flood corridor vulnerability**: Per-corridor breakdown (CT River, Park River, Hockanum, Farmington, Salmon Brook) of flood-zone outages.

10. **Section 14.4 — FLISR switching coverage analysis**: Per-substation switching effectiveness table, crew-hours and cost savings from automation.

11. **Section 14.5 — AMI detection coverage gaps**: Instant vs delayed detection stats, cumulative undetected customer-hours.

12. **Section 20 — Sensitivity analysis**: Factor sensitivity table (14 factors), crew count sensitivity curve with power-law model, IEEE reliability KPIs (SAIDI, SAIFI, CAIDI, ASAI).

13. **Section 21 — Executive summary**: Key findings with worst-hit town, automation impact, active realism factor count, and CEII disclaimer.

14. **Dispatch log expanded** from 1,000 to 2,000 entries.

15. **Table of contents** updated with all subsection references.

**Report now has 21 top-level sections with 35+ subsections.**

---

## Phase — Eversource real-data integration (June 2026)

**Goal:** Incorporate real Eversource CT reliability metrics and operational parameters from published sources to replace synthetic estimates with ground-truth values.

**Data sources investigated:**
- Eversource outage map (outagemap.eversource.com) — KUBRA Storm Center SC4 instance. All API endpoints return 403 Forbidden; real-time data not programmatically accessible.
- Eversource CT Reliability Scorecards (2025) — per-town data exists as PNG images, not machine-readable.
- RPA "State of the Grid in Connecticut" (2025) — SAIDI/SAIFI/peak load/generation mix data.
- Fox Weather smart switch coverage — 8,500 switches, 1.5M interruptions avoided/yr.
- Eversource CT Newsroom — ERP levels, 90% tree-cause rate, infrastructure stats.
- poweroutage.us, findenergy.com — blocked by 403 (bot protection).

**What was integrated:**

1. **`EVERSOURCE_CT` constants block** — 30+ real parameters including SAIDI (76.0 min 2021, 164.6 min statewide 2023), SAIFI (0.686/0.872), 1.3M customers, 23,000 mi distribution, 8,500 smart switches, 5-level ERP targets, peak loads, generation mix, investment figures.

2. **Tree-blocked rate: 30% → 90%** — Eversource states ">90% of storm outages caused by trees." The old 30% was a generic estimate. Now uses `EVERSOURCE_CT.treesCauseStorm`.

3. **FLISR switching rate: 20% → 42%** — Eversource reports 42% of outages restored within 5 minutes via smart switches. Now uses `EVERSOURCE_CT.restoredUnder5min`.

4. **Report section 13.2: ERP Level Classification** — Classifies each simulated event into Eversource's 5-level Emergency Response Plan (L5: 0-9% out, 1-3d → L1: 70-100% out, 18+d). Shows whether simulated restoration meets the ERP target.

5. **Report section 13.3: Eversource Published Benchmarks** — Side-by-side table comparing simulated SAIDI/SAIFI/CAIDI against real Eversource (2021) and CT statewide (2023) values.

6. **Report section 13.4: Eversource Infrastructure Summary** — Full infrastructure profile sourced from published data.

7. **Data sources updated** — 7 new source entries in the report's section 17 and in DATA_SOURCES.md (section 21).

**Key decisions:**
- Used 42% for FLISR rate during storms even though that's the all-conditions average — during major storms the rate is likely lower due to multiple concurrent faults overwhelming switching capacity. This is a known upper-bound estimate.
- Tree-blocked rate of 90% applies specifically to storm outages (not blue-sky), which is exactly what our simulation models.
- ERP level classification uses the simulated customer count against Eversource's full 1.3M CT base, not just Hartford County, since ERP levels are system-wide.

---

## Major open questions

1. **Should we calibrate against real Eversource outage data?** This was identified as the natural next research direction. Would require Eversource cooperation or PURA-filed records. Outcome: potentially publishable.

2. **MILP / constraint programming as a better scheduler?** Would beat the greedy baseline on optimization quality. Real research contribution if benchmarked properly.

3. **Pre-computed scenario library?** Identified as a near-term engineering fix for the "page freeze at max settings" complaint. Would let the most-common scenarios load instantly.

4. **Statewide scaling?** Documented but not implemented. Largest piece of remaining engineering work.

---
