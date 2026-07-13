"""
19_validate_against_eaglei.py -- Cross-validate this project's historical
storm dataset (data/hartford_doe_oe417.js) against ORNL's EAGLE-I recorded
outage data (see 18_fetch_eaglei_ct.py for the source and citation).

For each storm window, computes from EAGLE-I's 15-minute county-level data:
  - the real CT-statewide peak customers-without-power (all tracked CT
    utilities combined -- Eversource AND United Illuminating, so peaks are
    expected to be >= this dataset's Eversource-only figures)
  - the restoration duration: hours from storm onset until the statewide
    total first drops below max(baseline*2, 5% of peak), where baseline is
    the median statewide total over the 3 days BEFORE the storm window
    (blue-sky background noise -- CT always has a few hundred customers out).

Usage:
    python 19_validate_against_eaglei.py --year 2020
    (requires data/eaglei_ct_<year>.csv from 18_fetch_eaglei_ct.py)
"""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent

# (label, storm onset UTC, search window end, this dataset's entry for comparison)
# Onsets are the storm's local arrival converted to UTC (EDT = UTC-4).
STORM_WINDOWS = {
    2020: [
        ("Isaias 2020",        "2020-08-04 16:00", "2020-08-18 00:00", {"customers": 632632, "duration_h": 264, "note": "Eversource-only peak in dataset"}),
        ("Aug 2020 Tornado",   "2020-08-27 19:00", "2020-09-02 00:00", {"customers": 54000,  "duration_h": 96,  "note": "ES ~25k + UI ~29k combined in dataset"}),
        ("Oct 2020 Derecho",   "2020-10-07 20:00", "2020-10-13 00:00", {"customers": 90000,  "duration_h": 96,  "note": "LOWER-CONFIDENCE regional-comparison estimate"}),
    ],
    2021: [
        ("Henri 2021",         "2021-08-22 14:00", "2021-08-26 00:00", {"customers": 23000,  "duration_h": 48,  "note": ""}),
        ("Ida remnants 2021",  "2021-09-01 20:00", "2021-09-05 00:00", {"customers": 20000,  "duration_h": 48,  "note": "duration interpolated from Henri"}),
    ],
    2022: [
        ("Dec 2022 Windstorm", "2022-12-23 00:00", "2022-12-28 00:00", {"customers": 120000, "duration_h": 72,  "note": "99%-restored milestone in dataset"}),
    ],
}


def load_statewide_series(year: int) -> dict[datetime, int]:
    path = HERE / "data" / f"eaglei_ct_{year}.csv"
    series: dict[datetime, int] = defaultdict(int)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = datetime.strptime(row["run_start_time"], "%Y-%m-%d %H:%M:%S")
            try:
                # Actual column name in the published files is customers_out
                # (the Scientific Data paper's schema table calls it "sum").
                series[t] += int(float(row["customers_out"] or 0))
            except ValueError:
                continue
    return dict(series)


def analyze(series: dict[datetime, int], label: str, onset_s: str, end_s: str, ref: dict) -> None:
    onset = datetime.strptime(onset_s, "%Y-%m-%d %H:%M")
    end = datetime.strptime(end_s, "%Y-%m-%d %H:%M")

    pre = [v for t, v in series.items() if onset - timedelta(days=3) <= t < onset]
    pre.sort()
    baseline = pre[len(pre)//2] if pre else 0

    window = {t: v for t, v in series.items() if onset <= t <= end}
    if not window:
        print(f"{label}: NO EAGLE-I DATA in window")
        return
    peak_t = max(window, key=window.get)
    peak = window[peak_t]

    def time_to(threshold: float) -> float | None:
        for t in sorted(window):
            if t > peak_t and window[t] <= threshold:
                return (t - onset).total_seconds() / 3600
        return None

    # Two endpoints, because "restored" is ambiguous:
    #  - bulk: 95% of peak load restored (media/utility "substantially
    #    complete" language tends to track this)
    #  - full: back to within 2x the blue-sky baseline (last-customer tail,
    #    which is what this dataset's duration_h and the model's totalTime
    #    both represent)
    bulk_h = time_to(peak * 0.05)
    full_h = time_to(max(baseline * 2, 500))

    print(f"\n=== {label} ===")
    print(f"  pre-storm baseline (median, 3 days prior): {baseline:,} customers out")
    print(f"  EAGLE-I CT peak: {peak:,} customers at {peak_t} UTC  (all CT utilities)")
    print(f"  dataset entry:   {ref['customers']:,} customers  ({ref['note'] or 'Eversource-only'})")
    print(f"  EAGLE-I bulk restoration (<=5% of peak still out):  "
          f"{f'{bulk_h:.0f}h' if bulk_h else 'not reached in window'}")
    print(f"  EAGLE-I full restoration (<=max(2x baseline, 500)): "
          f"{f'{full_h:.0f}h' if full_h else 'not reached in window'}")
    print(f"  dataset duration (full-restoration convention): {ref['duration_h']}h")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True, choices=sorted(STORM_WINDOWS))
    args = ap.parse_args()
    series = load_statewide_series(args.year)
    print(f"EAGLE-I CT {args.year}: {len(series):,} 15-min statewide samples")
    for label, onset, end, ref in STORM_WINDOWS[args.year]:
        analyze(series, label, onset, end, ref)


if __name__ == "__main__":
    main()
