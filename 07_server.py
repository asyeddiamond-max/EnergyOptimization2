"""
07_server.py — FastAPI backend for the Hartford County simulation.

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


app = FastAPI(
    title="Hartford County Grid Simulation Backend",
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


class ScheduleRequest(BaseModel):
    outages: list[Outage]
    crews: int = Field(ge=1, description="Number of repair crews")
    seed: int = 42
    realistic: bool = True
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
    tree_blocked_rate: float = Field(default=0.30, ge=0.0, le=1.0,
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


class JobResult(BaseModel):
    lat: float
    lon: float
    eta: float


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
    tolerance: float = Field(default=1.15, ge=1.01, le=2.0,
        description="Acceptable multiple of the floor restoration time")
    upper_bound: int | None = Field(default=None, description=
        "Override the upper-bound crew count tried; defaults to max(50, N/10)")


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
    tree_blocked_rate: float = 0.30
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
    base_seed: int = 42
    n_runs: int = Field(default=30, ge=2, le=200,
                        description="Number of seeds to sample")


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
                              tree_blocked_rate: float, tree_crew_share: float):
    """Partition outages and crews into tree vs line subsystems. The split
    is seed-deterministic so the same scenario produces the same partition
    every run."""
    import random as _rand
    rng = _rand.Random((seed * 7919 + 17) & 0xFFFFFFFF)
    tree_idx, line_idx = [], []
    for i in range(len(req_outages)):
        (tree_idx if rng.random() < tree_blocked_rate else line_idx).append(i)
    n_tree = max(1, int(round(crews * tree_crew_share)))
    n_line = max(1, crews - n_tree)
    return tree_idx, line_idx, n_tree, n_line


def _run_scheduler_specialized(req_outages, crews, seed, realistic,
                               customer_weight, tree_blocked_rate, tree_crew_share,
                               hierarchical=False, tiered_priority=False,
                               storm_duration=0.0):
    """Crew specialization model: split outages by type, split crews by type,
    run two independent scheduler calls IN PARALLEL, merge results. Total
    restoration time = max of the two subsystems' finish times.

    The two subsystems are independent so running them sequentially wastes
    wall-clock time. Numba releases the GIL during JIT-compiled code, so a
    plain ThreadPoolExecutor delivers real parallelism here."""
    from concurrent.futures import ThreadPoolExecutor
    tree_idx, line_idx, n_tree, n_line = _split_for_specialization(
        req_outages, crews, seed, tree_blocked_rate, tree_crew_share,
    )
    # Avoid degenerate sub-systems where a partition is empty.
    if not tree_idx or not line_idx:
        return _run_scheduler(req_outages, crews, seed, realistic,
                              customer_weight, hierarchical=hierarchical,
                              tiered_priority=tiered_priority,
                              storm_duration=storm_duration)

    tree_outages = [req_outages[i] for i in tree_idx]
    line_outages = [req_outages[i] for i in line_idx]

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_tree = ex.submit(_run_scheduler, tree_outages, n_tree,
                             seed + 1, realistic, customer_weight,
                             False, tree_blocked_rate, tree_crew_share,
                             hierarchical, tiered_priority, storm_duration)
        fut_line = ex.submit(_run_scheduler, line_outages, n_line,
                             seed + 2, realistic, customer_weight,
                             False, tree_blocked_rate, tree_crew_share,
                             hierarchical, tiered_priority, storm_duration)
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


def _run_scheduler(req_outages: list[Outage], crews: int, seed: int,
                   realistic: bool, customer_weight: float = 0.0,
                   crew_specialization: bool = False,
                   tree_blocked_rate: float = 0.30,
                   tree_crew_share: float = 0.20,
                   hierarchical: bool = False,
                   tiered_priority: bool = False,
                   storm_duration: float = 0.0,
                   ) -> tuple[float, list[CrewResult]]:
    """Call the shared scheduler and convert the result into our response shape."""
    if crew_specialization and len(req_outages) >= 10:
        return _run_scheduler_specialized(
            req_outages, crews, seed, realistic, customer_weight,
            tree_blocked_rate, tree_crew_share, hierarchical, tiered_priority,
            storm_duration,
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
        )
    elif _FAST:
        crews_out, total_time, _timeline = plan_restoration_fast(
            outage_tuples, crews, realistic=realistic, seed=seed
        )
    elif art is not None:
        rnd = art.mulberry32((seed * 31 + 99) & 0xFFFFFFFF)
        crews_out, total_time, _timeline = art.plan_restoration(
            outage_tuples, crews, rnd, realistic=realistic
        )
    else:
        raise RuntimeError("No scheduler backend available")
    crew_results = [
        CrewResult(
            depot_lat=c["depot"][0],
            depot_lon=c["depot"][1],
            finish_time_h=c["time"],
            n_jobs=len(c["jobs"]),
            jobs=[JobResult(lat=j["lat"], lon=j["lon"], eta=j["eta"])
                  for j in c["jobs"]],
        )
        for c in crews_out
    ]
    return total_time, crew_results


# --- Endpoints -----------------------------------------------------------

@app.get("/")
def root():
    return {
        "name": "Hartford County Grid Simulation Backend",
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
    total, crews = _run_scheduler(
        req.outages, req.crews, req.seed, req.realistic, req.customer_weight,
        crew_specialization=req.crew_specialization,
        tree_blocked_rate=req.tree_blocked_rate,
        tree_crew_share=req.tree_crew_share,
        hierarchical=req.hierarchical,
        tiered_priority=req.tiered_priority,
        storm_duration=req.storm_duration,
    )
    return ScheduleResponse(total_time_h=total, crews=crews)


def _scheduler_time_only(outage_tuples, m_crews, seed, realistic):
    """Run the scheduler and return only the total restoration time.

    Skips the expensive per-job result construction — recommend search only
    needs the makespan, not the dispatch sequence."""
    if _NUMBA:
        _, total, _ = plan_restoration_numba(
            outage_tuples, m_crews, realistic=realistic, seed=seed
        )
        return float(total)
    if _FAST:
        _, total, _ = plan_restoration_fast(
            outage_tuples, m_crews, realistic=realistic, seed=seed
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
    upper = req.upper_bound or max(50, (N + 9) // 10)
    upper = min(upper, N)

    cache: dict[int, float] = {}
    evaluations: list[RecommendEvaluation] = []

    def t_at(m: int) -> float:
        if m in cache:
            return cache[m]
        t = _scheduler_time_only(outage_tuples, m, req.seed, req.realistic)
        cache[m] = t
        evaluations.append(RecommendEvaluation(crews=m, total_time_h=t))
        return t

    floor_t = t_at(upper)
    target = floor_t * req.tolerance

    lo, hi = 1, upper
    while lo < hi:
        mid = (lo + hi) // 2
        if t_at(mid) <= target:
            hi = mid
        else:
            lo = mid + 1

    return RecommendResponse(
        recommended_crews=lo,
        recommended_time_h=t_at(lo),
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
    outage_tuples, crews, seed, realistic = args
    try:
        from scheduler_numba import plan_restoration_numba
        _, total, _ = plan_restoration_numba(outage_tuples, crews,
                                             realistic=realistic, seed=seed)
        return total
    except Exception:
        from scheduler_fast import plan_restoration_fast
        _, total, _ = plan_restoration_fast(outage_tuples, crews,
                                            realistic=realistic, seed=seed)
        return total


@app.post("/api/monte_carlo", response_model=MonteCarloResponse)
def monte_carlo(req: MonteCarloRequest) -> MonteCarloResponse:
    """Run the scheduler N times with different seeds and return aggregate
    statistics over the resulting restoration times. Parallelized across CPU
    cores via ProcessPoolExecutor so 30 seeds finish in ~30/n_cores the time."""
    outage_tuples = [(o.lat, o.lon) for o in req.outages]
    # Numba is so fast (~tens of ms per run on typical scenarios) that the
    # ProcessPoolExecutor overhead — Windows spawn + per-worker JIT cache
    # load — costs more than the parallelism saves. Only use the pool when
    # per-run cost is expected to dominate spawn overhead.
    N = len(outage_tuples)
    use_pool = (N * req.crews) > 10_000_000  # heuristic: ~1s+ per run
    if use_pool:
        jobs = [(outage_tuples, req.crews,
                 (req.base_seed + k * 9973) & 0xFFFFFFFF, req.realistic)
                for k in range(req.n_runs)]
        pool = _get_pool()
        times = list(pool.map(_mc_worker, jobs))
    else:
        times = []
        for k in range(req.n_runs):
            seed = (req.base_seed + k * 9973) & 0xFFFFFFFF
            total, _ = _run_scheduler(req.outages, req.crews, seed, req.realistic)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
