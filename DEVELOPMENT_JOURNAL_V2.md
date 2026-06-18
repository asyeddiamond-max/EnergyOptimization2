# Hartford County Grid Simulation — Development Journal

A running log of design questions encountered during development and the direction chosen for each. Decisions are highlighted in red. Updated continuously.

---

## Phase 1 — Foundation: a basic interactive map

| Question | Decision / Direction Taken |
|----------|----------------------------|
| Which mapping library to use? | <span style="color:red">**Leaflet** — open source, no API key required, smaller bundle than Mapbox</span> |
| How to host without a backend? | <span style="color:red">**Single self-contained HTML file** served by GitHub Pages — no server required</span> |
| Where does population data come from? | <span style="color:red">**US Census 2020 decennial counts**, hard-coded for all 29 Hartford County towns</span> |
| Should the county polygon be fetched live or cached? | <span style="color:red">**Cached locally** in hartford_boundary.json so the simulation works offline and isn't rate-limited by Nominatim</span> |
| Which basemap tiles to use? | <span style="color:red">**CARTO Light** for the muted gray background — keeps the simulation overlays readable</span> |

---

## Phase 2 — Isolation of Hartford County

| Question | Decision / Direction Taken |
|----------|----------------------------|
| How to make the county feel like a discrete entity, not just a label on a map? | <span style="color:red">**Polygon mask** covering everything outside the county boundary, greying the surroundings while keeping the inside fully visible</span> |
| How visible should the boundary be? | <span style="color:red">After several user iterations, **1 px bright red line on a dedicated top pane** so nothing else can paint over it</span> |
| Should the map allow panning outside the county? | <span style="color:red">**Yes** — locking it felt too restrictive. The user can pan freely; the mask makes the focus obvious</span> |

---

## Phase 3 — Synthetic distribution grid

| Question | Decision / Direction Taken |
|----------|----------------------------|
| Where should substations be placed? | <span style="color:red">**Weighted k-means** on town centroids + uniform-area samples. Blends population-driven placement with rural coverage</span> |
| Should we try to use real Eversource substation locations? | <span style="color:red">**No** — locations are publicly visible but linking them to specific circuits requires CEII-protected data. Documented as synthetic</span> |
| How should feeders and laterals be generated? | <span style="color:red">**Random walks from each substation**, clipped to stay inside the county. Each feeder spawns laterals at midpoints</span> |
| How many substations should the slider allow? | <span style="color:red">**20 to 300** — based on Eversource's actual ~35 distribution substations in Hartford County plus headroom for stress testing</span> |
| Should grid generation be reproducible? | <span style="color:red">**Yes — every random choice uses a seeded PRNG** so the same seed + sliders produces identical output</span> |

---

## Phase 4 — Storm simulation

| Question | Decision / Direction Taken |
|----------|----------------------------|
| How should outage locations be distributed? | <span style="color:red">**Uniform random over network segments**, weighted slightly toward laterals which represent most of the mileage</span> |
| How is "customers affected" calculated? | <span style="color:red">**Sum of each downed segment's share of its parent feeder's customer base**, capped at county population (~940k)</span> |
| What's the maximum storm size? | <span style="color:red">**25,000 outage locations** — matches Sandy-scale catastrophic events in southern New England</span> |
| Should we render outages as DOM elements or canvas? | <span style="color:red">**Custom canvas point-cloud layer** at scales above ~1,000 outages — DOM elements freeze the page at high counts</span> |

---

## Phase 5 — Restoration scheduler

| Question | Decision / Direction Taken |
|----------|----------------------------|
| What scheduling algorithm? | <span style="color:red">**Greedy nearest-outage** with a min-heap on crew finish times. Fast, well-understood baseline. MILP would be more accurate but doesn't run in the browser</span> |
| How are crew depots placed? | <span style="color:red">**k-means clustering of outage locations** when M ≤ 200 crews. Beyond that, cycle through outage points</span> |
| What repair time should the baseline use? | <span style="color:red">**1.5 hours** — typical for a tripped-fuse-level repair in published Eversource summaries</span> |
| Should we show every repair job on the map? | <span style="color:red">**First 30 jobs per crew as numbered circles** (visually clear), everything beyond that as small colored dots (avoids DOM blowup)</span> |

---

## Phase 6 — Optimal crew count recommender

| Question | Decision / Direction Taken |
|----------|----------------------------|
| What's the optimization target? | <span style="color:red">**Smallest crew count whose restoration time is within 15% of the theoretical floor**</span> |
| How is the "floor" defined? | <span style="color:red">**Restoration time at the upper-bound crew count** — past this, more crews just sit idle</span> |
| What's the upper bound? | <span style="color:red">**max(50, N/10) crews** — past this, additional crews wait for outages to be discovered</span> |
| How long should the search take? | <span style="color:red">Initially synchronous (would freeze the page); now async with progress bars. **Sub-second on typical scenarios**, several seconds at max settings</span> |

---

## Phase 7 — Realistic mode toggle

| Question | Decision / Direction Taken |
|----------|----------------------------|
| What's wrong with the baseline simulation? | <span style="color:red">**~12-hour restoration estimates** for major storms — wildly optimistic vs. Eversource's 2–7 day actuals</span> |
| Which real-world factors do we model? | <span style="color:red">**Seven factors** from the SCALING document's §4 uncertainty table: assessment delay, workday clamp, stochastic repair, discovery ramp, mutual-aid waves, road-network proxy, tier-1 priority + sectionalizers</span> |
| Should this replace the baseline or be a toggle? | <span style="color:red">**Toggle (default ON)** — keeps the optimistic mode as a reference point for comparison</span> |
| What target should realistic mode match? | <span style="color:red">**The 2–7 day range** reported in public Eversource storm after-action filings for major events (Isaias, Sandy, etc.)</span> |
| How was the log-normal repair distribution chosen? | <span style="color:red">**Median 2 h, 90th percentile 6 h** — captures the "tripped fuse vs. broken pole" spread without requiring real data</span> |

---

## Phase 8 — Performance optimization rounds

| Question | Decision / Direction Taken |
|----------|----------------------------|
| How to make point-in-polygon checks fast? | <span style="color:red">**Precomputed 256×256 inside-county bitmap** — O(1) lookup instead of O(P) ray-casting per call</span> |
| How to make nearest-outage queries fast at scale? | <span style="color:red">**Spatial grid hash** with 0.005° cells — O(log N) instead of O(N) per call</span> |
| How to render 25,000 outages without freezing? | <span style="color:red">**Custom PointCloudLayer** that draws all points in a single canvas pass instead of 25K separate Leaflet circleMarker objects</span> |
| How to make the scheduler responsive at high N? | <span style="color:red">**Async with setTimeout(0) yields every 3,000–4,000 outage assignments** so the browser can repaint between chunks</span> |
| How to find next discovery time efficiently? | <span style="color:red">**Pre-sorted discovery index with monotonic pointer** — O(log N) binary search instead of O(N) linear scan per query</span> |
| Should the recommender share precomputed state across binary-search iterations? | <span style="color:red">**Yes** — discovery times, sorted index, grid hash all built once and shared. Cuts ~10× repeated setup cost</span> |

---

## Phase 9 — Export functionality

| Question | Decision / Direction Taken |
|----------|----------------------------|
| What formats to export? | <span style="color:red">**Both GeoJSON and Esri shapefile** — different consumers prefer different formats</span> |
| How are shapefiles generated in-browser? | <span style="color:red">**shp-write library** via CDN — produces real .shp/.shx/.dbf/.prj bundles, downloaded as a zip</span> |
| What attributes to include? | <span style="color:red">**Schema with ≤10-character column names** (shapefile constraint), documented in README</span> |
| How are scenarios made reproducible? | <span style="color:red">**Manifest JSON** included with every export, recording the seed and every slider position</span> |

---

## Phase 10 — Repository structure and deployment

| Question | Decision / Direction Taken |
|----------|----------------------------|
| How to organize the repo? | <span style="color:red">**Numbered file convention** (01_, 02_, etc.) matching the user's existing CVRP repo style</span> |
| How to make the simulation publicly usable? | <span style="color:red">**GitHub Pages deployment** at asyeddiamond-max.github.io/EnergyOptimization2/ — no install required</span> |
| Should the page be search-engine indexed? | <span style="color:red">**No** — noindex meta tag added. Discoverable via the URL but not via Google</span> |

---

## Phase 11 (in progress) — Web Worker for the scheduler

| Question | Decision / Direction Taken |
|----------|----------------------------|
| Why a Web Worker now? | <span style="color:red">**To get scheduler compute fully off the main thread.** Async yields keep the UI responsive most of the time, but at extreme settings the browser still hits the unresponsive-page limit</span> |
| Inline worker via Blob or separate file? | <span style="color:red">**Inline via Blob URL** — preserves the "single HTML file" deployment story</span> |
| Should it replace the inline scheduler or coexist? | <span style="color:red">**Coexist** with the inline scheduler as a fallback. If Worker isn't available, fall back to main-thread async execution</span> |
| What's the status? | <span style="color:red">**Worker infrastructure committed, integration still in progress.** Wiring planRestoration and recommendCrewCount to use it is the next step</span> |

---

## Major open questions (next directions)

| Question | Current Thinking |
|----------|------------------|
| Should we calibrate against real Eversource outage data? | <span style="color:red">**Yes — this is the end goal of the project.** Would require Eversource cooperation or extracting data from public PURA filings. Publishable result if successful</span> |
| Should we implement MILP/CP as a better scheduler? | <span style="color:red">**Worth exploring** as a benchmark against the greedy baseline. Real research contribution if a clean comparison is published</span> |
| Should we add a pre-computed scenario library? | <span style="color:red">**Yes, near-term**. Would solve the page-isn't-responding complaint for the most-common scenarios while keeping live computation for custom ones</span> |
| Should we extend to all of Connecticut? | <span style="color:red">**Long-term goal**. Largest piece of remaining engineering. Requires per-Planning-Region orchestration and statewide rollup</span> |
