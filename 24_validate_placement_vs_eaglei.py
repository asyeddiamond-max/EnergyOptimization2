"""
24_validate_placement_vs_eaglei.py -- Does the concentrated placement put outages
in the RIGHT counties? Score it against EAGLE-I's real county-level footprint.

23_concentrated_placement.py showed the concentrated placement COLLAPSES spatial
dispersion toward a storm's real damage footprint. But "concentrated" is not the
same as "correct": collapsing outages into the wrong place is still wrong. This
script closes that gap with an INDEPENDENT, county-resolution ground truth.

ORNL EAGLE-I (18_fetch_eaglei_ct.py) records customers-without-power per COUNTY
every 15 minutes. For a given storm we can therefore ask, per county: how hard
was it *actually* hit? That gives a real 8-county impact distribution -- data
neither placement ever sees (placement uses census tracts + NCEI point reports;
EAGLE-I is the utilities' own outage-map archive).

We then measure how well each placement's county distribution matches EAGLE-I's:

    BASELINE     = customers-only weighting  (what the production model does today;
                   spreads outages across the populous SW corridor)
    CONCENTRATED = customers x NCEI-report proximity  (23_'s placement)

Metrics (placement county-share vs EAGLE-I county-share, over CT's 8 counties):
    Pearson r, Spearman rho   -- higher is better (1.0 = perfect)
    total-variation distance  -- 0.5*sum|p-q|, LOWER is better (0 = identical)
    top-3 capture             -- % of placed outages landing in EAGLE-I's 3
                                 hardest-hit counties; higher is better

Unit note: the model places OUTAGES (each ~35 geography-derived customers, roughly
flat across counties -- see 03_grid_simulation.html), so outage-count share is a
fair proxy for customer share. We compare spatial *distributions*, not magnitudes.

Placement math (concentrated_weights / load_reports) is imported unchanged from
23_concentrated_placement.py so this is a validation OF that prototype, not a
reimplementation of it.

Usage:
    python 24_validate_placement_vs_eaglei.py --storm oct2020
    python 24_validate_placement_vs_eaglei.py --storm oct2020 --sigma-km 12 --n 3000
"""
from __future__ import annotations
import argparse
import csv
import importlib.util
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT_DIR = HERE / "output"

# The 8 CT counties, canonical order (matches census-tract + EAGLE-I `county`).
COUNTIES = ["Fairfield", "Hartford", "Litchfield", "Middlesex",
            "New Haven", "New London", "Tolland", "Windham"]

# storm key -> (EAGLE-I year, window start, window end inclusive). Windows bound
# the storm's outage response so a county's peak is THIS storm, not a later one.
# Only storms whose EAGLE-I year has been fetched (18_) can be validated.
STORM_WINDOWS = {
    "oct2020": (2020, datetime(2020, 10, 7, 12), datetime(2020, 10, 10, 0)),
    "sep2019": (2019, datetime(2019, 9, 2, 0),  datetime(2019, 9, 6, 0)),
    "may2018": (2018, datetime(2018, 5, 15, 0), datetime(2018, 5, 18, 0)),
}


def _load_23():
    """Import 23_concentrated_placement.py (numeric name -> importlib)."""
    spec = importlib.util.spec_from_file_location(
        "placement23", HERE / "23_concentrated_placement.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_tracts_with_county():
    txt = (DATA / "connecticut_census_tracts.js").read_text(encoding="utf-8")
    arr = json.loads(re.search(r"=\s*(\[.*\])\s*;", txt, re.S).group(1))
    lat = np.array([t["lat"] for t in arr], dtype=float)
    lon = np.array([t["lon"] for t in arr], dtype=float)
    pop = np.array([t.get("pop", 0) for t in arr], dtype=float)
    cty = np.array([t.get("county", "") for t in arr])
    return lat, lon, pop, cty


def eaglei_county_peak(year, t0, t1):
    """Per-county PEAK customers_out over [t0, t1]. Schema drifts by year:
    customers_out (2020-2022) / sum (2023) -- handle both."""
    path = DATA / f"eaglei_ct_{year}.csv"
    if not path.exists():
        raise SystemExit(
            f"EAGLE-I {year} not downloaded ({path.name}). "
            f"Run: python 18_fetch_eaglei_ct.py --year {year}")
    peak = defaultdict(float)
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = r.get("run_start_time", "")
            if len(ts) < 16:
                continue
            try:
                tt = datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if not (t0 <= tt <= t1):
                continue
            c = r.get("county", "")
            v = r.get("customers_out")
            if v in (None, ""):
                v = r.get("sum")
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v > peak[c]:
                peak[c] = v
    return np.array([peak.get(c, 0.0) for c in COUNTIES], dtype=float)


def county_share(weights, county_codes, n_counties, n, n_seeds, base_seed=1000):
    """Average per-county outage-count share over n_seeds Monte Carlo draws.
    Returns (mean_share[8], std_share[8])."""
    p = weights / weights.sum()
    shares = np.zeros((n_seeds, n_counties))
    for s in range(n_seeds):
        rng = np.random.default_rng(base_seed + s)
        idx = rng.choice(len(weights), size=n, p=p)
        counts = np.bincount(county_codes[idx], minlength=n_counties).astype(float)
        shares[s] = counts / counts.sum()
    return shares.mean(axis=0), shares.std(axis=0)


def _pearson(a, b):
    a = a - a.mean(); b = b - b.mean()
    d = math.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else float("nan")


def _spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return _pearson(ra, rb)


def _tv(p, q):
    """Total-variation distance between two distributions (0=identical,1=disjoint)."""
    return 0.5 * float(np.abs(p - q).sum())


def _metrics(place_share, actual_share, top_k_idx):
    return {
        "pearson": _pearson(place_share, actual_share),
        "spearman": _spearman(place_share, actual_share),
        "tv": _tv(place_share, actual_share),
        "top3": 100.0 * float(place_share[top_k_idx].sum()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storm", default="oct2020", choices=sorted(STORM_WINDOWS))
    ap.add_argument("--sigma-km", type=float, default=12.0)
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--seeds", type=int, default=40)
    a = ap.parse_args()

    p23 = _load_23()
    year, t0, t1 = STORM_WINDOWS[a.storm]
    date_str, label = p23.STORMS[a.storm]

    lat, lon, pop, cty = load_tracts_with_county()
    code = {c: i for i, c in enumerate(COUNTIES)}
    county_codes = np.array([code.get(c, -1) for c in cty])
    if (county_codes < 0).any():
        bad = sorted(set(cty[county_codes < 0]))
        raise SystemExit(f"tracts with unrecognized county: {bad}")

    reports = p23.load_reports(date_str)
    actual = eaglei_county_peak(year, t0, t1)
    if actual.sum() == 0:
        raise SystemExit(f"no EAGLE-I outages in window {t0}..{t1}; wrong window?")
    actual_share = actual / actual.sum()
    top3_idx = np.argsort(actual_share)[-3:]

    w_base = pop.copy()
    w_conc = p23.concentrated_weights(lat, lon, pop, reports, a.sigma_km)

    base_share, base_std = county_share(w_base, county_codes, len(COUNTIES), a.n, a.seeds)
    conc_share, conc_std = county_share(w_conc, county_codes, len(COUNTIES), a.n, a.seeds)

    m_base = _metrics(base_share, actual_share, top3_idx)
    m_conc = _metrics(conc_share, actual_share, top3_idx)

    # ---- report -------------------------------------------------------------
    print(f"\n{'='*74}")
    print(f"COUNTY-LEVEL VALIDATION vs EAGLE-I  --  {label}")
    print(f"  window {t0:%Y-%m-%d %H:%M} .. {t1:%Y-%m-%d %H:%M} (EAGLE-I {year}), "
          f"{len(reports)} NCEI reports, n={a.n} x {a.seeds} seeds, sigma={a.sigma_km:.0f}km")
    print(f"{'='*74}")
    top3_names = [COUNTIES[i] for i in reversed(top3_idx)]
    print(f"EAGLE-I hardest-hit (peak customers-out): "
          f"{', '.join(f'{COUNTIES[i]} {100*actual_share[i]:.0f}%' for i in reversed(np.argsort(actual_share)))}")
    print(f"-> top-3 counties to match: {', '.join(top3_names)}\n")

    print(f"{'county':12}{'EAGLE-I':>10}{'BASELINE':>12}{'CONCENTR.':>12}   who moved toward truth")
    print(f"{'-'*74}")
    order = list(reversed(np.argsort(actual_share)))
    for i in order:
        a_s, b_s, c_s = actual_share[i], base_share[i], conc_share[i]
        # did concentrated move closer to EAGLE-I than baseline, for this county?
        closer = "concentrated" if abs(c_s - a_s) < abs(b_s - a_s) else "baseline"
        arrow = "OK " if closer == "concentrated" else "   "
        print(f"{COUNTIES[i]:12}{100*a_s:>9.1f}%{100*b_s:>11.1f}%{100*c_s:>11.1f}%   {arrow}{closer}")

    print(f"\n{'metric':22}{'BASELINE':>12}{'CONCENTR.':>12}   better")
    print(f"{'-'*60}")
    rows = [
        ("Pearson r  (^)", m_base["pearson"], m_conc["pearson"], "high"),
        ("Spearman rho (^)", m_base["spearman"], m_conc["spearman"], "high"),
        ("total-var dist (v)", m_base["tv"], m_conc["tv"], "low"),
        ("top-3 capture % (^)", m_base["top3"], m_conc["top3"], "high"),
    ]
    for name, b, c, d in rows:
        better = ("concentrated" if ((c > b) if d == "high" else (c < b)) else "baseline")
        fmt = (lambda x: f"{x:.3f}") if "%" not in name else (lambda x: f"{x:.1f}")
        print(f"{name:22}{fmt(b):>12}{fmt(c):>12}   {better}")

    print(f"\nInterpretation:")
    dtv = m_base["tv"] - m_conc["tv"]
    print(f"  Concentrated placement's county distribution is "
          f"{'CLOSER' if dtv > 0 else 'FARTHER'} to EAGLE-I's real footprint "
          f"(TV {m_base['tv']:.2f} -> {m_conc['tv']:.2f}, {'-' if dtv>0 else '+'}{abs(dtv):.2f}).")
    print(f"  Top-3 hardest-hit capture: baseline {m_base['top3']:.0f}% -> "
          f"concentrated {m_conc['top3']:.0f}% of outages land in the counties "
          f"EAGLE-I shows were actually hit hardest.")

    make_plot(a.storm, label, COUNTIES, order, actual_share,
              base_share, base_std, conc_share, conc_std, m_base, m_conc)


def make_plot(storm, label, counties, order, actual, base, base_std,
              conc, conc_std, m_base, m_conc):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = [counties[i] for i in order]
    a = np.array([actual[i] for i in order]) * 100
    b = np.array([base[i] for i in order]) * 100
    c = np.array([conc[i] for i in order]) * 100
    be = np.array([base_std[i] for i in order]) * 100
    ce = np.array([conc_std[i] for i in order]) * 100

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(14, 5.4),
                                   gridspec_kw={"width_ratios": [1.7, 1]})
    fig.suptitle(f"County-level validation against EAGLE-I — {label}",
                 fontsize=13, weight="bold")

    x = np.arange(len(names)); w = 0.27
    axL.bar(x - w, a, w, label="EAGLE-I actual", color="#111827")
    axL.bar(x, b, w, yerr=be, capsize=2, label="baseline (customers only)", color="#93c5fd")
    axL.bar(x + w, c, w, yerr=ce, capsize=2, label="concentrated (× NCEI)", color="#dc2626")
    axL.set_xticks(x); axL.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    axL.set_ylabel("share of storm's outage impact (%)")
    axL.set_title("Where each method puts the impact\n(counties sorted by real severity →)",
                  fontsize=9)
    axL.legend(fontsize=8)
    axL.grid(axis="y", alpha=0.25)

    # scatter: placement share vs actual share, 45-deg = perfect
    lim = max(a.max(), b.max(), c.max()) * 1.1
    axR.plot([0, lim], [0, lim], "--", color="#9ca3af", lw=1, zorder=0)
    axR.scatter(a, b, s=55, color="#3b82f6", label=f"baseline (r={m_base['pearson']:.2f})",
                edgecolor="#1e3a8a", zorder=3)
    axR.scatter(a, c, s=55, color="#dc2626", label=f"concentrated (r={m_conc['pearson']:.2f})",
                edgecolor="#7f1d1d", zorder=3)
    for i, nm in enumerate(names):
        axR.annotate(nm, (a[i], c[i]), fontsize=6.5, xytext=(3, 3),
                     textcoords="offset points", color="#7f1d1d")
    axR.set_xlabel("EAGLE-I actual county share (%)")
    axR.set_ylabel("placement county share (%)")
    axR.set_title("Closer to the 45° line = better match", fontsize=9)
    axR.legend(fontsize=8, loc="upper left")
    axR.grid(alpha=0.25)
    axR.set_xlim(0, lim); axR.set_ylim(0, lim)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"county_validation_{storm}.png"
    fig.savefig(out, dpi=120, facecolor="white")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
