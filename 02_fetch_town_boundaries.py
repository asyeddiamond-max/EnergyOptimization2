"""
02_fetch_town_boundaries.py — Cache all Connecticut town outlines from OSM.

Queries Overpass for every `admin_level=8` administrative-boundary relation
inside the Connecticut statewide bbox. Connecticut has 169 towns (its
municipalities double as the primary local government unit, unlike most
states); we take whatever OSM returns inside the bbox rather than a
hand-typed name list, so the script doesn't go stale if OSM's town-boundary
coverage changes.

We use MultiLineString instead of Polygon because OSM's outer ways are
fragmented and reliable ring-stitching across all towns is fiddly — for
visualization purposes the line geometry is identical, and L.geoJSON renders
it the same way.

Connecticut's town boundaries are LEGAL boundaries, which extend well out into
Long Island Sound -- coastal towns own rectangular blocks of open water (~20-23%
of Greenwich's and Stamford's legal area). Drawn raw, that puts green town lines
across the middle of the Sound. clip_to_land() intersects each town with the
land-only shape so the outlines hug the real coastline instead. This is a
RENDERING concern only: connecticut_towns.geojson is consumed solely by the map
layer in 03_grid_simulation.html, never by the grid/scheduler logic.

Writes both:
  - data/connecticut_towns.geojson   (GeoJSON FeatureCollection)
  - data/connecticut_towns.js        (same content wrapped as a JS global so the
                                       interactive can <script src> it without
                                       needing fetch + a web server)

Usage:
    python 02_fetch_town_boundaries.py
    python 02_fetch_town_boundaries.py --clip-only   # re-clip existing data,
                                                     # no Overpass round-trip
"""
from __future__ import annotations
import json
import sys
import urllib.request
import urllib.parse
from pathlib import Path

OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = (40.95, -73.73, 42.05, -71.79)   # south, west, north, east — Connecticut statewide
BOUNDARY_FILE = Path(__file__).parent / "data" / "connecticut_boundary.json"


def _boundary_rings():
    """Load the real CT state polygon (run 01_fetch_county_boundary.py first)."""
    data = json.loads(BOUNDARY_FILE.read_text())
    coords = data[0]["geojson"]["coordinates"]
    rings = []
    def flatten(c):
        if isinstance(c[0][0], (int, float)):
            rings.append(c)
        else:
            for cc in c:
                flatten(cc)
    flatten(coords)
    return rings


def _point_in_any_ring(lon: float, lat: float, rings: list) -> bool:
    """Standard ray-casting point-in-polygon test, OR'd across every ring
    (Nominatim can return a MultiPolygon with several disjoint rings)."""
    for ring in rings:
        inside = False
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if ((y1 > lat) != (y2 > lat)) and \
               (lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1):
                inside = not inside
        if inside:
            return True
    return False

QUERY = (
    "[out:json][timeout:300];"
    f'relation["boundary"="administrative"]["admin_level"="8"]'
    f'({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});'
    "out geom;"
)

OUT_GEOJSON = Path(__file__).parent / "data" / "connecticut_towns.geojson"
OUT_JS      = Path(__file__).parent / "data" / "connecticut_towns.js"


def fetch_overpass() -> dict:
    print("Querying Overpass: all admin_level=8 towns inside Connecticut bbox")
    url = OVERPASS + "?" + urllib.parse.urlencode({"data": QUERY})
    req = urllib.request.Request(url, headers={"User-Agent": "connecticut-grid-resilience/1.0"})
    with urllib.request.urlopen(req, timeout=320) as r:
        return json.loads(r.read())


def build_feature_collection(raw: dict) -> dict:
    rings = _boundary_rings()
    features = []
    seen_names = set()
    out_of_state = []
    for el in raw.get("elements", []):
        if el.get("type") != "relation":
            continue
        name = el.get("tags", {}).get("name")
        if not name:
            continue
        lines = []
        all_pts = []
        for m in el.get("members", []):
            if m.get("type") != "way" or m.get("role") != "outer" or not m.get("geometry"):
                continue
            coords = [[round(p["lon"], 5), round(p["lat"], 5)] for p in m["geometry"]]
            if len(coords) >= 2:
                lines.append(coords)
                all_pts.extend(coords)
        if not lines:
            continue
        # A bbox query necessarily also catches border towns in MA/RI/NY --
        # a rectangle can't match Connecticut's actual shape. Keep only
        # relations whose centroid genuinely falls inside the real state
        # polygon (fetched separately by 01_fetch_county_boundary.py).
        cx = sum(p[0] for p in all_pts) / len(all_pts)
        cy = sum(p[1] for p in all_pts) / len(all_pts)
        if not _point_in_any_ring(cx, cy, rings):
            out_of_state.append(name)
            continue
        # OSM sometimes returns the same town as two relations (e.g. a
        # borough + the enclosing town); keep the first and skip dupes.
        if name in seen_names:
            continue
        seen_names.add(name)
        features.append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": {"type": "MultiLineString", "coordinates": lines},
        })
    if out_of_state:
        print(f"  dropped {len(out_of_state)} out-of-state relations (bbox spillover): "
              f"{sorted(out_of_state)}")
    print(f"  matched {len(features)} towns")
    return {"type": "FeatureCollection", "features": features}


LAND_FILE = Path(__file__).parent / "data" / "connecticut_land_boundary.json"


def clip_to_land(fc: dict) -> dict:
    """Trim each town's boundary LINES to the land-only shape.

    Direct line intersection: geom.intersection(land) keeps the parts of a
    town's boundary ways that lie on land and drops the parts over open water.
    That is all this needs to do -- a coastal town's outline should simply END
    at the shoreline (an open seaward edge is correct; there is no border over
    the Sound). Every land-side border segment, including every shared
    town-to-town border, is preserved bit-for-bit.

    (An earlier version polygonized each town into an AREA and took its
    boundary, trying to make the clipped edge trace the coast. That was lossy:
    collapsing the rich multi-way border into a single outer ring dropped
    interior detail and left the statewide mesh visibly sparse -- 1,454 line
    pieces down to 310. Do NOT reintroduce the polygonize approach.)
    """
    from shapely.geometry import shape, mapping

    land = shape(json.loads(LAND_FILE.read_text(encoding="utf-8"))[0]["geojson"])
    # Tiny outward buffer (~30m) so boundary ways that run exactly along the
    # shoreline or a state line aren't dropped by floating-point edge cases.
    land_buf = land.buffer(0.0003)

    out, dropped = [], 0
    for f in fc["features"]:
        name = (f.get("properties") or {}).get("name")
        try:
            clipped = shape(f["geometry"]).intersection(land_buf)
            if clipped.is_empty or clipped.length == 0:
                dropped += 1
                continue
            out.append({**f, "geometry": mapping(clipped)})
        except Exception as e:                       # never let one town break the set
            print(f"  clip failed for {name!r} ({e}); keeping unclipped")
            out.append(f)
    if dropped:
        print(f"  dropped {dropped} town(s) with no land border")
    print(f"  clipped {len(out)}/{len(fc['features'])} town outlines to land")
    return {"type": "FeatureCollection", "features": out}


def _write(fc: dict) -> None:
    text = json.dumps(fc, separators=(",", ":"))
    OUT_GEOJSON.write_text(text)
    OUT_JS.write_text("window.CONNECTICUT_TOWNS_GEOJSON = " + text + ";")
    print(f"Wrote {OUT_GEOJSON}  ({OUT_GEOJSON.stat().st_size} bytes)")
    print(f"Wrote {OUT_JS}  ({OUT_JS.stat().st_size} bytes)")


def main() -> None:
    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    if "--clip-only" in sys.argv:
        # Re-clip what's already on disk; no Overpass round-trip.
        fc = json.loads(OUT_GEOJSON.read_text(encoding="utf-8"))
        print(f"Re-clipping {len(fc['features'])} existing town outlines to land...")
        _write(clip_to_land(fc))
        return
    raw = fetch_overpass()
    fc = build_feature_collection(raw)
    # Connecticut has 169 towns; OSM coverage can occasionally miss a couple
    # or fold a borough in as a separate relation, so we check against a
    # generous floor rather than requiring the exact number.
    if len(fc["features"]) < 140:
        sys.exit(f"Too few towns matched ({len(fc['features'])}); check the Overpass response.")
    _write(clip_to_land(fc))


if __name__ == "__main__":
    main()
