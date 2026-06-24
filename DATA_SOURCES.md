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

## 6 · Planned / pending data sources

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
