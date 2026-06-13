# Scaling Roadmap — From Hartford County to Statewide Connecticut

This document is the plan for two related upgrades:
1. Export the current in-browser simulation to **standard GIS file formats** (GeoJSON and Esri Shapefile) so the synthetic grid can be opened in QGIS, ArcGIS, R, Python (geopandas), etc.
2. Scale the model **from one county to all eight Connecticut counties** (or, equivalently, all nine 2022-era Planning Regions), eventually treating Connecticut as a single statewide model.

These two goals reinforce each other. Once we can serialize the grid to a shapefile, scaling to more geography is mostly a matter of repeating the same pipeline over more polygons.

---

## Part 1 — Export to GeoJSON and Shapefile

### Why both formats

| Format | Pros | Cons |
|--------|------|------|
| GeoJSON | Web-native, human-readable, no external libraries needed to write | Larger files, slow at scale, no built-in attribute typing |
| Shapefile | The de-facto standard in utility GIS, ArcGIS first-class support, indexed for fast spatial queries | Multi-file (`.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`), 2 GB / 255 column limits, attribute names capped at 10 chars |

The simulation currently holds the grid in plain JavaScript arrays:
- `substations` — array of `{lat, lon, color, popServed}`
- `feeders` — array of `{subIdx, pts: [[lat,lon],...], popServed, color}`
- `laterals` — array of `{feederIdx, pts: [[lat,lon],...], popServed}`
- `storm.outages` — array of `{lat, lon, kind, fi, li, popLoss}`
- `plan.crews[].jobs` — array of repair-job assignments per crew

Each of these maps cleanly onto a GIS feature layer.

### Step 1.1 — Add a "Download GeoJSON" button

Smallest change. Serialize the in-memory arrays as a FeatureCollection per layer (substations as Points, feeders as LineStrings, laterals as LineStrings, outages as Points). Wire a button in the sidebar that builds a `Blob`, calls `URL.createObjectURL`, and triggers a download.

A single zip with five GeoJSON files (`substations.geojson`, `feeders.geojson`, `laterals.geojson`, `outages.geojson`, `restoration_plan.geojson`) is enough for most downstream uses. JSZip can build the archive in-browser.

This unlocks immediate compatibility with QGIS, geopandas, R `sf`, Mapbox, kepler.gl, and Felt.

### Step 1.2 — Convert GeoJSON to Shapefile

Two paths:

**(a) Server-side conversion (recommended for clean results).** Add a tiny converter script outside the browser:
```python
import geopandas as gpd
gpd.read_file("substations.geojson").to_file("substations.shp", driver="ESRI Shapefile")
```
Wrap in `make.py` or a GitHub Action so collaborators can drop a GeoJSON in and get a zipped shapefile back.

**(b) In-browser conversion using `shp-write` or `shpjs`.** These npm packages can write shapefile bytes directly from a GeoJSON FeatureCollection. Trade-off: bundle size grows from a few KB to a few hundred KB, and shapefile attribute-naming caveats become the user's problem.

Either way, the metadata file (`.prj`) should declare EPSG:4326 (WGS84 lat/lon), matching what the browser stores.

### Step 1.3 — Attribute schema (per layer)

Define stable column names ahead of time so downstream users have a contract:

**substations.shp**
| Column | Type | Description |
|--------|------|-------------|
| sub_id | int | Unique 1..N |
| lat, lon | float | Centroid |
| pop_serv | int | Estimated customers served |
| n_feeders | int | Outgoing feeder count |
| color_hex | str | Display color from palette |

**feeders.shp**
| Column | Type | Description |
|--------|------|-------------|
| feed_id | int | Unique |
| sub_id | int | Foreign key to substation |
| n_segs | int | Number of vertices |
| length_km | float | Computed haversine length |
| pop_serv | int | Customers downstream of this feeder |

**laterals.shp**
| Column | Type | Description |
|--------|------|-------------|
| lat_id | int | Unique |
| feed_id | int | Parent feeder |
| length_km | float | |
| pop_serv | int | |

**outages.shp** (one row per failure point)
| Column | Type | Description |
|--------|------|-------------|
| out_id | int | |
| seed | int | The reproducibility seed |
| feed_id | int | (-1 if on a lateral) |
| lat_id | int | (-1 if on a feeder) |
| pop_loss | int | |

**restoration_plan.shp** (one row per repair job)
| Column | Type | Description |
|--------|------|-------------|
| job_ord | int | 0-based order in crew's queue |
| crew_id | int | |
| out_id | int | Foreign key to outage |
| eta_h | float | Hours from t=0 to completion |

### Step 1.4 — Stable identifiers across reruns

Once a configuration is committed to a shapefile, the sub_id / feed_id / lat_id assignments should be deterministic for the same (seed, k, feeders-per-sub) tuple. The in-memory model already is, because everything flows from one seeded PRNG. The only step needed is to expose the seed and the input parameters as **dataset-level metadata** — write them into a `manifest.json` that ships alongside the shapefiles. That's enough for anyone to regenerate the exact same dataset later.

---

## Part 2 — Scaling Hartford → All of Connecticut

The simulation was scoped to one county because that's a tractable demo size. Scaling to the whole state is mostly a data and performance problem, not a modeling-logic problem.

### Step 2.1 — Replace hard-coded TOWNS with a data file

Currently `TOWNS` is a hand-coded array of 29 Hartford-County towns with lat/lon/pop. To go statewide we need all 169 CT towns. Pull from:

- **US Census Bureau TIGER/Line Shapefiles** → `cb_2022_09_cousub_500k.shp` covers all CT county subdivisions (towns).
- **2020 Decennial Census** → table P1, "Total Population," joined by GEOID.

Output: `connecticut_towns.geojson` with one feature per town carrying `name`, `pop2020`, `county`, `centroid_lat/lon`, `boundary`. Load it at boot with `fetch()`.

This single data swap takes the model from a 940k-customer county to a ~3.6M-customer state.

### Step 2.2 — Replace the single county polygon with all 8 county polygons

The current `hartford_boundary.json` is one feature. For statewide we want the eight CT counties (or the nine post-2022 Planning Regions, which Connecticut now uses instead of counties for most purposes). Sources:
- **CT GIS Open Data Portal** → "CT Counties" or "CT Planning Regions" shapefiles, both EPSG:2234 (CT State Plane). Reproject to EPSG:4326 for the browser.
- Or pull from OpenStreetMap relations: each Planning Region is a `boundary=administrative` relation.

The inside-county point-in-polygon test generalizes naturally — just iterate over all eight polygons. The inside-bitmap accelerator (currently 256×256 over one county's bbox) becomes 1024×1024 over the state's bbox to keep cell resolution comparable.

### Step 2.3 — Per-county sub-models, joined at the state level

A naïve scale-up (one giant k-means over 3.6M customers spread across CT) gets slow and produces less-realistic clusters. Better:

- **Run the existing pipeline once per county/region.** Each produces its own substations + feeders + laterals.
- **Pre-compute totals per region** so the sidebar shows a "Selected region" dropdown and the stats reflect only the selected scope (or the whole state).
- **Allow inter-region transmission lines** to be added as a thin top-level layer, sourced from the OSM `power=line` data we already have cached.

This decomposition keeps each k-means run small, lets users explore one region at a time, and gives us the option to later add inter-region tie capacity to the outage model (so a substation failure in one region can be partly compensated from a neighbor).

### Step 2.4 — Performance budget at statewide scale

Rough sizing for an "Eversource-coverage" statewide model:
- ~700 substations (5x Hartford)
- ~3,500 feeder backbones
- ~25,000 laterals
- ~50,000 outages in a Sandy-class storm

Hot paths and their fixes:

| Hot path | Today (county) | At state scale | Mitigation |
|----------|---------------|----------------|------------|
| K-means | 1,800 pts × k=100, OK | ~12k pts × k=700, ~50x slower | Per-region k-means; cap k per region |
| Feeder/lateral generation | ~25k polyline segments | ~140k segments | Already O(n); bitmap inside-test stays O(1) |
| Storm outage placement | Pick from segment array | Same algorithm, 5x array | Fine; segment-array indexing is O(1) |
| Restoration greedy | O(M·N²) where N=outages | At N=50k, becomes 50k² × M | **Needs spatial bucketing** (k-d tree on outage locations) → O(M·N·log N) |
| Leaflet rendering | ~25k polylines, ~5k markers | ~150k polylines, ~50k markers | Switch to **Canvas renderer** (`L.canvas()`) and **`L.markercluster`** for the marker layers |

The single biggest change for statewide is the restoration scheduler. Greedy "earliest-completion" with no spatial index is fine at 5,000 jobs and becomes the bottleneck at 50,000. A k-d tree query for "nearest unrepaired outage to crew C" cuts the inner loop from O(N) to O(log N) per step.

### Step 2.5 — Better demand modeling than town centroids

Town centroids work as a starting point but blur within-town variation. Once we're statewide, the same effort spent on five-county zooming would pay better dividends spent on finer demand:

- **Census block groups** (~200,000 in CT, average population ~180) give realistic intra-town distribution. TIGER provides geometry; ACS gives population.
- **Eversource Hosting Capacity Map** publishes circuit-level load profile data for solar interconnection studies. It's not the full circuit map, but the per-feeder peak loads it provides are a real calibration target.
- **Building footprints from Microsoft Open Buildings** or **OSM** can act as a customer-count proxy in rural areas where census-block-group resolution is coarse.

Wiring any of these in is a `fetch()` call and a re-weighting of the demand-point loop — no architectural change.

### Step 2.6 — A real outage model worth using

The current "outage hits a random segment, kills its share of customers" is fine for visualization but doesn't model:
- **Spatial correlation** — real storms have spatial structure (a tree falls on circuit A, then five more fall within 200 m). Implement by sampling outage locations from a Cox process (Poisson with intensity proportional to local tree-canopy density × local wind exposure).
- **Cascading failures** — distribution circuits sometimes lose voltage support and trip neighbors. Adds a Markov-chain layer; out of scope for a synthetic model unless calibrated to real outage reports.
- **Customer-minutes-out (CMO)** — the standard reliability metric, integrating affected-customer × outage-duration. Once restoration scheduling is in, computing CMO is a one-line postprocess. It would make optimization runs (Part 3) directly comparable to public utility reports.

### Step 2.7 — Crew logistics

At the county scale, crews drive 30 mph in a straight line. At the state scale, that's clearly wrong: I-84 is 65 mph, rural Route 169 is 35 mph. Two paths:

- **Cheap fix:** weight the travel time by a road-density proxy from OSM (`highway=motorway` segments along the straight line → multiply speed).
- **Proper fix:** offload the travel time to a real routing engine. OSRM and Valhalla both run as Docker containers, ingest OSM data, and give isochrone / matrix queries. The simulation would precompute a depot-to-outage time matrix at boot.

The proper fix is more work but pays off later: once routes are real, the restoration plan can also account for mutual-aid crews arriving from out of state along specific corridors.

---

## Part 3 — What scaling enables

Once Parts 1 and 2 are done, several research questions become directly testable inside this same UI:

1. **Where should new substations go statewide to minimize expected customer-minutes-out?** Run the storm simulator over a Monte Carlo ensemble of 1,000 storms, sum CMO, and use that as an objective for facility-location optimization. Cheap to do once outage modeling is calibrated.

2. **How does crew pre-positioning policy interact with optimal substation placement?** With realistic travel times (Step 2.7) and Monte Carlo storms, you can compare "all crews depot in Hartford" vs. "crews pre-positioned at the eight county seats" head-to-head.

3. **How does community resilience change when you add N microgrids?** Treat a microgrid as a substation-with-island-mode capability — during outage, its served customers stay up. Adding a slider for "microgrid count" and re-running the impact stats answers the question quantitatively.

4. **What's the marginal value of one more crew?** Sweep the crew slider, hold seed constant, plot total restoration time. Inflection points tell utilities where the next crew dollar stops paying off — useful for state-level emergency planning.

None of these require leaving the browser. The current architecture — pure client-side, seeded, reproducible — was chosen specifically to make these research uses cheap to run on a laptop.

---

## Suggested execution order

1. **Week 1:** Add GeoJSON download button (Part 1.1). Easy win, enables downstream use immediately.
2. **Week 2:** Add `manifest.json` metadata so reruns are bit-identical (Part 1.4).
3. **Weeks 3–4:** Server-side GeoJSON-to-Shapefile converter; document the attribute schema (Parts 1.2, 1.3).
4. **Weeks 5–6:** Replace hard-coded TOWNS with a data-driven `connecticut_towns.geojson` and let the user toggle a region (Parts 2.1, 2.2). Still per-region under the hood — single-county runs work the same.
5. **Weeks 7–8:** Per-region orchestration and statewide totals (Part 2.3). UI shows region selector.
6. **Weeks 9–10:** Performance pass — Canvas renderer, marker clustering, k-d tree restoration (Part 2.4).
7. **Months 3–4:** Real demand data (Step 2.5) and storm correlation (Step 2.6) when the visualization story is solid.
8. **Months 5+:** Real travel times via OSRM/Valhalla (Step 2.7), Monte Carlo optimization experiments (Part 3).

This sequencing prioritizes shippable artifacts at every step: anyone can use the work at the end of any phase.
