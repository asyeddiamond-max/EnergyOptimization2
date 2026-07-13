"""
05_generate_artifacts.py - Generate matplotlib PNG artifacts for output/.

Reproduces the simulation pipeline (k-means substation placement, feeder/
lateral generation, storm simulation, restoration scheduling) in Python so
the output/ folder can be regenerated with proper PNG visualizations
matching the research-project pattern.

Outputs (in output/):
    03a_county_topology.png  - state outline + 169 town outlines + centroids
    03b_synthetic_grid.png   - adds 100 substations + feeders + laterals
    03c_grid_outages.png     - adds a 500-outage storm
    03d_restoration_plan.png - adds 10 crews + repair-job assignments
    03e_outage_curve.png     - customers without power vs hours

Requirements:
    pip install matplotlib numpy

Run from the project root:
    python 05_generate_artifacts.py

The PowerShell variant (05_generate_artifacts.ps1) is a fallback that
produces SVG snapshots instead, suitable for environments without Python.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import List, Dict, Any

try:
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon
    from matplotlib.collections import LineCollection, PatchCollection
except ImportError:
    raise SystemExit("matplotlib + numpy required. Install with: pip install matplotlib numpy")


ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT  = ROOT / "output"
OUT.mkdir(exist_ok=True)

TOWNS = json.loads((DATA / "connecticut_towns_population.json").read_text())
# Population != customer accounts -- see the matching comment in
# 03_grid_simulation.html. CT population 3,605,944 vs ~1,633,000 real
# Eversource + United Illuminating customer accounts statewide.
POP_TO_CUSTOMER_RATIO = 1633000 / 3605944  # ~0.4529
TOTAL_POP = sum(t["pop"] for t in TOWNS) * POP_TO_CUSTOMER_RATIO
PALETTE = ["#ff7f0e","#1f77b4","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf","#1fb8d1","#c266a7","#7e5fc4","#f4c842","#a68272"]

# --- Load polygons ---
boundary = json.loads((DATA / "connecticut_boundary.json").read_text())
county_coords = boundary[0]["geojson"]["coordinates"][0]
towns_geo = json.loads((DATA / "connecticut_towns.geojson").read_text())

LON = [c[0] for c in county_coords]
LAT = [c[1] for c in county_coords]
LON_MIN, LON_MAX = min(LON)-0.01, max(LON)+0.01
LAT_MIN, LAT_MAX = min(LAT)-0.01, max(LAT)+0.01


def new_axes(title: str, figsize=(11, 10)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(LON_MIN, LON_MAX)
    ax.set_ylim(LAT_MIN, LAT_MAX)
    ax.set_aspect("equal")
    ax.set_facecolor("#f8fafc")
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.set_title(title, fontsize=13, weight="600", color="#1e293b", pad=14)
    return fig, ax


def draw_geography(ax):
    ax.add_patch(MplPolygon(county_coords, closed=True, fill=True, fc="#fef3c7", ec="#dc2626", lw=2.5, alpha=0.25))
    ax.add_patch(MplPolygon(county_coords, closed=True, fill=False, ec="#dc2626", lw=2.5))
    for feat in towns_geo["features"]:
        for line in feat["geometry"]["coordinates"]:
            xs = [p[0] for p in line]; ys = [p[1] for p in line]
            ax.plot(xs, ys, color="#16a34a", lw=1.1, alpha=0.85)
    for t in TOWNS:
        r = (2 + math.sqrt(t["pop"]) / 40) * 0.0008
        ax.scatter([t["lon"]], [t["lat"]], s=(2 + math.sqrt(t["pop"]) / 10), c="#16a34a", alpha=0.35, edgecolors="#15803d", lw=0.6, zorder=3)


# --- Algorithm port: substation placement, feeders, laterals, storm, scheduler ---

def mulberry32(seed: int):
    state = seed & 0xFFFFFFFF
    def rnd():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = (state ^ (state >> 15)) * (1 | state)
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def build_demand_points(rnd):
    pts = []
    for t in TOWNS:
        n = max(8, round(math.sqrt(t["pop"]) / 2))
        w = t["pop"] / n
        for _ in range(n):
            r = 0.005 + rnd() * 0.015
            a = rnd() * 2 * math.pi
            pts.append((t["lat"] + math.sin(a) * r * 0.85, t["lon"] + math.cos(a) * r, w))
    return pts


def kmeans_simple(pts, k, rnd, iters=12):
    n = len(pts)
    # k-means++ seeding (simplified)
    first = int(rnd() * n)
    centers = [(pts[first][0], pts[first][1])]
    minD = [((pts[i][0] - centers[0][0]) ** 2 + (pts[i][1] - centers[0][1]) ** 2) for i in range(n)]
    while len(centers) < k:
        s = sum(minD[i] * pts[i][2] for i in range(n))
        r = rnd() * s
        idx = n - 1
        for i in range(n):
            r -= minD[i] * pts[i][2]
            if r <= 0:
                idx = i; break
        centers.append((pts[idx][0], pts[idx][1]))
        for i in range(n):
            d = (pts[i][0] - centers[-1][0]) ** 2 + (pts[i][1] - centers[-1][1]) ** 2
            if d < minD[i]:
                minD[i] = d
    # Lloyd iterations
    for _ in range(iters):
        sums = [[0.0, 0.0, 0.0] for _ in range(k)]
        for la, lo, w in pts:
            best, bd = 0, float("inf")
            for c, (cla, clo) in enumerate(centers):
                d = (la - cla) ** 2 + (lo - clo) ** 2
                if d < bd:
                    bd, best = d, c
            sums[best][0] += la * w; sums[best][1] += lo * w; sums[best][2] += w
        for c in range(k):
            if sums[c][2] > 0:
                centers[c] = (sums[c][0] / sums[c][2], sums[c][1] / sums[c][2])
    return centers


def generate_feeders_and_laterals(substations, rnd, feeders_per_sub=5):
    feeders, laterals = [], []
    for si, (sla, slo) in enumerate(substations):
        color = PALETTE[si % len(PALETTE)]
        for f in range(feeders_per_sub):
            la, lo, ang = sla, slo, (f / feeders_per_sub) * 2 * math.pi + rnd() * 0.4
            pts = [(la, lo)]
            for _ in range(8 + int(rnd() * 8)):
                ang += (rnd() - 0.5) * 0.5
                step = 0.004 + rnd() * 0.005
                lo += math.cos(ang) * step
                la += math.sin(ang) * step
                pts.append((la, lo))
            feeders.append({"subIdx": si, "pts": pts, "color": color})
            # Laterals from each midpoint
            for _ in range(4 + int(rnd() * 5)):
                anchor = pts[1 + int(rnd() * (len(pts) - 1))]
                lla, llo, lang = anchor[0], anchor[1], rnd() * 2 * math.pi
                lpts = [(lla, llo)]
                for _ in range(3 + int(rnd() * 5)):
                    lang += (rnd() - 0.5) * 1.0
                    lstep = 0.0015 + rnd() * 0.0025
                    llo += math.cos(lang) * lstep
                    lla += math.sin(lang) * lstep
                    lpts.append((lla, llo))
                if len(lpts) >= 2:
                    laterals.append({"feederIdx": len(feeders) - 1, "pts": lpts})
    return feeders, laterals


def simulate_storm(feeders, laterals, n_outages, rnd):
    all_segs = []
    for fi, f in enumerate(feeders):
        for s in range(len(f["pts"]) - 1):
            all_segs.append(("f", fi, s))
    for li, l in enumerate(laterals):
        for s in range(len(l["pts"]) - 1):
            all_segs.append(("l", li, s))
    outages = []
    for _ in range(n_outages):
        kind, idx, s = all_segs[int(rnd() * len(all_segs))]
        arr = feeders[idx]["pts"] if kind == "f" else laterals[idx]["pts"]
        a, b = arr[s], arr[s + 1]
        t = rnd()
        la = a[0] + (b[0] - a[0]) * t
        lo = a[1] + (b[1] - a[1]) * t
        outages.append((la, lo))
    return outages


def haversine_miles(la1, lo1, la2, lo2):
    R = 3958.8
    toR = math.pi / 180
    dlat = (la2 - la1) * toR
    dlon = (lo2 - lo1) * toR
    s = (math.sin(dlat / 2) ** 2 + math.cos(la1 * toR) * math.cos(la2 * toR) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(s))


def plan_restoration(outages, m_crews, rnd_master, realistic=True, total_customers=None):
    """Rolling-horizon greedy scheduler with all 5 items 1-5 modeled when realistic=True.

    Returns (crews, total_time, timeline) where timeline = list of (hour, remaining).

    total_customers: real total customer count for this storm, driving
    workload_mult (ported from the JS scheduler's workloadSlowdownMult — see
    03_grid_simulation.html:planRestoration()). None -> no slowdown; this
    illustrative/demo script has no per-outage customer data by default.
    """
    if not outages or m_crews == 0:
        return [], 0.0, []
    tc = float(total_customers) if total_customers else 0.0
    workload_mult = max(1.0, 0.00928 * (tc ** 0.473)) if tc > 0 else 1.0
    # Small-storm overnight ops (see scheduler_numba.plan_restoration_numba).
    overnight_ops = 0 < tc <= 70000
    import heapq
    import math as _math
    TRAVEL_MPH = 25 if realistic else 30
    ASSESSMENT_DELAY = 12 if realistic else 0
    WORKDAY_HOURS = 24 if overnight_ops else (14 if realistic else 24)
    ROAD_MULTIPLIER = 1.5 if realistic else 1.0
    N = len(outages)

    def clamp(t):
        if not realistic:
            return t
        dn = int(t // 24); ind = t - dn * 24
        return (dn + 1) * 24 if ind > WORKDAY_HOURS else t

    # Independent RNG streams for repair durations and discovery times,
    # so a binary search over m doesn't shuffle the realized values.
    rnd_repair = mulberry32(1117)
    rnd_disc   = mulberry32(991)

    def sample_repair():
        if not realistic:
            return 1.5
        # Box-Muller normal
        u1 = max(1e-10, rnd_repair())
        u2 = rnd_repair()
        z = _math.sqrt(-2 * _math.log(u1)) * _math.cos(2 * _math.pi * u2)
        return max(0.25, min(12.0, _math.exp(_math.log(2) + 0.857 * z)))

    # Item 3: discovery times
    disc_time = [0.0] * N
    if realistic:
        for i in range(N):
            u = rnd_disc()
            if u < 0.30:
                disc_time[i] = ASSESSMENT_DELAY + u * (1.0 / 0.30)
            else:
                v = (u - 0.30) / 0.70
                t_after = -_math.log(max(1e-9, 1 - 0.99 * v)) / 0.1
                disc_time[i] = ASSESSMENT_DELAY + 1 + min(36.0, t_after)

    # Item 4: mutual-aid waves
    if realistic and m_crews >= 6:
        n_init = _math.ceil(m_crews * 0.5)
        n_w1   = _math.ceil(m_crews * 0.3)
        n_w2   = m_crews - n_init - n_w1
        arrivals = ([ASSESSMENT_DELAY] * n_init +
                    [ASSESSMENT_DELAY + 24] * n_w1 +
                    [ASSESSMENT_DELAY + 48] * n_w2)
    else:
        arrivals = [ASSESSMENT_DELAY] * m_crews

    depots = [outages[i % N] for i in range(m_crews)]
    crews = [{"depot": d, "time": arrivals[i], "lat": d[0], "lon": d[1], "jobs": []}
             for i, d in enumerate(depots)]
    done = [False] * N
    remaining = N
    heap = [(arrivals[c], c) for c in range(m_crews)]
    heapq.heapify(heap)
    timeline = [(0.0, N)]

    def next_discovery_after(t):
        best = float("inf")
        for i in range(N):
            if done[i]:
                continue
            if disc_time[i] > t and disc_time[i] < best:
                best = disc_time[i]
        return best

    while remaining > 0:
        t_now, ci = heapq.heappop(heap)
        crew = crews[ci]
        # Item 1 + 3: rolling-horizon find-nearest-visible
        best, bd = -1, float("inf")
        for i in range(N):
            if done[i]:
                continue
            if realistic and disc_time[i] > t_now:
                continue
            dx = outages[i][0] - crew["lat"]; dy = outages[i][1] - crew["lon"]
            d = dx * dx + dy * dy
            if d < bd:
                bd, best = d, i
        if best == -1:
            # No visible work; fast-forward to next discovery (realistic) or quit (baseline)
            if realistic:
                nxt = next_discovery_after(t_now)
                if not _math.isfinite(nxt):
                    break
                crew["time"] = nxt
                heapq.heappush(heap, (nxt, ci))
                continue
            break
        done[best] = True
        remaining -= 1
        miles = haversine_miles(crew["lat"], crew["lon"], outages[best][0], outages[best][1]) * ROAD_MULTIPLIER
        repair_h = sample_repair()
        eta = clamp(crew["time"] + (miles / TRAVEL_MPH + repair_h) * workload_mult)
        crew["time"] = eta
        crew["lat"], crew["lon"] = outages[best]
        crew["jobs"].append((outages[best], eta))
        heapq.heappush(heap, (eta, ci))
        if remaining % max(1, N // 80) == 0:
            timeline.append((eta, remaining))
    # Only crews that actually did work define "restoration complete" (see
    # scheduler_numba.py's plan_restoration_numba for the fuller rationale).
    busy_times = [c["time"] for c in crews if c["jobs"]]
    total = max(busy_times) if busy_times else 0.0
    return crews, total, sorted(timeline)


# --- Drawing helpers ---

def draw_feeders(ax, feeders, lw=1.2, alpha=0.85):
    for f in feeders:
        xs = [p[1] for p in f["pts"]]; ys = [p[0] for p in f["pts"]]
        ax.plot(xs, ys, color=f["color"], lw=lw, alpha=alpha)


def draw_laterals(ax, laterals, lw=0.5, alpha=0.7):
    for l in laterals:
        xs = [p[1] for p in l["pts"]]; ys = [p[0] for p in l["pts"]]
        ax.plot(xs, ys, color="#bfc4cb", lw=lw, alpha=alpha)


def draw_substations(ax, substations):
    for i, (la, lo) in enumerate(substations):
        ax.scatter([lo], [la], s=110, marker="*", c=PALETTE[i % len(PALETTE)], edgecolors="#111", lw=0.6, zorder=5)


def draw_outages(ax, outages):
    if not outages:
        return
    xs = [o[1] for o in outages]; ys = [o[0] for o in outages]
    ax.scatter(xs, ys, s=4, c="#7f1d1d", alpha=0.85, edgecolors="black", lw=0.2, zorder=6)


# --- Generate the artifacts ---

def main():
    # 03a — geography only
    fig, ax = new_axes(f"Connecticut: boundary, {len(TOWNS)} towns, centroids sized by population")
    draw_geography(ax)
    fig.savefig(OUT / "03a_county_topology.png", dpi=110, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    print("Wrote output/03a_county_topology.png")

    # 03b — synthetic grid
    rnd_grid = mulberry32(42)
    demand = build_demand_points(rnd_grid)
    substations = kmeans_simple(demand, 100, rnd_grid)

    # 03f — substations on the actual county outline (clean reference view)
    fig, ax = new_axes(f"100 synthetic substations inside Connecticut (seed 42, no feeders shown)")
    draw_geography(ax)
    draw_substations(ax, substations)
    fig.savefig(OUT / "03f_substations_on_county.png", dpi=110, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    print("Wrote output/03f_substations_on_county.png")

    feeders, laterals = generate_feeders_and_laterals(substations, rnd_grid, feeders_per_sub=5)

    fig, ax = new_axes(f"Synthetic distribution grid: 100 substations, {len(feeders)} feeders, {len(laterals)} laterals (seed 42)")
    draw_geography(ax)
    draw_laterals(ax, laterals)
    draw_feeders(ax, feeders)
    draw_substations(ax, substations)
    fig.savefig(OUT / "03b_synthetic_grid.png", dpi=110, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    print("Wrote output/03b_synthetic_grid.png")

    # 03c — storm overlay
    rnd_storm = mulberry32(42 * 7919 + 13)
    outages = simulate_storm(feeders, laterals, 500, rnd_storm)

    fig, ax = new_axes(f"Storm scenario: 500 outage locations on a synthetic grid (seed 42)")
    draw_geography(ax)
    draw_laterals(ax, laterals)
    draw_feeders(ax, feeders)
    draw_substations(ax, substations)
    draw_outages(ax, outages)
    fig.savefig(OUT / "03c_grid_outages.png", dpi=110, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    print("Wrote output/03c_grid_outages.png")

    # 03d — restoration plan
    rnd_plan = mulberry32(42 * 31 + 99)
    crews, total_time, timeline = plan_restoration(outages, 10, rnd_plan, realistic=True)

    fig, ax = new_axes(f"Restoration plan: 10 crews, realistic mode, total {total_time:.1f} h")
    draw_geography(ax)
    draw_laterals(ax, laterals)
    draw_feeders(ax, feeders)
    draw_substations(ax, substations)
    for ci, crew in enumerate(crews):
        color = PALETTE[ci % len(PALETTE)]
        # depot square
        ax.scatter([crew["depot"][1]], [crew["depot"][0]], s=80, marker="s", c=color, edgecolors="#111", lw=1.0, zorder=7)
        # numbered repair circles for the first 30
        for order, (o, _) in enumerate(crew["jobs"][:30]):
            ax.scatter([o[1]], [o[0]], s=80, c=color, edgecolors="#111", lw=0.6, zorder=8)
            ax.annotate(str(order + 1), (o[1], o[0]), ha="center", va="center", fontsize=6, color="white", weight="bold", zorder=9)
    fig.savefig(OUT / "03d_restoration_plan.png", dpi=110, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    print("Wrote output/03d_restoration_plan.png")

    # 03e — outage curve
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ts = [t for t, _ in timeline]
    ys = [r for _, r in timeline]
    # Approximate customer count = outages_remaining * avg_pop_per_outage
    avg_cust_per_outage = TOTAL_POP * 0.5 / max(1, len(outages))   # 0.5 for sectionalizer halving
    cust = [r * avg_cust_per_outage for r in ys]
    ax.fill_between(ts, cust, alpha=0.45, color="#fecaca", label="customers without power")
    ax.plot(ts, cust, color="#dc2626", lw=2.2)
    ax.set_xlabel("hours since storm")
    ax.set_ylabel("customers without power")
    ax.set_title(f"Outage curve: {int(cust[0]):,} customers out at t=0, restoration to zero at t={total_time:.1f} h (realistic mode)")
    ax.set_facecolor("#f8fafc")
    ax.grid(alpha=0.25)
    ax.axvline(12, color="#94a3b8", lw=1, ls="--")
    ax.annotate("crews dispatched\nafter 12 h assessment", (12, max(cust) * 0.7), xytext=(14, max(cust) * 0.7), fontsize=10, color="#475569")
    fig.tight_layout()
    fig.savefig(OUT / "03e_outage_curve.png", dpi=110, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    print("Wrote output/03e_outage_curve.png")

    print("\nDone.")


if __name__ == "__main__":
    main()
