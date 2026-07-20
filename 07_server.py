"""
07_server.py — FastAPI backend for the Connecticut grid simulation.

Hosts the same restoration scheduler algorithm as the browser, plus
research-grade capabilities that the browser can't easily do:
    * Monte Carlo ensembles (re-run a storm scenario with N different seeds,
      report mean / 95% CI of total restoration time)
    * (future) MILP-based optimal scheduler for benchmarking against greedy
    * (future) Calibration endpoint that compares model output to a real
      Eversource storm report

Run locally:
    pip install -r requirements.txt
    uvicorn 07_server:app --reload --port 8000

Then in the browser interactive: set the "Server URL" field to
    http://localhost:8000
and toggle on "Use server backend" to delegate compute over HTTP.

Deploy free tier options:
    Render.com       (web service, slow cold start)
    Fly.io           (always-on after first ping)
    Railway          ($5/mo equivalent free tier)
    HuggingFace Spaces (works for non-ML Python apps too)

For a Docker build:
    docker build -t hartford-grid-server .
    docker run -p 8000:8000 hartford-grid-server

CORS is wide open by default so the GitHub Pages frontend can call this from
any origin. In production you'd restrict the allowed origins list.
"""
from __future__ import annotations

import statistics
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


# We deliberately do NOT import 05_generate_artifacts.py at server
# startup. That file is the offline plotting/artifact generator — it
# raises SystemExit if matplotlib is missing (not catchable with
# `except Exception`) and tries to load data files that aren't in the
# Docker image. The server's fast paths (Numba/NumPy) are 50-100x
# faster anyway, so this fallback was never used in production.
art = None

# NumPy-vectorized scheduler. ~50-100x faster on big scenarios; the server
# uses it by default and falls back to the reference implementation only if
# NumPy is missing.
try:
    from scheduler_fast import plan_restoration_fast
    _FAST = True
except ImportError:
    _FAST = False

# Numba-JIT'd scheduler — ~10x faster than the NumPy version on hot scenarios.
# Falls through to NumPy if numba isn't installed.
try:
    from scheduler_numba import plan_restoration_numba
    _NUMBA = True
except Exception:
    _NUMBA = False

# Process pool for Monte Carlo: runs N seeds across CPU cores in parallel.
from concurrent.futures import ProcessPoolExecutor
import os
_POOL = None
def _get_pool():
    global _POOL
    if _POOL is None:
        n = max(1, (os.cpu_count() or 2) - 1)
        _POOL = ProcessPoolExecutor(max_workers=n)
    return _POOL


# --- Disk-backed result cache -------------------------------------------
# Statewide requests (up to 25k outages, 1000 crews, or a 200-run Monte Carlo
# ensemble) are expensive enough that repeat requests -- the same canonical
# preset hit by multiple users, or a user re-running a scenario they already
# computed -- are worth serving from cache instead of recomputing. Keyed by a
# hash of the full request body (including every outage coordinate), so any
# difference in input produces a different cache entry. Survives server
# restarts (unlike an in-memory dict) since Render's free tier can idle/sleep
# and cold-start between requests.
import hashlib
import json
from pathlib import Path

_CACHE_DIR = Path(__file__).parent / "cache"
_CACHE_DIR.mkdir(exist_ok=True)
_CACHE_MAX_FILES = 500  # basic hygiene cap; prune oldest when exceeded


def _cache_path(prefix: str, req: BaseModel) -> Path:
    payload = req.model_dump_json(exclude_defaults=False).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:24]
    return _CACHE_DIR / f"{prefix}_{digest}.json"


def _prune_cache_if_needed() -> None:
    files = sorted(_CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if len(files) > _CACHE_MAX_FILES:
        for f in files[: len(files) - _CACHE_MAX_FILES]:
            try:
                f.unlink()
            except OSError:
                pass


def cached_response(prefix: str, req: BaseModel, response_model: type[BaseModel], compute):
    """Return compute()'s cached result if this exact request was seen
    before, otherwise compute, persist to disk, and return it."""
    path = _cache_path(prefix, req)
    if path.exists():
        try:
            return response_model.model_validate_json(path.read_text())
        except Exception:
            pass  # corrupt/stale cache entry -- fall through and recompute
    result = compute()
    try:
        _CACHE_DIR.mkdir(exist_ok=True)  # self-heal if the dir was removed underneath us
        path.write_text(result.model_dump_json())
        _prune_cache_if_needed()
    except OSError:
        pass  # cache write failures shouldn't fail the request
    return result


app = FastAPI(
    title="Connecticut Grid Simulation Backend",
    description=(
        "HTTP API for the restoration scheduler and Monte Carlo ensemble "
        "analysis. Designed to be called from the browser-based interactive."
    ),
    version="1.0.0",
)

# Wide-open CORS so the GitHub Pages frontend can call this. Restrict in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gzip-compress responses > 1 KB. At 25k outages the schedule response is
# ~1.5 MB of JSON; gzip brings it to ~150 KB. Major savings on network time.
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1024)


# Pre-warm the Numba JIT at server startup so the first user request after
# a Render redeploy doesn't pay a ~10s JIT compile penalty. Runs synthetic
# scheduler calls covering every (grid/dense × weighted/nearest) signature
# the production code paths use.
@app.on_event("startup")
def _prewarm_numba():
    if not _NUMBA:
        return
    try:
        import random as _r
        _r.seed(0)
        warm_pts = [(41.7 + _r.random() * 0.01, -72.7 + _r.random() * 0.01)
                    for _ in range(1200)]
        warm_cust = [10.0 + 100.0 * _r.random() for _ in range(1200)]
        # Triggers compile of: grid + pure-nearest, dense + pure-nearest.
        plan_restoration_numba(warm_pts, 8, realistic=True, seed=1,
                               customers=warm_cust, customer_weight=0.0)
        plan_restoration_numba(warm_pts[:500], 4, realistic=True, seed=1,
                               customers=warm_cust[:500], customer_weight=0.0)
        # Triggers compile of: grid + weighted, dense + weighted.
        plan_restoration_numba(warm_pts, 8, realistic=True, seed=1,
                               customers=warm_cust, customer_weight=5000.0)
        plan_restoration_numba(warm_pts[:500], 4, realistic=True, seed=1,
                               customers=warm_cust[:500], customer_weight=5000.0)
        print("[startup] Numba JIT pre-warmed for all scheduler signatures")
    except Exception as e:
        print(f"[startup] JIT pre-warm failed (non-fatal): {e}")


# --- Schemas ---------------------------------------------------------------

class Outage(BaseModel):
    lat: float
    lon: float
    critical: bool = False
    customers: float = 0.0  # number of customers served by this outage point
    feeder_id: int = -1     # parent feeder index (for hierarchical restoration)
    is_feeder: int = 0      # 1 if this is a backbone fault, 0 if a lateral fault
    priority: int = 0       # dispatch tier: 0 normal, 1 critical facility,
                            # 2 make-safe / public-safety hazard (highest)
    sub_id: int = -1        # index of the assigned substation (territory).
                            # Set by the frontend as the nearest real
                            # substation; used by crew_stickiness to partition
                            # outages into service-area groups.
    tree_blocked: int = -1  # -1 = let server decide stochastically (legacy);
                            # 0 = line-only outage; 1 = tree-blocked. Set by
                            # the frontend per-outage so urban vs rural
                            # substation territories + vegetation-trim age
                            # can vary the rate spatially.


class ScheduleRequest(BaseModel):
    outages: list[Outage]
    crews: int = Field(ge=1, description="Number of repair crews")
    seed: int = 42
    realistic: bool = True
    # True for a storm confined to one corner of the state (a concentrated
    # severe-thunderstorm complex or tornado/derecho, is_localized_reports in
    # hartford_storm_tracks.js) rather than a broad, statewide-track storm.
    # Confirmed via 2 real concentrated storms that workloadSlowdownMult's
    # customer-count-scaled large-scale logistics friction (see
    # scheduler_numba.py:plan_restoration_numba) overshoots for these --
    # their base dispatch mechanics alone already land within the same
    # 0.97-1.25 real/sim range the broad storms hit WITH the multiplier.
    is_localized: bool = False
    # Customer-impact weighting (realism factor #4). When > 0, the scheduler
    # biases dispatch toward outages that restore more customers, not just
    # nearest. score(o) = customers(o) - customer_weight * distance²(o).
    # Default 0 preserves the original pure-nearest behavior.
    customer_weight: float = Field(default=0.0, ge=0.0)
    # Crew specialization. When True, splits outages into tree-blocked
    # (need a tree crew to clear before line work) vs line-only, and splits
    # crews into tree (20%) and line (80%). The two subsystems run
    # independently — total restoration time = max(tree_time, line_time).
    crew_specialization: bool = False
    tree_blocked_rate: float = Field(default=0.90, ge=0.0, le=1.0,
        description="Fraction of outages requiring tree clearing")
    tree_crew_share: float = Field(default=0.20, ge=0.05, le=0.5,
        description="Fraction of total crews that are tree crews")
    # The Realism Fix: hierarchical restoration. When True, a lateral's
    # customers are not energized until its parent feeder's backbone faults
    # are repaired (post-process gating of restoration times).
    hierarchical: bool = False
    # The Realism Fix (Phase 2): tiered priority dispatch. When True, outages
    # are served in priority order — make-safe / public-safety hazards first,
    # then critical facilities (hospitals, water, 911), then general load.
    # Implemented by giving higher tiers a large effective-customer bonus so
    # the customer-weighted dispatch serves them first.
    tiered_priority: bool = False
    # The Realism Fix (Phase 3): weather window. Hours of storm during which
    # no work happens (bucket trucks grounded). Shifts crew arrivals + outage
    # discovery to after the storm passes. 0 = no window (back-compat).
    storm_duration: float = Field(default=0.0, ge=0.0, le=120.0)
    # Crew stickiness (advisor's main critique). When True, crews are assigned
    # to a substation territory and only repair outages in that territory —
    # a Storrs crew won't drive to New Haven. Implemented by partitioning the
    # outages by sub_id, splitting crews proportionally to territory customer
    # count, and running one independent sub-scheduler per territory in a
    # thread pool. Total restoration time = max across territories.
    crew_stickiness: bool = False
    # Multi-day storm drag (behavioral / sociotechnical). When True and the
    # storm is "big" (storm_duration > 12 h or N outages > 5000), apply a
    # joint slowdown capturing several documented effects: crew fatigue from
    # multi-day operations, out-of-town mutual-aid crews unfamiliar with the
    # territory, resource exhaustion (parts/fuel/lodging), and the well-known
    # paradox that triple-time pay incentives can lengthen rather than
    # shorten major-event timelines. Implemented as a road-multiplier and
    # assessment-delay bump at the server-helper level (no scheduler refactor).
    storm_drag: bool = False
    # Soil saturation (environmental). Wet ground from heavy rainfall pulls
    # roots out more easily (more tree damage to power lines) and makes
    # pole-setting / equipment repair slower (mud, equipment getting stuck).
    # When True: +25% road impedance and +30% effective tree-blocked rate.
    soil_saturation: bool = False
    # Pre-storm staging (logistical). When True, the utility had pre-
    # positioned crews and materials before the storm hit, so the post-
    # storm assessment delay is essentially zero — work begins as soon as
    # winds drop below the safety threshold. Real Eversource practice for
    # forecastable events. Cancels the standard 12-hour assessment delay.
    pre_storm_staging: bool = False


class JobResult(BaseModel):
    lat: float
    lon: float
    eta: float
    # Index into the request's outages array. Returned so the browser can map
    # each job back to its exact outage instead of matching by (lat,lon), which
    # collapsed when two outages shared a coordinate ("restored more than once").
    outage_idx: int = -1


class CrewResult(BaseModel):
    depot_lat: float
    depot_lon: float
    finish_time_h: float
    n_jobs: int
    jobs: list[JobResult] = []


class ScheduleResponse(BaseModel):
    total_time_h: float
    crews: list[CrewResult]
    backend: str = "python-greedy"


class RecommendRequest(BaseModel):
    outages: list[Outage]
    seed: int = 42
    realistic: bool = True
    is_localized: bool = False
    tolerance: float = Field(default=1.15, ge=1.01, le=2.0,
        description="Acceptable multiple of the floor restoration time")
    upper_bound: int | None = Field(default=None, description=
        "Override the upper-bound crew count tried; defaults to max(50, N/10)")
    # Full scheduler flags — same as ScheduleRequest so results match the simulation
    customer_weight: float = 0.0
    crew_specialization: bool = False
    tree_blocked_rate: float = 0.90
    tree_crew_share: float = 0.20
    hierarchical: bool = False
    tiered_priority: bool = False
    storm_duration: float = 0.0
    crew_stickiness: bool = False
    storm_drag: bool = False
    soil_saturation: bool = False
    pre_storm_staging: bool = False


class RecommendEvaluation(BaseModel):
    crews: int
    total_time_h: float


class RecommendResponse(BaseModel):
    recommended_crews: int
    recommended_time_h: float
    floor_time_h: float
    upper_bound: int
    tolerance: float
    evaluations: list[RecommendEvaluation]


class BatchScenario(BaseModel):
    """One storm scenario in a batch sweep. Reuses the same fields as
    ScheduleRequest, plus an optional human-readable label so the response
    can be matched up with the request order."""
    label: str = ""
    outages: list[Outage]
    crews: int = Field(ge=1)
    seed: int = 42
    realistic: bool = True
    customer_weight: float = 0.0
    crew_specialization: bool = False
    tree_blocked_rate: float = 0.90
    tree_crew_share: float = 0.20


class BatchRequest(BaseModel):
    scenarios: list[BatchScenario] = Field(min_length=1, max_length=200)
    # Optional list of worker URLs to fan out to. When empty, runs all
    # scenarios serially on this server (still works, just no parallelism).
    workers: list[str] = []


class BatchScenarioResult(BaseModel):
    label: str
    total_time_h: float
    n_crews: int
    elapsed_ms: float
    worker: str
    error: str = ""


class BatchResponse(BaseModel):
    results: list[BatchScenarioResult]
    total_elapsed_ms: float
    n_workers: int


class ObservedPoint(BaseModel):
    hour: float
    customers_restored: float


class CalibrateRequest(BaseModel):
    """Inputs for the calibration framework. The observed curve is a list of
    (hour, customers_restored) samples from a real storm — typically pulled
    from a PURA storm-event filing or an Eversource post-mortem. We optimise
    the four most-tunable realism parameters to minimise RMSE between the
    simulator's restoration curve on the given scenario and this observed
    curve."""
    outages: list[Outage]
    crews: int = Field(ge=1)
    seed: int = 42
    observed: list[ObservedPoint] = Field(min_length=2,
        description="Sampled points from the real restoration curve")
    # Optional starting point + bounds for the optimisation.
    initial_travel_mph: float = 25.0
    initial_assessment_delay: float = 12.0
    initial_workday_hours: float = 14.0
    initial_road_multiplier: float = 1.5
    max_iters: int = Field(default=80, ge=10, le=400)


class CalibrateResponse(BaseModel):
    travel_mph: float
    assessment_delay: float
    workday_hours: float
    road_multiplier: float
    rmse: float
    initial_rmse: float
    n_evaluations: int
    converged: bool
    simulated_curve: list[ObservedPoint]


class MonteCarloRequest(BaseModel):
    outages: list[Outage]
    crews: int = Field(ge=1)
    realistic: bool = True
    is_localized: bool = False
    base_seed: int = 42
    n_runs: int = Field(default=30, ge=2, le=200,
                        description="Number of seeds to sample")
    # Realistic sub-flags — same as ScheduleRequest so results match the simulation
    customer_weight: float = 0.0
    crew_specialization: bool = False
    tree_blocked_rate: float = 0.90
    tree_crew_share: float = 0.20
    hierarchical: bool = False
    tiered_priority: bool = False
    storm_duration: float = 0.0
    crew_stickiness: bool = False
    storm_drag: bool = False
    soil_saturation: bool = False
    pre_storm_staging: bool = False


class MonteCarloResponse(BaseModel):
    n_runs: int
    mean_h: float
    median_h: float
    stddev_h: float
    p05_h: float
    p95_h: float
    min_h: float
    max_h: float
    individual_h: list[float]


# --- Helpers --------------------------------------------------------------

def _split_for_specialization(req_outages: list[Outage], crews: int, seed: int,
                              tree_blocked_rate: float, tree_crew_share: float,
                              tree_blocked_rate_multiplier: float = 1.0):
    """Partition outages and crews into tree vs line subsystems.

    Per-outage tree_blocked classification (frontend can set tree_blocked
    explicitly, e.g. higher rate in rural / older-trim territories, lower in
    urban areas). For outages with tree_blocked == -1 we fall back to the
    legacy stochastic assignment using tree_blocked_rate × multiplier (e.g.
    multiplier > 1 under soil_saturation = wet, more roots pulled out).

    Seed-deterministic so the same scenario produces the same partition."""
    import random as _rand
    rng = _rand.Random((seed * 7919 + 17) & 0xFFFFFFFF)
    eff_rate = max(0.0, min(1.0, tree_blocked_rate * tree_blocked_rate_multiplier))
    tree_idx, line_idx = [], []
    for i, o in enumerate(req_outages):
        if getattr(o, "tree_blocked", -1) == 1:
            tree_idx.append(i)
        elif getattr(o, "tree_blocked", -1) == 0:
            line_idx.append(i)
        else:
            (tree_idx if rng.random() < eff_rate else line_idx).append(i)
    n_tree = max(1, int(round(crews * tree_crew_share)))
    n_line = max(1, crews - n_tree)
    return tree_idx, line_idx, n_tree, n_line


def _run_scheduler_sticky(req_outages, crews, seed, realistic, customer_weight,
                          crew_specialization, tree_blocked_rate, tree_crew_share,
                          hierarchical, tiered_priority, storm_duration,
                          road_multiplier=1.5, assessment_delay=12.0,
                          tree_blocked_rate_multiplier=1.0, total_customers=None,
                          is_localized=False, overnight_ops=None):
    """Crew stickiness: partition outages by substation territory (sub_id),
    split crews proportionally to each territory's customer count, run one
    independent sub-scheduler per territory in parallel. Total restoration =
    max across territories.

    Models the real-utility behaviour that a crew assigned to Storrs works in
    Storrs/Mansfield rather than driving to New Haven. Composes with every
    other realism toggle — each sub-scheduler call carries them through."""
    from concurrent.futures import ThreadPoolExecutor
    from collections import defaultdict
    # Group outages by their sub_id; outages missing a sub_id (sub_id < 0)
    # get a synthetic catch-all bucket.
    groups: dict[int, list] = defaultdict(list)
    for o in req_outages:
        groups[o.sub_id if o.sub_id >= 0 else -1].append(o)

    # Weight each territory by total customers so we hand it crews
    # proportional to the load it serves.
    weights = {sid: max(1.0, sum(o.customers for o in g)) for sid, g in groups.items()}
    total_w = sum(weights.values())

    # Allocate at least 1 crew per territory; distribute the remainder by
    # weight using the largest-remainder method so the total exactly equals
    # the requested crew count.
    n_groups = len(groups)
    if crews <= n_groups:
        # Tiny crew count vs many territories: give 1 to the n biggest
        # territories, none to the rest (the smallest get folded into the
        # nearest territory below).
        sids_sorted = sorted(groups.keys(), key=lambda s: -weights[s])
        alloc = {s: 0 for s in groups}
        for s in sids_sorted[:crews]:
            alloc[s] = 1
        # Fold zero-crew territories into the largest one so no outage is orphaned.
        biggest = sids_sorted[0]
        for s in list(groups.keys()):
            if alloc[s] == 0:
                groups[biggest].extend(groups[s])
                del groups[s]; del alloc[s]
    else:
        # >= 1 crew each, distribute remainder by weight.
        raw = {s: 1 + (crews - n_groups) * weights[s] / total_w for s in groups}
        alloc = {s: int(r) for s, r in raw.items()}
        rem = crews - sum(alloc.values())
        fracs = sorted(((raw[s] - alloc[s], s) for s in raw), reverse=True)
        for _, s in fracs[:rem]:
            alloc[s] += 1

    # Total customers for workload_mult MUST be the whole storm's, not each
    # territory's own subset — the staging/fuel/lodging/coordination friction
    # this multiplier stands in for is a function of the storm's overall
    # scale, not how much of it one territory's sub-scheduler happens to see.
    # Forced to 0 for a geographically-concentrated storm (is_localized),
    # which yields workload_mult=1x in plan_restoration_numba/fast -- see
    # ScheduleRequest.is_localized's docstring for why.
    if total_customers is None:
        total_customers = 0 if is_localized else sum(o.customers for o in req_outages)

    # Run each territory's sub-scheduler in parallel.
    def run_one(sid: int, outs: list, m: int, sub_seed: int):
        return _run_scheduler(
            outs, m, sub_seed, realistic, customer_weight,
            crew_specialization=crew_specialization,
            tree_blocked_rate=tree_blocked_rate, tree_crew_share=tree_crew_share,
            hierarchical=hierarchical, tiered_priority=tiered_priority,
            storm_duration=storm_duration, crew_stickiness=False,  # avoid recursion
            road_multiplier=road_multiplier,
            assessment_delay=assessment_delay,
            tree_blocked_rate_multiplier=tree_blocked_rate_multiplier,
            total_customers=total_customers,
            is_localized=is_localized,
            overnight_ops=overnight_ops,
        )

    futures = []
    max_workers = min(16, max(2, n_groups))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for i, (sid, outs) in enumerate(groups.items()):
            futures.append((sid, ex.submit(run_one, sid, outs, alloc[sid],
                                           seed + 100 + i)))
        results = [(sid, fut.result()) for sid, fut in futures]

    # Merge crew lists; total = max across territories.
    merged: list[CrewResult] = []
    total_h = 0.0
    for _sid, (t_sub, crews_sub) in results:
        if t_sub > total_h:
            total_h = t_sub
        merged.extend(crews_sub)
    return total_h, merged


def _run_scheduler_specialized(req_outages, crews, seed, realistic,
                               customer_weight, tree_blocked_rate, tree_crew_share,
                               hierarchical=False, tiered_priority=False,
                               storm_duration=0.0, road_multiplier=1.5,
                               assessment_delay=12.0,
                               tree_blocked_rate_multiplier=1.0,
                               total_customers=None, is_localized=False,
                               overnight_ops=None):
    """Crew specialization model: split outages by type, split crews by type,
    run two independent scheduler calls IN PARALLEL, merge results. Total
    restoration time = max of the two subsystems' finish times.

    The two subsystems are independent so running them sequentially wastes
    wall-clock time. Numba releases the GIL during JIT-compiled code, so a
    plain ThreadPoolExecutor delivers real parallelism here."""
    from concurrent.futures import ThreadPoolExecutor
    # See _run_scheduler_sticky for why this must be the whole storm's total,
    # not each subsystem's own outage-count-derived subset (and why it's
    # forced to 0 -- i.e. workload_mult=1x -- for a concentrated storm).
    if total_customers is None:
        total_customers = 0 if is_localized else sum(o.customers for o in req_outages)
    tree_idx, line_idx, n_tree, n_line = _split_for_specialization(
        req_outages, crews, seed, tree_blocked_rate, tree_crew_share,
        tree_blocked_rate_multiplier,
    )
    # Avoid degenerate sub-systems where a partition is empty.
    if not tree_idx or not line_idx:
        return _run_scheduler(req_outages, crews, seed, realistic,
                              customer_weight, hierarchical=hierarchical,
                              tiered_priority=tiered_priority,
                              storm_duration=storm_duration,
                              road_multiplier=road_multiplier,
                              assessment_delay=assessment_delay,
                              total_customers=total_customers,
                              is_localized=is_localized,
                              overnight_ops=overnight_ops)

    tree_outages = [req_outages[i] for i in tree_idx]
    line_outages = [req_outages[i] for i in line_idx]

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_tree = ex.submit(_run_scheduler, tree_outages, n_tree,
                             seed + 1, realistic, customer_weight,
                             False, tree_blocked_rate, tree_crew_share,
                             hierarchical, tiered_priority, storm_duration,
                             False, road_multiplier, assessment_delay,
                             tree_blocked_rate_multiplier,
                             total_customers=total_customers, is_localized=is_localized,
                             overnight_ops=overnight_ops)
        fut_line = ex.submit(_run_scheduler, line_outages, n_line,
                             seed + 2, realistic, customer_weight,
                             False, tree_blocked_rate, tree_crew_share,
                             hierarchical, tiered_priority, storm_duration,
                             False, road_multiplier, assessment_delay,
                             tree_blocked_rate_multiplier,
                             total_customers=total_customers, is_localized=is_localized,
                             overnight_ops=overnight_ops)
        t_tree, crews_tree = fut_tree.result()
        t_line, crews_line = fut_line.result()

    # Merge crew lists; relabel jobs with the right outage type tag so the
    # frontend can color or tooltip them differently if it wants.
    merged = []
    for c in crews_tree:
        merged.append(CrewResult(
            depot_lat=c.depot_lat, depot_lon=c.depot_lon,
            finish_time_h=c.finish_time_h, n_jobs=c.n_jobs, jobs=c.jobs,
        ))
    for c in crews_line:
        merged.append(CrewResult(
            depot_lat=c.depot_lat, depot_lon=c.depot_lon,
            finish_time_h=c.finish_time_h, n_jobs=c.n_jobs, jobs=c.jobs,
        ))
    total = max(t_tree, t_line)
    return total, merged


# Effective-customer bonus per priority tier. Large enough that a higher tier
# is always preferred over any realistic customer count within a crew's local
# search window, giving near-hard tiering while reusing the fast weighted path.
_PRIORITY_BONUS = 1.0e5


def _scaled_assessment(base: float, total_customers: float) -> float:
    """Small-event damage-assessment scaling -- parity with the JS scheduler
    (see the ASSESSMENT_DELAY comment in 03_grid_simulation.html:
    planRestoration()). Scales a base assessment delay DOWN for small storms
    (a few thousand scattered outages dispatch in hours, not the ~12h a
    statewide mega-storm needs to survey damage + mobilize mutual aid),
    anchored so events >=60,000 customers keep the full base, tapering to a
    4h floor. base==0 (pre-storm staging) stays 0. Computed HERE from the
    REAL customer sum -- deliberately not derived downstream, since the
    is_localized path zeroes the total_customers passed to the scheduler and
    a small localized storm must still get the reduced delay."""
    if base <= 0 or total_customers <= 0 or total_customers >= 60000:
        return base
    return max(4.0, min(base, base * (total_customers / 60000.0) ** 0.4))


def _run_scheduler(req_outages: list[Outage], crews: int, seed: int,
                   realistic: bool, customer_weight: float = 0.0,
                   crew_specialization: bool = False,
                   tree_blocked_rate: float = 0.90,
                   tree_crew_share: float = 0.20,
                   hierarchical: bool = False,
                   tiered_priority: bool = False,
                   storm_duration: float = 0.0,
                   crew_stickiness: bool = False,
                   road_multiplier: float = 1.5,
                   assessment_delay: float = 12.0,
                   tree_blocked_rate_multiplier: float = 1.0,
                   total_customers: float | None = None,
                   is_localized: bool = False,
                   overnight_ops: bool | None = None,
                   ) -> tuple[float, list[CrewResult]]:
    """Call the shared scheduler and convert the result into our response shape.

    total_customers: real (non-priority-bonused) total customer count for the
    whole storm, used to derive workload_mult in the core scheduler. Computed
    once here (or passed down from a caller that already knows it, e.g. a
    territory/specialization sub-call) so it never gets recomputed from a
    partial subset of outages — see _run_scheduler_sticky.
    is_localized: True for a storm confined to one corner of the state (see
    ScheduleRequest.is_localized) -- forces total_customers to 0 when the
    caller didn't already supply one, which yields workload_mult=1x.
    overnight_ops: small-storm overnight operations (see scheduler_numba.py
    for the EAGLE-I-derived rationale). Decided HERE from the whole storm's
    REAL customer sum -- deliberately not derived downstream from
    total_customers, because the is_localized path zeroes total_customers
    (to kill workload_mult) and a small localized storm must still get
    overnight ops. Threaded through territory/specialization sub-calls like
    total_customers so subsets never re-decide it."""
    if overnight_ops is None:
        real_total = sum(o.customers for o in req_outages)
        overnight_ops = bool(realistic and 0 < real_total <= 70000)
    if total_customers is None:
        total_customers = 0 if is_localized else sum(o.customers for o in req_outages)
    if crew_stickiness and len(req_outages) >= 10 and \
            any(o.sub_id >= 0 for o in req_outages):
        return _run_scheduler_sticky(
            req_outages, crews, seed, realistic, customer_weight,
            crew_specialization, tree_blocked_rate, tree_crew_share,
            hierarchical, tiered_priority, storm_duration, road_multiplier,
            assessment_delay, tree_blocked_rate_multiplier,
            total_customers=total_customers, is_localized=is_localized,
            overnight_ops=overnight_ops,
        )
    if crew_specialization and len(req_outages) >= 10:
        return _run_scheduler_specialized(
            req_outages, crews, seed, realistic, customer_weight,
            tree_blocked_rate, tree_crew_share, hierarchical, tiered_priority,
            storm_duration, road_multiplier,
            assessment_delay, tree_blocked_rate_multiplier,
            total_customers=total_customers, is_localized=is_localized,
            overnight_ops=overnight_ops,
        )
    outage_tuples = [(o.lat, o.lon) for o in req_outages]
    customers = [o.customers for o in req_outages]
    eff_weight = customer_weight
    if tiered_priority:
        # Add a per-tier bonus to the dispatch-scoring customer value so the
        # weighted scheduler serves higher tiers first. Force the weighted
        # path on (weight>0) even if customer-impact weighting is off. This
        # only affects dispatch ORDER — the customers-restored curve is built
        # frontend-side from real customer counts, not these effective values.
        customers = [o.customers + _PRIORITY_BONUS * o.priority for o in req_outages]
        if eff_weight <= 0.0:
            eff_weight = 5000.0
    if _NUMBA:
        crews_out, total_time, _timeline = plan_restoration_numba(
            outage_tuples, crews, realistic=realistic, seed=seed,
            customers=customers, customer_weight=eff_weight,
            feeder_id=[o.feeder_id for o in req_outages] if hierarchical else None,
            is_feeder=[o.is_feeder for o in req_outages] if hierarchical else None,
            hierarchical=hierarchical,
            storm_duration=storm_duration,
            road_multiplier=road_multiplier,
            assessment_delay=assessment_delay,
            total_customers=total_customers,
            overnight_ops=overnight_ops,
        )
    elif _FAST:
        crews_out, total_time, _timeline = plan_restoration_fast(
            outage_tuples, crews, realistic=realistic, seed=seed,
            total_customers=total_customers,
            overnight_ops=overnight_ops,
        )
    elif art is not None:
        rnd = art.mulberry32((seed * 31 + 99) & 0xFFFFFFFF)
        crews_out, total_time, _timeline = art.plan_restoration(
            outage_tuples, crews, rnd, realistic=realistic,
            total_customers=total_customers,
        )
    else:
        raise RuntimeError("No scheduler backend available")
    crew_results = [
        CrewResult(
            depot_lat=c["depot"][0],
            depot_lon=c["depot"][1],
            finish_time_h=c["time"],
            n_jobs=len(c["jobs"]),
            jobs=[JobResult(lat=j["lat"], lon=j["lon"], eta=j["eta"],
                            outage_idx=int(j.get("outage_idx", -1)))
                  for j in c["jobs"]],
        )
        for c in crews_out
    ]
    return total_time, crew_results


# --- Endpoints -----------------------------------------------------------

@app.get("/")
def root():
    return {
        "name": "Connecticut Grid Simulation Backend",
        "endpoints": [
            "GET  /              — this index",
            "GET  /health        — health check",
            "POST /api/schedule  — run the greedy scheduler",
            "POST /api/recommend — binary-search the optimal crew count",
            "POST /api/monte_carlo — N-run ensemble with different seeds",
            "POST /api/calibrate — tune realism parameters against an observed curve",
            "POST /api/batch    — fan out N scenarios across worker URLs in parallel",
        ],
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, Any]:
    """Report the git commit + backend mode the running server was built
    from. Lets the frontend display 'connected to: 3d074d2' so the user
    can verify the deploy is current vs. the GitHub HEAD."""
    sha = os.environ.get("RENDER_GIT_COMMIT", "unknown")
    if sha != "unknown":
        sha = sha[:7]
    backend = "numba" if _NUMBA else ("numpy" if _FAST else "python")
    return {"commit": sha, "backend": backend}


@app.post("/api/schedule", response_model=ScheduleResponse)
def schedule(req: ScheduleRequest) -> ScheduleResponse:
    def _compute() -> ScheduleResponse:
        # Multi-day storm drag: when the storm is "big" (long duration or many
        # outages), apply joint behavioural/sociotechnical slowdowns capturing
        # crew fatigue, out-of-town-crew unfamiliarity, resource exhaustion, and
        # the documented paradox that triple-time pay incentives can lengthen
        # major-event timelines. +6 hours of staging/coordination delay, and a
        # 15% bump on the road multiplier to capture cumulative debris + slower
        # mutual-aid driving + out-of-area routing.
        # ---- Multi-day storm drag (behavioral / sociotechnical) ----
        eff_storm = req.storm_duration
        eff_road = 1.5
        if req.storm_drag and (req.storm_duration > 12 or len(req.outages) > 5000):
            eff_storm = req.storm_duration + 6.0
            eff_road = 1.5 * 1.15
        # ---- Soil saturation (environmental) ----
        # Wet ground pulls roots out more easily (more tree damage), and slows
        # equipment + repair operations (mud, hydraulic stuck).
        tree_blocked_mult = 1.0
        if req.soil_saturation:
            eff_road *= 1.25
            tree_blocked_mult = 1.30
        # ---- Pre-storm staging (logistical) ----
        # Pre-positioned crews skip the 12 h post-storm assessment; work starts
        # as soon as winds drop below the safety threshold. For non-staged
        # storms the 12h base is scaled DOWN for small events (see
        # _scaled_assessment), computed from the whole storm's real customer
        # sum before is_localized can zero it.
        eff_assess = _scaled_assessment(
            0.0 if req.pre_storm_staging else 12.0,
            sum(o.customers for o in req.outages),
        )
        total, crews = _run_scheduler(
            req.outages, req.crews, req.seed, req.realistic, req.customer_weight,
            crew_specialization=req.crew_specialization,
            tree_blocked_rate=req.tree_blocked_rate,
            tree_crew_share=req.tree_crew_share,
            hierarchical=req.hierarchical,
            tiered_priority=req.tiered_priority,
            storm_duration=eff_storm,
            crew_stickiness=req.crew_stickiness,
            road_multiplier=eff_road,
            assessment_delay=eff_assess,
            tree_blocked_rate_multiplier=tree_blocked_mult,
            is_localized=req.is_localized,
        )
        return ScheduleResponse(total_time_h=total, crews=crews)

    return cached_response("schedule", req, ScheduleResponse, _compute)


def _scheduler_time_only(outage_tuples, m_crews, seed, realistic,
                         req: "RecommendRequest | None" = None):
    """Run the scheduler and return only the total restoration time.

    If a full RecommendRequest is supplied, routes through _run_scheduler so
    all realistic-mode flags (crew stickiness, specialization, hierarchy, etc.)
    are applied — matching what the full simulation produces."""
    # total_customers must be computed the same way regardless of which
    # branch below runs, or a bare-bones recommend call (no realism flags
    # set) would silently skip workload_mult while /api/schedule doesn't —
    # producing a "recommended" crew count that undershoots the time the
    # actual simulation goes on to report for that count.
    if req is not None:
        real_total = sum(o.customers for o in req.outages)
        total_customers = 0 if req.is_localized else real_total
        # Overnight ops from the REAL sum (see _run_scheduler) so small
        # localized storms keep overnight behavior in the recommend search.
        overnight_ops = bool(realistic and 0 < real_total <= 70000)
        # Small-event assessment scaling from the real sum, matching
        # schedule() so the recommended crew count is consistent with what
        # the full simulation reports (see _scaled_assessment).
        eff_assess = _scaled_assessment(12.0, real_total) if realistic else 0.0
    else:
        total_customers = None
        overnight_ops = None
        eff_assess = None
    if req is not None and (req.crew_specialization or req.crew_stickiness
                            or req.hierarchical or req.tiered_priority
                            or req.customer_weight or req.storm_duration):
        # Convert outage_tuples back to Outage objects with full metadata
        outages = [o for o in req.outages]
        total, _ = _run_scheduler(
            outages, m_crews, seed, realistic,
            customer_weight=req.customer_weight,
            crew_specialization=req.crew_specialization,
            tree_blocked_rate=req.tree_blocked_rate,
            tree_crew_share=req.tree_crew_share,
            hierarchical=req.hierarchical,
            tiered_priority=req.tiered_priority,
            storm_duration=req.storm_duration,
            crew_stickiness=req.crew_stickiness,
            assessment_delay=eff_assess,
            total_customers=total_customers,
            is_localized=req.is_localized,
            overnight_ops=overnight_ops,
        )
        return float(total)
    if _NUMBA:
        _, total, _ = plan_restoration_numba(
            outage_tuples, m_crews, realistic=realistic, seed=seed,
            total_customers=total_customers,
            overnight_ops=overnight_ops,
            assessment_delay=(eff_assess if eff_assess is not None else 12.0),
        )
        return float(total)
    if _FAST:
        _, total, _ = plan_restoration_fast(
            outage_tuples, m_crews, realistic=realistic, seed=seed,
            total_customers=total_customers,
            overnight_ops=overnight_ops,
        )
        return float(total)
    raise RuntimeError("No scheduler backend available")


@app.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest) -> RecommendResponse:
    """Find the smallest crew count that achieves a restoration time within
    `tolerance` × the theoretical floor (crews == N). Binary search; each
    iteration runs the full Numba scheduler. At N=250k a single scheduler
    call is ~660 ms, so the whole search (~17 iterations) takes ~10-12 s
    — vs minutes for the in-browser JS path."""
    N = len(req.outages)
    if N == 0:
        return RecommendResponse(
            recommended_crews=0, recommended_time_h=0.0,
            floor_time_h=0.0, upper_bound=0, tolerance=req.tolerance,
            evaluations=[],
        )

    outage_tuples = [(o.lat, o.lon) for o in req.outages]
    # Cap upper at 5000 (slider max) — no point searching beyond what the UI allows
    upper = req.upper_bound or min(5000, max(50, N // 5))
    upper = min(upper, N)

    cache: dict[int, float] = {}
    evaluations: list[RecommendEvaluation] = []

    # Round crew counts to nearest 50 — cuts binary search from ~12 to ~7 iterations
    # (log2(5000/50) ≈ 7) while still being accurate to within 50 crews.
    # Full realistic scheduler is used so the result matches Plan restoration flags.
    # Most iterations hit low crew counts (~500-1500) which are fast (~0.3-0.7s);
    # only the floor eval at 5000 crews is slow (~2s). Total: ~8-10s.
    STEP = 50

    def snap(m: int) -> int:
        return max(STEP, round(m / STEP) * STEP)

    def t_realistic(m: int) -> float:
        m = snap(m)
        if m in cache:
            return cache[m]
        t = _scheduler_time_only(outage_tuples, m, req.seed, req.realistic, req)
        cache[m] = t
        evaluations.append(RecommendEvaluation(crews=m, total_time_h=t))
        return t

    floor_t = t_realistic(upper)
    target  = floor_t * req.tolerance

    lo, hi = STEP, upper
    while lo < hi:
        mid = snap((lo + hi) // 2)
        if t_realistic(mid) <= target:
            hi = mid
        else:
            lo = mid + STEP

    best = snap(lo)
    return RecommendResponse(
        recommended_crews=best,
        recommended_time_h=t_realistic(best),
        floor_time_h=floor_t,
        upper_bound=upper,
        tolerance=req.tolerance,
        evaluations=evaluations,
    )


def _build_simulated_curve(outage_tuples, customers, m_crews, seed,
                           travel_mph, assessment_delay,
                           workday_hours, road_multiplier,
                           sample_hours):
    """Run the scheduler with the given realism parameters and return a
    (sample_hours, simulated_customers_restored) curve sampled at the same
    hours as the observed curve so RMSE is comparable point-for-point."""
    if not _NUMBA:
        raise RuntimeError("Calibration requires the Numba scheduler")
    crews_out, _total, _timeline = plan_restoration_numba(
        outage_tuples, m_crews, realistic=True, seed=seed,
        customers=customers, customer_weight=0.0,
        travel_mph=travel_mph, assessment_delay=assessment_delay,
        workday_hours=workday_hours, road_multiplier=road_multiplier,
    )
    # Collect (eta, customers) pairs across all crews/jobs.
    pairs = []
    for c in crews_out:
        for j in c["jobs"]:
            cust = customers[j["outage_idx"]] if j["outage_idx"] < len(customers) else 0.0
            pairs.append((j["eta"], cust))
    pairs.sort()
    # Cumulative customers restored over time.
    cum_t, cum_c = [], []
    running = 0.0
    for t, c in pairs:
        running += c
        cum_t.append(t); cum_c.append(running)
    # Sample the cumulative curve at each requested hour. Step-function
    # interpolation: at hour h, find the latest dispatch eta <= h.
    out = []
    j = 0
    for h in sample_hours:
        while j < len(cum_t) and cum_t[j] <= h:
            j += 1
        out.append(cum_c[j - 1] if j > 0 else 0.0)
    return out


@app.post("/api/calibrate", response_model=CalibrateResponse)
def calibrate(req: CalibrateRequest) -> CalibrateResponse:
    """Calibration framework. Optimises the four most-tunable realism
    parameters (travel_mph, assessment_delay, workday_hours, road_multiplier)
    to minimise RMSE between the simulator's restoration curve on the given
    scenario and the observed curve from a real storm.

    Uses scipy.optimize.minimize with Nelder-Mead (gradient-free, well-suited
    to this kind of black-box objective). Each evaluation is one full Numba
    scheduler run, so a 50-iteration calibration on a 5k-outage scenario
    takes a few seconds. At 250k outages it's a minute or two — still
    feasible for a research workflow."""
    from scipy.optimize import minimize

    outage_tuples = [(o.lat, o.lon) for o in req.outages]
    customers = [o.customers for o in req.outages]
    sample_hours = [p.hour for p in req.observed]
    observed = [p.customers_restored for p in req.observed]

    eval_count = {"n": 0}

    def objective(x):
        travel, assess, workday, road = x
        eval_count["n"] += 1
        # Reject implausible parameter values up front to keep Nelder-Mead
        # inside a reasonable region.
        if travel < 5.0 or travel > 60.0: return 1e12
        if assess < 0.0 or assess > 48.0: return 1e12
        if workday < 4.0 or workday > 24.0: return 1e12
        if road < 1.0 or road > 4.0: return 1e12
        sim = _build_simulated_curve(
            outage_tuples, customers, req.crews, req.seed,
            travel, assess, workday, road, sample_hours,
        )
        # RMSE between simulated and observed cumulative restoration curves.
        diffs = [(s - o) for s, o in zip(sim, observed)]
        return (sum(d * d for d in diffs) / len(diffs)) ** 0.5

    x0 = [req.initial_travel_mph, req.initial_assessment_delay,
          req.initial_workday_hours, req.initial_road_multiplier]
    initial_rmse = objective(x0)

    result = minimize(
        objective, x0, method="Nelder-Mead",
        options={"maxiter": req.max_iters, "xatol": 0.1, "fatol": 1.0,
                 "disp": False},
    )

    best = result.x
    final_rmse = float(result.fun)
    # Compute the final simulated curve at the best fit so the client can plot.
    final_sim = _build_simulated_curve(
        outage_tuples, customers, req.crews, req.seed,
        float(best[0]), float(best[1]), float(best[2]), float(best[3]),
        sample_hours,
    )

    return CalibrateResponse(
        travel_mph=float(best[0]),
        assessment_delay=float(best[1]),
        workday_hours=float(best[2]),
        road_multiplier=float(best[3]),
        rmse=final_rmse,
        initial_rmse=float(initial_rmse),
        n_evaluations=eval_count["n"],
        converged=bool(result.success),
        simulated_curve=[
            ObservedPoint(hour=h, customers_restored=c)
            for h, c in zip(sample_hours, final_sim)
        ],
    )


def _dispatch_batch_scenario(scenario: BatchScenario, worker_url: str
                             ) -> BatchScenarioResult:
    """Run one scenario. If worker_url is empty or matches our own server,
    runs locally (in-process). Otherwise POSTs to that worker's /api/schedule
    and returns just the total time + crew count from the response."""
    import time
    start = time.time()
    try:
        if not worker_url:
            # Local in-process path.
            total, crews = _run_scheduler(
                scenario.outages, scenario.crews, scenario.seed,
                scenario.realistic, scenario.customer_weight,
                crew_specialization=scenario.crew_specialization,
                tree_blocked_rate=scenario.tree_blocked_rate,
                tree_crew_share=scenario.tree_crew_share,
            )
            elapsed = (time.time() - start) * 1000
            return BatchScenarioResult(
                label=scenario.label, total_time_h=total, n_crews=len(crews),
                elapsed_ms=elapsed, worker="local",
            )

        # Remote worker path — POST to the worker's /api/schedule.
        import json
        import urllib.request
        body = scenario.model_dump()
        body.pop("label", None)
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            worker_url.rstrip("/") + "/api/schedule",
            data=data, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.loads(r.read())
        elapsed = (time.time() - start) * 1000
        return BatchScenarioResult(
            label=scenario.label,
            total_time_h=float(resp.get("total_time_h", 0.0)),
            n_crews=len(resp.get("crews", [])),
            elapsed_ms=elapsed, worker=worker_url,
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return BatchScenarioResult(
            label=scenario.label, total_time_h=0.0, n_crews=0,
            elapsed_ms=elapsed, worker=worker_url or "local", error=str(e),
        )


@app.post("/api/batch", response_model=BatchResponse)
def batch(req: BatchRequest) -> BatchResponse:
    """Fan out N scenarios across M worker URLs in parallel. Each scenario
    becomes one HTTP POST to a worker's /api/schedule. When workers list is
    empty, runs serially in-process. The user spins up additional free
    Render services (each with its own URL) and pastes their URLs into the
    workers list to scale linearly."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    start = time.time()
    workers = [w.strip() for w in req.workers if w.strip()]
    # Round-robin scenarios onto workers (or local if list empty).
    assignments: list[tuple[BatchScenario, str]] = []
    if workers:
        for i, s in enumerate(req.scenarios):
            assignments.append((s, workers[i % len(workers)]))
    else:
        for s in req.scenarios:
            assignments.append((s, ""))
    # Parallel fan-out via threads (one thread per scenario; bounded so we
    # don't open hundreds of sockets at once).
    max_parallel = max(1, len(workers)) if workers else 1
    max_parallel = min(max_parallel * 4, len(assignments), 32)
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        results = list(pool.map(lambda a: _dispatch_batch_scenario(*a),
                                assignments))
    total_elapsed = (time.time() - start) * 1000
    return BatchResponse(
        results=results, total_elapsed_ms=total_elapsed,
        n_workers=len(workers) if workers else 1,
    )


def _mc_worker(args):
    """Top-level (picklable) worker invoked in the process pool."""
    outage_tuples, crews, seed, realistic, total_customers, overnight_ops, assessment_delay = args
    try:
        from scheduler_numba import plan_restoration_numba
        _, total, _ = plan_restoration_numba(outage_tuples, crews,
                                             realistic=realistic, seed=seed,
                                             total_customers=total_customers,
                                             overnight_ops=overnight_ops,
                                             assessment_delay=assessment_delay)
        return total
    except Exception:
        from scheduler_fast import plan_restoration_fast
        _, total, _ = plan_restoration_fast(outage_tuples, crews,
                                            realistic=realistic, seed=seed,
                                            total_customers=total_customers,
                                            overnight_ops=overnight_ops)
        return total


@app.post("/api/monte_carlo", response_model=MonteCarloResponse)
def monte_carlo(req: MonteCarloRequest) -> MonteCarloResponse:
    """Run the scheduler N times with different seeds and return aggregate
    statistics over the resulting restoration times. Parallelized across CPU
    cores via ProcessPoolExecutor so 30 seeds finish in ~30/n_cores the time.
    Results are disk-cached (see cached_response) since a full ensemble at
    statewide scale is the single most expensive request this server serves."""
    def _compute() -> MonteCarloResponse:
        outage_tuples = [(o.lat, o.lon) for o in req.outages]
        # Compute effective flags (mirrors schedule() logic).
        eff_storm = req.storm_duration + (6.0 if req.storm_drag else 0.0)
        eff_road  = 1.5 * (1.25 if req.soil_saturation else 1.0)
        tree_mult = 1.3 if req.soil_saturation else 1.0
        real_total = sum(o.customers for o in req.outages)
        # Small-event assessment scaling from the real customer sum (parity
        # with schedule() and the JS scheduler; see _scaled_assessment).
        eff_assess = _scaled_assessment(0.0 if req.pre_storm_staging else 12.0, real_total)
        has_sub_flags = (
            req.crew_specialization or req.crew_stickiness or req.hierarchical
            or req.tiered_priority or req.customer_weight > 0 or req.storm_duration > 0
            or req.storm_drag or req.soil_saturation or req.pre_storm_staging
        )
        # Only use the process pool when sub-flags are all off (the pool worker uses
        # bare numba which ignores sub-flags). When any sub-flag is active, run
        # serially through _run_scheduler so results match the main simulation.
        N = len(outage_tuples)
        use_pool = not has_sub_flags and (N * req.crews) > 10_000_000
        if use_pool:
            total_customers = 0 if req.is_localized else real_total
            overnight_ops = bool(req.realistic and 0 < real_total <= 70000)
            jobs = [(outage_tuples, req.crews,
                     (req.base_seed + k * 9973) & 0xFFFFFFFF, req.realistic,
                     total_customers, overnight_ops, eff_assess)
                    for k in range(req.n_runs)]
            pool = _get_pool()
            times = list(pool.map(_mc_worker, jobs))
        else:
            times = []
            for k in range(req.n_runs):
                seed = (req.base_seed + k * 9973) & 0xFFFFFFFF
                total, _ = _run_scheduler(
                    req.outages, req.crews, seed, req.realistic,
                    customer_weight=req.customer_weight,
                    crew_specialization=req.crew_specialization,
                    tree_blocked_rate=req.tree_blocked_rate,
                    tree_crew_share=req.tree_crew_share,
                    hierarchical=req.hierarchical,
                    tiered_priority=req.tiered_priority,
                    storm_duration=eff_storm,
                    crew_stickiness=req.crew_stickiness,
                    road_multiplier=eff_road,
                    assessment_delay=eff_assess,
                    tree_blocked_rate_multiplier=tree_mult,
                    is_localized=req.is_localized,
                )
                times.append(total)
        times_sorted = sorted(times)
        n = len(times_sorted)
        def pct(p: float) -> float:
            idx = max(0, min(n - 1, int(p * (n - 1))))
            return times_sorted[idx]
        return MonteCarloResponse(
            n_runs=n,
            mean_h=statistics.mean(times),
            median_h=statistics.median(times),
            stddev_h=statistics.stdev(times) if n >= 2 else 0.0,
            p05_h=pct(0.05),
            p95_h=pct(0.95),
            min_h=min(times),
            max_h=max(times),
            individual_h=times,
        )

    return cached_response("monte_carlo", req, MonteCarloResponse, _compute)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
