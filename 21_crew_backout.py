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
# source, disclosed peak crews, disclosed-crew confidence, HRRR wind key.
#   time_src: "eaglei" (measured 15-min) | "pura" (regulatory) | "documented"
#   crew_conf: "real" (utility/press disclosed) | "interp" (interpolated here)
#   wind_key: HRRR grid key for wind-weighted placement, or None -> uniform
#             (pre-HRRR storms 2011-2012, and the synthetic-track Aug 2020 /
#             flooding Ida, have no gridded wind footprint).
# is_localized: concentrated storms (severe-thunderstorm complex / tornado
# confined to one corner) skip the large-scale workload_mult, matching the
# calibration -- see gate in 03_grid_simulation.html / 07_server.py.
# *** UNIT WARNING (2026-07-17): the `crews` column is NOT one consistent
# *** quantity, and that invalidates the old "real-disclosed storms cluster at
# *** 0.71x disclosed" headline this script used to print.
#
# Wanik, He, Layton, Anagnostou & Hartman (2017) studied this exact utility and
# these exact storms with Eversource's internal records. They define "crews" as
# the daily maximum of TWO-MAN RESTORATION crews, and report 1,068 of them for
# the Oct 2011 Nor'easter. data/hartford_doe_oe417.js's daily_crews counted
# 4,800 for the same storm -- because it counts TOTAL DEPLOYED PERSONNEL
# (line + tree + support). A 4.5x unit mismatch, not a bad number.
#
# The model's implied crews are REPAIR units, so they are only comparable to the
# two-man restoration-crew definition. Right now exactly ONE storm has a real
# figure on that definition (Snowtober, from Wanik et al.). Every other row's
# crew count is news/press-sourced total personnel or an interpolation of one,
# so its ratio is NOT a validation signal -- it is a unit error waiting to be
# resolved. crew_conf now records the DEFINITION, not just the confidence:
#   "restore" = real two-man restoration crews (comparable)
#   "personnel" = total deployed personnel/press figure (NOT comparable)
#   "interp" = interpolated from a "personnel" figure (NOT comparable)
# TODO: Wanik et al. Fig 2b has the real daily restoration-crew curves for Irene
# and Sandy too; get the underlying values (Prof. Wanik is the first author).
#
# *** THE DEEPER TRAP -- the back-out CANNOT escape its own calibration unit. ***
# Swapping Snowtober's crew count to Wanik's real 1,068 makes it read 3.10x
# (implied 3,309), and the model needs 569h at 1,068 crews vs the real 264h.
# That is NOT simply "the model is 3x wrong". The model's crew productivity was
# TUNED so that 4,800 -- a TOTAL-PERSONNEL number -- reproduces Snowtober's real
# 264h (16_calibrate ratio 0.97). So this model's "crew" is calibrated as a
# deployed-personnel unit, and therefore its implied crews are
# personnel-equivalents, not two-man restoration crews. Comparing that output
# against Wanik's 1,068 is STILL a unit error, just a different one.
#
# The consequence is structural: a model-inversion crew estimate only means
# anything in the unit its forward model was calibrated against. To produce
# restoration-crew estimates, the model must first be RE-CALIBRATED against real
# restoration-crew counts (Wanik et al. Fig 2b / Eversource internal records).
# Until then every ratio in this table is uninterpretable, and the previously
# reported "0.71x disclosed" headline should not be cited.
STORMS = [
    # label,            n_out, cust,   real_h, time_src,     crews, crew_conf, wind_key, is_localized
    ("Isaias 2020",     20450, 632632, 199,   "eaglei",     4500,  "personnel", "isaias_2020",   False),
    ("Sandy 2012",      15500, 496769, 264,   "pura",       4000,  "interp", None,              False),
    ("Irene 2011",      21350, 671789, 288,   "pura",       3800,  "interp", None,              False),
    # The ONLY row whose crew count is on the model-comparable definition.
    ("Snowtober 2011",  26050, 807228, 264,   "pura",       1068,  "restore", None,             False),
    ("Dec 2022",         3450, 106021,  75,   "eaglei",     1100,  "personnel", "dec2022",       False),
    ("March 2023",        450,  13863,  60,   "eaglei",      350,  "interp", None,              False),
    ("Dec 2023",         2850,  86770,  83,   "eaglei",      700,  "interp", "dec2023",         False),
    ("Jan 2024",          200,   6409,  26,   "eaglei",      500,  "interp", "jan2024",         False),
    ("Aug 2020 Tornado", 2050,  63912,  66,   "eaglei",      380,  "personnel", None,           True),
    ("Oct 2020 Derecho",  950,  27943,  28,   "eaglei",      300,  "interp", "oct2020_derecho", False),
    ("Henri 2021",        830,  23000,  34,   "eaglei",      300,  "interp", "henri_2021",      False),
    ("Ida 2021",         1250,  36822,  51,   "eaglei",      300,  "interp", None,              False),
    ("July 2026",        6000, 180000, 108,   "documented",  702,  "personnel", "july2026",     True),
]
# Notes on the four EAGLE-I storms added 2026-07-15 (years 2022/2023/2024
# streamed via 18_fetch_eaglei_ct.py; measured via 19_validate_against_eaglei.py):
#   Dec 2022 : EAGLE-I peak 106,021 / full-restore 75h (dataset had 120k/72h --
#              close). REAL disclosed crews: 1,100+ (Eversource press release) --
#              second large storm with a genuinely-sourced crew count, after
#              Isaias. The key new validation point. Model IMPLIES 1,541 (ratio
#              1.40) -- but the disclosed 1,100 is EVERSOURCE-ONLY; the press
#              release adds "plus hundreds of out-of-state mutual-aid workers,"
#              i.e. true total ~1,100 + ~400 ~= 1,500, which the model's 1,541
#              reconciles almost exactly. So the >1x ratio isn't a model miss --
#              it's the back-out recovering the uncounted mutual-aid crews.
#              (Has its OWN HRRR grid now -- 12_/dec2022, peak gust 64mph -- but
#              that broad flat wind field makes wind placement ~= uniform here.)
#   Dec 2023 : EAGLE-I peak 86,770 / 83h (dataset 89k/96h -- peak spot-on, time
#              was ~13h long). Crews (700) RECLASSIFIED real->interp: the dataset
#              entry cites no crew source (unlike Dec 2022/Isaias/July 2026), so
#              700 is an estimate, not a disclosure -- honest downgrade.
#   March 2023: EAGLE-I peak 13,863 / 60h (dataset 26.8k/72h -- peak ~2x
#              overstated, from a same-day news snapshot). Crews interp.
#   Jan 2024 : EAGLE-I reveals a CLUSTER of MINOR events (Jan 9-10 6.4k, Jan
#              13-14 10.5k, Jan 16-17 6k), NOT the dataset's single 52k storm
#              (~8x overstated). Isolated the dated Jan 9-10 event: 6,409 / 26h.
#              Its disclosed 500 crews was interpolated FROM the wrong 52k peak,
#              so its implied/disclosed ratio is not a meaningful signal -- kept
#              as an interp (orange) context point only.
# Pattern worth noting: the well-SOURCED storms (Dec 2022, Dec 2023 peak, Isaias)
# hold up against EAGLE-I; the news-snapshot / interpolated ones (Jan 2024,
# March 2023, Oct 2020) were systematically OVER-stated in the dataset.

CREW_LO, CREW_HI = 8, 12000       # binary-search bounds
N_SEED = 4                        # median over this many seeds per evaluation


def load_land_polygon():
    from shapely.geometry import shape
    lb = json.loads((DATA / "connecticut_land_boundary.json").read_text())
    return shape(lb[0]["geojson"])


def _import_placer():
    """Reuse 20_ensemble_vs_actual's validated wind-weighted placement +
    wind loader (module name starts with a digit -> import via importlib)."""
    import importlib
    return importlib.import_module("20_ensemble_vs_actual")


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


def place_points(wind_key, n, land_poly, rng, placer, wind_cache):
    """Wind-weighted (Gaussian transfer) placement when the storm has an HRRR
    grid; uniform otherwise. Returns (points, placement_label)."""
    if wind_key is None:
        return [(la, lo) for (la, lo) in uniform_ct_points(n, land_poly, rng)], "uniform"
    if wind_key not in wind_cache:
        lats, lons, wind, _rain, _s = placer.load_wind(wind_key)
        wind_cache[wind_key] = (lats, lons, wind)
    lats, lons, wind = wind_cache[wind_key]
    pts = placer.place_outages(lats, lons, wind, land_poly, n, "gaussian", rng)
    return [(la, lo) for (la, lo, _w) in pts], "wind"


def _scaled_assessment(base, cust):
    """Small-event assessment scaling, identical to 07_server._scaled_assessment
    and the JS scheduler -- so the back-out uses the SAME model config the
    calibration did."""
    if base <= 0 or cust <= 0 or cust >= 60000:
        return base
    return max(4.0, min(base, base * (cust / 60000.0) ** 0.4))


def model_time(outages, m_crews, real_cust, is_localized):
    """Median model restoration time (busy-crew completion) over N_SEED seeds,
    replicating the server/JS config: size-scaled assessment delay, overnight
    ops below 70k customers, and (for is_localized concentrated storms) the
    workload_mult skip via total_customers=0."""
    from scheduler_numba import plan_restoration_numba
    per = max(1.0, real_cust / len(outages))
    customers = [per] * len(outages)
    assess = _scaled_assessment(12.0, real_cust)
    overnight = 0 < real_cust <= 70000
    tc_arg = 0.0 if is_localized else float(real_cust)   # is_localized -> workload_mult=1
    ts = []
    for s in range(N_SEED):
        _crews, total, _tl = plan_restoration_numba(
            outages, m_crews, realistic=True, seed=42 + s * 137,
            customers=customers, total_customers=tc_arg,
            assessment_delay=assess, overnight_ops=overnight,
        )
        ts.append(total)
    return float(np.median(ts))


def backout_crews(outages, real_h, real_cust, is_localized):
    """Binary-search the constant crew count whose model restoration time
    matches real_h. Returns (implied_crews, model_time_at_that_M, floor_h).
    floor_h = model time at CREW_HI (the fastest the model can go); if
    real_h < floor_h the storm restored faster than the model can achieve at
    any crew count (the assessment/overnight/travel floor is the bottleneck,
    not crews) -> implied crews is reported as '>CREW_HI'."""
    t_hi = model_time(outages, CREW_HI, real_cust, is_localized)   # fastest possible
    t_lo = model_time(outages, CREW_LO, real_cust, is_localized)   # slowest
    if real_h <= t_hi:
        return None, t_hi, t_hi          # unreachable: below the model floor
    if real_h >= t_lo:
        return CREW_LO, t_lo, t_hi       # needs fewer than the min tried
    lo, hi = CREW_LO, CREW_HI
    while hi - lo > max(5, int(0.02 * lo)):
        mid = (lo + hi) // 2
        t = model_time(outages, mid, real_cust, is_localized)
        if t > real_h:       # too slow -> need more crews
            lo = mid
        else:                # fast enough -> can use fewer
            hi = mid
    m = (lo + hi) // 2
    return m, model_time(outages, m, real_cust, is_localized), t_hi


def main():
    land = load_land_polygon()
    rng = np.random.default_rng(7)
    placer = _import_placer()
    wind_cache = {}

    rows = []
    print(f"{'Storm':<17}{'cust':>8}{'realH':>6}{'src':>5}{'place':>6}"
          f"{'model@disc':>11}{'implied':>9}{'disc':>6}{'conf':>7}{'impl/disc':>10}")
    for label, n_out, cust, real_h, tsrc, disc, cconf, wind_key, is_loc in STORMS:
        pts, place_lbl = place_points(wind_key, n_out, land, rng, placer, wind_cache)
        # Raw model accuracy: what the model predicts at the DISCLOSED crew
        # count, next to the real time -- makes the inversion interpretable.
        t_disc = model_time(pts, disc, cust, is_loc)
        implied, t_at, floor_h = backout_crews(pts, real_h, cust, is_loc)
        if implied is None:
            ratio_s = "n/a(floor)"
            impl_s = f">{CREW_HI}"
            impl_val = np.nan
        else:
            impl_val = implied
            impl_s = f"{implied}"
            ratio_s = f"{implied/disc:.2f}"
        print(f"{label:<17}{cust:>8}{real_h:>6}{tsrc[:4]:>5}{place_lbl:>6}"
              f"{t_disc:>10.0f}h{impl_s:>9}{disc:>6}{cconf:>7}{ratio_s:>10}"
              + (f"  [floor {floor_h:.0f}h > real {real_h}h]" if implied is None else ""))
        rows.append(dict(label=label, cust=cust, real_h=real_h, tsrc=tsrc,
                         place=place_lbl, t_disc=t_disc, implied=impl_val,
                         disc=disc, cconf=cconf, floor_h=floor_h))

    make_plot(rows)


def make_plot(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 6.2))
    fig.suptitle("Crew count back-out: model-implied effective crews vs utility-disclosed",
                 fontsize=13, weight="bold")

    ok = [r for r in rows if not np.isnan(r["implied"])]
    floored = [r for r in rows if np.isnan(r["implied"])]
    # LOG-LOG left panel: crews span 49-3731 and customers 6k-807k (~2 orders
    # of magnitude), so log axes spread the many small storms out of the
    # bottom-left corner. On log axes the 1:1 line and any constant-ratio guide
    # are still straight (parallel) diagonals.
    for r in ok:
        color = "#16a34a" if r["cconf"] == "restore" else "#f59e0b"
        marker = "s" if r["place"] == "wind" else "o"
        axL.scatter(r["disc"], r["implied"], s=80, color=color, marker=marker,
                    edgecolor="#222", zorder=5)
        axL.annotate(r["label"], (r["disc"], r["implied"]), fontsize=7,
                     xytext=(6, 3), textcoords="offset points")
    lo = 30
    hi = max(max(r["disc"] for r in rows), max(r["implied"] for r in ok)) * 1.6
    diag = np.array([lo, hi])
    axL.plot(diag, diag, ls="--", color="#888", zorder=2, label="1:1 (model = disclosed)")
    # No mean line any more. Averaging these ratios would average two different
    # UNITS (two-man restoration crews vs total deployed personnel) -- see the
    # UNIT WARNING at the top. Only the green "restore" point is a real
    # like-for-like comparison; the orange ones are plotted for context only.
    # Floor storms (real faster than the model can go at any crew count): draw
    # at the top edge with an up-triangle -> "implied is off the top / undefined".
    for r in floored:
        axL.scatter(r["disc"], hi*0.92, s=90, color="#16a34a" if r["cconf"] == "real" else "#f59e0b",
                    marker="^", edgecolor="#222", zorder=5)
        axL.annotate(f"{r['label']} (>{CREW_HI}, model floor {r['floor_h']:.0f}h>real {r['real_h']}h)",
                     (r["disc"], hi*0.92), fontsize=6.5, xytext=(6, -2), textcoords="offset points")
    axL.set_xscale("log"); axL.set_yscale("log")
    axL.set_xlim(lo, hi*1.5); axL.set_ylim(lo, hi*1.5)
    axL.set_xlabel("utility-DISCLOSED peak crews (log)")
    axL.set_ylabel("model-IMPLIED effective crews (log)")
    axL.set_title("Implied vs disclosed crews — GREEN = real two-man RESTORATION crews\n"
                  "(the only like-for-like comparison); ORANGE = total deployed personnel\n"
                  "or interpolation — WRONG UNIT, context only. ■ wind, ● uniform, ▲ floor",
                  fontsize=8.5)
    axL.legend(fontsize=8, loc="upper left"); axL.grid(alpha=0.3, which="both")

    # Right: implied crews vs storm size (customers), log-x. implied (filled) +
    # disclosed (hollow blue) for each storm, connected so the gap is visible.
    for r in ok:
        color = "#16a34a" if r["cconf"] == "restore" else "#f59e0b"
        axR.plot([r["cust"], r["cust"]], [r["implied"], r["disc"]],
                 color="#bbb", lw=0.8, zorder=1)
        axR.scatter(r["cust"], r["implied"], s=70, color=color, edgecolor="#222", zorder=5)
        axR.annotate(r["label"], (r["cust"], r["implied"]), fontsize=7,
                     xytext=(5, 4), textcoords="offset points")
    for r in rows:
        axR.scatter(r["cust"], r["disc"], s=45, facecolor="none",
                    edgecolor="#2563eb", zorder=4)
    axR.plot([], [], "o", color="#16a34a", label="implied (vs real restoration crews)")
    axR.plot([], [], "o", color="#f59e0b", label="implied (vs personnel/interp -- wrong unit)")
    axR.plot([], [], "o", markerfacecolor="none", markeredgecolor="#2563eb",
             label="disclosed peak crews")
    axR.set_xscale("log")
    axR.set_xlabel("storm peak customers out (log)")
    axR.set_ylabel("crews")
    axR.set_title("Crews vs storm size — surge/reserve relationship", fontsize=10)
    axR.legend(fontsize=8); axR.grid(alpha=0.3, which="both")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "crew_backout.png"
    fig.savefig(out, dpi=115, facecolor="white")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
