"""
15_fetch_storm_events.py — Real per-report storm-damage locations for CT storms
that have no HURDAT2 track (not a hurricane) and no HRRR wind grid (too recent,
or otherwise outside the 5 storms 12_fetch_hrrr_storm_wind.py already covers).

Source: NOAA/NCEI Storm Events Database bulk CSV export
(https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/), one gzipped
CSV per year, no login required. Each row is a single NWS-verified storm
report (Thunderstorm Wind, Tornado, Hail, etc.) with its own lat/lon and,
for wind/tornado reports, a magnitude -- exactly the shape the simulator's
existing wind-field-weighted outage placement wants (see simulateStorm() in
03_grid_simulation.html, which already does Gaussian track-decay placement
around HURDAT2 points; this script produces the same {lat, lon, wind_kt}
point shape from real severe-thunderstorm reports instead).

IMPORTANT CAVEAT: NCEI receives final Storm Data ~75-90 days after the end of
a data month (documented at https://www.ncei.noaa.gov/stormevents/faq.jsp).
A storm from earlier this month will NOT be in the bulk file yet -- this
script will simply find 0 matching rows for anything that recent. Re-run it
once the storm is a few months old.

Usage:
    python 15_fetch_storm_events.py --date 2026-07-04 --state CONNECTICUT --out data/connecticut_storm_events_2026-07-04.json
    python 15_fetch_storm_events.py --date 2018-05-15 --state CONNECTICUT --out data/connecticut_storm_events_2018-05-15.json
"""
from __future__ import annotations
import argparse
import csv
import gzip
import io
import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
NCEI_INDEX_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
NCEI_FILE_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/{name}"
UA = {"User-Agent": "Mozilla/5.0"}

# Wind-relevant event types the simulator's Gaussian track-decay placement can use.
WIND_EVENT_TYPES = {"Thunderstorm Wind", "High Wind", "Tornado", "Marine Thunderstorm Wind"}

# Approximate Enhanced Fujita midpoint wind speeds (mph), converted to knots
# (mph / 1.15078), used only when a Tornado report has no MAGNITUDE (NCEI
# doesn't record tornado wind speed directly, only the F/EF-scale rating).
EF_MIDPOINT_KT = {
    "EF0": 65, "EF1": 90, "EF2": 115, "EF3": 140, "EF4": 170, "EF5": 200,
    "F0": 65, "F1": 90, "F2": 115, "F3": 140, "F4": 170, "F5": 200,
}
for _k in list(EF_MIDPOINT_KT):
    EF_MIDPOINT_KT[_k] = round(EF_MIDPOINT_KT[_k] / 1.15078, 1)


def _latest_file_for_year(year: int) -> str:
    req = urllib.request.Request(NCEI_INDEX_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    names = sorted(set(re.findall(rf"StormEvents_details-ftp_v1\.0_d{year}_c\d+\.csv\.gz", html)))
    if not names:
        raise SystemExit(f"No NCEI Storm Events file found for {year} -- check {NCEI_INDEX_URL}")
    return names[-1]  # lexicographically sorted -c<published-date> suffix -> last is newest


def _download_year(year: int, cache_dir: Path) -> list[dict]:
    cache_dir.mkdir(exist_ok=True)
    fname = _latest_file_for_year(year)
    cache_path = cache_dir / fname
    if not cache_path.exists():
        req = urllib.request.Request(NCEI_FILE_URL.format(name=fname), headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r:
            cache_path.write_bytes(r.read())
    text = gzip.decompress(cache_path.read_bytes()).decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _row_wind_kt(row: dict) -> float | None:
    mag = (row.get("MAGNITUDE") or "").strip()
    if mag:
        try:
            return float(mag)
        except ValueError:
            pass
    if row["EVENT_TYPE"] == "Tornado":
        return EF_MIDPOINT_KT.get((row.get("TOR_F_SCALE") or "").strip())
    return None


def fetch_storm_reports(date: str, state: str, window_hours: int = 12, cache_dir: Path | None = None) -> list[dict]:
    """date: 'YYYY-MM-DD'. Returns real NCEI storm reports within +/- window_hours
    of that date for the given state, as {lat, lon, wind_kt, event_type, location, time}."""
    year = int(date[:4])
    cache_dir = cache_dir or (HERE / "data" / "_ncei_cache")
    rows = _download_year(year, cache_dir)
    target_day = date[8:10] + "-" + {
        "01": "JAN", "02": "FEB", "03": "MAR", "04": "APR", "05": "MAY", "06": "JUN",
        "07": "JUL", "08": "AUG", "09": "SEP", "10": "OCT", "11": "NOV", "12": "DEC",
    }[date[5:7]] + "-" + date[2:4]
    out = []
    for row in rows:
        if row.get("STATE", "").upper() != state.upper():
            continue
        if row.get("EVENT_TYPE") not in WIND_EVENT_TYPES:
            continue
        bdt = row.get("BEGIN_DATE_TIME", "")
        if target_day not in bdt:
            continue
        lat, lon = row.get("BEGIN_LAT", ""), row.get("BEGIN_LON", "")
        if not lat or not lon:
            continue
        wind_kt = _row_wind_kt(row)
        if wind_kt is None:
            continue
        out.append({
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "wind_kt": wind_kt,
            "event_type": row["EVENT_TYPE"],
            "location": row.get("BEGIN_LOCATION", ""),
            "county": row.get("CZ_NAME", ""),
            "time": bdt,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Storm date, YYYY-MM-DD")
    ap.add_argument("--state", default="CONNECTICUT")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    reports = fetch_storm_reports(args.date, args.state)
    print(f"Found {len(reports)} real {args.state} storm reports for {args.date}.")
    if not reports:
        print("This is expected if the storm is very recent -- NCEI publishes final "
              "Storm Data ~75-90 days after the end of the data month. Re-run later.")
        return
    for r in reports[:10]:
        print(f"  {r['time']}  {r['event_type']:<20} {r['wind_kt']:>5.0f} kt  "
              f"({r['lat']}, {r['lon']})  {r['location']}, {r['county']}")
    if len(reports) > 10:
        print(f"  ... and {len(reports) - 10} more")

    out_path = HERE / args.out
    out_path.write_text(json.dumps(reports, indent=1))
    print(f"\nWrote {len(reports)} reports to {out_path}")


if __name__ == "__main__":
    main()
