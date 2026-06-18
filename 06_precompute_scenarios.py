"""
06_precompute_scenarios.py — Pre-compute canonical scenarios for instant loading.

For each named scenario, runs the full simulation pipeline (substations,
feeders, laterals, storm, restoration) and saves the result as a single
self-contained JSON file in scenarios/. The interactive can then load any
scenario instantly (no in-browser computation), giving the user a "preset"
dropdown that bypasses the multi-second compute path.

This is Alternative #2 from the performance discussion: a curated scenario
library that handles the common cases at zero compute cost.

Run:
    python 06_precompute_scenarios.py

Output:
    scenarios/quiet_day_realistic.json
    scenarios/thunderstorm_realistic.json
    ...

Each JSON contains everything the interactive needs to render the scenario:
substations, feeders, laterals, outages, and the full restoration plan.

Reuses the algorithms ported in 05_generate_artifacts.py.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# Import the simulation functions from 05_generate_artifacts.py.
# We re-use the exact algorithms so presets match what the live scheduler
# would produce.
import importlib.util
spec = importlib.util.spec_from_file_location("art", Path(__file__).parent / "05_generate_artifacts.py")
art = importlib.util.module_from_spec(spec)
spec.loader.exec_module(art)


SCENARIOS_DIR = Path(__file__).parent / "scenarios"
SCENARIOS_DIR.mkdir(exist_ok=True)


# The fixed grid parameters every preset shares. Keeping these constant means
# the substations + feeders + laterals are identical across scenarios; only
# the storm and restoration vary. This makes A/B comparison meaningful — the
# user can pick "thunderstorm under-staffed" vs "thunderstorm well-staffed"
# and see exactly what the extra crews buy them.
SEED = 42
K_SUBSTATIONS = 100
FEEDERS_PER_SUB = 5


# 12 canonical scenarios spanning the parameter space the user will care about.
# Each one has a short name (used as filename) and a friendly label (shown in
# the dropdown). Storm sizes match real Eversource event categories.
SCENARIOS = [
    # name                          label                                      outages   crews  realistic
    ("quiet_day_realistic",         "Quiet day · 100 outages · 5 crews",            100,     5,  True),
    ("thunderstorm_realistic",      "Thunderstorm · 500 outages · 10 crews",        500,    10,  True),
    ("thunderstorm_well_staffed",   "Thunderstorm · 500 outages · 50 crews",        500,    50,  True),
    ("major_storm_understaffed",    "Major storm · 2,000 outages · 20 crews",      2000,    20,  True),
    ("major_storm_well_staffed",    "Major storm · 2,000 outages · 100 crews",     2000,   100,  True),
    ("tropical_storm",              "Tropical storm · 5,000 outages · 200 crews",  5000,   200,  True),
    ("sandy_scale",                 "Sandy-scale · 10,000 outages · 500 crews",   10000,   500,  True),
    ("sandy_scale_all_hands",       "Sandy-scale · 10,000 outages · 1,000 crews", 10000,  1000,  True),
    ("worst_case",                  "Worst case · 25,000 outages · 1,000 crews",  25000,  1000,  True),
    # Optimistic-baseline comparisons (same storms, but with realistic mode off)
    ("thunderstorm_optimistic",     "Thunderstorm (optimistic) · 500 outages · 10 crews",  500,   10,  False),
    ("major_storm_optimistic",      "Major storm (optimistic) · 2,000 outages · 100 crews", 2000, 100,  False),
    ("sandy_scale_optimistic",      "Sandy-scale (optimistic) · 10,000 outages · 500 crews", 10000, 500, False),
]


def build_grid_once():
    """Substations, feeders, laterals — identical across all scenarios."""
    rnd = art.mulberry32(SEED)
    demand = art.build_demand_points(rnd)
    substations = art.kmeans_simple(demand, K_SUBSTATIONS, rnd)
    feeders, laterals = art.generate_feeders_and_laterals(
        substations, rnd, feeders_per_sub=FEEDERS_PER_SUB
    )
    return substations, feeders, laterals


def serialize_scenario(name, label, outages_count, crews_count, realistic,
                       substations, feeders, laterals):
    """Run the storm + restoration for one scenario and return the JSON-ready dict."""
    # Storm: use a different seed offset (matches the JS scheduler's seed*7919+13 derivation)
    storm_seed = (SEED * 7919 + 13) & 0xFFFFFFFF
    rnd_storm = art.mulberry32(storm_seed)
    outages = art.simulate_storm(feeders, laterals, outages_count, rnd_storm)

    # Plan restoration. realistic=True applies the seven-factor scheduler.
    rnd_plan = art.mulberry32((SEED * 31 + 99) & 0xFFFFFFFF)
    crews, total_time, timeline = art.plan_restoration(
        outages, crews_count, rnd_plan, realistic=realistic
    )

    # Estimate customers affected. art.simulate_storm returns just lat/lon
    # tuples; population impact is computed from the segment's customer share.
    # For preset purposes we estimate from the total county population × fraction
    # of segments hit. This is an approximation since we don't track per-outage
    # popLoss in the Python port, but good enough for the preset display.
    TOTAL_POP = 939773
    SECTIONALIZER_FACTOR = 0.5 if realistic else 1.0
    total_cust_affected = min(
        TOTAL_POP,
        int(outages_count * (TOTAL_POP / sum(len(f["pts"]) for f in feeders))
            * SECTIONALIZER_FACTOR)
    )

    return {
        "name": name,
        "label": label,
        "params": {
            "k_substations": K_SUBSTATIONS,
            "feeders_per_sub": FEEDERS_PER_SUB,
            "outages": outages_count,
            "crews": crews_count,
            "seed": SEED,
            "realistic": realistic,
        },
        "substations": [
            {"lat": round(la, 5), "lon": round(lo, 5)} for la, lo in substations
        ],
        "feeders": [
            {
                "subIdx": f["subIdx"],
                "color": f["color"],
                "pts": [[round(p[0], 5), round(p[1], 5)] for p in f["pts"]],
            }
            for f in feeders
        ],
        "laterals": [
            {
                "feederIdx": l["feederIdx"],
                "pts": [[round(p[0], 5), round(p[1], 5)] for p in l["pts"]],
            }
            for l in laterals
        ],
        "outages": [
            {"lat": round(o[0], 5), "lon": round(o[1], 5)} for o in outages
        ],
        "total_customers_affected": total_cust_affected,
        "plan": {
            "total_time_hours": round(total_time, 2),
            "crews": [
                {
                    "depot": {"lat": round(c["depot"][0], 5), "lon": round(c["depot"][1], 5)},
                    "jobs": [
                        {
                            "lat": round(j[0][0], 5),
                            "lon": round(j[0][1], 5),
                            "eta": round(j[1], 2),
                        }
                        for j in c["jobs"]
                    ],
                }
                for c in crews
            ],
        },
    }


def main():
    print("Building base grid (substations + feeders + laterals)…")
    substations, feeders, laterals = build_grid_once()
    print(f"  {len(substations)} substations, {len(feeders)} feeders, {len(laterals)} laterals")

    # Build a small index file the interactive can fetch to populate the dropdown
    # without having to download every scenario JSON up-front.
    index = []

    for name, label, outages_count, crews_count, realistic in SCENARIOS:
        print(f"  -> {name}: {outages_count} outages x {crews_count} crews ({'realistic' if realistic else 'optimistic'})")
        scenario = serialize_scenario(
            name, label, outages_count, crews_count, realistic,
            substations, feeders, laterals
        )
        out_path = SCENARIOS_DIR / f"{name}.json"
        out_path.write_text(json.dumps(scenario, separators=(",", ":")))
        size_kb = out_path.stat().st_size / 1024
        total_h = scenario["plan"]["total_time_hours"]
        index.append({
            "name": name,
            "label": label,
            "size_kb": round(size_kb, 1),
            "total_time_hours": total_h,
        })
        print(f"     wrote {out_path.name}  ({size_kb:.1f} KB, total restoration {total_h:.1f} h)")

    # Write the index
    (SCENARIOS_DIR / "index.json").write_text(json.dumps(index, indent=2))
    print(f"\nWrote scenarios/index.json with {len(index)} scenarios.")


if __name__ == "__main__":
    main()
