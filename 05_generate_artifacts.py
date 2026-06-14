"""
05_generate_artifacts.py - Generate matplotlib PNG artifacts for output/.

Reproduces the simulation pipeline (k-means substation placement, feeder/
lateral generation, storm simulation, restoration scheduling) in Python so
the output/ folder can be regenerated with proper PNG visualizations
matching the research-project pattern.

Outputs (in output/):
    03a_county_topology.png  - county outline + 29 town outlines + centroids
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

TOWNS = [
    {"n":"Hartford","lat":41.7637,"lon":-72.6851,"pop":121054},
    {"n":"New Britain","lat":41.6612,"lon":-72.7795,"pop":74992},
    {"n":"West Hartford","lat":41.7620,"lon":-72.7420,"pop":64083},
    {"n":"Bristol","lat":41.6718,"lon":-72.9493,"pop":60833},
    {"n":"Manchester","lat":41.7759,"lon":-72.5215,"pop":59713},
    {"n":"East Hartford","lat":41.7823,"lon":-72.6120,"pop":51045},
    {"n":"Southington","lat":41.6001,"lon":-72.8781,"pop":43501},
    {"n":"Enfield","lat":41.9762,"lon":-72.5917,"pop":42141},
    {"n":"Glastonbury","lat":41.7126,"lon":-72.6081,"pop":35159},
    {"n":"Newington","lat":41.6981,"lon":-72.7237,"pop":30152},
    {"n":"Windsor","lat":41.8525,"lon":-72.6437,"pop":29492},
    {"n":"South Windsor","lat":41.8237,"lon":-72.6223,"pop":26918},
    {"n":"Farmington","lat":41.7201,"lon":-72.8320,"pop":26712},
    {"n":"Wethersfield","lat":41.7142,"lon":-72.6526,"pop":26492},
    {"n":"Simsbury","lat":41.8762,"lon":-72.8009,"pop":24517},
    {"n":"Bloomfield","lat":41.8281,"lon":-72.7295,"pop":21535},
    {"n":"Rocky Hill","lat":41.6648,"lon":-72.6648,"pop":20845},
    {"n":"Berlin","lat":41.6212,"lon":-72.7456,"pop":20175},
    {"n":"Avon","lat":41.8098,"lon":-72.8303,"pop":18871},
    {"n":"Plainville","lat":41.6745,"lon":-72.8589,"pop":17716},
    {"n":"Suffield","lat":41.9837,"lon":-72.6520,"pop":15735},
    {"n":"Windsor Locks","lat":41.9292,"lon":-72.6234,"pop":12613},
    {"n":"Granby","lat":41.9526,"lon":-72.7898,"pop":11282},
    {"n":"East Windsor","lat":41.9123,"lon":-72.5453,"pop":11190},
    {"n":"Canton","lat":41.8348,"lon":-72.8945,"pop":10124},
    {"n":"Burlington","lat":41.7720,"lon":-72.9590,"pop":9701},
    {"n":"Marlborough","lat":41.6320,"lon":-72.4598,"pop":6307},
    {"n":"East Granby","lat":41.9434,"lon":-72.7320,"pop":5184},
    {"n":"Hartland","lat":41.9856,"lon":-72.9534,"pop":1885},
]
TOTAL_POP = sum(t["pop"] for t in TOWNS)
PALETTE = ["#ff7f0e","#1f77b4","#2ca02c","#d62728","#9467bd","#8c564b","#e377c2","#7f7f7f","#bcbd22","#17becf","#1fb8d1","#c266a7","#7e5fc4","#f4c842","#a68272"]

# --- Load polygons ---
boundary = json.loads((DATA / "hartford_boundary.json").read_text())
county_coords = boundary[0]["geojson"]["coordinates"][0]
towns_geo = json.loads((DATA / "hartford_towns.geojson").read_text())

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


def plan_restoration(outages, m_crews, rnd, realistic=True):
    if not outages or m_crews == 0:
        return [], 0.0, []
    REPAIR_HRS = 3.0 if realistic else 1.5
    TRAVEL_MPH = 25 if realistic else 30
    ASSESSMENT_DELAY = 12 if realistic else 0
    WORKDAY_HOURS = 14 if realistic else 24
    N = len(outages)
    # Depots: cycle outage points (simplified; full version k-means for small M).
    depots = [outages[i % N] for i in range(m_crews)]
    crews = [{"depot": d, "time": ASSESSMENT_DELAY, "lat": d[0], "lon": d[1], "jobs": []} for d in depots]
    done = [False] * N
    remaining = N
    # Min-heap by (time, crew_idx)
    import heapq
    heap = [(ASSESSMENT_DELAY, c) for c in range(m_crews)]
    heapq.heapify(heap)
    # Customer-out timeline samples (step decay).
    timeline = [(0.0, N)]
    while remaining > 0:
        t_now, ci = heapq.heappop(heap)
        crew = crews[ci]
        best, bd = -1, float("inf")
        for i in range(N):
            if done[i]:
                continue
            d = (outages[i][0] - crew["lat"]) ** 2 + (outages[i][1] - crew["lon"]) ** 2
            if d < bd:
                bd, best = d, i
        if best == -1:
            break
        done[best] = True
        remaining -= 1
        miles = haversine_miles(crew["lat"], crew["lon"], outages[best][0], outages[best][1])
        eta = crew["time"] + miles / TRAVEL_MPH + REPAIR_HRS
        # Workday clamp
        day_n = int(eta // 24)
        in_day = eta - day_n * 24
        if in_day > WORKDAY_HOURS:
            eta = (day_n + 1) * 24
        crew["time"] = eta
        crew["lat"], crew["lon"] = outages[best]
        crew["jobs"].append((outages[best], eta))
        heapq.heappush(heap, (eta, ci))
        # Record outage curve every ~50 repairs
        if remaining % max(1, N // 80) == 0:
            timeline.append((eta, remaining))
    total = max(c["time"] for c in crews)
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
    fig, ax = new_axes("Hartford County: boundary, 29 towns, centroids sized by population")
    draw_geography(ax)
    fig.savefig(OUT / "03a_county_topology.png", dpi=110, bbox_inches="tight", facecolor="#f8fafc")
    plt.close(fig)
    print("Wrote output/03a_county_topology.png")

    # 03b — synthetic grid
    rnd_grid = mulberry32(42)
    demand = build_demand_points(rnd_grid)
    substations = kmeans_simple(demand, 100, rnd_grid)

    # 03f — substations on the actual county outline (clean reference view)
    fig, ax = new_axes(f"100 synthetic substations inside Hartford County (seed 42, no feeders shown)")
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

    # Copy the live interactive into output/ for discoverability.
    import shutil
    shutil.copy(ROOT / "03_grid_simulation.html", OUT / "03_grid_simulation.html")
    print("Copied 03_grid_simulation.html into output/")

    print("\nDone.")


if __name__ == "__main__":
    main()
