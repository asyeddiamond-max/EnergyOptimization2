# Hartford County Power-Grid Simulation

An interactive browser-based model of a synthetic electric distribution grid covering Hartford County, Connecticut, with a storm-outage simulator and a crew-restoration planner. Built as a research and visualization tool — not a production utility-planning system.

## What this is

A single self-contained HTML file (`hartford_county_simulation.html`) plus a cached county boundary polygon (`hartford_boundary.json`). It runs entirely in the browser using Leaflet and a CARTO basemap. No backend, no database, no build step.

When you open it, the model:

1. Loads the real Hartford County boundary from OpenStreetMap (cached locally).
2. Places `N` synthetic substations across the county using a hybrid of population-weighted and area-weighted k-means clustering.
3. Generates a synthetic distribution network — colored feeder backbones radiating from each substation, plus gray laterals branching from the feeders.
4. On demand, simulates a storm that knocks out `M` random points across the network and counts the customers affected.
5. On demand, plans a restoration: assigns repair crews from depots and computes the total time to restore everyone.

Every random choice is controlled by a single integer seed, so any given configuration is fully reproducible.

## Goals of this simulation

1. **Make grid-resilience problems visible and interactive.** Most power-system research lives in textbooks, MATLAB scripts, or proprietary utility software. The goal here is to give anyone with a browser a way to *play* with substation counts, storm severity, and crew counts, and watch the impact numbers move.

2. **Provide a transparent, reproducible baseline.** Because the entire grid + storm + plan is regenerated from a seed and a handful of sliders, two people running the same configuration get identical results. Reproducibility matters for research and for sharing scenarios.

3. **Honestly separate what's real from what's synthetic.**
   - **Real:** the Hartford County boundary, the town centroids and 2020-census populations used to weight demand.
   - **Synthetic:** every substation, feeder, and lateral location. Real distribution-network topology is not public information (utilities classify it as Critical Energy/Electric Infrastructure Information, CEII).

   This file makes the synthetic parts look plausible without pretending they map to Eversource's actual circuits.

4. **Lay the groundwork for outage-optimization research.** The current simulation answers descriptive questions: *if a storm hits, how many customers go dark, and how long does restoration take with N crews?* The next step (see `SCALING.md`) is normative: *where should new substations go, how should we redraw feeders, and how should we pre-position crews to minimize expected customer-minutes-out?*

5. **Be portable.** A single HTML file + one JSON. No npm. No Docker. No login. You can email it to a collaborator, post it on a class website, or run it offline.

## How to run it

The HTML uses `fetch()` to load the boundary file, so you need a tiny web server (not a `file://` open).

Pick whichever you have:

| Tool | Command (run from the unzipped folder) |
|------|----------------------------------------|
| Python | `python -m http.server 8000` |
| Node.js | `npx serve .` |
| PHP | `php -S localhost:8000` |
| VS Code | Install "Live Server" extension, right-click the HTML, "Open with Live Server" |

Then open `http://localhost:8000/hartford_county_simulation.html` in any modern browser.

External CDN dependencies (auto-loaded at runtime, nothing to install):
- Leaflet 1.9.4 — the map library
- CARTO basemap tiles — the gray background

## Controls and what they mean

### Random seed (top of sidebar)
Controls *every* random choice in the model: where substations land, where feeders branch, where the storm strikes, where crew depots sit. Same seed + same sliders = identical output every time.

**Why a seed is separate from the storm slider:** the storm slider sets *how many* outages occur; the seed sets *where* they fall. Changing one doesn't affect the other.

### Section 1: Distribution grid

- **Substations** (20–300, default 100): number of substations placed in the county. Higher counts give tighter coverage, smaller service areas, and less population per substation.
- **Feeders per substation** (3–10, default 5): how many backbone feeder circuits radiate from each substation. More feeders per substation means more redundancy and more total miles of medium-voltage line.
- **Generate distribution grid**: runs the placement and network generation. Re-rendering is reasonably fast — for k=100 the whole pipeline takes under a second thanks to a precomputed inside-county bitmap and a typed-array k-means implementation.

### Section 2: Storm simulation

- **Storm outages** (50–5,000): number of failure points scattered along feeders and laterals. Each failure removes a chunk of the affected line's downstream customers.
- **Simulate storm**: runs it. Displays:
  - **Customers without power** — total population on disabled segments, capped at county population.
  - **Outage locations** — count of damaged points the crews will need to visit.

### Section 3: Restoration plan

- **Repair crews** (1–50): number of independent two-person line crews available.
- **Plan restoration**: computes a schedule. Crews start at automatically-placed depots, then use earliest-completion greedy scheduling (each step picks the crew+job pair whose finish time is soonest, given 30 mph travel and 1.5 h fixed repair time).
- **Total restoration time** = the maximum across all crews' finish times. That's when the last customer gets power back.

### Reset storm
Clears storm and restoration state without touching the grid layout.

## What's modeled vs. abstracted

This is *not* a power-flow model. It does not solve Kirchhoff's laws, model voltage sag, fault currents, or protection coordination. It treats the grid as a topological tree: customers attach to laterals, laterals attach to feeders, feeders attach to substations. A failure anywhere along a branch disconnects everything downstream.

This is also *not* a true facility-location optimization. The substations are placed by k-means clustering for visual realism and reasonable spatial coverage, not to minimize a real objective like capacity-constrained customer-minutes-out under N-1 contingency.

What it *does* model reasonably:
- Population-weighted demand distribution
- Approximate spatial extent of the distribution network
- Customer counts affected by random failure points
- Crew scheduling with realistic travel and repair-time parameters

What you should not do:
- Don't show the feeder routes to anyone and tell them it's Eversource's grid. It isn't.
- Don't use the restoration time estimate to make planning decisions for a real utility — it's calibrated only to the orders of magnitude reported in public storm-after-action reports.

## Files in this bundle

```
hartford_county_simulation.html   # the entire app (HTML + CSS + JS, ~40 KB)
hartford_boundary.json            # OSM Hartford County polygon (~30 KB)
README.md                         # this file
SCALING.md                        # roadmap to shapefile export + statewide scaling
```

## Acknowledgments

- **OpenStreetMap contributors** — county boundary
- **Carto** — gray basemap tiles
- **Leaflet** — map rendering
- **US Census Bureau** — town population data (2020 decennial census)

## License

MIT-style — do whatever you want with the code; please don't represent it as utility-source data.
