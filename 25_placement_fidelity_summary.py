"""
25_placement_fidelity_summary.py -- The cross-storm finding from the county
validation (24_): WHEN does public-report-based outage placement reproduce a
storm's real county footprint, and when does it fail?

24_validate_placement_vs_eaglei.py scores one storm at a time against EAGLE-I.
Run over the two CT storms that have BOTH NCEI point reports and a clear
county-level EAGLE-I signal, it produces a clean, opposite pair of results:

    May 2018 macroburst/tornadoes (western CT, 58 NCEI reports):
        concentrated placement r = 0.96  -- near-perfect county match
    Oct 2020 serial derecho     (rural NE CT, 14 NCEI reports):
        concentrated placement r = -0.03 -- no better than chance

The mechanism is the same in both: NCEI Storm Events reports are filed where
damage is OBSERVED, which is population-biased. When a storm hits the populated,
well-surveyed southwest, the report network densely samples the damage and the
placement is faithful. When a storm tracks the rural, forested northeast, the
network under-samples it (2 of 14 reports in the two hardest-hit counties) and
the placement misses -- even though EAGLE-I shows those rural counties took ~47%
of the outages.

So "concentrated placement" is not simply right or wrong: its spatial fidelity
is GOVERNED BY the storm-report network's coverage of the damage area, which is
itself population-biased. This quantifies and bounds ORNL's qualitative claim
that reconstructing outage detail from public data "is not possible" -- it is
possible where the public report network covers the damage, and fails where it
does not, and the boundary is measurable.

This module reuses 24_'s validated scoring functions (no reimplementation),
runs both storms, prints a cross-storm table, and emits one summary figure plus
a markdown finding.

Usage:
    python 25_placement_fidelity_summary.py
"""
from __future__ import annotations
import importlib.util
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
OUT_DIR = HERE / "output"

# Storms with BOTH NCEI reports and a clear county-level EAGLE-I signal.
# (A tornado like "sep2019" is excluded: it is sub-county, so it produces no
# county-scale EAGLE-I signal to validate against -- itself a finding, see 24_.)
SUMMARY_STORMS = ["may2018", "oct2020"]


def _load(numeric_stem):
    spec = importlib.util.spec_from_file_location(
        numeric_stem.replace(".py", "").replace("_", ""), HERE / numeric_stem)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_storm(V, p23, storm, sigma_km=12.0, n=3000, seeds=40):
    """Reuse 24_'s functions to score one storm; return everything needed to
    plot + report."""
    year, t0, t1 = V.STORM_WINDOWS[storm]
    date_str, label = p23.STORMS[storm]

    lat, lon, pop, cty = V.load_tracts_with_county()
    code = {c: i for i, c in enumerate(V.COUNTIES)}
    county_codes = np.array([code[c] for c in cty])

    reports = p23.load_reports(date_str)
    actual = V.eaglei_county_peak(year, t0, t1)
    actual_share = actual / actual.sum()
    top3_idx = np.argsort(actual_share)[-3:]

    base_share, base_std = V.county_share(pop.copy(), county_codes, len(V.COUNTIES), n, seeds)
    w_conc = p23.concentrated_weights(lat, lon, pop, reports, sigma_km)
    conc_share, conc_std = V.county_share(w_conc, county_codes, len(V.COUNTIES), n, seeds)

    return {
        "storm": storm, "label": label, "n_reports": len(reports),
        "actual": actual_share, "base": base_share, "base_std": base_std,
        "conc": conc_share, "conc_std": conc_std, "top3_idx": top3_idx,
        "m_base": V._metrics(base_share, actual_share, top3_idx),
        "m_conc": V._metrics(conc_share, actual_share, top3_idx),
    }


def print_table(V, results):
    print(f"\n{'='*78}")
    print("PLACEMENT FIDELITY vs EAGLE-I county footprint -- cross-storm summary")
    print(f"{'='*78}")
    hdr = f"{'storm':26}{'NCEI':>6}{'baseline r':>12}{'concentr. r':>13}{'top3 base->conc':>18}"
    print(hdr); print("-" * 78)
    for r in results:
        top3 = f"{r['m_base']['top3']:.0f}%->{r['m_conc']['top3']:.0f}%"
        print(f"{r['label'][:25]:26}{r['n_reports']:>6}"
              f"{r['m_base']['pearson']:>12.2f}{r['m_conc']['pearson']:>13.2f}{top3:>18}")
    print("-" * 78)
    print("Reading: dense report coverage (May 2018, 58 reports over the affected SW)")
    print("  -> concentrated placement nails the footprint (r 0.67 -> 0.96).")
    print("Sparse/biased coverage (Oct 2020, 14 reports, rural NE under-reported)")
    print("  -> no public covariate reproduces it (r ~ 0); footprint is track-driven.")


def make_summary_plot(V, results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(results), figsize=(7.2 * len(results), 5.2))
    if len(results) == 1:
        axes = [axes]
    fig.suptitle("Public-report outage placement vs EAGLE-I: fidelity tracks report coverage",
                 fontsize=13, weight="bold")

    for ax, r in zip(axes, results):
        order = list(reversed(np.argsort(r["actual"])))
        names = [V.COUNTIES[i] for i in order]
        a = np.array([r["actual"][i] for i in order]) * 100
        b = np.array([r["base"][i] for i in order]) * 100
        c = np.array([r["conc"][i] for i in order]) * 100
        be = np.array([r["base_std"][i] for i in order]) * 100
        ce = np.array([r["conc_std"][i] for i in order]) * 100
        x = np.arange(len(names)); w = 0.27
        ax.bar(x - w, a, w, label="EAGLE-I actual", color="#111827")
        ax.bar(x, b, w, yerr=be, capsize=2, label="baseline (pop only)", color="#93c5fd")
        ax.bar(x + w, c, w, yerr=ce, capsize=2, label="concentrated (× NCEI)", color="#dc2626")
        ax.set_xticks(x); ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel("share of storm's outage impact (%)")
        verdict = ("MATCH" if r["m_conc"]["pearson"] > 0.5 else "MISS")
        ax.set_title(f"{r['label']}\n{r['n_reports']} NCEI reports  |  "
                     f"concentrated r = {r['m_conc']['pearson']:.2f}  [{verdict}]",
                     fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.25)

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "placement_fidelity_summary.png"
    fig.savefig(out, dpi=120, facecolor="white")
    print(f"\nWrote {out}")
    return out


def write_finding(V, results):
    r_may = next(r for r in results if r["storm"] == "may2018")
    r_oct = next(r for r in results if r["storm"] == "oct2020")
    md = f"""# Finding: when public storm-report data reproduces the county-level outage footprint

**One line.** Placing storm outages by proximity to public NCEI storm-event
reports reproduces a storm's real county-level footprint *only when the report
network densely samples the damage area* — which, because reports are filed
where damage is observed, is population-biased. Rural-tracking storms are
systematically mis-placed.

## What was tested

For each storm we compare three per-county distributions over Connecticut's 8
counties:

- **EAGLE-I actual** — ORNL's county-resolution customers-out record (the
  utilities' own outage-map archive), peak during the storm window. Independent
  ground truth; neither placement ever sees it.
- **Baseline placement** — outages weighted by customer/population exposure only
  (what the production model effectively does; spreads across the SW corridor).
- **Concentrated placement** — outages weighted by population × proximity to real
  NCEI wind/tornado reports (`23_concentrated_placement.py`).

Scored with Pearson r, Spearman ρ, total-variation distance, and top-3 capture
(`24_validate_placement_vs_eaglei.py`, 3000 outages × 40 Monte-Carlo seeds).

## Result

| Storm | NCEI reports | baseline r | concentrated r | top-3 capture (base→conc) |
|---|---:|---:|---:|---:|
| May 2018 macroburst/tornadoes (western CT) | {r_may['n_reports']} | {r_may['m_base']['pearson']:.2f} | **{r_may['m_conc']['pearson']:.2f}** | {r_may['m_base']['top3']:.0f}% → {r_may['m_conc']['top3']:.0f}% |
| Oct 2020 serial derecho (rural NE CT) | {r_oct['n_reports']} | {r_oct['m_base']['pearson']:.2f} | {r_oct['m_conc']['pearson']:.2f} | {r_oct['m_base']['top3']:.0f}% → {r_oct['m_conc']['top3']:.0f}% |

**May 2018** hit the populated, well-surveyed southwest. 58 reports densely
covered the damage; concentrated placement reproduced the footprint almost
perfectly (r = {r_may['m_conc']['pearson']:.2f}) and moved outages off Hartford
(baseline 25% → actual 3%) onto New Haven/Fairfield.

**Oct 2020** tracked the rural, forested northeast. EAGLE-I shows Windham +
Tolland took ~47% of the state's outages, but only 2 of 14 NCEI reports were
filed there. Every public covariate — population, tree canopy (near-uniform at
county scale, 34–52%), NCEI proximity, and their product — scored r ≈ 0. The
footprint was set by the storm's mesoscale track, which the population-biased
report network fails to sample.

## Why this matters (and why it is honest, not a win-claim)

- It is **not** "our placement is better." On a broad rural storm the
  concentrated placement is *no better than chance*, and slightly worse than the
  naive baseline.
- It **is** a characterized limit: public-report placement fidelity is governed
  by report-network coverage of the damage, and that coverage is
  population-biased. This is a testable, quantified refinement of ORNL's
  qualitative "not possible from public data" statement.
- **County resolution cannot validate localized storms.** A single tornado
  (e.g. Sep 2019) is sub-county and produces no county-scale EAGLE-I signal at
  all — so the storms where concentrated placement helps most are exactly the
  ones county data can validate least. Sub-county validation needs
  non-public (utility) outage data.

## Caveats / what a publishable version needs

- Only 2 storms with both data sources locally; a real study needs N storms
  across types (convective, tropical/coastal, winter, tornado) and ideally
  several utilities/states.
- County resolution (8 units) is coarse; the interesting fidelity question is
  sub-county (feeder/town), which requires utility records.
- NCEI report wind values are estimated/measured inconsistently; the kernel
  bandwidth (σ = 12 km) was not tuned per storm.

_Artifacts: `output/placement_fidelity_summary.png`,
`output/county_validation_may2018.png`, `output/county_validation_oct2020.png`.
Generated by `25_placement_fidelity_summary.py` over
`24_validate_placement_vs_eaglei.py`._
"""
    out = HERE / "PLACEMENT_FIDELITY_FINDING.md"
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out}")


def main():
    V = _load("24_validate_placement_vs_eaglei.py")
    p23 = V._load_23()
    results = [run_storm(V, p23, s) for s in SUMMARY_STORMS]
    print_table(V, results)
    make_summary_plot(V, results)
    write_finding(V, results)


if __name__ == "__main__":
    main()
