"""
02_fetch_town_boundaries.py — Cache the 29 Hartford County town outlines from OSM.

Queries Overpass for every `admin_level=8` administrative-boundary relation
inside the Hartford County bbox, filters down to the 29 named towns, and
emits each town's outer-way geometry as a MultiLineString GeoJSON feature.
We use MultiLineString instead of Polygon because OSM's outer ways are
fragmented and reliable ring-stitching across all 29 towns is fiddly — for
visualization purposes the line geometry is identical, and L.geoJSON renders
it the same way.

Writes both:
  - data/hartford_towns.geojson   (~140 KB GeoJSON FeatureCollection)
  - data/hartford_towns.js        (same content wrapped as a JS global so the
                                   interactive can <script src> it without
                                   needing fetch + a web server)

Usage:
    python 02_fetch_town_boundaries.py
"""
from __future__ import annotations
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

OVERPASS = "https://overpass.kumi.systems/api/interpreter"
BBOX = (41.54, -73.05, 42.05, -72.40)   # south, west, north, east

WANTED = {
    "Hartford","New Britain","West Hartford","Bristol","Manchester","Enfield",
    "East Hartford","Southington","Glastonbury","South Windsor","Windsor",
    "Newington","Wethersfield","Rocky Hill","Bloomfield","Plainville",
    "Farmington","Berlin","Avon","Simsbury","Windsor Locks","East Windsor",
    "Suffield","Granby","Canton","Marlborough","East Granby","Hartland",
    "Burlington",
}

QUERY = (
    "[out:json][timeout:90];"
    f'relation["boundary"="administrative"]["admin_level"="8"]'
    f'({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});'
    "out geom;"
)

OUT_GEOJSON = Path(__file__).parent / "data" / "hartford_towns.geojson"
OUT_JS      = Path(__file__).parent / "data" / "hartford_towns.js"


def fetch_overpass() -> dict:
    print(f"Querying Overpass: {len(WANTED)} towns inside Hartford County bbox")
    url = OVERPASS + "?" + urllib.parse.urlencode({"data": QUERY})
    req = urllib.request.Request(url, headers={"User-Agent": "hartford-grid-resilience/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def build_feature_collection(raw: dict) -> dict:
    features = []
    matched = set()
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        name = el.get("tags", {}).get("name")
        if not name or name not in WANTED:
            continue
        lines = []
        for m in el.get("members", []):
            if m.get("type") != "way" or m.get("role") != "outer" or not m.get("geometry"):
                continue
            coords = [[round(p["lon"], 5), round(p["lat"], 5)] for p in m["geometry"]]
            if len(coords) >= 2:
                lines.append(coords)
        if not lines:
            continue
        features.append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": {"type": "MultiLineString", "coordinates": lines},
        })
        matched.add(name)
    missing = WANTED - matched
    if missing:
        print(f"  warn: missing {len(missing)} towns: {sorted(missing)}")
    print(f"  matched {len(matched)}/{len(WANTED)} towns")
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    raw = fetch_overpass()
    fc = build_feature_collection(raw)
    if len(fc["features"]) < 25:
        sys.exit("Too few towns matched; check the Overpass response.")
    text = json.dumps(fc, separators=(",", ":"))
    OUT_GEOJSON.write_text(text)
    OUT_JS.write_text("window.HARTFORD_TOWNS_GEOJSON = " + text + ";")
    print(f"Wrote {OUT_GEOJSON}  ({OUT_GEOJSON.stat().st_size} bytes)")
    print(f"Wrote {OUT_JS}  ({OUT_JS.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
