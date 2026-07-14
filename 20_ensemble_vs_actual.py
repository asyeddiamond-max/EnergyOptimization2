"""
20_ensemble_vs_actual.py -- Wind-weighted outage placement + Monte-Carlo
restoration ensemble vs the real EAGLE-I restoration curve.

The full pipeline the analysis asks for, for one real storm:

  1) Time series of ACTUAL outages being restored, by state AND by county,
     from ORNL's EAGLE-I recorded 15-min county data (18_fetch_eaglei_ct.py).
  2) Weather footprint maps -- extreme wind (HRRR GUST grid, always) and
     extreme rain (HRRR 1h APCP grid, if 12_fetch_hrrr_storm_wind.py has been
     re-run with rain; degrades gracefully to wind-only otherwise).
  3) Place N_OUT (default 2000) outages across the state weighted by the wind
     footprint (highest outage density in the highest-wind locations), two
     ways -- a GAUSSIAN transfer and an EXPONENTIAL transfer -- for comparison.
  4) Those N_OUT (lat, lon, wind, customers) points are written to CSV, ready
     to feed into the statewide restoration model.
  5) Feed them into that model (scheduler_numba, the same JIT'd scheduler the
     server uses) M times with different seeds -> an uncertainty ENVELOPE of
     restoration curves, overlaid on the EAGLE-I actual. Fast: numba JIT, so
     M=60 runs of a 2000-outage / 200-crew schedule finish in a couple seconds
     after warm-up.

Scenario: CREWS crews (default 200), clock starting at the storm's onset
("Saturday night" in the July-4-2026 framing; here it's each storm's real
onset hour). The model applies its own mutual-aid arrival ramp from that t0.

Requires: numpy, matplotlib, scipy, shapely, scheduler_numba (numba).

Usage:
    python 20_ensemble_vs_actual.py                     # oct2020_derecho, 200 crews
    python 20_ensemble_vs_actual.py --storm isaias_2020 --crews 200 --runs 60
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT_DIR = HERE / "output"

# Storm configs. "actual" is either an EAGLE-I year (research-grade 15-min
# county data -> full state + per-county curves) OR a "documented" curve
# (peak customers + fraction-restored milestones from news/utility reporting,
# state-level only) for events EAGLE-I doesn't cover yet -- it lags the
# present by months, so 2026 storms have no EAGLE-I.
#   wind_key, actual_spec, onset_UTC, real_peak_crews, label
# actual_spec: ("eaglei", year) | ("documented", peak, [(hour, frac_restored)...])
STORMS = {
    "july2026": ("july2026",
                 ("documented", 180000,
                  [(0, 0.0), (24, 0.45), (48, 0.85), (72, 0.98), (108, 1.0)]),
                 "2026-07-05 00:00", 702,
                 "July 4 2026 Severe Thunderstorm Complex"),
    "oct2020_derecho": ("oct2020_derecho", ("eaglei", 2020), "2020-10-07 20:00", 300,
                        "October 2020 Northeast Derecho"),
    "isaias_2020":     ("isaias_2020", ("eaglei", 2020), "2020-08-04 16:00", 4500,
                        "Tropical Storm Isaias (Aug 2020)"),
    "henri_2021":      ("henri_2021", ("eaglei", 2021), "2021-08-22 14:00", 300,
                        "Tropical Storm Henri (Aug 2021)"),
}
COUNTY_NAMES = {
    "09001": "Fairfield", "09003": "Hartford", "09005": "Litchfield",
    "09007": "Middlesex", "09009": "New Haven", "09011": "New London",
    "09013": "Tolland", "09015": "Windham",
}


# --------------------------------------------------------------------------
# 1) EAGLE-I actual restoration curves (state + per-county)
# --------------------------------------------------------------------------
def load_eaglei(year: int):
    """Returns {fips: {datetime: customers_out}} and a sorted state series."""
    by_county: dict[str, dict[datetime, int]] = defaultdict(dict)
    state: dict[datetime, int] = defaultdict(int)
    path = DATA / f"eaglei_ct_{year}.csv"
    for row in csv.DictReader(open(path, encoding="utf-8")):
        try:
            t = datetime.strptime(row["run_start_time"], "%Y-%m-%d %H:%M:%S")
            v = int(float(row["customers_out"] or 0))
        except (ValueError, KeyError):
            continue
        by_county[row["fips_code"]][t] = v
        state[t] += v
    return by_county, dict(state)


def restoration_curve(series: dict[datetime, int], onset: datetime,
                      window_h: int, sample_h: np.ndarray):
    """Fraction of the peak restored, sampled at sample_h hours after onset."""
    end = onset + timedelta(hours=window_h)
    win = {t: v for t, v in series.items() if onset <= t <= end}
    if not win:
        return None, 0
    peak_t = max(win, key=win.get)
    peak = win[peak_t]
    if peak <= 0:
        return None, 0
    ts = sorted(win)
    hrs = np.array([(t - onset).total_seconds() / 3600 for t in ts])
    out = np.array([win[t] for t in ts], dtype=float)
    # fraction restored = 1 - out/peak, but only meaningful from the peak on;
    # before the peak, "restored" is 0 (still climbing).
    frac = np.clip(1.0 - out / peak, 0.0, 1.0)
    frac[hrs < (peak_t - onset).total_seconds() / 3600] = 0.0
    return np.interp(sample_h, hrs, frac, left=0.0, right=frac[-1]), peak


# --------------------------------------------------------------------------
# 2) Weather footprint (wind, and rain if present)
# --------------------------------------------------------------------------
def load_wind(wind_key: str):
    raw = (DATA / "connecticut_storm_wind.js").read_text(encoding="utf-8")
    d = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    g = d["grid"]
    lats = np.array(g["lats"]); lons = np.array(g["lons"])
    s = d["storms"][wind_key]
    wind = np.array(s["peak_wind_mph"], dtype=float)       # [n_lat][n_lon]
    rain = np.array(s["peak_rain_in"], dtype=float) if s.get("peak_rain_in") else None
    return lats, lons, wind, rain, s


def load_land_polygon():
    from shapely.geometry import shape
    lb = json.loads((DATA / "connecticut_land_boundary.json").read_text())
    return shape(lb[0]["geojson"])


# --------------------------------------------------------------------------
# 3) Wind-weighted placement: Gaussian vs Exponential transfer
# --------------------------------------------------------------------------
def place_outages(lats, lons, wind, land_poly, n_out, method, rng,
                  gauss_sigma=0.45, exp_beta=4.0):
    """Sample n_out (lat, lon, wind_mph) points whose spatial density follows
    the wind field. Two transfers from normalized wind wn in [0,1]:
      - 'gaussian':   density ∝ exp(-((wn-1)^2)/(2σ^2))  (Gaussian falloff
                      from the peak-wind value -- concentrated near the max,
                      moderate spread)
      - 'exponential':density ∝ exp(β·wn)                (exponential emphasis
                      -- sharper concentration at the very windiest cells)
    Cells are jittered to real lat/lon and rejected outside CT land."""
    from shapely.geometry import Point
    LON, LAT = np.meshgrid(lons, lats)
    w = np.nan_to_num(wind, nan=float(np.nanmin(wind)))
    wn = (w - w.min()) / (w.max() - w.min() + 1e-9)
    if method == "gaussian":
        dens = np.exp(-((wn - 1.0) ** 2) / (2 * gauss_sigma ** 2))
    elif method == "exponential":
        dens = np.exp(exp_beta * wn)
    else:
        raise ValueError(method)

    # Zero out cells whose center is off CT land, so the density lives only
    # over places that can actually have outages.
    on_land = np.zeros(LAT.shape, dtype=bool)
    for i in range(LAT.shape[0]):
        for j in range(LAT.shape[1]):
            if land_poly.contains(Point(LON[i, j], LAT[i, j])):
                on_land[i, j] = True
    dens = np.where(on_land, dens, 0.0)
    if dens.sum() <= 0:
        dens = on_land.astype(float)
    p = (dens / dens.sum()).ravel()

    dlat = float(lats[1] - lats[0])
    dlon = float(lons[1] - lons[0])
    flat_lat = LAT.ravel(); flat_lon = LON.ravel(); flat_w = w.ravel()
    pts = []
    tries = 0
    idx_pool = np.arange(p.size)
    while len(pts) < n_out and tries < n_out * 40:
        take = n_out - len(pts)
        cells = rng.choice(idx_pool, size=take, p=p)
        jl = flat_lat[cells] + (rng.random(take) - 0.5) * dlat
        jo = flat_lon[cells] + (rng.random(take) - 0.5) * dlon
        for la, lo, wc in zip(jl, jo, flat_w[cells]):
            if land_poly.contains(Point(lo, la)):
                pts.append((round(float(la), 5), round(float(lo), 5), round(float(wc), 1)))
                if len(pts) >= n_out:
                    break
        tries += take
    return pts[:n_out]


# --------------------------------------------------------------------------
# 5) Feed to the statewide model M times -> restoration-curve ensemble
# --------------------------------------------------------------------------
def daily_ramp_arrivals(crews_per_day, max_crews, start_h):
    """Crew arrival times for a "N crews/day" ramp: crews come online in
    daily waves of `crews_per_day`, first wave at `start_h` (Saturday-night
    mobilization after the storm passes), up to `max_crews` total. E.g.
    200/day, cap 702, start 6h -> 200 crews at 6h, 400 at 30h, 600 at 54h,
    702 at 78h."""
    import numpy as _np
    return _np.array([start_h + (c // crews_per_day) * 24.0
                      for c in range(max_crews)], dtype=float)


def ensemble_curves(placements, crews, seed0, sample_h, total_customers,
                    crew_arrivals=None):
    """placements: list of point-lists (one per MC run). crew_arrivals: optional
    explicit crew-arrival schedule (len == crews). Returns an array
    [n_runs, len(sample_h)] of fraction-restored curves."""
    from scheduler_numba import plan_restoration_numba
    n = len(placements[0])
    per_cust = max(1.0, total_customers / n)   # each outage point ~ this many customers
    curves = []
    for k, pts in enumerate(placements):
        outages = [(la, lo) for (la, lo, _w) in pts]
        customers = [per_cust] * len(pts)
        crews_out, _total, _tl = plan_restoration_numba(
            outages, crews, realistic=True, seed=seed0 + k * 101,
            customers=customers, total_customers=total_customers,
            crew_arrivals=crew_arrivals,
        )
        etas = []
        for c in crews_out:
            for j in c["jobs"]:
                etas.append(j["eta"])
        etas.sort()
        if not etas:
            curves.append(np.zeros_like(sample_h)); continue
        etas = np.array(etas)
        # fraction of jobs (== customers, uniform per_cust) finished by hour h
        frac = np.searchsorted(etas, sample_h, side="right") / len(etas)
        curves.append(frac)
    return np.array(curves)


# --------------------------------------------------------------------------
# Plotting
# --------------------------------------------------------------------------
def make_figure(cfg_label, lats, lons, wind, rain, placements_g, placements_e,
                sample_h, state_curve, county_curves, env_g, env_e, crew_desc,
                actual_note, out_png, land_poly):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly

    def land_patches(ax):
        polys = (land_poly.geoms if land_poly.geom_type == "MultiPolygon"
                 else [land_poly])
        for g in polys:
            ax.add_patch(MplPoly(np.array(g.exterior.coords), closed=True,
                                 fill=False, edgecolor="#333", lw=0.8, zorder=5))

    has_rain = rain is not None
    fig = plt.figure(figsize=(16, 11))
    fig.suptitle(f"{cfg_label}  —  wind-weighted placement + restoration "
                 f"ensemble vs actual", fontsize=14, weight="bold")

    # Row 1: wind footprint, rain footprint, gaussian placement, exp placement
    ax1 = fig.add_subplot(3, 2, 1)
    pc = ax1.pcolormesh(lons, lats, wind, cmap="YlOrRd", shading="auto")
    fig.colorbar(pc, ax=ax1, label="peak gust (mph)")
    land_patches(ax1); ax1.set_title("Weather footprint: extreme WIND (HRRR GUST)")
    ax1.set_xlabel("lon"); ax1.set_ylabel("lat")

    ax2 = fig.add_subplot(3, 2, 2)
    if has_rain:
        pc = ax2.pcolormesh(lons, lats, rain, cmap="Blues", shading="auto")
        fig.colorbar(pc, ax=ax2, label="1h precip (in)")
        ax2.set_title("Weather footprint: extreme RAIN (HRRR APCP)")
    else:
        ax2.text(0.5, 0.5, "rain footprint pending\n(re-run 12_fetch_hrrr_storm_wind.py\nwith APCP)",
                 ha="center", va="center", transform=ax2.transAxes, color="#888")
        ax2.set_title("Weather footprint: extreme RAIN")
    land_patches(ax2); ax2.set_xlabel("lon"); ax2.set_ylabel("lat")

    for ax, pts, name in [(fig.add_subplot(3, 2, 3), placements_g[0], "GAUSSIAN"),
                          (fig.add_subplot(3, 2, 4), placements_e[0], "EXPONENTIAL")]:
        arr = np.array(pts)
        ax.pcolormesh(lons, lats, wind, cmap="YlOrRd", shading="auto", alpha=0.35)
        ax.scatter(arr[:, 1], arr[:, 0], s=3, c="#111", marker="x", linewidths=0.5, alpha=0.6)
        land_patches(ax)
        ax.set_title(f"{len(pts)} outages placed — {name} wind weighting")
        ax.set_xlabel("lon"); ax.set_ylabel("lat")

    # Row 3: state restoration ensemble vs actual; per-county actual
    ax5 = fig.add_subplot(3, 2, 5)
    # Crew model: daily ramp. Gaussian vs Exponential placement overlap
    # almost exactly -> kernel choice barely affects restoration timing.
    # The uncertainty band is the 5-95th percentile across the ensemble
    # (placement + stochastic repair-time variation); it is genuinely narrow
    # because at a fixed crew schedule the whole-state restoration time is
    # crew-bound and thus quite predictable -- the spread is a real result,
    # not a missing band.
    for env, color, name in [(env_g, "#2563eb", "Gaussian placement"),
                             (env_e, "#7c3aed", "Exponential placement")]:
        lo, med, hi = np.percentile(env, [5, 50, 95], axis=0)
        ax5.fill_between(sample_h, 100 * lo, 100 * hi, color=color, alpha=0.30,
                         label=f"model 5–95% band — {name}")
        ax5.plot(sample_h, 100 * med, color=color, lw=1.6)
    if state_curve is not None:
        ax5.plot(sample_h, 100 * state_curve, color="#111", lw=2.5, ls="--",
                 label=f"ACTUAL — {actual_note}")
    ax5.set_xlabel("hours after storm onset (Sat night)")
    ax5.set_ylabel("% customers restored")
    ax5.set_title(f"Statewide restoration ensemble vs actual\ncrew model: {crew_desc}",
                  fontsize=10)
    ax5.legend(fontsize=8, loc="lower right"); ax5.grid(alpha=0.3); ax5.set_ylim(0, 101)

    ax6 = fig.add_subplot(3, 2, 6)
    if county_curves:
        for fips, cv in county_curves.items():
            if cv is not None:
                ax6.plot(sample_h, 100 * cv, lw=1.3, label=COUNTY_NAMES.get(fips, fips))
        ax6.set_title("ACTUAL restoration by county (EAGLE-I)")
        ax6.legend(fontsize=7, ncol=2)
    else:
        ax6.text(0.5, 0.5, "County-level ACTUAL restoration\nnot available for 2026\n\n"
                 "(ORNL EAGLE-I — the research-grade county\n15-min outage record — lags the present\n"
                 "by months; 2026 not yet published)",
                 ha="center", va="center", transform=ax6.transAxes, color="#555", fontsize=10)
        ax6.set_title("ACTUAL restoration by county")
    ax6.set_xlabel("hours after storm onset"); ax6.set_ylabel("% restored")
    ax6.grid(alpha=0.3); ax6.set_ylim(0, 101)

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    OUT_DIR.mkdir(exist_ok=True)
    fig.savefig(out_png, dpi=115, facecolor="white")
    print(f"Wrote {out_png}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storm", default="july2026", choices=sorted(STORMS))
    ap.add_argument("--crews-per-day", type=int, default=200,
                    help="crews added per day in the ramp (starting Sat night)")
    ap.add_argument("--max-crews", type=int, default=None,
                    help="cap the ramp at this many crews (default: storm's real peak)")
    ap.add_argument("--ramp-start-h", type=float, default=6.0,
                    help="hours after onset when the first crew wave starts")
    ap.add_argument("--runs", type=int, default=60)
    ap.add_argument("--n-out", type=int, default=2000)
    ap.add_argument("--window-h", type=int, default=None,
                    help="hours after onset to analyze (default: storm-appropriate)")
    args = ap.parse_args()

    wind_key, actual_spec, onset_s, real_crews, label = STORMS[args.storm]
    onset = datetime.strptime(onset_s, "%Y-%m-%d %H:%M")
    window_h = args.window_h or (240 if real_crews > 1000 else 120)
    sample_h = np.linspace(0, window_h, 240)
    rng = np.random.default_rng(12345)

    print(f"=== {label} ===")
    if actual_spec[0] == "eaglei":
        year = actual_spec[1]
        print(f"Loading EAGLE-I {year} actual restoration (state + county)...")
        by_county, state = load_eaglei(year)
        state_curve, state_peak = restoration_curve(state, onset, window_h, sample_h)
        county_curves = {f: restoration_curve(s, onset, window_h, sample_h)[0]
                         for f, s in by_county.items()}
        actual_note = f"EAGLE-I measured (real ~{real_crews} crews)"
    else:  # documented
        _, state_peak, pts = actual_spec
        hrs = np.array([h for h, _ in pts]); frac = np.array([f for _, f in pts])
        state_curve = np.interp(sample_h, hrs, frac, left=0.0, right=frac[-1])
        county_curves = {}  # no county-level actual exists for 2026 (EAGLE-I lags)
        actual_note = (f"documented (news/utility; real {real_crews} crews) — "
                       f"EAGLE-I county data not available for 2026 yet")
        print(f"  documented state-level actual ({len(pts)} milestones); "
              f"county-level actual unavailable (no EAGLE-I for {onset.year})")
    print(f"  statewide peak {state_peak:,} customers out")

    print("Loading HRRR weather footprint...")
    lats, lons, wind, rain, _s = load_wind(wind_key)
    land_poly = load_land_polygon()
    print(f"  wind peak {np.nanmax(wind):.0f} mph"
          + (f", rain peak {np.nanmax(rain):.2f} in/hr" if rain is not None else ", rain: not fetched"))

    print(f"Placing {args.n_out} outages x {args.runs} runs (Gaussian & Exponential)...")
    placements_g = [place_outages(lats, lons, wind, land_poly, args.n_out, "gaussian", rng)
                    for _ in range(args.runs)]
    placements_e = [place_outages(lats, lons, wind, land_poly, args.n_out, "exponential", rng)
                    for _ in range(args.runs)]

    # 4) write the first placement of each method to CSV for the statewide model
    OUT_DIR.mkdir(exist_ok=True)
    csv_path = OUT_DIR / f"outage_locations_{args.storm}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["method", "lat", "lon", "wind_mph"])
        for la, lo, w in placements_g[0]:
            wr.writerow(["gaussian", la, lo, w])
        for la, lo, w in placements_e[0]:
            wr.writerow(["exponential", la, lo, w])
    print(f"  wrote {csv_path} ({2*args.n_out} rows for the statewide model)")

    # "N crews/day" ramp, capped at the storm's real peak crew count.
    max_crews = args.max_crews or real_crews
    arrivals = daily_ramp_arrivals(args.crews_per_day, max_crews, args.ramp_start_h)
    wave_hours = sorted(set(int(a) for a in arrivals))
    crew_desc = (f"{args.crews_per_day} crews/day ramp (waves at h="
                 f"{','.join(map(str, wave_hours))}; -> {max_crews} by h{wave_hours[-1]})")
    print(f"Running {args.runs}-member ensemble through the statewide model")
    print(f"  crew model: {crew_desc}")
    tc = state_peak or (args.n_out * 15)
    import time
    t0 = time.time()
    env_g = ensemble_curves(placements_g, max_crews, 1000, sample_h, tc, arrivals)
    env_e = ensemble_curves(placements_e, max_crews, 5000, sample_h, tc, arrivals)
    print(f"  {2*args.runs} model runs in {time.time()-t0:.1f}s")

    med_g = np.percentile(env_g, 50, axis=0)[-1] * 100
    med_e = np.percentile(env_e, 50, axis=0)[-1] * 100
    print(f"  model median restored by {window_h}h: "
          f"Gaussian {med_g:.0f}%, Exponential {med_e:.0f}%")
    if state_curve is not None:
        print(f"  ACTUAL restored by {window_h}h: {state_curve[-1]*100:.0f}%")

    make_figure(label, lats, lons, wind, rain, placements_g, placements_e,
                sample_h, state_curve, county_curves, env_g, env_e, crew_desc,
                actual_note, OUT_DIR / f"ensemble_vs_actual_{args.storm}.png", land_poly)


if __name__ == "__main__":
    main()
