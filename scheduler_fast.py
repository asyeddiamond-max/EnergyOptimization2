"""
scheduler_fast.py — NumPy-vectorized port of plan_restoration() for the server.

Same algorithm as 05_generate_artifacts.py:plan_restoration but the hot inner
loop ("find nearest undone visible outage from this crew's location") is a
single vectorized argmin over a masked squared-distance array instead of a
Python for-loop. On 25k-outage scenarios this is ~50-100x faster than the pure
Python version, which makes 30-seed Monte Carlo runs finish in seconds instead
of minutes.

The output shape matches plan_restoration() so the server's response
construction works unchanged.
"""
from __future__ import annotations

import heapq
import math
import numpy as np

try:
    from scipy.spatial import cKDTree
    _HAS_KDTREE = True
except ImportError:
    _HAS_KDTREE = False


def _mulberry32(seed: int):
    state = [seed & 0xFFFFFFFF]
    def gen():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = state[0]
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return gen


def _haversine_miles_vec(lat1, lon1, lat2_arr, lon2_arr):
    """Vectorized haversine. lat1/lon1 scalar, lat2_arr/lon2_arr ndarray."""
    R = 3958.7613
    p1 = math.radians(lat1)
    p2 = np.radians(lat2_arr)
    dphi = p2 - p1
    dlam = np.radians(lon2_arr - lon1)
    a = np.sin(dphi * 0.5) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlam * 0.5) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def plan_restoration_fast(outages, m_crews, realistic=True, seed=42, total_customers=None,
                          overnight_ops=None, assessment_delay=None):
    """Vectorized scheduler. `outages` is a list of (lat, lon) tuples.

    Returns (crews, total_time, timeline) in the same shape as the reference
    implementation in 05_generate_artifacts.py.

    total_customers: real total customer count for this storm. Drives
    workload_mult below (ported from the JS scheduler's workloadSlowdownMult
    — see 03_grid_simulation.html:planRestoration()). None/0 -> no slowdown
    (this fallback path has no per-outage customer data to sum itself).
    overnight_ops: small-storm overnight operations (see scheduler_numba.py's
    plan_restoration_numba for the EAGLE-I-derived rationale); None derives
    it from total_customers.
    assessment_delay: pre-work damage-assessment hours; None derives the same
    small-event scaling as the JS scheduler / _scaled_assessment (12h base,
    tapering to a 4h floor below 60k customers).
    """
    N = len(outages)
    if N == 0 or m_crews == 0:
        return [], 0.0, []

    tc = float(total_customers) if total_customers is not None else 0.0
    workload_mult = max(1.0, 0.00928 * (tc ** 0.473)) if tc > 0 else 1.0
    if overnight_ops is None:
        overnight_ops = 0 < tc <= 70000

    TRAVEL_MPH = 25 if realistic else 30
    if assessment_delay is not None:
        ASSESSMENT_DELAY = assessment_delay if realistic else 0
    elif realistic and 0 < tc < 60000:
        ASSESSMENT_DELAY = max(4.0, min(12.0, 12.0 * (tc / 60000.0) ** 0.4))
    else:
        ASSESSMENT_DELAY = 12 if realistic else 0
    WORKDAY_HOURS = 24 if overnight_ops else (14 if realistic else 24)
    ROAD_MULTIPLIER = 1.5 if realistic else 1.0

    lat = np.array([o[0] for o in outages], dtype=np.float64)
    lon = np.array([o[1] for o in outages], dtype=np.float64)

    # Per-seed RNG streams so Monte Carlo runs actually vary.
    rnd_repair = _mulberry32((seed * 1117 + 23) & 0xFFFFFFFF)
    rnd_disc = _mulberry32((seed * 991 + 7) & 0xFFFFFFFF)

    # Pre-sample repair durations: one per outage (matches reference behavior
    # of pulling from the stream once per dispatched job, in dispatch order).
    # The reference advances the stream in dispatch order, not outage-index
    # order — to keep parity, we'll consume on demand from a generator below.
    def sample_repair():
        if not realistic:
            return 1.5
        u1 = max(1e-10, rnd_repair())
        u2 = rnd_repair()
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        return max(0.25, min(12.0, math.exp(math.log(2) + 0.857 * z)))

    # Discovery times — vectorized
    if realistic:
        u = np.array([rnd_disc() for _ in range(N)], dtype=np.float64)
        disc = np.empty(N, dtype=np.float64)
        mask_lo = u < 0.30
        disc[mask_lo] = ASSESSMENT_DELAY + u[mask_lo] * (1.0 / 0.30)
        v = (u[~mask_lo] - 0.30) / 0.70
        t_after = -np.log(np.maximum(1e-9, 1 - 0.99 * v)) / 0.1
        disc[~mask_lo] = ASSESSMENT_DELAY + 1 + np.minimum(36.0, t_after)
    else:
        disc = np.zeros(N, dtype=np.float64)

    # Pre-sort discovery times so the "next discovery after t" lookup is
    # O(log N) via searchsorted instead of O(N) via masked-min. This matters
    # when m_crews >> N/avg_jobs_per_crew and many crews are idle waiting.
    disc_sorted = np.sort(disc) if realistic else None

    # Mutual-aid waves
    if realistic and m_crews >= 6:
        n_init = math.ceil(m_crews * 0.5)
        n_w1 = math.ceil(m_crews * 0.3)
        n_w2 = m_crews - n_init - n_w1
        arrivals = ([ASSESSMENT_DELAY] * n_init +
                    [ASSESSMENT_DELAY + 24] * n_w1 +
                    [ASSESSMENT_DELAY + 48] * n_w2)
    else:
        arrivals = [ASSESSMENT_DELAY] * m_crews

    depots = [outages[i % N] for i in range(m_crews)]
    crews = [{"depot": d, "time": arrivals[i], "lat": d[0], "lon": d[1], "jobs": []}
             for i, d in enumerate(depots)]

    done = np.zeros(N, dtype=bool)
    remaining = N
    heap = [(arrivals[c], c) for c in range(m_crews)]
    heapq.heapify(heap)
    timeline = [(0.0, N)]
    INF = np.float64(np.inf)

    # KD-tree over outage locations for O(log N) nearest-neighbor lookups.
    # We can't delete from a static tree, so on each dispatch we query the
    # K nearest, walk them in order, and accept the first one that's both
    # undone and (in realistic mode) already discovered. K grows when too
    # many candidates are filtered out. Falls back to vectorized argmin
    # if scipy isn't installed.
    coords = np.column_stack((lat, lon)) if _HAS_KDTREE else None
    kdtree = cKDTree(coords) if _HAS_KDTREE else None

    def clamp(t):
        if not realistic:
            return t
        dn = int(t // 24); ind = t - dn * 24
        return (dn + 1) * 24 if ind > WORKDAY_HOURS else t

    while remaining > 0:
        t_now, ci = heapq.heappop(heap)
        crew = crews[ci]

        # Nearest-undone-visible search. KD-tree path is O(K log N) where K
        # is the number of nearest neighbors we have to walk before finding
        # one that's valid; grows when the area around the crew is mostly
        # already done. Fallback path is the vectorized O(N) scan.
        best = -1
        if kdtree is not None:
            qpt = (crew["lat"], crew["lon"])
            # Cap K to ~256: past that, KD-tree's query cost approaches a
            # vectorized scan, so just fall through to the O(N) path.
            K_CAP = min(256, N)
            k = min(32, N)
            while True:
                _d, idxs = kdtree.query(qpt, k=k)
                if k == 1:
                    idxs = np.array([int(idxs)])
                for ii in idxs:
                    i = int(ii)
                    if done[i]:
                        continue
                    if realistic and disc[i] > t_now:
                        continue
                    best = i
                    break
                if best != -1 or k >= K_CAP:
                    break
                k = min(K_CAP, k * 4)
        if best == -1:
            # Fallback / not-found: do the vectorized masked argmin.
            dx = lat - crew["lat"]
            dy = lon - crew["lon"]
            d2 = dx * dx + dy * dy
            invalid = done | (disc > t_now) if realistic else done
            d2_masked = np.where(invalid, INF, d2)
            cand = int(np.argmin(d2_masked))
            if np.isfinite(d2_masked[cand]):
                best = cand
        if best == -1:
            # Nothing visible. Fast-forward to next discovery or quit.
            if realistic:
                # O(log N) lookup of first discovery strictly after t_now.
                # We don't filter by done here — at worst we wake the crew
                # slightly early and it loops once more, which is fine.
                idx = int(np.searchsorted(disc_sorted, t_now, side="right"))
                if idx >= N:
                    break
                nxt = float(disc_sorted[idx])
                crew["time"] = nxt
                heapq.heappush(heap, (nxt, ci))
                continue
            break

        done[best] = True
        remaining -= 1
        miles = _haversine_miles_vec(crew["lat"], crew["lon"],
                                     np.array([lat[best]]),
                                     np.array([lon[best]]))[0] * ROAD_MULTIPLIER
        repair_h = sample_repair()
        eta = clamp(crew["time"] + (miles / TRAVEL_MPH + repair_h) * workload_mult)
        crew["time"] = eta
        crew["lat"] = float(lat[best])
        crew["lon"] = float(lon[best])
        crew["jobs"].append({
            "outage_idx": int(best),
            "lat": float(lat[best]),
            "lon": float(lon[best]),
            "eta": float(eta),
        })
        heapq.heappush(heap, (eta, ci))
        if remaining % max(1, N // 80) == 0:
            timeline.append((eta, remaining))

    # Only crews that actually did work define "restoration complete" (see
    # scheduler_numba.py's plan_restoration_numba for the fuller explanation
    # of why an idle crew's raw arrival time isn't real work finishing).
    busy_times = [c["time"] for c in crews if c["jobs"]]
    total = max(busy_times) if busy_times else 0.0
    return crews, total, sorted(timeline)
