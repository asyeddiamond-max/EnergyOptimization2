"""
scheduler_numba.py — Numba-JIT'd scheduler.

The whole dispatch loop is compiled to native code. No scipy KD-tree (Numba
doesn't support it), but the masked-argmin inner scan and the heap ops are
all in C-speed code, so even though it's algorithmically the same O(N^2) as
the NumPy version, the constant factor drops by ~10x on hot scenarios.

Compiled lazily on first call; warm-up is ~2s. Subsequent calls are fast.

We keep the same RNG semantics (Mulberry32 with per-seed streams for repair
durations and discovery times) so results match the NumPy reference for the
same seed.
"""
from __future__ import annotations

import math
import numpy as np
from numba import njit


@njit(cache=True)
def _mulberry32_step(state):
    state = (state + 0x6D2B79F5) & 0xFFFFFFFF
    t = state
    t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
    t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    u = ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return state, u


@njit(cache=True, fastmath=True)
def _run_scheduler(lat, lon, m_crews, realistic, seed, customers, customer_weight):
    """Dense-scan scheduler. When customer_weight > 0, dispatch picks the
    outage maximizing (customers - customer_weight * d²) rather than the
    nearest one. Default 0 preserves pure-nearest behavior."""
    N = lat.shape[0]
    use_weighted = customer_weight > 0.0
    TRAVEL_MPH = 25.0 if realistic else 30.0
    ASSESSMENT_DELAY = 12.0 if realistic else 0.0
    WORKDAY_HOURS = 14.0 if realistic else 24.0
    ROAD_MULTIPLIER = 1.5 if realistic else 1.0
    INF = 1e18

    # Per-seed RNG streams.
    rep_state = (seed * 1117 + 23) & 0xFFFFFFFF
    disc_state = (seed * 991 + 7) & 0xFFFFFFFF

    # Discovery times.
    disc = np.zeros(N, dtype=np.float64)
    if realistic:
        for i in range(N):
            disc_state, u = _mulberry32_step(disc_state)
            if u < 0.30:
                disc[i] = ASSESSMENT_DELAY + u * (1.0 / 0.30)
            else:
                v = (u - 0.30) / 0.70
                t_after = -math.log(max(1e-9, 1.0 - 0.99 * v)) / 0.1
                disc[i] = ASSESSMENT_DELAY + 1.0 + min(36.0, t_after)
    disc_sorted = np.sort(disc) if realistic else disc

    # Mutual-aid waves: arrival times for each crew.
    arrivals = np.empty(m_crews, dtype=np.float64)
    if realistic and m_crews >= 6:
        n_init = int(math.ceil(m_crews * 0.5))
        n_w1 = int(math.ceil(m_crews * 0.3))
        for c in range(m_crews):
            if c < n_init:
                arrivals[c] = ASSESSMENT_DELAY
            elif c < n_init + n_w1:
                arrivals[c] = ASSESSMENT_DELAY + 24.0
            else:
                arrivals[c] = ASSESSMENT_DELAY + 48.0
    else:
        for c in range(m_crews):
            arrivals[c] = ASSESSMENT_DELAY

    # Crew state: current position and current time.
    crew_lat = np.empty(m_crews, dtype=np.float64)
    crew_lon = np.empty(m_crews, dtype=np.float64)
    crew_time = np.empty(m_crews, dtype=np.float64)
    crew_jobs = np.zeros(m_crews, dtype=np.int32)
    for c in range(m_crews):
        crew_lat[c] = lat[c % N]
        crew_lon[c] = lon[c % N]
        crew_time[c] = arrivals[c]

    # Min-heap as parallel arrays (key=time, value=crew_idx). Standard
    # binary-heap operations, inlined since heapq isn't usable in nopython.
    heap_k = np.empty(m_crews, dtype=np.float64)
    heap_v = np.empty(m_crews, dtype=np.int32)
    for c in range(m_crews):
        heap_k[c] = arrivals[c]
        heap_v[c] = c
    # heapify
    n_heap = m_crews
    for start in range(n_heap // 2 - 1, -1, -1):
        # sift down
        i = start
        while True:
            l = 2 * i + 1
            r = 2 * i + 2
            smallest = i
            if l < n_heap and heap_k[l] < heap_k[smallest]:
                smallest = l
            if r < n_heap and heap_k[r] < heap_k[smallest]:
                smallest = r
            if smallest == i:
                break
            heap_k[i], heap_k[smallest] = heap_k[smallest], heap_k[i]
            heap_v[i], heap_v[smallest] = heap_v[smallest], heap_v[i]
            i = smallest

    done = np.zeros(N, dtype=np.bool_)
    remaining = N

    # Flat dispatch log so the wrapper can rebuild per-crew job lists for
    # the browser visualization. Each successful dispatch appends one entry.
    log_crew = np.empty(N, dtype=np.int32)
    log_outage = np.empty(N, dtype=np.int32)
    log_eta = np.empty(N, dtype=np.float64)
    n_log = 0

    while remaining > 0:
        # heap-pop
        t_now = heap_k[0]
        ci = heap_v[0]
        n_heap -= 1
        if n_heap > 0:
            heap_k[0] = heap_k[n_heap]
            heap_v[0] = heap_v[n_heap]
            # sift down
            i = 0
            while True:
                l = 2 * i + 1
                r = 2 * i + 2
                smallest = i
                if l < n_heap and heap_k[l] < heap_k[smallest]:
                    smallest = l
                if r < n_heap and heap_k[r] < heap_k[smallest]:
                    smallest = r
                if smallest == i:
                    break
                heap_k[i], heap_k[smallest] = heap_k[smallest], heap_k[i]
                heap_v[i], heap_v[smallest] = heap_v[smallest], heap_v[i]
                i = smallest

        cx = crew_lat[ci]
        cy = crew_lon[ci]

        # Find best undone visible outage. With customer_weight == 0 this is
        # pure-nearest (pick min d²). With customer_weight > 0 it's the
        # outage that maximises customers - customer_weight*d² — a real-world
        # utility heuristic where dispatchers detour to high-customer
        # restorations rather than blindly taking the nearest job.
        best = -1
        best_d2 = INF
        best_score = -INF
        for i in range(N):
            if done[i]:
                continue
            if realistic and disc[i] > t_now:
                continue
            dx = lat[i] - cx
            dy = lon[i] - cy
            d2 = dx * dx + dy * dy
            if use_weighted:
                score = customers[i] - customer_weight * d2
                if score > best_score:
                    best_score = score
                    best = i
            else:
                if d2 < best_d2:
                    best_d2 = d2
                    best = i

        if best == -1:
            # Idle — fast-forward to next discovery via binary search on the
            # sorted discovery list.
            if realistic:
                lo = 0
                hi = N
                while lo < hi:
                    mid = (lo + hi) // 2
                    if disc_sorted[mid] <= t_now:
                        lo = mid + 1
                    else:
                        hi = mid
                if lo >= N:
                    # No more discoveries possible; this crew is done.
                    continue
                nxt = disc_sorted[lo]
                crew_time[ci] = nxt
                # heap-push
                heap_k[n_heap] = nxt
                heap_v[n_heap] = ci
                n_heap += 1
                i = n_heap - 1
                while i > 0:
                    parent = (i - 1) // 2
                    if heap_k[parent] > heap_k[i]:
                        heap_k[parent], heap_k[i] = heap_k[i], heap_k[parent]
                        heap_v[parent], heap_v[i] = heap_v[i], heap_v[parent]
                        i = parent
                    else:
                        break
                continue
            continue

        # Repair sample (log-normal, capped).
        if realistic:
            rep_state, u1 = _mulberry32_step(rep_state)
            rep_state, u2 = _mulberry32_step(rep_state)
            if u1 < 1e-10:
                u1 = 1e-10
            z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
            repair_h = math.exp(math.log(2.0) + 0.857 * z)
            if repair_h < 0.25:
                repair_h = 0.25
            elif repair_h > 12.0:
                repair_h = 12.0
        else:
            repair_h = 1.5

        # Haversine miles.
        R = 3958.7613
        p1 = cx * math.pi / 180.0
        p2 = lat[best] * math.pi / 180.0
        dphi = p2 - p1
        dlam = (lon[best] - cy) * math.pi / 180.0
        a = math.sin(dphi * 0.5) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam * 0.5) ** 2
        miles = 2.0 * R * math.asin(math.sqrt(a)) * ROAD_MULTIPLIER

        eta = crew_time[ci] + miles / TRAVEL_MPH + repair_h
        # Workday clamp.
        if realistic:
            dn = int(eta // 24.0)
            ind = eta - dn * 24.0
            if ind > WORKDAY_HOURS:
                eta = (dn + 1) * 24.0

        done[best] = True
        remaining -= 1
        crew_time[ci] = eta
        crew_lat[ci] = lat[best]
        crew_lon[ci] = lon[best]
        crew_jobs[ci] += 1
        log_crew[n_log] = ci
        log_outage[n_log] = best
        log_eta[n_log] = eta
        n_log += 1

        # heap-push
        heap_k[n_heap] = eta
        heap_v[n_heap] = ci
        n_heap += 1
        i = n_heap - 1
        while i > 0:
            parent = (i - 1) // 2
            if heap_k[parent] > heap_k[i]:
                heap_k[parent], heap_k[i] = heap_k[i], heap_k[parent]
                heap_v[parent], heap_v[i] = heap_v[i], heap_v[parent]
                i = parent
            else:
                break

    total = 0.0
    for c in range(m_crews):
        if crew_time[c] > total:
            total = crew_time[c]
    return total, crew_time, crew_jobs, log_crew[:n_log], log_outage[:n_log], log_eta[:n_log]


@njit(cache=True, fastmath=True)
def _run_scheduler_grid(lat, lon, m_crews, realistic, seed, G, customers, customer_weight):
    # NOTE: customer_weight is accepted for signature parity but ignored —
    # ring-expansion termination assumes the score is a monotonic function
    # of distance, which weighted scoring breaks. When the caller wants
    # weighted scoring at scale, the wrapper routes through _run_scheduler
    # (dense flat scan) instead.
    """Spatial-grid-hash variant. Same algorithm as _run_scheduler but the
    nearest-outage search uses a GxG bucket grid: look up the crew's cell,
    walk concentric rings of cells until a valid outage is found, then
    pick the nearest within those rings. O(K) per dispatch where K is
    local bucket density, not O(N)."""
    N = lat.shape[0]
    TRAVEL_MPH = 25.0 if realistic else 30.0
    ASSESSMENT_DELAY = 12.0 if realistic else 0.0
    WORKDAY_HOURS = 14.0 if realistic else 24.0
    ROAD_MULTIPLIER = 1.5 if realistic else 1.0
    INF = 1e18

    # Bounding box + cell mapping.
    lat_min = lat[0]; lat_max = lat[0]
    lon_min = lon[0]; lon_max = lon[0]
    for i in range(1, N):
        if lat[i] < lat_min: lat_min = lat[i]
        if lat[i] > lat_max: lat_max = lat[i]
        if lon[i] < lon_min: lon_min = lon[i]
        if lon[i] > lon_max: lon_max = lon[i]
    # Tiny inflation so all points are strictly inside.
    eps = 1e-9
    lat_span = lat_max - lat_min + eps
    lon_span = lon_max - lon_min + eps
    inv_lat = G / lat_span
    inv_lon = G / lon_span

    # Bucket build: counting sort into a flat array.
    cell_of = np.empty(N, dtype=np.int64)
    bucket_count = np.zeros(G * G, dtype=np.int64)
    for i in range(N):
        cy_ = int((lat[i] - lat_min) * inv_lat)
        cx_ = int((lon[i] - lon_min) * inv_lon)
        if cy_ >= G: cy_ = G - 1
        if cx_ >= G: cx_ = G - 1
        c = cy_ * G + cx_
        cell_of[i] = c
        bucket_count[c] += 1
    bucket_start = np.empty(G * G + 1, dtype=np.int64)
    bucket_start[0] = 0
    for c in range(G * G):
        bucket_start[c + 1] = bucket_start[c] + bucket_count[c]
    cursor = np.zeros(G * G, dtype=np.int64)
    bucket_idx = np.empty(N, dtype=np.int64)
    for i in range(N):
        c = cell_of[i]
        bucket_idx[bucket_start[c] + cursor[c]] = i
        cursor[c] += 1

    # Discovery times.
    rep_state = (seed * 1117 + 23) & 0xFFFFFFFF
    disc_state = (seed * 991 + 7) & 0xFFFFFFFF
    disc = np.zeros(N, dtype=np.float64)
    if realistic:
        for i in range(N):
            disc_state, u = _mulberry32_step(disc_state)
            if u < 0.30:
                disc[i] = ASSESSMENT_DELAY + u * (1.0 / 0.30)
            else:
                v = (u - 0.30) / 0.70
                t_after = -math.log(max(1e-9, 1.0 - 0.99 * v)) / 0.1
                disc[i] = ASSESSMENT_DELAY + 1.0 + min(36.0, t_after)
    disc_sorted = np.sort(disc) if realistic else disc

    # Mutual-aid arrivals.
    arrivals = np.empty(m_crews, dtype=np.float64)
    if realistic and m_crews >= 6:
        n_init = int(math.ceil(m_crews * 0.5))
        n_w1 = int(math.ceil(m_crews * 0.3))
        for c in range(m_crews):
            if c < n_init:
                arrivals[c] = ASSESSMENT_DELAY
            elif c < n_init + n_w1:
                arrivals[c] = ASSESSMENT_DELAY + 24.0
            else:
                arrivals[c] = ASSESSMENT_DELAY + 48.0
    else:
        for c in range(m_crews):
            arrivals[c] = ASSESSMENT_DELAY

    crew_lat = np.empty(m_crews, dtype=np.float64)
    crew_lon = np.empty(m_crews, dtype=np.float64)
    crew_time = np.empty(m_crews, dtype=np.float64)
    crew_jobs = np.zeros(m_crews, dtype=np.int32)
    for c in range(m_crews):
        crew_lat[c] = lat[c % N]
        crew_lon[c] = lon[c % N]
        crew_time[c] = arrivals[c]

    # Min-heap (parallel arrays).
    heap_k = np.empty(m_crews, dtype=np.float64)
    heap_v = np.empty(m_crews, dtype=np.int32)
    for c in range(m_crews):
        heap_k[c] = arrivals[c]
        heap_v[c] = c
    n_heap = m_crews
    for start in range(n_heap // 2 - 1, -1, -1):
        i = start
        while True:
            l = 2 * i + 1; r = 2 * i + 2; smallest = i
            if l < n_heap and heap_k[l] < heap_k[smallest]: smallest = l
            if r < n_heap and heap_k[r] < heap_k[smallest]: smallest = r
            if smallest == i: break
            heap_k[i], heap_k[smallest] = heap_k[smallest], heap_k[i]
            heap_v[i], heap_v[smallest] = heap_v[smallest], heap_v[i]
            i = smallest

    done = np.zeros(N, dtype=np.bool_)
    remaining = N

    # Track how many outages are currently discovered-and-undone. Avoids
    # the catastrophic ring expansion when crew_count >> available_work
    # (typical in early hours of realistic mode with many crews). When
    # n_available is 0, we fast-forward this crew immediately instead of
    # scanning the whole grid for nothing.
    next_disc_idx = 0  # pointer into disc_sorted of next not-yet-available
    n_available = 0

    # Flat dispatch log for visualization (see _run_scheduler).
    log_crew = np.empty(N, dtype=np.int32)
    log_outage = np.empty(N, dtype=np.int32)
    log_eta = np.empty(N, dtype=np.float64)
    n_log = 0

    while remaining > 0:
        # heap-pop
        t_now = heap_k[0]; ci = heap_v[0]; n_heap -= 1
        if n_heap > 0:
            heap_k[0] = heap_k[n_heap]; heap_v[0] = heap_v[n_heap]
            i = 0
            while True:
                l = 2 * i + 1; r = 2 * i + 2; smallest = i
                if l < n_heap and heap_k[l] < heap_k[smallest]: smallest = l
                if r < n_heap and heap_k[r] < heap_k[smallest]: smallest = r
                if smallest == i: break
                heap_k[i], heap_k[smallest] = heap_k[smallest], heap_k[i]
                heap_v[i], heap_v[smallest] = heap_v[smallest], heap_v[i]
                i = smallest

        # Advance the discovery pointer to reflect new outages now available.
        if realistic:
            while next_disc_idx < N and disc_sorted[next_disc_idx] <= t_now:
                next_disc_idx += 1
                n_available += 1
        else:
            n_available = remaining

        # No work available right now — fast-forward without ring expansion.
        if n_available == 0:
            if realistic and next_disc_idx < N:
                nxt = disc_sorted[next_disc_idx]
                crew_time[ci] = nxt
                heap_k[n_heap] = nxt; heap_v[n_heap] = ci; n_heap += 1
                i = n_heap - 1
                while i > 0:
                    parent = (i - 1) // 2
                    if heap_k[parent] > heap_k[i]:
                        heap_k[parent], heap_k[i] = heap_k[i], heap_k[parent]
                        heap_v[parent], heap_v[i] = heap_v[i], heap_v[parent]
                        i = parent
                    else:
                        break
                continue
            continue

        cx = crew_lat[ci]; cy_pos = crew_lon[ci]
        # Crew's home cell.
        cy_ = int((cx - lat_min) * inv_lat)
        cx_ = int((cy_pos - lon_min) * inv_lon)
        if cy_ < 0: cy_ = 0
        if cy_ >= G: cy_ = G - 1
        if cx_ < 0: cx_ = 0
        if cx_ >= G: cx_ = G - 1

        best = -1
        best_d2 = INF
        ring = 0
        # Expand outward in concentric rings until we either find a valid
        # candidate and a full ring with no closer one possible, or exhaust.
        max_ring = G  # at most full grid
        while ring <= max_ring:
            # Enumerate Chebyshev-distance == ring cells without duplicates.
            # Ring 0 = single center cell. Ring>=1 = 4 strips (top, bottom,
            # left, right) clamped at use site.
            if ring == 0:
                gy_list_lo = cy_; gy_list_hi = cy_
                gx_list_lo = cx_; gx_list_hi = cx_
                # Single cell.
                if 0 <= cy_ < G and 0 <= cx_ < G:
                    c = cy_ * G + cx_
                    s = bucket_start[c]; e = bucket_start[c + 1]
                    for k in range(s, e):
                        i = bucket_idx[k]
                        if done[i]: continue
                        if realistic and disc[i] > t_now: continue
                        dx = lat[i] - cx; dy = lon[i] - cy_pos
                        d2 = dx * dx + dy * dy
                        if d2 < best_d2:
                            best_d2 = d2; best = i
            else:
                # Top and bottom rows: gy in {cy_-ring, cy_+ring}, gx full
                # range [cx_-ring, cx_+ring].
                for side in range(2):
                    gy = cy_ - ring if side == 0 else cy_ + ring
                    if gy < 0 or gy >= G:
                        continue
                    gx_lo = cx_ - ring
                    gx_hi = cx_ + ring
                    if gx_lo < 0: gx_lo = 0
                    if gx_hi >= G: gx_hi = G - 1
                    for gx in range(gx_lo, gx_hi + 1):
                        c = gy * G + gx
                        s = bucket_start[c]; e = bucket_start[c + 1]
                        for k in range(s, e):
                            i = bucket_idx[k]
                            if done[i]: continue
                            if realistic and disc[i] > t_now: continue
                            dx = lat[i] - cx; dy = lon[i] - cy_pos
                            d2 = dx * dx + dy * dy
                            if d2 < best_d2:
                                best_d2 = d2; best = i
                # Left and right columns: gx in {cx_-ring, cx_+ring}, gy
                # in (cy_-ring, cy_+ring) exclusive (corners already done).
                for side in range(2):
                    gx = cx_ - ring if side == 0 else cx_ + ring
                    if gx < 0 or gx >= G:
                        continue
                    gy_lo = cy_ - ring + 1
                    gy_hi = cy_ + ring - 1
                    if gy_lo < 0: gy_lo = 0
                    if gy_hi >= G: gy_hi = G - 1
                    for gy in range(gy_lo, gy_hi + 1):
                        c = gy * G + gx
                        s = bucket_start[c]; e = bucket_start[c + 1]
                        for k in range(s, e):
                            i = bucket_idx[k]
                            if done[i]: continue
                            if realistic and disc[i] > t_now: continue
                            dx = lat[i] - cx; dy = lon[i] - cy_pos
                            d2 = dx * dx + dy * dy
                            if d2 < best_d2:
                                best_d2 = d2; best = i

            if best >= 0:
                # Stop expanding when no cell at distance > ring can hold
                # an outage closer than our current best.
                cell_h = lat_span / G
                cell_w = lon_span / G
                cell_min = cell_h if cell_h < cell_w else cell_w
                ring_min = ring * cell_min
                if ring >= 1 and ring_min * ring_min >= best_d2:
                    break
            # Check if we've covered the whole grid.
            if (cy_ - ring <= 0) and (cy_ + ring >= G - 1) \
               and (cx_ - ring <= 0) and (cx_ + ring >= G - 1):
                break
            ring += 1

        if best == -1:
            # No visible work; fast-forward to next discovery.
            if realistic:
                lo = 0; hi = N
                while lo < hi:
                    mid = (lo + hi) // 2
                    if disc_sorted[mid] <= t_now:
                        lo = mid + 1
                    else:
                        hi = mid
                if lo >= N:
                    continue
                nxt = disc_sorted[lo]
                crew_time[ci] = nxt
                heap_k[n_heap] = nxt; heap_v[n_heap] = ci; n_heap += 1
                i = n_heap - 1
                while i > 0:
                    parent = (i - 1) // 2
                    if heap_k[parent] > heap_k[i]:
                        heap_k[parent], heap_k[i] = heap_k[i], heap_k[parent]
                        heap_v[parent], heap_v[i] = heap_v[i], heap_v[parent]
                        i = parent
                    else:
                        break
                continue
            continue

        # Repair sample.
        if realistic:
            rep_state, u1 = _mulberry32_step(rep_state)
            rep_state, u2 = _mulberry32_step(rep_state)
            if u1 < 1e-10: u1 = 1e-10
            z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
            repair_h = math.exp(math.log(2.0) + 0.857 * z)
            if repair_h < 0.25: repair_h = 0.25
            elif repair_h > 12.0: repair_h = 12.0
        else:
            repair_h = 1.5

        R = 3958.7613
        p1 = cx * math.pi / 180.0
        p2 = lat[best] * math.pi / 180.0
        dphi = p2 - p1
        dlam = (lon[best] - cy_pos) * math.pi / 180.0
        a = math.sin(dphi * 0.5) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam * 0.5) ** 2
        miles = 2.0 * R * math.asin(math.sqrt(a)) * ROAD_MULTIPLIER

        eta = crew_time[ci] + miles / TRAVEL_MPH + repair_h
        if realistic:
            dn = int(eta // 24.0); ind = eta - dn * 24.0
            if ind > WORKDAY_HOURS:
                eta = (dn + 1) * 24.0

        done[best] = True
        remaining -= 1
        n_available -= 1
        crew_time[ci] = eta
        crew_lat[ci] = lat[best]
        crew_lon[ci] = lon[best]
        crew_jobs[ci] += 1
        log_crew[n_log] = ci
        log_outage[n_log] = best
        log_eta[n_log] = eta
        n_log += 1

        heap_k[n_heap] = eta; heap_v[n_heap] = ci; n_heap += 1
        i = n_heap - 1
        while i > 0:
            parent = (i - 1) // 2
            if heap_k[parent] > heap_k[i]:
                heap_k[parent], heap_k[i] = heap_k[i], heap_k[parent]
                heap_v[parent], heap_v[i] = heap_v[i], heap_v[parent]
                i = parent
            else:
                break

    total = 0.0
    for c in range(m_crews):
        if crew_time[c] > total:
            total = crew_time[c]
    return total, crew_time, crew_jobs, log_crew[:n_log], log_outage[:n_log], log_eta[:n_log]


def plan_restoration_numba(outages, m_crews, realistic=True, seed=42,
                           customers=None, customer_weight=0.0):
    """Public wrapper that returns the same shape as plan_restoration_fast.

    customers: optional list of per-outage customer counts. If None, treated
        as zeros and customer-weighted scoring becomes pure-nearest anyway.
    customer_weight: float >= 0. When > 0, dispatch maximises
        (customers - customer_weight * d²) instead of minimising d². Routes
        through the dense scheduler regardless of N because the grid hash's
        ring-expansion termination doesn't generalise to weighted scoring.
    """
    N = len(outages)
    if N == 0 or m_crews == 0:
        return [], 0.0, []
    lat = np.array([o[0] for o in outages], dtype=np.float64)
    lon = np.array([o[1] for o in outages], dtype=np.float64)
    if customers is not None and len(customers) == N:
        cust_arr = np.array(customers, dtype=np.float64)
    else:
        cust_arr = np.zeros(N, dtype=np.float64)

    use_weighted = customer_weight > 0.0
    # Grid hash + ring expansion assumes nearest-distance termination, which
    # breaks under customer-weighted scoring. Use dense flat scan for the
    # weighted path even at large N.
    if N >= 1000 and not use_weighted:
        G = max(8, int(math.sqrt(N / 5.0)))
        total, crew_time, crew_jobs, log_crew, log_outage, log_eta = \
            _run_scheduler_grid(lat, lon, m_crews, realistic, seed, G,
                                cust_arr, 0.0)
    else:
        total, crew_time, crew_jobs, log_crew, log_outage, log_eta = \
            _run_scheduler(lat, lon, m_crews, realistic, seed,
                           cust_arr, float(customer_weight))

    # Rebuild per-crew job sequences from the flat dispatch log. The log is
    # already in dispatch order, so iterating it preserves repair sequence
    # within each crew. Each job carries the outage's lat/lon and finish eta
    # so the browser can draw the numbered markers without a second round.
    crews = [
        {"depot": outages[c % N], "time": float(crew_time[c]),
         "lat": float(outages[c % N][0]), "lon": float(outages[c % N][1]),
         "jobs": []}
        for c in range(m_crews)
    ]
    for k in range(log_crew.shape[0]):
        ci = int(log_crew[k])
        oi = int(log_outage[k])
        crews[ci]["jobs"].append({
            "outage_idx": oi,
            "lat": float(lat[oi]),
            "lon": float(lon[oi]),
            "eta": float(log_eta[k]),
        })
    return crews, float(total), [(0.0, N), (float(total), 0)]
