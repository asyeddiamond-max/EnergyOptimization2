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

This version is more robust: it reuses the same 170 real town relations
02_fetch_town_boundaries.py already cached in data/connecticut_towns.geojson
(each a MultiLineString of raw "outer" way segments), but instead of just
drawing the outline, uses shapely's polygonize() to stitch each town's
outer ways into closed polygons, then unions all of them together. Since
CT's towns tile the entire state with no gaps, this union IS the state's
land area -- comprehensive by construction, with no dependency on finding
the "right" named water body.

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
from pathlib import Path

from shapely.geometry import shape, mapping, LineString, Polygon
from shapely.ops import polygonize, unary_union, linemerge

HERE = Path(__file__).parent
BOUNDARY_FILE = HERE / "data" / "connecticut_boundary.json"
TOWNS_FILE = HERE / "data" / "connecticut_towns.geojson"
OUT_JSON = HERE / "data" / "connecticut_land_boundary.json"


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

    print(f"State boundary area: {state_poly.area:.4f} deg^2")
    print(f"Land-only area:      {land.area:.4f} deg^2  ({100*land.area/state_poly.area:.1f}% of the full legal boundary)")

    out = [{"geojson": mapping(land)}]
    OUT_JSON.write_text(json.dumps(out))
    print(f"\nWrote {OUT_JSON}")


if __name__ == "__main__":
    main()
