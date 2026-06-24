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
| **Used by** | The interactive — `generateGrid()` anchors all substations at the real HIFLD locations; synthetic feeders + laterals grow from these points. Map tooltips show real name + voltage. |
| **Record count** | 49 substations inside the county (as of last fetch) |
| **License** | HIFLD: public domain (U.S. government work). OSM fallback: © OpenStreetMap contributors, ODbL 1.0. |
| **Refresh** | `python 08_fetch_substations.py` |

**Honest coverage notes**
- HIFLD covers transmission and sub-transmission substations well (115 kV, 345 kV). Smaller neighborhood **distribution** substations are below HIFLD's threshold and aren't in any public dataset.
- HIFLD labels a handful of substations `UNKNOWN<id>` or `Deadend<id>` when the operator name isn't public. The fetch script relabels those by city (e.g. "Farmington substation") so markers are readable while locations stay exact.
- A more complete view would require an **ISO New England** or **Eversource GIS** export (currently being pursued via the advisor). The fetch script is straightforward to repoint when that data arrives.

---

## 4 · Planned / pending data sources

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
