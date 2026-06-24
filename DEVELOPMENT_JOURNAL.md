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

## Major open questions

1. **Should we calibrate against real Eversource outage data?** This was identified as the natural next research direction. Would require Eversource cooperation or PURA-filed records. Outcome: potentially publishable.

2. **MILP / constraint programming as a better scheduler?** Would beat the greedy baseline on optimization quality. Real research contribution if benchmarked properly.

3. **Pre-computed scenario library?** Identified as a near-term engineering fix for the "page freeze at max settings" complaint. Would let the most-common scenarios load instantly.

4. **Statewide scaling?** Documented but not implemented. Largest piece of remaining engineering work.

---
