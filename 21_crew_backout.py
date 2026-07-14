"""
21_crew_backout.py -- Estimate each storm's crew count by INVERTING the
restoration model, then validate against the utility's disclosed crew numbers.

The idea: the model's restoration time is monotonic in crew count (more crews
-> faster). So for a storm whose REAL restoration time we measured (by tracking
the actual outage decay -- ORNL EAGLE-I 15-min data where it exists, PURA
docket / news where it doesn't), we can binary-search the crew count M at which
the model reproduces that real time. That M is the "model-implied effective
crew count." Comparing it to the crews the utility ACTUALLY disclosed tells us:

  - implied ~ disclosed  -> the model's crew productivity is calibrated right
  - implied systematically off -> quantifies model bias, or reveals real crew
    inefficiency (out-of-town mutual-aid crews work slower, "crews" may bundle
    support staff, etc.)
  - implied-vs-disclosed across storm sizes -> surge/reserve behavior

Uses scheduler_numba (the real statewide model) consistently for every storm,
so any systematic model offset is the same across the comparison. Placement is
uniform over CT land at each storm's calibrated outage count -- for a whole-
state restoration TIME the count + crews dominate; exact spatial pattern is
second-order (and using one placement scheme keeps storms comparable).

Usage:
    python 21_crew_backout.py
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT_DIR = HERE / "output"

# name, calibrated n_out, customer peak, real restoration hours, real-time
# source, disclosed peak crews, disclosed-crew confidence.
#   time_src: "eaglei" (measured 15-min) | "pura" (regulatory) | "documented"
#   crew_conf: "real" (utility/press disclosed) | "interp" (interpolated here)
STORMS = [
    # label,            n_out, cust,   real_h, time_src,     crews, crew_conf
    ("Isaias 2020",     20450, 632632, 199,   "eaglei",     4500,  "real"),
    ("Sandy 2012",      15500, 496769, 264,   "pura",       4000,  "interp"),
    ("Irene 2011",      21350, 671789, 288,   "pura",       3800,  "interp"),
    ("Snowtober 2011",  26050, 807228, 264,   "pura",       4800,  "interp"),
    ("Aug 2020 Tornado", 2050,  63912,  66,   "eaglei",      380,  "real"),
    ("Oct 2020 Derecho",  950,  27943,  28,   "eaglei",      300,  "interp"),
    ("Henri 2021",        830,  23000,  34,   "eaglei",      300,  "interp"),
    ("Ida 2021",         1250,  36822,  51,   "eaglei",      300,  "interp"),
    ("Dec 2023",         2850,  89000,  96,   "documented",  700,  "real"),
    ("July 2026",        6000, 180000, 108,   "documented",  702,  "real"),
]

CREW_LO, CREW_HI = 8, 12000       # binary-search bounds
N_SEED = 4                        # median over this many seeds per evaluation


def load_land_polygon():
    from shapely.geometry import shape
    lb = json.loads((DATA / "connecticut_land_boundary.json").read_text())
    return shape(lb[0]["geojson"])


def uniform_ct_points(n, land_poly, rng):
    from shapely.geometry import Point
    minx, miny, maxx, maxy = land_poly.bounds
    pts = []
    while len(pts) < n:
        take = (n - len(pts)) * 2
        xs = rng.uniform(minx, maxx, take)
        ys = rng.uniform(miny, maxy, take)
        for x, y in zip(xs, ys):
            if land_poly.contains(Point(x, y)):
                pts.append((round(float(y), 5), round(float(x), 5)))
                if len(pts) >= n:
                    break
    return pts


def model_time(outages, m_crews, total_customers):
    """Median model restoration time (busy-crew completion) over N_SEED seeds."""
    from scheduler_numba import plan_restoration_numba
    per = max(1.0, total_customers / len(outages))
    customers = [per] * len(outages)
    ts = []
    for s in range(N_SEED):
        _crews, total, _tl = plan_restoration_numba(
            outages, m_crews, realistic=True, seed=42 + s * 137,
            customers=customers, total_customers=total_customers,
        )
        ts.append(total)
    return float(np.median(ts))


def backout_crews(outages, real_h, total_customers):
    """Binary-search the constant crew count whose model restoration time
    matches real_h. Returns (implied_crews, model_time_at_that_M, floor_h).
    floor_h = model time at CREW_HI (the fastest the model can go); if
    real_h < floor_h the storm restored faster than the model can achieve at
    any crew count (the assessment/overnight/travel floor is the bottleneck,
    not crews) -> implied crews is reported as '>CREW_HI'."""
    t_hi = model_time(outages, CREW_HI, total_customers)   # fastest possible
    t_lo = model_time(outages, CREW_LO, total_customers)   # slowest
    if real_h <= t_hi:
        return None, t_hi, t_hi          # unreachable: below the model floor
    if real_h >= t_lo:
        return CREW_LO, t_lo, t_hi       # needs fewer than the min tried
    lo, hi = CREW_LO, CREW_HI
    while hi - lo > max(5, int(0.02 * lo)):
        mid = (lo + hi) // 2
        t = model_time(outages, mid, total_customers)
        if t > real_h:       # too slow -> need more crews
            lo = mid
        else:                # fast enough -> can use fewer
            hi = mid
    m = (lo + hi) // 2
    return m, model_time(outages, m, total_customers), t_hi


def main():
    land = load_land_polygon()
    rng = np.random.default_rng(7)

    rows = []
    print(f"{'Storm':<17}{'cust':>8}{'realH':>6}{'src':>5}"
          f"{'model@disc':>11}{'implied':>9}{'disc':>6}{'conf':>7}{'impl/disc':>10}")
    for label, n_out, cust, real_h, tsrc, disc, cconf in STORMS:
        pts = uniform_ct_points(n_out, land, rng)
        # Raw model accuracy: what the model predicts at the DISCLOSED crew
        # count, next to the real time -- makes the inversion interpretable.
        t_disc = model_time(pts, disc, cust)
        implied, t_at, floor_h = backout_crews(pts, real_h, cust)
        if implied is None:
            ratio_s = "n/a(floor)"
            impl_s = f">{CREW_HI}"
            impl_val = np.nan
        else:
            impl_val = implied
            impl_s = f"{implied}"
            ratio_s = f"{implied/disc:.2f}"
        print(f"{label:<17}{cust:>8}{real_h:>6}{tsrc[:4]:>5}"
              f"{t_disc:>10.0f}h{impl_s:>9}{disc:>6}{cconf:>7}{ratio_s:>10}"
              + (f"  [floor {floor_h:.0f}h > real {real_h}h]" if implied is None else ""))
        rows.append(dict(label=label, cust=cust, real_h=real_h, tsrc=tsrc,
                         t_disc=t_disc, implied=impl_val, disc=disc,
                         cconf=cconf, floor_h=floor_h))

    make_plot(rows)


def make_plot(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 6.2))
    fig.suptitle("Crew count back-out: model-implied effective crews vs utility-disclosed",
                 fontsize=13, weight="bold")

    ok = [r for r in rows if not np.isnan(r["implied"])]
    # Left: implied vs disclosed, 1:1 line. Color by disclosed-crew confidence.
    for r in rows:
        color = "#16a34a" if r["cconf"] == "real" else "#f59e0b"
        marker = "o" if not np.isnan(r["implied"]) else "v"
        y = r["implied"] if not np.isnan(r["implied"]) else r["disc"]
        axL.scatter(r["disc"], y, s=70, color=color, marker=marker,
                    edgecolor="#222", zorder=5)
        axL.annotate(r["label"], (r["disc"], y), fontsize=7,
                     xytext=(5, 4), textcoords="offset points")
    mx = max(max(r["disc"] for r in rows),
             max(r["implied"] for r in ok)) * 1.15
    axL.plot([0, mx], [0, mx], ls="--", color="#888", label="1:1 (model = disclosed)")
    axL.set_xlabel("utility-DISCLOSED peak crews")
    axL.set_ylabel("model-IMPLIED effective crews")
    axL.set_title("Implied vs disclosed  (green=disclosed real, orange=interpolated;\n"
                  "▽ = storm restored faster than model floor, plotted at disclosed)",
                  fontsize=9)
    axL.legend(fontsize=8); axL.grid(alpha=0.3)
    axL.set_xlim(0, mx); axL.set_ylim(0, mx)

    # Right: implied crews vs storm size (customers) -> surge/reserve curve.
    for r in ok:
        color = "#16a34a" if r["cconf"] == "real" else "#f59e0b"
        axR.scatter(r["cust"], r["implied"], s=70, color=color, edgecolor="#222", zorder=5)
        axR.annotate(r["label"], (r["cust"], r["implied"]), fontsize=7,
                     xytext=(5, 4), textcoords="offset points")
    # disclosed for comparison (hollow)
    for r in rows:
        axR.scatter(r["cust"], r["disc"], s=45, facecolor="none",
                    edgecolor="#2563eb", zorder=4)
    axR.plot([], [], "o", color="#16a34a", label="implied (disclosed real)")
    axR.plot([], [], "o", color="#f59e0b", label="implied (disclosed interp)")
    axR.plot([], [], "o", markerfacecolor="none", markeredgecolor="#2563eb",
             label="disclosed peak crews")
    axR.set_xlabel("storm peak customers out")
    axR.set_ylabel("crews")
    axR.set_title("Crews vs storm size — surge/reserve relationship", fontsize=10)
    axR.legend(fontsize=8); axR.grid(alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "crew_backout.png"
    fig.savefig(out, dpi=115, facecolor="white")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
