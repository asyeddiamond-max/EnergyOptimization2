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


# --- Schemas ---------------------------------------------------------------

class Outage(BaseModel):
    lat: float
    lon: float
    critical: bool = False
    customers: float = 0.0  # number of customers served by this outage point


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

def _run_scheduler(req_outages: list[Outage], crews: int, seed: int,
                   realistic: bool, customer_weight: float = 0.0
                   ) -> tuple[float, list[CrewResult]]:
    """Call the shared scheduler and convert the result into our response shape."""
    outage_tuples = [(o.lat, o.lon) for o in req_outages]
    customers = [o.customers for o in req_outages]
    if _NUMBA:
        crews_out, total_time, _timeline = plan_restoration_numba(
            outage_tuples, crews, realistic=realistic, seed=seed,
            customers=customers, customer_weight=customer_weight,
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
    total, crews = _run_scheduler(req.outages, req.crews, req.seed,
                                  req.realistic, req.customer_weight)
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
