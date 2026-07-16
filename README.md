# Connecticut Power-Grid Resilience Simulation

A browser-first, server-augmented interactive simulator for distribution-grid storm restoration across the entire state of Connecticut. Models up to 25,000 outages and 5,000 crews per scenario in under a second, with seven realism factors, a calibration framework for future tuning against real Eversource data, customer-impact-weighted dispatch, and Monte Carlo ensemble analysis.

Designed as a research instrument for the **restoration side** of the distribution-grid resilience problem — a downstream complement to the UConn Eversource Energy Center group's outage-prediction work.

---

## Try it live

[**Open the simulator →**](https://asyeddiamond-max.github.io/EnergyOptimization2/03_grid_simulation.html)

The server backend at `hartford-grid-server.onrender.com` is auto-detected by the page. The simulator runs entirely in the browser as a fallback if the server is offline.

- [`/health`](https://hartford-grid-server.onrender.com/health) — server health check
- [`/version`](https://hartford-grid-server.onrender.com/version) — running commit + backend mode

---

## What's in the simulator

| Capability | How |
|---|---|
| Real statewide Connecticut distribution grid | 299 HIFLD substations across all 8 counties, branching feeders + laterals, census-tract-weighted demand (883 tracts) |
| Weather/customer-weighted outage locations | Browser Worker combines HRRR wind and rain, census customer exposure, Gaussian smoothing, and the live network; default is 2,000 unique points × 50 customers |
| Realistic-mode scheduler with seven factors | assessment delay, log-normal repair, discovery ramp, mutual-aid waves, road proxy, workday clamp, critical priority |
| Real critical facilities (HIFLD/EPA) | 1,143 hospitals, fire stations, EMS, water plants statewide — outages near real facilities get priority-1 restoration |
| NLCD tree canopy per substation | USGS 30m canopy cover (live-computed 1km buffer mean per substation) replaces the distance-based urban/suburban/rural heuristic |
| NOAA HURDAT2 storm tracks | Sandy, Isaias, Irene, Henri track overlays on the map with wind-speed markers |
| Statewide HRRR wind/rain grid | 41×65 grid (~3km resolution) for 8 cached events; sourced from the NOAA AWS archive |
| DOE OE-417 disturbance database | 8 real CT outage events for calibrating simulated vs. actual restoration timelines |
| Census tract population | 883 tracts (2020 Census P.L. 94-171) for much finer demand placement than the 169-town model |
| Customer-impact-weighted dispatch | scheduler can favor outages serving more customers, not just nearest |
| Crew specialization (line vs tree) | 80/20 fleet split, 30% tree-blocked outages, parallel subsystems |
| Optimal-crew-count recommendation | server-side binary search via Numba (10 s at 250 k outages) |
| Monte Carlo ensembles | N seeds, returns mean / median / stddev / 5th / 95th percentiles |
| Calibration framework | `/api/calibrate` tunes 4 realism parameters via SciPy Nelder-Mead against an observed restoration curve |
| Multi-server batch sweeps | `/api/batch` fans scenarios out across worker URLs |
| Customers-restored-over-time curve | inline SVG overlay after each Plan restoration |
| Simulation report download | comprehensive text report with grid stats, storm impact, crew performance, top substations, cost estimates, restoration timeline milestones, and academic references (Wanik, Journal of Homeland Security, IBEW) |
| Real restoration curve overlay | DOE OE-417 events (Sandy, Isaias, Irene, etc.) overlaid on simulated restoration curve for direct comparison |
| Crew mobilization chart | Time-series chart showing simulated crew arrivals vs. real daily crew counts from Isaias 2020 |
| Behavioral overtime analysis | Triple-time pay effect: models reduced urgency on non-critical repairs (15–30% productivity loss by day 5) |
| Academic references | Full citations: Wanik et al. (2015) storm outage modeling, Journal of Homeland Security infrastructure resilience, IBEW/Circadian crew fatigue research |
| Flood-zone road closures | 17 real river corridors statewide (5 FEMA NFHL in Hartford County + 12 USGS NHD-traced across the other 7 counties) add +35% road impedance for outages nearby |
| Equipment/material shortage | progressive repair delay after 60% completion in major events (Eversource Isaias model) |
| Customer callback lag | 2–8h discovery delay for ~15% of rural lateral outages not covered by SCADA |
| Crew time-series ramp | Logistic mobilization curve calibrated to Isaias 2020 PURA daily crew counts (16% day 1 → 100% day 7) |
| Crew fatigue & overtime | Progressive productivity decline (+5%/day after day 2); behavioral overtime incentive model (IBEW double-time) |
| Customers-without-power curve | High→low restoration graph with real DOE event overlay for comparison |
| Scientific outage placement | Wind damage × rain amplification × relative customer exposure, boundary-aware Gaussian-smoothed at 10 km, then sampled on live feeder/lateral segments |
| Underground line model | Eligible urban lateral failures remain in the initial scenario and receive a 1.35× local repair-time modifier |
| Switching / back-feed (FLISR) | Eligible feeder failures remain in the initial total and become explicit five-minute automatic restoration events |
| AMI smart meter coverage | Spatially-varying outage detection: urban 70% AMI (instant), suburban 50%, rural 30% (callback delays) |
| Mutual-aid travel time | Out-of-state crews (MA/RI +2h, NY +4h, PA/OH +6h) based on IBEW mutual-aid protocols |
| Deepened crew stickiness | Crews complete entire feeder circuits before moving to a new one, matching real utility dispatch |
| GIS export | GeoJSON + Esri shapefile |

---

## Architecture

```
                       ┌────────────────────────────────┐
                       │ Browser (GitHub Pages)         │
                       │ 03_grid_simulation.html        │
                       │  - Leaflet map + UI            │
                       │  - Outage model controls       │
                       │  - Diagnostic map surfaces     │
                       │  - In-browser scheduler        │
                       │    (JS, fallback)              │
                       │  - Auto-detects + warm-pings   │
                       │    the server backend          │
                       └─────────┬──────────────────────┘
                                 │
                                 ├── Web Worker ────────────────┐
                                 │   outage_location_worker.js  │
                                 │                              ▼
                                 │                    outage_location_model.js
                                 │                    (one scientific generator)
                                 │
                                 │  HTTPS, gzip (optional restoration)
                                 ▼
                       ┌────────────────────────────────┐
                       │ Render free-tier service       │
                       │ FastAPI (07_server.py)         │
                       │  - /api/schedule               │
                       │  - /api/recommend              │
                       │  - /api/monte_carlo            │
                       │  - /api/calibrate              │
                       │  - /api/batch                  │
                       └─────────┬──────────────────────┘
                                 │
                                 ▼
                       ┌────────────────────────────────┐
                       │ Numba-JIT scheduler            │
                       │ scheduler_numba.py             │
                       │  - Grid-hash + Chebyshev rings │
                       │  - n_available counter         │
                       │  - Customer-weighted scoring   │
                       │  - Pre-warmed at server boot   │
                       └────────────────────────────────┘
```

## Weather-weighted outage-location workflow

No Python, backend, JSON import, or downloaded handoff file is required:

1. Open `03_grid_simulation.html` through GitHub Pages or any static web server.
2. Choose a storm, seed, outage count, and optional scientific parameters.
3. Click **Generate outage scenario**.
4. Inspect outage points and the customer, weather, raw-impact, or
   Gaussian-smoothed diagnostic surface.
5. Set the crew count and click **Plan restoration**.

The browser sends the live in-memory feeder/lateral network to
`outage_location_worker.js`, which calls the same pure
`outage_location_model.js` used by the automated tests. The default generates
2,000 unique Connecticut network locations with exactly 50 customers each,
so the restoration curve begins at exactly 100,000 customers without power.
`outage_restoration_adapter.js` then attaches deterministic critical-facility,
tree, flood, callback, switching, underground, feeder, and substation metadata
without moving a point or changing its initial customer count.

The version-one model is:

```text
wind_damage = max(0, (wind_mph - 35) / 25) ^ 2
rain_amplification = 1 + 0.5 * min(rain_in_per_hour, 2)
weather_severity = wind_damage * rain_amplification
raw_impact = weather_severity * relative_customer_exposure
smoothed_impact = boundary_aware_gaussian(raw_impact, 10 km)
segment_weight = smoothed_impact_at_midpoint * segment_length_km * susceptibility
```

The NOAA storm-track layer is visualization only and does not alter placement.
Events without complete HRRR wind/rain data require the explicitly labeled
basic network-placement mode; the page never silently changes algorithms.

---

## Repository layout

```
.
├── 01_fetch_county_boundary.py    # cache the Connecticut state polygon from OSM
├── 02_fetch_town_boundaries.py    # cache all 169 CT town polygons from OSM
├── 03_grid_simulation.html        # main browser UI, map, and restoration orchestration
├── outage_location_model.js      # sole weather/customer outage-location generator
├── outage_location_worker.js     # off-main-thread generation and progress protocol
├── outage_restoration_adapter.js # deterministic restoration metadata handoff
├── 04_geojson_to_shapefile.py     # offline GeoJSON → shapefile converter (optional)
├── 05_generate_artifacts.py       # offline matplotlib PNG generator for output/
├── 07_server.py                   # FastAPI backend (~780 LOC), disk-backed result cache
├── OUTAGE_LOCATION_WEB_MIGRATION_PLAN.md # completed browser migration record
├── OUTAGE_LOCATION_IMPLEMENTATION_PLAN.md # historical superseded Python plan
├── 08_fetch_substations.py        # cache 299 real HIFLD substations statewide
├── 09_fetch_critical_facilities.py # cache 1,143 real HIFLD/EPA critical facilities statewide
├── 10_fetch_tree_canopy.py        # live-compute NLCD tree canopy per substation (1km buffer)
├── 11_fetch_census_tracts.py      # cache 883 real census tracts + 169 town populations (keyless)
├── 12_fetch_hrrr_storm_wind.py    # builds the statewide 41x65 HRRR weather grid
├── 13_fetch_flood_corridors.py    # 12 real USGS NHD river corridors for the other 7 counties
├── scheduler_fast.py              # NumPy-vectorized fallback scheduler
├── scheduler_numba.py             # Numba-JIT production scheduler (~730 LOC)
├── tests/                          # dependency-free Node model/Worker/adapter acceptance tests
├── package.json                    # npm test command for browser-model tests
├── build_docx.py                  # regenerates the two .docx deliverables
├── data/                          # real-data inputs (HIFLD, EPA, NLCD, Census, NOAA, DOE, USGS)
│   ├── connecticut_substations.json    #   299 real HIFLD substations statewide
│   ├── connecticut_critical_facilities.js # 1,143 HIFLD/EPA hospitals/fire/EMS/water
│   ├── connecticut_census_tracts.js    #   883 real census tract centroids + populations
│   ├── connecticut_towns_population.js #   169 real town populations + centroids
│   ├── connecticut_tree_canopy.js      #   live-computed NLCD canopy per substation
│   ├── connecticut_storm_wind.js       #   statewide HRRR wind/temp grid (41x65)
│   ├── connecticut_flood_corridors.js  #   12 USGS-traced river corridors (7 counties)
│   ├── hartford_storm_tracks.js   #   NOAA HURDAT2 tracks (Sandy, Isaias, Irene, Henri)
│   ├── hartford_doe_oe417.js      #   DOE OE-417 disturbance events for CT
│   └── ...                        #   boundary, towns, etc.
├── output/                        # generated artifacts (PNGs)
├── wasm_scheduler/                # Rust source for the WASM scheduler (kept as reference;
│                                  #   benchmarked slower than V8 JS, not used in production)
├── wasm/scheduler.wasm            # compiled WASM artifact (17 KB)
├── render.yaml                    # Render Blueprint for auto-deploy
├── Dockerfile                     # for the server backend
├── requirements.txt
├── JOURNAL.html                   # development journal (14 chapters, colored, browser-viewable)
├── Hartford_Grid_Dev_Journal.docx # same content as Word doc (drag into Google Drive)
└── Hartford_Grid_Research_Context.docx # 19 cited papers + niche analysis + open questions
```

---

## Running locally

### Just the browser interactive (zero install)

```bash
# Any local web server pointed at the repo root
python -m http.server 8080
# Then: http://localhost:8080/03_grid_simulation.html
```

The page works entirely client-side. The server backend is optional; the page auto-detects whether it's reachable and falls back to in-browser compute.

### With the FastAPI backend locally

```bash
pip install -r requirements.txt
python -m uvicorn 07_server:app --port 8000
```

Then open the interactive and either leave the default Server URL (`https://hartford-grid-server.onrender.com`) or change it to `http://localhost:8000`.

### With Docker

```bash
docker build -t hartford-grid-server .
docker run -p 8000:8000 hartford-grid-server
```

---

## Testing

The outage-location production code and its tests are JavaScript-only:

```bash
npm test
```

The dependency-free suite covers frozen Python-to-JavaScript component parity,
scientific controls, determinism, every complete HRRR event, exact customer
totals, Connecticut geography, network membership, Worker cancellation and
responsiveness, restoration metadata, and zero-endpoint accounting. The
100,000-segment performance fixture is built deterministically in JavaScript;
there is no exported production-network file or second generator to maintain.

## Current limitations

- Feeder and lateral topology is synthetic around 299 real HIFLD substations;
  it is not utility GIS topology.
- The model creates plausible outage locations, but it has not yet been
  validated against restricted EAGLE-I or utility outage-point data.
- July 2026 has complete cached HRRR arrays but a 27.6 mph in-state maximum,
  below the default 35 mph damage threshold. The UI asks the reviewer to lower
  the threshold explicitly or choose basic placement.
- Monte Carlo outage placement and exponential-kernel comparison are deferred;
  the normal review flow intentionally produces one reproducible scenario.
- The optional FastAPI scheduler does not implement every browser-only
  restoration modifier. The page explains when it routes planning locally.

---

## Benchmarks

End-to-end times for a single Plan restoration at varying scales, with the Numba server backend:

| Scenario | Time |
|---|---|
| 2 k outages × 100 crews | **< 10 ms** (server scheduler) |
| 10 k × 500 | ~50 ms |
| 25 k × 500 | ~70 ms |
| 25 k × 5 000 (worst case, realistic) | ~480 ms |
| 25 k × 5 000 + customer-priority + crew-specialization | ~2.3 s |
| 50 k × 1 000 | ~220 ms |
| **100 k × 2 000 (statewide Connecticut scale)** | **~660 ms** |

History of the speedup at 25k × 5000 over the project:

| Step | Time |
|---|---|
| Reference (pure Python on server) | ~minutes / unusable |
| NumPy vectorization | tens of seconds |
| Numba JIT | 118 s |
| Numba + grid hash + `n_available` counter | **0.48 s** (246× from prior step) |

---

## Documentation deliverables

Three documents in the repo capture the project's full development arc and research context:

- **`JOURNAL.html`** — open in any browser. Chapters covering everything from foundations through The Realism Fix, with verbatim user-question quotes, colored category tags, a cross-project "Problems Faced" appendix, and an addendum on the Realism Fix phases + advisor feedback. Browser-viewable and printable.
- **`Hartford_Grid_Dev_Journal.docx`** — same content as a Word document for upload to Google Docs (drag into `drive.google.com` → right-click → Open with Google Docs → auto-converts). Regenerate with `python build_docx.py`.
- **`Hartford_Grid_Research_Context.docx`** — 19 cited research papers across 6 themes (each with author/title/venue + "Why it matters" + "What it does" + "Key terms" vocab), niche analysis, sketch of paper introduction, open research questions, and PURA / Eversource data sources to pursue.
- **`ROADMAP.md`** — advisor-feedback incorporation plan: the feedback organized by theme, a prioritized track-by-track implementation plan, and the data/links to collect.
- **`DATA_SOURCES.md`** — provenance file for every real-world dataset the simulation uses (Connecticut state boundary, 169 towns, 299 real HIFLD substations, 1,143 critical facilities, 883 census tracts, statewide HRRR wind grid, 17 flood corridors) plus planned sources (ISO-NE, DW crew curves, Eversource outage data). Source URLs, fetch scripts, licenses, refresh commands, and honest coverage notes for each.

---

## Status & roadmap

**Engineering side:** the grid, critical facilities, census tracts, towns, tree canopy, HRRR wind grid, and flood corridors are all real data covering the entire state of Connecticut (8 counties). Territory/feeder rendering is canvas-batched and the territory-coloring pass runs in a Web Worker; the FastAPI backend disk-caches expensive `/api/schedule` and `/api/monte_carlo` results. Calibration framework is ready, multi-server batch is ready, all toggles work at max settings.

**The Realism Fix (done):** three composable realism phases shipped and tested —
**Phase 1** hierarchical restoration (laterals can't energize until their feeder is back),
**Phase 2** tiered priority (make-safe → critical → general load),
**Phase 3** weather window (no work during the storm itself).
Revert point for the original realism work: `git tag before-realism-fix`.
Switching/back-feed and underground interactions are now explicit restoration
metadata: they never remove an outage or change the initial 50-customer value.

**Advisor feedback & next priorities:** detailed advisor feedback reshaped the
roadmap — see **[`ROADMAP.md`](ROADMAP.md)** for the full plan. Headline next steps:
flip the restoration curve to "customers without power" (high→zero); add **crew
stickiness** (a crew stays on its assigned circuit until done rather than greedily
bouncing — the advisor's main critique); model **crews as a time series** (David Wanik
CT crews-over-time paper); integrate **real ISO New England substation data**; and
build toward multi-storm / multi-state storytelling. Outage-location validation
against observed utility data remains the next scientific priority when access
becomes available.

**Research side:** calibration against one real Eversource event (Isaias 2020 PURA
filing, May 2018 tornado, etc.) using the built `/api/calibrate` framework. Data
acquisition (ISO-NE substations, wind/temp Colabs, crew counts) is the bottleneck and
is partly on the advisor side.

**Deferred:** WebGPU (Alternative #5). The Numba server already handles Connecticut scale.

---

## License

MIT. See [LICENSE](LICENSE).

## Citation

If this work informs research, please cite the GitHub repository:

> Diamond, A. S. (2026). *Connecticut Power-Grid Resilience Simulation.* GitHub repository: https://github.com/asyeddiamond-max/EnergyOptimization2
