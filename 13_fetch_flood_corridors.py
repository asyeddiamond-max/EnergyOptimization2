"""
13_fetch_flood_corridors.py — Real flood-prone river corridors for the other 7
Connecticut counties (Hartford County already has 5: Connecticut, Park,
Hockanum, Farmington rivers, Salmon Brook).

Unlike the original 5 Hartford corridors (a handful of manually-placed
centerline points each), this pulls real river geometry from the USGS
National Hydrography Dataset (NHD) "Flowline - Small Scale" ArcGIS layer,
which represents each named river as many short connected reaches. We fetch
every reach matching a river's GNIS name, stitch them end-to-end into
continuous paths (rivers can split into more than one component -- we keep
the longest), then simplify to a manageable point count.

Source: USGS National Map, hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/4
        (NHD Flowline - Small Scale, attribute GNIS_NAME)

12 major named rivers covering the other 7 counties:
    Housatonic, Naugatuck, Quinnipiac, Norwalk, Shepaug  (Fairfield/Litchfield/New Haven)
    Salmon River                                          (Middlesex; distinct from Hartford's Salmon Brook)
    Thames, Yantic, Shetucket, Quinebaug, Willimantic, Natchaug  (New London/Tolland/Windham)

Writes:
    data/connecticut_flood_corridors.json / .js
        window.CONNECTICUT_FLOOD_CORRIDORS_EXTRA = [{name, pts:[[lat,lon],...]}, ...]
    (03_grid_simulation.html merges this with the existing 5 Hartford corridors
    into one FLOOD_CORRIDORS array.)

Usage:
    python 13_fetch_flood_corridors.py
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
OUT_JSON = HERE / "data" / "connecticut_flood_corridors.json"
OUT_JS = HERE / "data" / "connecticut_flood_corridors.js"

NHD_URL = "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/4/query"
UA = {"User-Agent": "connecticut-grid-resilience/1.0"}

# CT statewide bbox + small buffer, so we only pull CT-relevant reaches even
# for rivers (like the Housatonic) whose full length extends into MA/NY.
CT_BBOX = {"xmin": -73.9, "ymin": 40.9, "xmax": -71.7, "ymax": 42.15, "spatialReference": {"wkid": 4326}}

RIVERS = [
    "Housatonic River", "Naugatuck River", "Quinnipiac River", "Norwalk River",
    "Shepaug River", "Salmon River", "Thames River", "Yantic River",
    "Shetucket River", "Quinebaug River", "Willimantic River", "Natchaug River",
]

SNAP_TOL = 0.0006  # ~50-60m, endpoint-matching tolerance for stitching reaches
SIMPLIFY_MAX_PTS = 18


def fetch_reaches(name: str) -> list[list[list[float]]]:
    params = {
        "where": f"gnis_name='{name}'",
        "geometry": json.dumps(CT_BBOX),
        "geometryType": "esriGeometryEnvelope", "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
        "outFields": "gnis_name", "returnGeometry": "true", "outSR": "4326", "f": "json",
        "geometryPrecision": "5",
    }
    url = NHD_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    if "error" in d:
        raise RuntimeError(f"{name}: {d['error']}")
    paths = []
    for f in d.get("features", []):
        geo = f.get("geometry")
        if geo and geo.get("paths"):
            for p in geo["paths"]:
                if len(p) >= 2:
                    paths.append([[pt[1], pt[0]] for pt in p])  # -> [lat, lon]
    return paths


def _close(a, b, tol=SNAP_TOL):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def stitch(paths: list[list[list[float]]]) -> list[list[float]]:
    """Chain reach segments end-to-end into the longest connected path."""
    remaining = [list(p) for p in paths]
    best_chain: list[list[float]] = []

    while remaining:
        chain = remaining.pop(0)
        grown = True
        while grown:
            grown = False
            for i, seg in enumerate(remaining):
                if _close(chain[-1], seg[0]):
                    chain = chain + seg[1:]
                    remaining.pop(i); grown = True; break
                if _close(chain[-1], seg[-1]):
                    chain = chain + list(reversed(seg))[1:]
                    remaining.pop(i); grown = True; break
                if _close(chain[0], seg[-1]):
                    chain = seg[:-1] + chain
                    remaining.pop(i); grown = True; break
                if _close(chain[0], seg[0]):
                    chain = list(reversed(seg))[:-1] + chain
                    remaining.pop(i); grown = True; break
        if len(chain) > len(best_chain):
            best_chain = chain

    return best_chain


def simplify(path: list[list[float]], max_pts: int) -> list[list[float]]:
    if len(path) <= max_pts:
        return path
    step = len(path) / max_pts
    idx = sorted(set(round(i * step) for i in range(max_pts)))
    idx = [min(i, len(path) - 1) for i in idx]
    out = [path[i] for i in idx]
    if out[-1] != path[-1]:
        out.append(path[-1])
    return out


def main():
    corridors = []
    for name in RIVERS:
        print(f"Fetching {name}...")
        reaches = fetch_reaches(name)
        if not reaches:
            print(f"  WARNING: no reaches found for {name}, skipping")
            continue
        chain = stitch(reaches)
        simplified = simplify(chain, SIMPLIFY_MAX_PTS)
        corridors.append({"name": name, "pts": [[round(la, 5), round(lo, 5)] for la, lo in simplified]})
        print(f"  {len(reaches)} reaches -> stitched to {len(chain)} pts -> simplified to {len(simplified)} pts")

    OUT_JSON.write_text(json.dumps(corridors, indent=2))
    OUT_JS.write_text(
        "// Real flood-prone river corridors for the 7 non-Hartford CT counties.\n"
        "// Source: USGS National Hydrography Dataset (NHD Flowline - Small Scale).\n"
        "// See: 13_fetch_flood_corridors.py\n\n"
        "window.CONNECTICUT_FLOOD_CORRIDORS_EXTRA = " + json.dumps(corridors) + ";\n"
    )
    print(f"\nWrote {len(corridors)} river corridors -> {OUT_JSON}")


if __name__ == "__main__":
    main()
