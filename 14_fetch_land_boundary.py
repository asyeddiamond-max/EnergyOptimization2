"""
14_fetch_land_boundary.py — Compute a LAND-ONLY Connecticut polygon for grid
generation, separate from the real legal state boundary used for the map's
red outline.

Connecticut's real legal state boundary (data/connecticut_boundary.json,
see 01_fetch_county_boundary.py) genuinely extends into Long Island Sound --
that's an accurate, well-documented fact (a line from an 1880s CT-NY
boundary compact), not a data bug, and the map's red outline should keep
showing it as-is.

But the grid generator (generateGrid() in 03_grid_simulation.html) uses that
same polygon as its ONLY constraint for where feeders/laterals/outages can
be placed -- so it was happily growing distribution lines out into open
water, since "inside the state's legal jurisdiction" and "on land with real
electrical infrastructure" are not the same thing. This script subtracts the
real Long Island Sound water body (a real OSM polygon, not a bounding box)
from the state boundary, producing a land-only shape for that specific use.

Source: OpenStreetMap via Nominatim, "Long Island Sound" (relation, real
        polygon geometry, not a placeholder point)
Requires: shapely (pip install shapely)

Writes:
    data/connecticut_land_boundary.json
        Same [{"geojson": {...}}] shape as connecticut_boundary.json, so it's
        a drop-in for buildInsideBitmap() in 03_grid_simulation.html.

Usage:
    python 14_fetch_land_boundary.py
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from pathlib import Path

from shapely.geometry import shape, mapping

HERE = Path(__file__).parent
BOUNDARY_FILE = HERE / "data" / "connecticut_boundary.json"
OUT_JSON = HERE / "data" / "connecticut_land_boundary.json"
UA = {"User-Agent": "connecticut-grid-resilience/1.0"}


def fetch_water_body(query: str) -> dict:
    params = {"q": query, "format": "json", "polygon_geojson": "1", "limit": "1"}
    url = "https://nominatim.openstreetmap.org/search.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        results = json.loads(r.read())
    if not results or not results[0].get("geojson") or results[0]["geojson"]["type"] not in ("Polygon", "MultiPolygon"):
        raise RuntimeError(f"No real polygon found for {query!r} -- got {results[0].get('geojson', {}).get('type') if results else 'no results'}")
    return results[0]["geojson"]


def main() -> None:
    ct = json.loads(BOUNDARY_FILE.read_text())
    ct_geo = ct[0]["geojson"]
    ct_poly = shape(ct_geo)

    print("Fetching Long Island Sound (real OSM polygon)...")
    lis_geo = fetch_water_body("Long Island Sound")
    lis_poly = shape(lis_geo)
    print(f"  Long Island Sound bounds: {lis_poly.bounds}")

    land = ct_poly.difference(lis_poly)
    if land.is_empty:
        raise RuntimeError("Land/water difference produced an empty polygon -- check inputs")

    print(f"State boundary area: {ct_poly.area:.4f} deg^2")
    print(f"Land-only area:      {land.area:.4f} deg^2  ({100*land.area/ct_poly.area:.1f}% of the full legal boundary)")

    out = [{"geojson": mapping(land)}]
    OUT_JSON.write_text(json.dumps(out))
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
