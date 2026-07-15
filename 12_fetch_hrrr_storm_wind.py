"""
12_fetch_hrrr_storm_wind.py — Densify the HRRR wind/temp/soil-moisture grid from
Hartford-County-only (15x21) to statewide Connecticut (41x65).

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

Writes:
    data/connecticut_storm_wind.js — window.CONNECTICUT_STORM_WIND = {...}

Usage:
    python 12_fetch_hrrr_storm_wind.py
"""
from __future__ import annotations
import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
OUT_JS = HERE / "data" / "connecticut_storm_wind.js"

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
    lons_neg = np.where(lons_2d > 180, lons_2d - 360, lons_2d)
    mask = (
        (lats_2d >= LAT_MIN) & (lats_2d <= LAT_MAX) &
        (lons_neg >= LON_MIN) & (lons_neg <= LON_MAX)
    )
    return griddata(
        (lons_neg[mask], lats_2d[mask]),
        ds[_first_var(ds)].values[mask],
        (LON_GRID, LAT_GRID),
        method="linear",
    )


def get_storm_data(key, cfg):
    from herbie import Herbie
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
    H = Herbie(date_str, model="hrrr", product="sfc", fxx=0, verbose=False)
    # 1-hour accumulated precip (APCP) needs a forecast hour > 0 -- the fxx=0
    # analysis has a zero accumulation window. fxx=1 gives the 1h total ending
    # at date_str+1h, a good "rain footprint" proxy for the peak hour.
    H_apcp = Herbie(date_str, model="hrrr", product="sfc", fxx=1, verbose=False)

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


def main():
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


if __name__ == "__main__":
    main()
