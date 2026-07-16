"""
12_fetch_hrrr_storm_wind.py — Prepare statewide HRRR weather for the browser.

Ports the logic from fetch_hrrr_storm_wind.ipynb (originally written for a
notebook/Colab environment) into a plain script, and swaps the Hartford-only
target grid for one covering the real Connecticut state boundary (from
data/connecticut_boundary.json) at roughly HRRR's native ~3km resolution.

Same 5 storms as before (all HRRR-era, i.e. 2014+): Isaias 2020, Henri 2021,
May 2018 tornado/derecho outbreak, January 2024 wind storm, December 2023
nor'easter. Sandy (2012) and Irene (2011) predate the HRRR archive and would
need ERA5 reanalysis instead -- out of scope here, same as the original
notebook.

HRRR uses a Lambert Conformal projection (lat/lon are 2-D arrays), so we clip
to a CT bounding box and use scipy.interpolate.griddata to regrid the scattered
HRRR points onto our regular statewide lat/lon grid.

In addition to the existing representative-hour cache, this script can build a
curated, hourly storm timeline.  The timeline is the single source of weather
values for both the browser visualization and the outage-location model; the
animation must never be generated from a separate approximation.

Writes:
    data/connecticut_storm_wind.js — representative-hour compatibility data
    data/connecticut_storm_timelines.js — curated hourly storm data

Usage:
    python 12_fetch_hrrr_storm_wind.py
    python 12_fetch_hrrr_storm_wind.py --timeline-only --timeline isaias_2020
"""
from __future__ import annotations
import argparse
import json
import warnings
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
OUT_JS = HERE / "data" / "connecticut_storm_wind.js"
TIMELINE_OUT_JS = HERE / "data" / "connecticut_storm_timelines.js"
HRRR_CACHE = HERE / "cache" / "hrrr"

# Statewide CT target grid, ~3km spacing (HRRR's native resolution), with a
# small buffer beyond the real state boundary (lat 40.95-42.05, lon -73.73 to
# -71.79, from data/connecticut_boundary.json).
TARGET_LATS = np.linspace(40.90, 42.10, 41)
TARGET_LONS = np.linspace(-73.80, -71.70, 65)
LON_GRID, LAT_GRID = np.meshgrid(TARGET_LONS, TARGET_LATS)

# HRRR extraction bounding box (statewide CT + buffer for interpolation edge effects)
LAT_MIN, LAT_MAX = 40.5, 42.5
LON_MIN, LON_MAX = -74.3, -71.2

STORMS = {
    "isaias_2020": {"date": "2020-08-04 18:00", "precip_type": "rain"},
    "henri_2021":  {"date": "2021-08-22 14:00", "precip_type": "rain"},
    "may2018":     {"date": "2018-05-15 21:00", "precip_type": "rain"},
    "jan2024":     {"date": "2024-01-10 19:00", "precip_type": "mix"},
    "dec2023":     {"date": "2023-12-18 18:00", "precip_type": "snow"},
    # NWS-confirmed serial derecho, real NCEI storm reports show 52-60kt
    # thunderstorm wind across Fairfield/New Haven/Hartford/Tolland/Windham
    # counties between 16:30-17:05 EDT (20:30-21:05 UTC) -- using 21:00 UTC
    # (~5pm EDT) as the representative HRRR fetch time, same convention as
    # the other storms above (peak-passage hour, not storm start).
    "oct2020_derecho": {"date": "2020-10-07 21:00", "precip_type": "rain"},
    # July 4, 2026 severe thunderstorm complex -- the storm hit western CT
    # ~8pm EDT (00:00 UTC 7/5) with reported gusts to ~80mph; peak convective
    # window that evening. HRRR is available in near-real-time from the AWS
    # archive, so unlike the older synthetic-track July 2026 entry this pulls
    # the REAL measured wind/rain footprint for the event.
    "july2026":    {"date": "2026-07-05 00:00", "precip_type": "rain"},
    # Dec 2022 Pre-Christmas Windstorm -- broad rain/windstorm, EAGLE-I CT peak
    # at 2022-12-23 14:00 UTC (~9am EST). Added for the crew back-out so this
    # real-disclosed-crew storm (1,100+ crews) uses the same wind-weighted
    # placement as its size-peer Dec 2023, rather than uniform.
    "dec2022":     {"date": "2022-12-23 14:00", "precip_type": "rain"},
}
STORM_NAMES = {
    "isaias_2020": "Tropical Storm Isaias",
    "henri_2021":  "Tropical Storm Henri",
    "may2018":     "May 2018 Tornadoes / Derecho",
    "jan2024":     "January 2024 Wind Storm",
    "dec2023":     "December 2023 Nor'easter",
    "oct2020_derecho": "October 2020 Northeast Serial Derecho",
    "july2026":    "July 4 2026 Severe Thunderstorm Complex",
    "dec2022":     "December 2022 Pre-Christmas Windstorm",
}

# Deliberately curated rather than accepting arbitrary dates.  A storm should
# be added here only after its time window and generated frames have been
# reviewed.  Isaias is the Phase 1 reference event.  The 24-hour interval
# covers the Connecticut approach, damaging passage, and departure.
CURATED_TIMELINES = {
    "isaias_2020": {
        "name": "Tropical Storm Isaias",
        "start": "2020-08-04 06:00",
        "end": "2020-08-05 05:00",
        "precip_type": "rain",
        "timezone_note": "UTC (02:00 Aug 4 through 01:00 Aug 5 EDT)",
    },
}

TIMELINE_SCHEMA_VERSION = 1
ANTECEDENT_RAIN_HOURS = 6


def _first_var(ds):
    skip = {
        "latitude", "longitude", "valid_time", "step", "time",
        "surface", "heightAboveGround", "depthBelowLandLayer", "level",
    }
    return next(v for v in ds.data_vars if v not in skip)


def extract_to_grid(ds):
    from scipy.interpolate import griddata
    lats_2d = ds.latitude.values
    lons_2d = ds.longitude.values
    values = np.squeeze(ds[_first_var(ds)].values)
    lons_neg = np.where(lons_2d > 180, lons_2d - 360, lons_2d)
    mask = (
        (lats_2d >= LAT_MIN) & (lats_2d <= LAT_MAX) &
        (lons_neg >= LON_MIN) & (lons_neg <= LON_MAX)
    )
    return griddata(
        (lons_neg[mask], lats_2d[mask]),
        values[mask],
        (LON_GRID, LAT_GRID),
        method="linear",
    )


def _hrrr(date_str, fxx):
    """Create a Herbie request whose downloaded subsets stay inside the repo."""
    from herbie import Herbie

    HRRR_CACHE.mkdir(parents=True, exist_ok=True)
    return Herbie(
        date_str,
        model="hrrr",
        product="sfc",
        fxx=fxx,
        save_dir=HRRR_CACHE,
        verbose=False,
    )


def _parse_utc(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def _hour_range(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(hours=1)


def _hrrr_time(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


def _iso_utc(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validated_grid(values, label):
    values = np.asarray(values, dtype=float)
    if values.shape != LAT_GRID.shape:
        raise ValueError(f"{label} has shape {values.shape}; expected {LAT_GRID.shape}")
    if not np.isfinite(values).all():
        count = int(values.size - np.isfinite(values).sum())
        raise ValueError(f"{label} contains {count} non-finite grid cells")
    return values


def _flat_rounded(values, decimals):
    return np.round(values, decimals).reshape(-1).tolist()


def _grid_summary(wind_mph, rain_1h_in, rain_6h_in):
    peak_index = np.unravel_index(int(np.argmax(wind_mph)), wind_mph.shape)
    return {
        "mean_wind_mph": round(float(np.mean(wind_mph)), 1),
        "max_wind_mph": round(float(np.max(wind_mph)), 1),
        "max_wind_lat": round(float(TARGET_LATS[peak_index[0]]), 5),
        "max_wind_lon": round(float(TARGET_LONS[peak_index[1]]), 5),
        "mean_rain_1h_in": round(float(np.mean(rain_1h_in)), 3),
        "max_rain_1h_in": round(float(np.max(rain_1h_in)), 3),
        "mean_rain_6h_in": round(float(np.mean(rain_6h_in)), 3),
        "max_rain_6h_in": round(float(np.max(rain_6h_in)), 3),
    }


def fetch_wind_grid(valid_time):
    """Fetch HRRR analysis gusts valid at ``valid_time``."""
    hrrr = _hrrr(_hrrr_time(valid_time), fxx=0)
    values = extract_to_grid(hrrr.xarray("GUST:surface")) * 2.23694
    return _validated_grid(values, f"wind at {_iso_utc(valid_time)}")


def fetch_rain_grid_ending_at(valid_time):
    """Fetch one-hour APCP whose forecast interval ends at ``valid_time``.

    HRRR f00 has no accumulation period.  Using the f01 field from the cycle
    one hour earlier aligns rain and gusts on the same valid timestamp.
    """
    cycle_time = valid_time - timedelta(hours=1)
    hrrr = _hrrr(_hrrr_time(cycle_time), fxx=1)
    values = extract_to_grid(hrrr.xarray("APCP:surface")) / 25.4
    values = np.maximum(values, 0.0)
    return _validated_grid(values, f"rain ending at {_iso_utc(valid_time)}")


def build_timeline(key, cfg):
    start = _parse_utc(cfg["start"])
    end = _parse_utc(cfg["end"])
    valid_times = list(_hour_range(start, end))
    if not valid_times:
        raise ValueError(f"Timeline {key} has no valid times")

    print(f"\nTimeline {key}: {_iso_utc(start)} through {_iso_utc(end)}")
    print(f"  {len(valid_times)} hourly frames; {ANTECEDENT_RAIN_HOURS}h rain memory")

    # Fetch enough pre-window rain to make the first frame's six-hour total
    # scientifically comparable to every later frame.
    rain_start = start - timedelta(hours=ANTECEDENT_RAIN_HOURS - 1)
    rain_by_time = {}
    for valid_time in _hour_range(rain_start, end):
        print(f"  rain  {_iso_utc(valid_time)}")
        rain_by_time[valid_time] = fetch_rain_grid_ending_at(valid_time)

    frames = []
    rain_window = deque(maxlen=ANTECEDENT_RAIN_HOURS)
    for valid_time in _hour_range(rain_start, end):
        rain_window.append(rain_by_time[valid_time])
        if valid_time < start:
            continue

        print(f"  gust  {_iso_utc(valid_time)}")
        wind_mph = fetch_wind_grid(valid_time)
        rain_1h_in = rain_by_time[valid_time]
        rain_6h_in = np.sum(np.stack(tuple(rain_window)), axis=0)
        frames.append({
            "valid_time": _iso_utc(valid_time),
            "wind_gust_mph": _flat_rounded(wind_mph, 1),
            "rain_1h_in": _flat_rounded(rain_1h_in, 3),
            "rain_6h_in": _flat_rounded(rain_6h_in, 3),
            "summary": _grid_summary(wind_mph, rain_1h_in, rain_6h_in),
        })

    return {
        "storm_id": key,
        "name": cfg["name"],
        "source": "NOAA HRRR via AWS public archive",
        "model": "hrrr",
        "product": "sfc",
        "precip_type": cfg["precip_type"],
        "start_time": _iso_utc(start),
        "end_time": _iso_utc(end),
        "interval_minutes": 60,
        "timezone_note": cfg["timezone_note"],
        "rain_alignment": "rain_1h_in is the f01 APCP interval ending at valid_time",
        "antecedent_rain_hours": ANTECEDENT_RAIN_HOURS,
        "frames": frames,
    }


def write_timeline_data(key):
    if key not in CURATED_TIMELINES:
        raise KeyError(f"Unknown curated timeline: {key}")
    storm = build_timeline(key, CURATED_TIMELINES[key])
    output = {
        "_populated": True,
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "purpose": "Shared weather source for outage modeling and map animation",
        "grid": {
            "lats": TARGET_LATS.tolist(),
            "lons": TARGET_LONS.tolist(),
            "n_lat": int(len(TARGET_LATS)),
            "n_lon": int(len(TARGET_LONS)),
            "storage": "row-major flat arrays; index = lat_index * n_lon + lon_index",
        },
        "storms": {key: storm},
    }
    header = (
        "// Curated hourly HRRR storm timelines for statewide Connecticut.\n"
        "// Generated by 12_fetch_hrrr_storm_wind.py -- do not hand-edit.\n"
        "// The map and outage model must consume these same frame arrays.\n\n"
    )
    body = "window.CONNECTICUT_STORM_TIMELINES = " + json.dumps(
        output, separators=(",", ":"), allow_nan=False
    ) + ";\n"
    TIMELINE_OUT_JS.write_text(header + body)
    print(f"\nWrote {TIMELINE_OUT_JS} ({len(storm['frames'])} hourly frames)")


def get_storm_data(key, cfg):
    date_str = cfg["date"]
    print(f"\n{key}  ({date_str})")
    rec = {
        "date": date_str[:10],
        "precip_type": cfg["precip_type"],
        "avg_temp_f": None,
        "soil_wetness": None,
        "peak_wind_mph": None,
        "peak_rain_in": None,   # 1h accumulated precip (inches) at the peak hour
    }
    H = _hrrr(date_str, fxx=0)
    # 1-hour accumulated precip (APCP) needs a forecast hour > 0 -- the fxx=0
    # analysis has a zero accumulation window. fxx=1 gives the 1h total ending
    # at date_str+1h, a good "rain footprint" proxy for the peak hour.
    H_apcp = _hrrr(date_str, fxx=1)

    try:
        # GUST:surface, not WIND:10 m above ground -- the sustained 10m wind
        # field badly understates convective/tornadic storms. Verified on
        # May 2018 (confirmed tornado outbreak): WIND topped out at 21mph
        # statewide, while real NCEI storm reports for the same day/event
        # recorded 40-100mph gusts. GUST is HRRR's actual peak-gust field and
        # lines up with that real data (statewide peak ~81mph for this storm).
        ds_w = H.xarray("GUST:surface")
        wind_mph = extract_to_grid(ds_w) * 2.23694
        rec["peak_wind_mph"] = np.round(wind_mph, 1).tolist()
        print(f"  gust  avg={np.nanmean(wind_mph):.1f}  peak={np.nanmax(wind_mph):.1f} mph")
    except Exception as e:
        print(f"  gust  FAILED: {e}")

    try:
        ds_t = H.xarray("TMP:2 m above ground")
        tmp_f = (extract_to_grid(ds_t) - 273.15) * 9 / 5 + 32
        rec["avg_temp_f"] = round(float(np.nanmean(tmp_f)), 1)
        print(f"  temp  avg={rec['avg_temp_f']} F")
    except Exception as e:
        print(f"  temp  FAILED: {e}")

    try:
        ds_p = H_apcp.xarray("APCP:surface")
        rain_in = extract_to_grid(ds_p) / 25.4  # kg/m^2 (mm) -> inches
        rec["peak_rain_in"] = np.round(rain_in, 2).tolist()
        print(f"  rain  avg={np.nanmean(rain_in):.2f}  peak={np.nanmax(rain_in):.2f} in/hr")
    except Exception as e:
        print(f"  rain  FAILED: {e}")

    for pat in ("SOILW:0-0.1 m below ground level", "SOILW:0-0.1 m", "SOILW"):
        try:
            ds_s = H.xarray(pat)
            rec["soil_wetness"] = round(float(np.nanmean(extract_to_grid(ds_s))), 3)
            print(f"  soil  avg={rec['soil_wetness']}")
            break
        except Exception:
            continue
    if rec["soil_wetness"] is None:
        print("  soil  FAILED: no matching GRIB label")

    return rec


def write_snapshot_data():
    n_pts = len(TARGET_LATS) * len(TARGET_LONS)
    print(f"Grid: {len(TARGET_LATS)} lat x {len(TARGET_LONS)} lon = {n_pts} points (statewide CT)")
    print(f"Storms: {list(STORMS.keys())}")

    storm_results = {k: get_storm_data(k, cfg) for k, cfg in STORMS.items()}

    output = {
        "_populated": True,
        "grid": {
            "lats": TARGET_LATS.tolist(),
            "lons": TARGET_LONS.tolist(),
            "n_lat": int(len(TARGET_LATS)),
            "n_lon": int(len(TARGET_LONS)),
            "note": "peak_wind_mph is row-major [n_lat][n_lon]. Bilinear-interpolate to (lat,lon).",
        },
        "storms": {k: {"name": STORM_NAMES[k], **storm_results[k]} for k in STORMS},
    }

    header = (
        "// HRRR wind speed, temperature, soil moisture -- statewide Connecticut.\n"
        "// Generated by 12_fetch_hrrr_storm_wind.py -- do not hand-edit.\n"
        "// Source: NOAA HRRR via AWS archive (herbie-data library).\n\n"
    )
    body = "window.CONNECTICUT_STORM_WIND = " + json.dumps(output) + ";\n"
    OUT_JS.write_text(header + body)

    n_ok = sum(1 for s in output["storms"].values() if s["peak_wind_mph"] is not None)
    print(f"\nWrote {OUT_JS}  ({n_ok}/{len(STORMS)} storms with wind data)")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build Connecticut HRRR snapshot or curated timeline data."
    )
    parser.add_argument(
        "--timeline",
        choices=sorted(CURATED_TIMELINES),
        help="Build the selected curated hourly timeline.",
    )
    parser.add_argument(
        "--timeline-only",
        action="store_true",
        help="Skip rebuilding the existing representative-hour storm cache.",
    )
    args = parser.parse_args()
    if args.timeline_only and not args.timeline:
        parser.error("--timeline-only requires --timeline")
    return args


def main():
    args = parse_args()
    if not args.timeline_only:
        write_snapshot_data()
    if args.timeline:
        write_timeline_data(args.timeline)


if __name__ == "__main__":
    main()
