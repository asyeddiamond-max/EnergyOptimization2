"""
23_concentrated_placement.py -- PROTOTYPE: place a localized storm's outages in
its REAL damage footprint (from NCEI point reports) instead of smearing them
statewide.

Why this exists (see the finding in 22_ / the design discussion): the production
model places outages by weather-severity x customer-exposure, Gaussian-smoothed
at 10 km. Because customers blanket Connecticut, that spreads EVERY storm's
outages across the whole state -- measured spatial dispersion is ~49.5 km for a
statewide hurricane AND a one-town tornado alike. So the model structurally
cannot represent a spatially-concentrated storm, and `is_localized` is a
friction-patch for that broken placement rather than a fix.

This prototype fixes the placement itself. NOAA NCEI Storm Events gives real,
geolocated wind/tornado damage points (data/connecticut_storm_events_*.json,
fetched by 15_fetch_storm_events.py). We place outages weighted by:

    tract_weight = customers(tract) * SUM_over_reports[ wind_excess(report)
                                       * exp(-dist(tract, report)^2 / 2 sigma^2) ]

i.e. outages happen where there is BOTH damaging weather (near a real report)
AND infrastructure to damage (customers). Tornado points (78 kt) pull far harder
than 40 kt thunderstorm-wind points, so a tornado's outages cluster along its
path; a broad derecho's spread along its whole swath.

Baseline (what the model does today) = customers-only weighting = statewide.

Outputs a side-by-side map + dispersion numbers, showing the concentrated
placement collapses dispersion toward the storm's real footprint. This is the
prerequisite the spread/dispersion friction term needed: once placement
concentrates, dispersion actually varies by storm.

Usage:
    python 23_concentrated_placement.py --storm sep2019
    python 23_concentrated_placement.py --storm may2018 --sigma-km 12 --n 2000
"""
from __future__ import annotations
import argparse
import json
import math
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT_DIR = HERE / "output"

# storm key -> (NCEI event-file date, human label). All are real, geolocated
# NCEI Storm Events pulls (15_fetch_storm_events.py).
STORMS = {
    "may2018": ("2018-05-15", "May 2018 derecho + tornadoes"),
    "sep2019": ("2019-09-04", "Sep 2019 Merrow tornado"),
    "oct2020": ("2020-10-07", "Oct 2020 serial derecho"),
}

WIND_ONSET_KT = 33.0   # ~38 mph, tree/line damage onset; weight is excess over this


def load_tracts():
    txt = (DATA / "connecticut_census_tracts.js").read_text(encoding="utf-8")
    arr = json.loads(re.search(r"=\s*(\[.*\])\s*;", txt, re.S).group(1))
    lat = np.array([t["lat"] for t in arr], dtype=float)
    lon = np.array([t["lon"] for t in arr], dtype=float)
    pop = np.array([t.get("pop", 0) for t in arr], dtype=float)
    return lat, lon, pop


def load_reports(date_str):
    d = json.loads((DATA / f"connecticut_storm_events_{date_str}.json").read_text(encoding="utf-8"))
    recs = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
    out = []
    for r in recs:
        la, lo, w = r.get("lat"), r.get("lon"), r.get("wind_kt")
        if la is None or lo is None:
            continue
        out.append((float(la), float(lo), float(w or WIND_ONSET_KT),
                    "ornado" in (r.get("event_type") or "")))
    return out


def _km(dlat, dlon, lat0):
    """Local flat-earth km for small offsets at CT latitude."""
    return math.hypot(dlat * 111.32, dlon * 111.32 * math.cos(math.radians(lat0)))


def concentrated_weights(lat, lon, pop, reports, sigma_km):
    """tract weight = pop * sum_reports[ wind_excess * gaussian(dist) ]."""
    lat0 = float(np.mean(lat))
    ky, kx = 111.32, 111.32 * math.cos(math.radians(lat0))
    w = np.zeros_like(pop)
    for rlat, rlon, rkt, is_tor in reports:
        dy = (lat - rlat) * ky
        dx = (lon - rlon) * kx
        d2 = dy * dy + dx * dx
        excess = max(1.0, rkt - WIND_ONSET_KT)
        w += excess * np.exp(-d2 / (2 * sigma_km * sigma_km))
    return pop * w


def sample(lat, lon, weights, n, rng, jitter_deg=0.02):
    p = weights / weights.sum()
    idx = rng.choice(len(weights), size=n, p=p)
    out_lat = lat[idx] + rng.uniform(-jitter_deg, jitter_deg, n)
    out_lon = lon[idx] + rng.uniform(-jitter_deg, jitter_deg, n)
    return out_lat, out_lon


def dispersion_km(la, lo):
    lat0 = float(np.mean(la))
    ky, kx = 111.32, 111.32 * math.cos(math.radians(lat0))
    return math.sqrt(np.mean(((la - la.mean()) * ky) ** 2 + ((lo - lo.mean()) * kx) ** 2))


def pct_within(la, lo, reports, radius_km):
    lat0 = float(np.mean(la)); ky, kx = 111.32, 111.32 * math.cos(math.radians(lat0))
    rl = np.array([[r[0], r[1]] for r in reports])
    hit = np.zeros(len(la), dtype=bool)
    for rlat, rlon in rl:
        d = np.hypot((la - rlat) * ky, (lo - rlon) * kx)
        hit |= d <= radius_km
    return 100.0 * hit.mean()


def land_polys():
    from shapely.geometry import shape
    lb = json.loads((DATA / "connecticut_land_boundary.json").read_text())
    g = shape(lb[0]["geojson"])
    return list(g.geoms) if g.geom_type == "MultiPolygon" else [g]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storm", default="sep2019", choices=sorted(STORMS))
    ap.add_argument("--sigma-km", type=float, default=12.0,
                    help="damage decay radius around each report point")
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()

    date_str, label = STORMS[a.storm]
    lat, lon, pop = load_tracts()
    reports = load_reports(date_str)
    rng = np.random.default_rng(42)

    w_base = pop.copy()                                   # today's behavior
    w_conc = concentrated_weights(lat, lon, pop, reports, a.sigma_km)

    bla, blo = sample(lat, lon, w_base, a.n, rng)
    cla, clo = sample(lat, lon, w_conc, a.n, rng)

    d_base, d_conc = dispersion_km(bla, blo), dispersion_km(cla, clo)
    print(f"\nStorm: {label}  ({len(reports)} real NCEI points, sigma={a.sigma_km:.0f} km)")
    print(f"{'':22}{'dispersion':>12}{'% within 25km of a report':>28}")
    print(f"{'BASELINE (statewide)':22}{d_base:>10.1f}km{pct_within(bla,blo,reports,25):>26.0f}%")
    print(f"{'CONCENTRATED (NCEI)':22}{d_conc:>10.1f}km{pct_within(cla,clo,reports,25):>26.0f}%")
    print(f"-> dispersion cut {100*(1-d_conc/d_base):.0f}%: the storm's outages now "
          f"sit in its real footprint, not statewide.")

    make_plot(a.storm, label, reports, bla, blo, cla, clo, d_base, d_conc)


def make_plot(storm, label, reports, bla, blo, cla, clo, d_base, d_conc):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    polys = land_polys()
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 5.6))
    fig.suptitle(f"Concentrated outage placement from real NCEI reports — {label}",
                 fontsize=13, weight="bold")
    for ax, (la, lo, ttl, d, col) in zip(
        (axL, axR),
        [(bla, blo, f"BASELINE: customers only (today) — dispersion {d_base:.0f} km", d_base, "#2563eb"),
         (cla, clo, f"CONCENTRATED: x NCEI report proximity — dispersion {d_conc:.0f} km", d_conc, "#dc2626")]):
        for poly in polys:
            xs, ys = poly.exterior.xy
            ax.fill(xs, ys, color="#eef2f7", zorder=0)
            ax.plot(xs, ys, color="#9aa7b8", lw=0.6, zorder=1)
        ax.scatter(lo, la, s=2, c=col, alpha=0.35, zorder=2)
        for rlat, rlon, rkt, is_tor in reports:
            ax.scatter(rlon, rlat, s=40 + (rkt - 33) * 6, marker="*",
                       facecolor="#f59e0b" if not is_tor else "#111",
                       edgecolor="#000", linewidths=0.4, zorder=5)
        ax.set_title(ttl, fontsize=9)
        ax.set_aspect(1 / math.cos(math.radians(41.6)))
        ax.set_xlim(-73.8, -71.7); ax.set_ylim(40.95, 42.1)
        ax.set_xlabel("lon"); ax.set_ylabel("lat")
    axR.scatter([], [], marker="*", c="#f59e0b", s=60, label="NCEI wind report")
    axR.scatter([], [], marker="*", c="#111", s=90, label="NCEI tornado")
    axR.legend(fontsize=8, loc="lower right")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"concentrated_placement_{storm}.png"
    fig.savefig(out, dpi=115, facecolor="white")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
