"""
14_fetch_land_boundary.py — Compute a LAND-ONLY Connecticut polygon for grid
generation, separate from the real legal state boundary used for the map's
red outline.

Connecticut's real legal state boundary (data/connecticut_boundary.json,
see 01_fetch_county_boundary.py) genuinely extends into coastal waters
(Long Island Sound, and points east) -- that's an accurate, well-documented
fact, not a data bug, and the map's red outline should keep showing it as-is.

But the grid generator (generateGrid() in 03_grid_simulation.html) uses that
same polygon as its ONLY constraint for where feeders/laterals/outages can
be placed -- so it was happily growing distribution lines out into open
water, since "inside the state's legal jurisdiction" and "on land with real
electrical infrastructure" are not the same thing.

First attempt subtracted the real "Long Island Sound" OSM polygon from the
state boundary -- correct for the central/western coast, but incomplete:
the water east of Long Island's forks (Gardiners Bay, Peconic Bay, Fishers
Island Sound, Block Island Sound) has no single named OSM polygon covering
it, only unusable point markers. Chasing every named bay/sound by hand
doesn't scale and can't be verified complete.

Second attempt (this file's previous version) dropped the Sound subtraction
entirely in favor of unioning all 170 real town boundary relations
(02_fetch_town_boundaries.py's data/connecticut_towns.geojson) into one
land shape -- comprehensive by construction, no dependency on finding the
"right" named water body. But CT's coastal towns' OSM administrative
boundaries ALSO extend into Long Island Sound (real maritime jurisdiction,
same underlying fact that makes the STATE boundary extend into the Sound),
so the town-union alone still let feeders/laterals grow miles out into open
water off Stamford/Greenwich -- confirmed by comparing town polygon extents
(e.g. Greenwich's polygon reaches lat 40.951, well south of its real
Tod's Point shoreline at ~41.00) and visually, in the running simulator.

This version combines both fixes: town-union as the base (comprehensive,
fixes the eastern-bay gaps the first attempt had), then ADDITIONALLY
subtracts the real Long Island Sound OSM polygon (fixes the central/western
coast overshoot the town-union alone left in, exactly where the first
attempt already proved this subtraction works well).

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

from shapely.geometry import shape, mapping, LineString, Polygon
from shapely.ops import polygonize, unary_union, linemerge

HERE = Path(__file__).parent
BOUNDARY_FILE = HERE / "data" / "connecticut_boundary.json"
TOWNS_FILE = HERE / "data" / "connecticut_towns.geojson"
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


def _town_shape(lines: list):
    """Real OSM way data often merges into a ring that's technically
    self-intersecting by a hair (e.g. Bridgeport: linemerge() closes fine,
    but is_simple is False), which makes polygonize() silently return
    nothing. Try the direct linemerge -> Polygon -> buffer(0) path first
    (buffer(0) is the standard fix for a slightly-invalid/self-intersecting
    polygon), and only fall back to polygonize() for towns whose ways don't
    merge into a single clean ring at all."""
    merged = linemerge(lines)
    rings = [merged] if merged.geom_type == "LineString" else list(merged.geoms)
    # NOTE: check closure only (first coord == last), not r.is_ring -- is_ring
    # also demands the ring be simple (non-self-intersecting), which excludes
    # exactly the case this function exists to handle (a closed-but-slightly-
    # self-intersecting ring, fixed below via buffer(0)).
    candidates = [Polygon(r.coords) for r in rings if len(r.coords) >= 4 and r.coords[0] == r.coords[-1]]
    if not candidates:
        candidates = list(polygonize(lines))
    if not candidates:
        return None
    fixed = [c if c.is_valid else c.buffer(0) for c in candidates]
    return unary_union(fixed)


def town_polygons(towns_fc: dict, state_poly) -> list:
    polys = []
    skipped_out_of_state = 0
    skipped_unpolygonizable = 0
    for feat in towns_fc["features"]:
        lines = [LineString(coords) for coords in feat["geometry"]["coordinates"] if len(coords) >= 2]
        if not lines:
            continue
        town_shape = _town_shape(lines)
        if town_shape is None or town_shape.is_empty:
            skipped_unpolygonizable += 1
            continue
        if not state_poly.contains(town_shape.representative_point()):
            skipped_out_of_state += 1
            continue
        polys.append(town_shape)
    print(f"  {len(polys)} towns polygonized "
          f"({skipped_out_of_state} out-of-state, {skipped_unpolygonizable} unpolygonizable)")
    return polys


def main() -> None:
    ct = json.loads(BOUNDARY_FILE.read_text())
    state_poly = shape(ct[0]["geojson"])

    towns_fc = json.loads(TOWNS_FILE.read_text())
    polys = town_polygons(towns_fc, state_poly)
    if len(polys) < 140:
        raise SystemExit(f"Too few towns polygonized ({len(polys)}); check {TOWNS_FILE}.")

    land = unary_union(polys)
    # Light intersection with the real state polygon as a sanity trim, in case
    # any border town's geometry overshoots CT's actual extent.
    land = land.intersection(state_poly)
    if land.is_empty:
        raise RuntimeError("Land union came back empty -- check inputs")
    town_union_area = land.area

    # Coastal towns' own OSM administrative boundaries extend into Long
    # Island Sound too (same real maritime-jurisdiction fact that makes the
    # state boundary do it), so the town union alone still lets feeders grow
    # miles into open water off the central/western coast (Stamford/
    # Greenwich). Subtract the real Sound polygon to trim that off -- this
    # was already validated to work well for exactly that stretch of coast
    # (see this file's git history); it just doesn't cover the eastern bays,
    # which the town union already handles.
    try:
        print("Fetching Long Island Sound (real OSM polygon) for an additional trim...")
        lis_geo = fetch_water_body("Long Island Sound")
        lis_poly = shape(lis_geo)
        land = land.difference(lis_poly)
        if land.is_empty:
            raise RuntimeError("Sound subtraction emptied the land polygon -- aborting trim")
    except Exception as e:
        print(f"  WARNING: Long Island Sound trim skipped ({e}); "
              f"using town-union land as-is.")

    print(f"State boundary area:      {state_poly.area:.4f} deg^2")
    print(f"Town-union land area:     {town_union_area:.4f} deg^2  ({100*town_union_area/state_poly.area:.1f}% of the full legal boundary)")
    print(f"After Sound trim:         {land.area:.4f} deg^2  ({100*land.area/state_poly.area:.1f}% of the full legal boundary)")

    out = [{"geojson": mapping(land)}]
    OUT_JSON.write_text(json.dumps(out))
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
