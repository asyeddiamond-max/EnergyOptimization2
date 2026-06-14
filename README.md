# Hartford County Power-Grid Simulation

An interactive browser-based model of a synthetic electric distribution grid covering Hartford County, Connecticut, with a storm-outage simulator, a crew-restoration planner, an optimal-crew-count recommender, and GeoJSON / Esri Shapefile export. Built as a research and visualization tool — not a production utility-planning system.

---

## Try it live

[**Open the full simulation →**](https://asyeddiamond-max.github.io/EnergyOptimization2/03_grid_simulation.html)

No install required. Works in any modern browser — sliders, map, storm simulation, restoration plan, and GIS export all run client-side.

Two lighter standalone previews (single SVG, no Leaflet basemap, no server needed):
- [**Grid + storm preview →**](https://asyeddiamond-max.github.io/EnergyOptimization2/03_grid_inline_preview.html) — substations and storm-outage shading
- [**Restoration preview →**](https://asyeddiamond-max.github.io/EnergyOptimization2/03_restoration_inline_preview.html) — adds the crew scheduler with depots and numbered repair circles

---

## Repository layout

```
.
├── 01_fetch_county_boundary.py    # cache Hartford polygon from OSM
├── 02_fetch_town_boundaries.py    # cache the 29 town polygons from OSM
├── 03_grid_simulation.html        # the main interactive (run via local server)
├── 03_grid_inline_preview.html    # standalone SVG preview: grid + storm
├── 03_restoration_inline_preview.html  # standalone SVG preview: + scheduler
├── 04_geojson_to_shapefile.py     # offline GeoJSON to shapefile converter
├── 05_generate_artifacts.py       # produce matplotlib PNG snapshots in output/
├── data/                          # cached OSM inputs (committed)
├── docs/                          # extended notes
├── output/                        # generated artifacts (mostly committed)
│   ├── 03_grid_simulation.html    # copy of the live interactive
│   ├── 03a_county_topology.png    # county outline + 29 towns + centroids
│   ├── 03b_synthetic_grid.png     # adds substations, feeders, laterals
│   ├── 03c_grid_outages.png       # adds a 500-outage storm
│   ├── 03d_restoration_plan.png   # adds 10 crews with numbered repairs
│   ├── 03e_outage_curve.png       # customers without power vs hours
│   ├── 03f_substations_on_county.png  # clean substations-only reference
│   └── exports/                   # user GeoJSON / shapefile bundles (gitignored)
├── source/                        # readable .txt mirrors of the HTML/JS
├── SCALING.md                     # roadmap to statewide CT scaling
├── LICENSE
└── requirements.txt               # geopandas (for 04), matplotlib (for 05)
```

Each numbered file is a self-contained step. Run them in order the first time, or just open `03_grid_simulation.html` directly (the cached data in `data/` is committed so you don't need 01/02 unless you want to refresh from OSM).

### Regenerating the artifacts in output/

The repo ships with pre-generated PNG snapshots in `output/` so you can see what the simulation produces without running anything. To regenerate them:

```
pip install matplotlib numpy
python 05_generate_artifacts.py
```

Outputs are deterministic at seed 42, so re-running produces bit-identical files.

---

## What this is

A single self-contained HTML file (`03_grid_simulation.html`) plus cached OSM data (`data/hartford_boundary.json` and `data/hartford_towns.js`). It runs entirely in the browser using Leaflet and a CARTO basemap. No backend, no database, no build step.

When you open it, the model:

1. Loads the real Hartford County boundary from OpenStreetMap (cached locally).
2. Loads the real outlines of all 29 Hartford County towns (cached locally).
3. Places `N` synthetic substations across the county using a hybrid of population-weighted and area-weighted k-means clustering.
4. Generates a synthetic distribution network — colored feeder backbones radiating from each substation, plus gray laterals branching from the feeders.
5. On demand, simulates a storm that knocks out `M` random points across the network, flags ~2% as critical-facility sites, and counts the customers affected.
6. On demand, plans a restoration: assigns repair crews from depots, computes the total time, and optionally models real-world delays (damage assessment, overnight downtime, tiered priority).
7. On demand, recommends the smallest crew count that gets restoration within 15% of the theoretical minimum.
8. On demand, exports the entire scenario (grid + storm + plan + manifest) as a GeoJSON zip or a real Esri shapefile bundle.

Every random choice is controlled by a single integer seed, so any given configuration is fully reproducible.

---

## Realistic mode

A new yellow toggle at the top of the sidebar (just under the seed) controls whether the simulation uses a "perfectly-coordinated theoretical operation" model or one calibrated against published Eversource storm-after-action reports. **The toggle is ON by default.**

When realistic mode is **on**:

| Real-world factor | What the model now does |
|---|---|
| Damage assessment | All crews stay at depot for the first **12 hours** while the utility surveys the network. No repairs happen during this window. |
| Workday vs. night ops | Each "day" is **14 work hours** (6 am – 8 pm). When a crew's running clock crosses 8 pm, it pauses overnight and resumes the next morning at 6 am. Real utilities suspend most pole-and-wire work after dark for safety. |
| Per-outage repair time | Bumped from 1.5 h to **3 h** to include diagnosis, repair, and re-energization verification. |
| Crew travel speed | Dropped from 30 mph to **25 mph** to reflect storm debris, detours, and reduced visibility. |
| Sectionalizers | Per-outage customer loss is **halved**. Real protective devices isolate only the segment between two switches rather than killing the whole downstream branch. |
| Critical-facility priority | ~**2% of outage locations are tagged "critical"** (hospitals, fire stations, water plants, etc.). The scheduler completes every critical-tier outage before touching anything else. On the map these render as larger, yellow-outlined markers. |

When realistic mode is **off**, the original simplified model runs — 1.5 h repairs, 30 mph travel, 24/7 crews, no assessment delay, no tiering, full downstream loss per outage. Useful as the "best-case theoretical floor" you'd compare reality against.

**Order-of-magnitude effect on a 5,000-outage Sandy-scale storm:**
- *Optimistic baseline (off):* ~9–15 hours to full restoration
- *Realistic mode (on):* ~3–5 days to full restoration — within range of the 2–7-day public Eversource reports for major storms.

---

## Goals

1. **Make grid-resilience problems visible and interactive.** Most power-system research lives in textbooks, MATLAB scripts, or proprietary utility software. The goal here is to give anyone with a browser a way to *play* with substation counts, storm severity, and crew counts, and watch the impact numbers move.

2. **Provide a transparent, reproducible baseline.** Because the entire grid + storm + plan is regenerated from a seed and a handful of sliders, two people running the same configuration get identical results. Reproducibility matters for research and for sharing scenarios.

3. **Honestly separate what's real from what's synthetic.**
   - **Real:** the Hartford County boundary, the 29 town polygons, town centroids, and 2020-census populations.
   - **Synthetic:** every substation, feeder, lateral, outage location, and crew depot. Real distribution-network topology is not public information.

4. **Lay the groundwork for outage-optimization research.** The current simulation answers descriptive questions: *if a storm hits, how many customers go dark, and how long does restoration take with N crews?* The next step (see `SCALING.md`) is normative.

5. **Be portable.** A single HTML file + a few JSONs. No npm. No Docker. No login. You can email it to a collaborator, post it on a class website, or run it offline.

---

## What is an "outage location"?

An **outage location** is a single point on the synthetic distribution network where a fault has occurred — a downed wire, a fallen tree on a feeder, a blown transformer. Each outage is:

- A **point in space** (lat, lon) sampled uniformly along a randomly chosen line segment, weighted toward laterals (which represent more total miles of line in the county than backbone feeders).
- **Attached to a parent segment**: each outage carries an attribute saying it lives on feeder `fi` or lateral `li`. That's what the GIS exports preserve so downstream analysts can join outages back to network topology.
- **Associated with a population loss** equal to the affected segment's share of its parent feeder's customer base. If a feeder serves 5,000 customers across 10 lateral branches, taking down one of those laterals drops ~500 customers.

Each outage is also a **work order** the restoration scheduler must assign to a crew. The restoration plan visits every outage location in some order, with each visit consuming `1.5 h + travel_time` of a crew's day.

The storm-outages slider lets you place from 50 to **25,000** outage locations across the county. For reference:
- 50–200 outages ≈ a typical thunderstorm or minor weather event.
- 500–2,000 outages ≈ a significant storm.
- 5,000–10,000 outages ≈ a tropical storm (Isaias 2020 in CT was around this scale).
- 15,000–25,000 outages ≈ a major-disaster scenario (Sandy 2012 was past 25K in southern New England).

The cap is generous — the synthetic network has tens of thousands of segments, so a 25K-outage storm leaves no segment untouched. Beyond that, outages start colliding with each other.

To keep 25,000 markers fast to pan, outage rendering switches to Leaflet's Canvas backend instead of SVG.

---

## How to run it

The HTML uses `fetch()` to load the boundary polygon, so you need a tiny web server (not a `file://` open). Pick whichever you have installed:

| Tool | Command (run from the project folder) |
|------|---------------------------------------|
| Python | `python -m http.server 8000` |
| Node.js | `npx serve .` |
| PHP | `php -S localhost:8000` |
| VS Code | Install the "Live Server" extension, right-click the HTML, "Open with Live Server" |

Then open `http://localhost:8000/03_grid_simulation.html` in any modern browser.

External CDN dependencies (auto-loaded at runtime — nothing to install):
- **Leaflet 1.9.4** — the map library
- **CARTO basemap tiles** — the soft-gray background
- **JSZip 3.10.1** — for bundling the GeoJSON / shapefile exports
- **shp-write 0.3.1** — for writing shapefile bytes in the browser

---

## Every control, explained

The sidebar is laid out top-to-bottom as a workflow: seed → grid → storm → restoration → export. Each section either configures the model or shows results.

### Random seed (yellow callout at the top)

A single integer that controls *every* random choice in the model: where substations land, where feeders branch, where the storm strikes, and where crew depots sit. Same seed + same sliders = bit-identical output every time, across reloads and across machines.

**Why seed and storm-outages are separate sliders:** the *number* of outages comes from the slider; the *positions* of outages come from the seed. Changing the slider gives you a different storm intensity at the same locations (within the network). Changing the seed re-rolls everything.

### Section 1 · Distribution grid

| Control | Range | Meaning |
|---------|-------|---------|
| Substations slider | 20 – 300 (default 100) | How many synthetic substations to place. Higher = denser coverage, smaller service areas, less population per substation. |
| Feeders / substation slider | 3 – 10 (default 5) | How many backbone feeder circuits radiate from each substation. More feeders = more redundancy and more total miles of medium-voltage line. |
| **Generate distribution grid** button | — | Runs the k-means placement and the network builder. Re-renders the grid in well under a second at k=100. |

### Section 2 · Storm simulation

| Control | Range | Meaning |
|---------|-------|---------|
| Storm outages slider | 50 – 25,000 (default 500) | How many failure points to scatter across feeders and laterals. |
| **Simulate storm** button | — | Places the outages and computes downstream customer impact. |
| Customers without power (red stat) | computed | Sum of population on disabled segments, capped at county population. |
| Outage locations (orange stat) | computed | Number of damaged points the crews will need to visit. |

### Section 3 · Restoration plan

| Control | Range | Meaning |
|---------|-------|---------|
| Repair crews slider | 1 – 5,000 (default 10) | Number of independent two-person line crews available. |
| **Plan restoration** button | — | Runs the scheduler: assigns each crew to outages using an earliest-free + nearest-outage greedy. |
| Total restoration time (green stat) | computed | `max(crew.finish_time)` across all crews — when the last customer gets power back. |
| **Find optimal crew count** button | — | Binary-searches for the smallest crew count that gets restoration within 15% of the theoretical floor. |
| Recommended crews (yellow stat) | computed | The result of the search, with a one-click **Apply to slider** that re-runs the plan with that count. |
| **Reset storm** button | — | Clears storm and restoration state without touching the grid layout. |

### Section 4 · Export

| Control | Output |
|---------|--------|
| **Download GeoJSON** | Zip with one GeoJSON FeatureCollection per layer (`substations.geojson`, `feeders.geojson`, `laterals.geojson`, `outages.geojson`, `restoration_plan.geojson`) plus a `manifest.json` recording every input parameter. |
| **Download Shapefile (zip)** | Multi-layer Esri shapefile bundle — `.shp`/`.shx`/`.dbf`/`.prj` per layer, organized into subfolders. CRS = WGS84 (EPSG:4326). |

Both files reuse the same underlying data; pick whichever your downstream tooling expects.

---

## Visual conventions on the map

Once a scenario is generated, the map carries the following layers (bottom-up):

| Layer | What you see | What it means |
|-------|--------------|---------------|
| CARTO light basemap | soft gray streets and labels | Geographic context |
| Town boundaries | thin green outlines | The 29 Hartford County towns (real OSM data) |
| County boundary | bold red outline | Hartford County boundary (real OSM data) |
| Laterals | thin gray polylines | Synthetic distribution laterals |
| Feeders | colored polylines | Synthetic feeder backbones, color = parent substation |
| Substations | colored stars | Synthetic substations, color from the palette |
| Outages | small dark red dots | Storm-induced failure points (Canvas rendered) |
| Crew depots | colored squares with a black border | Crew home bases, color = crew identity |
| Repair jobs | numbered colored circles (first 30 per crew) and small colored dots (after that) | Assigned outages, the number is the order in which that crew handles them |

Hovering over a substation or town shows a tooltip with its identifier or name.

---

## Architecture & in-memory data flow

The model maintains a few JavaScript arrays as the "world state." Every button mutates or reads them; every visual element is derived from them.

```
TOWNS (constant, 29 entries: name, lat, lon, pop)
        │
        ▼
buildDemandPoints(seed) ───► demand[] = town clusters + uniform-area samples
        │
        ▼
kmeans(demand, k) ───► substations[] = {lat, lon, color, popServed}
        │
        ▼
generateGrid() ─┬─► feeders[] = {subIdx, pts[], color, popServed}
                └─► laterals[] = {feederIdx, pts[], popServed}
        │
        ▼
simulateStorm(N) ───► storm.outages[] = {lat, lon, kind, fi|li, popLoss}
        │
        ▼
planRestoration(M) ───► plan.crews[] = {depot, color, jobs[], time}
```

Each of these arrays is what the GeoJSON / Shapefile exports serialize to disk — see `buildFeatureCollections()` in the source.

---

## Algorithms, explained

### Weighted k-means substation placement

Each town spawns a cluster of "demand points" — small jittered samples around its centroid, the count proportional to √population. On top of that, ~1,200 uniformly-sampled points spread across the county polygon contribute another ~35% of total weight. The mix encourages substations to cluster where people live *and* still reach rural corners.

K-means then runs with:
- **k-means++ seeding** (weighted by min-distance², for diversified initialization).
- **Squared-Euclidean lat/lon distance** — no trig in the inner loop, ~5x faster than haversine while preserving nearest-cluster ordering.
- **15 Lloyd iterations** on flat `Float64Array`s for cache efficiency.
- A **centroid-snap step** at the end of each iteration: if a centroid drifts outside the county (using the precomputed inside-county bitmap), it's snapped back to the nearest demand point.

### Feeder and lateral generation

For each substation:
- 3–10 **feeder backbones** radiate outward as random walks (8–16 segments each, ~0.4–1 km per segment). Each backbone is colored by its parent substation.
- From each backbone, 4–8 **laterals** branch off at midpoints as shorter random walks (3–7 segments each, ~150–400 m per segment).
- Every step is clipped to the county polygon — when the walk leaves Hartford County, that branch stops.

The inside-county check is accelerated by a 256×256 boolean **bitmap** precomputed once at boot. Each cell stores whether its center is inside the polygon, reducing per-step checks from O(P) ray-casts (P ≈ 800 polygon vertices) to O(1) array lookups.

### Storm placement

The storm picks `N` random line segments (weighted toward laterals since they make up the bulk of network mileage), and for each picks a uniform random point along that segment. Population loss per outage = the segment's share of its parent feeder's customer base. The seeded PRNG means the same `(seed, N)` always produces the same exact outage locations.

### Restoration scheduler

The fast scheduler that supports up to 5,000 crews:

1. **Depot placement:** for M ≤ 200 crews, depots come from a k-means on the outage locations themselves. For M > 200, depots are seeded by cycling through the outage points (k-means at that scale would dominate runtime).
2. **Min-heap of (finish_time, crew_idx):** popping the next-free crew is O(log M).
3. **Each crew's turn:** linear scan over remaining outages to find the closest (squared lat/lon distance). The actual mile distance is computed once at assignment for the travel-time math.
4. **Job time:** `eta = crew.time + dist/30 mph + 1.5 h repair`. Travel speed and repair time are constants — tunable in code.
5. **Termination:** when all outages are assigned. Total restoration time = `max(crew.time)` across all crews.

Complexity: O(N · (log M + N_remaining)). At N=5,000 outages and M=5,000 crews this finishes in ~50 ms.

### Optimal crew count recommendation

"Optimal" here means the smallest crew count whose restoration time is within **15% of the theoretical floor**.

- **Floor:** `scheduleOnly(N)` — one crew per outage, no queueing. This is the practical lower bound; beyond M=N, extra crews are idle.
- **Search:** binary search over M ∈ [1, N], evaluating the scheduler at each midpoint until the smallest M satisfying `t(M) ≤ floor × 1.15` is found.
- **Cost:** ~⌈log₂ N⌉ scheduler runs, each O(N²) = ~50 ms at N=5,000 → whole search in well under a second.

Tweak the tolerance by editing `const tolerance = 1.15;` in `recommendCrewCount()`.

---

## Performance notes

| Pipeline stage | Hot path | Optimization |
|----------------|----------|--------------|
| Inside-county check | per-segment polygon ray-cast | 256×256 precomputed bitmap → O(1) lookup |
| K-means distance | inner loop over k centroids | Squared lat/lon (no sin/cos/sqrt) on `Float64Array` |
| Feeder/lateral walks | thousands of segments | Bitmap inside-check + tight typed-array loops |
| Storm outage placement | uniform random along segments | O(N) linear pass, no per-storm rebuilding |
| Restoration scheduler | nearest-outage from current crew | Min-heap on crew time + `Uint8Array` done-flag (no `splice`) |
| Outage rendering | up to 25,000 markers | Leaflet Canvas renderer (`L.canvas()`) instead of SVG |
| Repair-job rendering | up to ~5,000 numbered icons | SVG `divIcon`s. Limit yourself if you go past ~10,000 jobs. |

Typical end-to-end timing at the defaults (k=100, 500 outages, 10 crews): grid generation ≈ 150 ms, storm ≈ 30 ms, plan ≈ 25 ms, recommendation ≈ 200 ms.

---

## What's modeled vs. abstracted

This is *not* a power-flow model. It does not solve Kirchhoff's laws, model voltage sag, fault currents, or protection coordination. It treats the grid as a topological tree: customers attach to laterals, laterals attach to feeders, feeders attach to substations. A failure anywhere along a branch disconnects everything downstream.

This is also *not* a true facility-location optimization. The substations are placed by k-means clustering for visual realism and reasonable spatial coverage, not to minimize a real objective like capacity-constrained customer-minutes-out under N-1 contingency.

What it *does* model reasonably:
- Population-weighted demand distribution
- Approximate spatial extent of a distribution network
- Customer counts affected by random failure points
- Crew scheduling with realistic travel and repair-time parameters

What you should **not** do:
- Don't show the feeder routes to anyone and tell them it's Eversource's grid. It isn't.
- Don't use the restoration time estimate to make planning decisions for a real utility — it's calibrated only to the orders of magnitude reported in public storm-after-action reports.

---

## Exporting to GIS formats (GeoJSON, Shapefile)

Section 4 of the sidebar saves the current scenario for use in QGIS, ArcGIS, geopandas, R `sf`, or any standard GIS tool.

**Download GeoJSON** → a zip with five GeoJSON FeatureCollections (one per layer) plus a `manifest.json` recording the seed and all slider positions. Use this for web tools and Python pipelines.

**Download Shapefile (zip)** → a multi-layer Esri shapefile bundle (`.shp`/`.shx`/`.dbf`/`.prj`) organized into subfolders per layer. CRS is WGS84 (EPSG:4326). Use this for ArcGIS Pro and utility GIS workflows.

Attribute schema (kept under the 10-character shapefile column-name limit):

| Layer | Geometry | Columns |
|-------|----------|---------|
| `substations` | Point | `sub_id`, `lat`, `lon`, `pop_serv`, `n_feeders`, `color_hex` |
| `feeders` | LineString | `feed_id`, `sub_id`, `pop_serv`, `length_km`, `color_hex` |
| `laterals` | LineString | `lat_id`, `feed_id`, `pop_serv`, `length_km` |
| `outages` | Point | `out_id`, `seed`, `kind`, `feed_id`, `lat_id`, `pop_loss` |
| `restoration_plan` | Point | `job_ord`, `crew_id`, `out_id`, `eta_h`, `depot_lat`, `depot_lon` |

If the in-browser shapefile path ever fails (CDN block, etc.), download the GeoJSON zip and convert offline:

```bash
pip install geopandas
python 04_geojson_to_shapefile.py path/to/hartford_grid_seed42_*.zip
```

The script writes a `<input>_shp/` folder next to the input with all the shapefiles. Same column schema either way.

---

## Files in this project

See the top-of-README "Repository layout" section. In short: numbered scripts at the root, cached OSM data in `data/`, generated artifacts in `output/`, readable code mirrors in `source/`, extended docs in `docs/`, plus `SCALING.md` and this `README.md` at the root.

---

## Acknowledgments

- **OpenStreetMap contributors** — county boundary and town polygons (ODbL license)
- **CARTO** — gray basemap tiles
- **Leaflet** — map rendering
- **JSZip and shp-write** — GIS-format export libraries
- **US Census Bureau** — town population data (2020 decennial census)

## License

MIT-style — do whatever you want with the code; please don't represent it as utility-source data.
