# Hartford County Power-Grid Resilience Simulation

A browser-first, server-augmented, Connecticut-scale interactive simulator for distribution-grid storm restoration. Models 100 000+ outages and 5 000+ crews per scenario in under a second, with seven realism factors, a calibration framework for future tuning against real Eversource data, customer-impact-weighted dispatch, and Monte Carlo ensemble analysis.

Designed as a research instrument for the **restoration side** of the distribution-grid resilience problem — a downstream complement to the UConn Eversource Energy Center group's outage-prediction work.

---

## Try it live

[**Open the simulator →**](https://asyeddiamond-max.github.io/EnergyOptimization2/03_grid_simulation.html)

The server backend at `hartford-grid-server.onrender.com` is auto-detected by the page. The simulator runs entirely in the browser as a fallback if the server is offline.

- [`/health`](https://hartford-grid-server.onrender.com/health) — server health check
- [`/version`](https://hartford-grid-server.onrender.com/version) — running commit + backend mode

For a lighter standalone preview (single SVG, no Leaflet basemap):
[**Open the inline preview →**](https://asyeddiamond-max.github.io/EnergyOptimization2/03_grid_inline_preview.html)

---

## What's in the simulator

| Capability | How |
|---|---|
| Synthetic Hartford County distribution grid | k-means substations, branching feeders + laterals, population-weighted demand |
| Realistic-mode scheduler with seven factors | assessment delay, log-normal repair, discovery ramp, mutual-aid waves, road proxy, workday clamp, critical priority |
| Customer-impact-weighted dispatch | scheduler can favor outages serving more customers, not just nearest |
| Crew specialization (line vs tree) | 80/20 fleet split, 30% tree-blocked outages, parallel subsystems |
| Optimal-crew-count recommendation | server-side binary search via Numba (10 s at 250 k outages) |
| Monte Carlo ensembles | N seeds, returns mean / median / stddev / 5th / 95th percentiles |
| Calibration framework | `/api/calibrate` tunes 4 realism parameters via SciPy Nelder-Mead against an observed restoration curve |
| Multi-server batch sweeps | `/api/batch` fans scenarios out across worker URLs |
| Customers-restored-over-time curve | inline SVG overlay after each Plan restoration |
| Pre-computed scenario library | 12 canned storms in `scenarios/`, loadable without compute |
| GIS export | GeoJSON + Esri shapefile |

---

## Architecture

```
                       ┌────────────────────────────────┐
                       │ Browser (GitHub Pages)         │
                       │ 03_grid_simulation.html        │
                       │  - Leaflet map + UI            │
                       │  - In-browser scheduler        │
                       │    (JS, fallback)              │
                       │  - Auto-detects + warm-pings   │
                       │    the server backend          │
                       └─────────┬──────────────────────┘
                                 │  HTTPS, gzip
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

---

## Repository layout

```
.
├── 01_fetch_county_boundary.py    # cache Hartford polygon from OSM
├── 02_fetch_town_boundaries.py    # cache the 29 town polygons from OSM
├── 03_grid_simulation.html        # the main interactive (~3k LOC, runs in any browser)
├── 03_grid_inline_preview.html    # lighter standalone SVG preview
├── 04_geojson_to_shapefile.py     # offline GeoJSON → shapefile converter (optional)
├── 05_generate_artifacts.py       # offline matplotlib PNG generator (used by scenario precomputer)
├── 06_precompute_scenarios.py     # batches scenario library JSON for the Alternative #2 dropdown
├── 07_server.py                   # FastAPI backend (~780 LOC)
├── scheduler_fast.py              # NumPy-vectorized fallback scheduler
├── scheduler_numba.py             # Numba-JIT production scheduler (~730 LOC)
├── build_docx.py                  # regenerates the two .docx deliverables
├── data/                          # cached OSM inputs
├── output/                        # generated artifacts (PNGs)
├── scenarios/                     # pre-computed scenario JSON files (Alt #2)
├── wasm_scheduler/                # Rust source for the WASM scheduler (kept as reference;
│                                  #   benchmarked slower than V8 JS, not used in production)
├── wasm/scheduler.wasm            # compiled WASM artifact (17 KB)
├── render.yaml                    # Render Blueprint for auto-deploy
├── Dockerfile                     # for the server backend
├── requirements.txt
├── JOURNAL.html                   # development journal (14 chapters, colored, browser-viewable)
├── Hartford_Grid_Dev_Journal.docx # same content as Word doc (drag into Google Drive)
├── Hartford_Grid_Research_Context.docx # 19 cited papers + niche analysis + open questions
└── PROGRESS_REPORT.md             # period progress report for academic review
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
| **100 k × 2 000 (Connecticut projection)** | **~660 ms** |

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

- **`JOURNAL.html`** — open in any browser. 14 chapters covering everything from foundations through the most recent commits, with verbatim user-question quotes, colored category tags, and a cross-project "Problems Faced" appendix. Browser-viewable and printable.
- **`Hartford_Grid_Dev_Journal.docx`** — same content as a Word document for upload to Google Docs (drag into `drive.google.com` → right-click → Open with Google Docs → auto-converts).
- **`Hartford_Grid_Research_Context.docx`** — 19 cited research papers across 6 themes (each with author/title/venue + "Why it matters" + "What it does" + "Key terms" vocab), niche analysis, sketch of paper introduction, open research questions, and PURA / Eversource data sources to pursue.
- **`PROGRESS_REPORT.md`** — focused snapshot of what changed in the most recent reporting period.

---

## Status & roadmap

**Engineering side:** essentially complete for the Hartford County / Connecticut scope. Calibration framework is ready, multi-server batch is ready, all toggles work at max settings.

**Research side:** next milestone is calibration against one real Eversource event (Isaias 2020 PURA filing, May 2018 tornado, etc.). The framework is built; data acquisition is the bottleneck.

**Deferred:** WebGPU (Alternative #5). The Numba server already handles Connecticut scale, so the urgency went away. Could be revisited if multi-state projection becomes the goal.

---

## License

MIT. See [LICENSE](LICENSE).

## Citation

If this work informs research, please cite the GitHub repository:

> Diamond, A. S. (2026). *Hartford County Power-Grid Resilience Simulation.* GitHub repository: https://github.com/asyeddiamond-max/EnergyOptimization2
