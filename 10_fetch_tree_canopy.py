"""
10_fetch_tree_canopy.py — Compute REAL mean tree-canopy percentage within a 1 km
buffer of every Connecticut substation, from the live USGS/MRLC NLCD 2021 Tree
Canopy Cover WMS (CONUS, 30 m resolution).

Unlike the original hand-populated NLCD_CANOPY_BY_SUBSTATION dict in
03_grid_simulation.html (49 Hartford-only entries, honestly disclosed in
DATA_SOURCES.md as "pre-computed means, not live raster queries"), this pulls a
small raster clip per substation directly from MRLC's GeoServer and averages the
real pixel values -- a genuine automated buffer-mean, not a manual estimate.

Method:
  For each substation, request a WMS GetMap in FORMAT=image/geotiff8 (a
  single-band, unstyled raster -- confirmed by cross-checking against
  GetFeatureInfo at known points: dense forest -> 88, downtown Hartford -> 0,
  a substation's exact clearing -> 0) covering a real 2km x 2km box centered on
  the substation (1000 m in each direction, converted to degrees per-substation
  using its own latitude for the longitude scale). Decode locally with PIL,
  mask to the actual 1 km-radius circle, and average the valid (0-100) pixels.

Source: USGS MRLC, mrlc.gov/data/nlcd-2021-usgs-tree-canopy-cover-conus
        WMS layer mrlc_display:NLCD_Canopy

Keyed by rounded "lat,lon" rather than substation name: HIFLD's NAME field is not
unique (e.g. 5 distinct physical substations are all literally named "Bridgeport
substation" at different coordinates), so a name-keyed dict would silently collapse
duplicates and drop most of the records.

Writes:
    data/connecticut_tree_canopy.json          {"lat,lon": canopy_pct}
    data/connecticut_tree_canopy.js            window.CONNECTICUT_TREE_CANOPY = {...}

Usage:
    python 10_fetch_tree_canopy.py
"""
from __future__ import annotations
import io
import json
import math
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
SUBSTATIONS_FILE = HERE / "data" / "connecticut_substations.json"
OUT_JSON = HERE / "data" / "connecticut_tree_canopy.json"
OUT_JS = HERE / "data" / "connecticut_tree_canopy.js"

WMS = "https://www.mrlc.gov/geoserver/mrlc_display/wms"
UA = {"User-Agent": "connecticut-grid-resilience/1.0"}

BUFFER_M = 1000.0     # 1 km buffer radius, matches DATA_SOURCES.md's documented methodology
PIXELS = 67           # ~30 m/pixel across a 2 km box, matching NLCD's native resolution
WORKERS = 8


def _canopy_mean(lat: float, lon: float) -> float | None:
    d_lat = BUFFER_M / 111_320.0
    d_lon = BUFFER_M / (111_320.0 * math.cos(math.radians(lat)))
    bbox = f"{lon - d_lon},{lat - d_lat},{lon + d_lon},{lat + d_lat}"
    params = {
        "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
        "LAYERS": "NLCD_Canopy", "BBOX": bbox,
        "WIDTH": str(PIXELS), "HEIGHT": str(PIXELS), "SRS": "EPSG:4326",
        "FORMAT": "image/geotiff8", "STYLES": "",
    }
    url = WMS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    arr = np.array(Image.open(io.BytesIO(data)))

    h, w = arr.shape
    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = (h - 1) / 2, (w - 1) / 2
    r_px = min(h, w) / 2
    circle = (yy - cy) ** 2 + (xx - cx) ** 2 <= r_px ** 2
    valid = circle & (arr <= 100)  # NLCD TCC uses values >100 for water/no-data
    if not valid.any():
        return None
    return round(float(arr[valid].mean()), 1)


def main() -> None:
    subs = json.loads(SUBSTATIONS_FILE.read_text())
    print(f"Computing 1km-buffer NLCD tree canopy for {len(subs)} substations...")

    results: dict[str, float] = {}
    failed = []

    def key_of(s):
        return f"{s['lat']:.6f},{s['lon']:.6f}"

    def work(s):
        return key_of(s), _canopy_mean(s["lat"], s["lon"])

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(work, s): s["name"] for s in subs}
        done = 0
        for fut in as_completed(futures):
            label = futures[fut]
            done += 1
            try:
                key, pct = fut.result()
                if pct is None:
                    failed.append(label)
                else:
                    results[key] = pct
            except Exception as e:
                failed.append(label)
                print(f"  [{done}/{len(subs)}] FAILED {label}: {e}")
            if done % 50 == 0:
                print(f"  [{done}/{len(subs)}] done")

    if failed:
        print(f"\n{len(failed)} substations had no valid canopy data: {failed}")

    OUT_JSON.write_text(json.dumps(results, indent=2, sort_keys=True))
    OUT_JS.write_text(
        "// Connecticut per-substation mean tree-canopy percentage within a 1km buffer,\n"
        "// live-computed from the USGS/MRLC NLCD 2021 Tree Canopy Cover WMS.\n"
        "// Source: 10_fetch_tree_canopy.py\n\n"
        "window.CONNECTICUT_TREE_CANOPY = " + json.dumps(results, sort_keys=True) + ";\n"
    )
    vals = list(results.values())
    print(f"\nWrote {len(results)} canopy values "
          f"(min={min(vals)}, max={max(vals)}, mean={sum(vals)/len(vals):.1f})")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_JS}")


if __name__ == "__main__":
    main()
