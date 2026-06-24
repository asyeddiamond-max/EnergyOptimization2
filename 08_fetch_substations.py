"""
08_fetch_substations.py — Cache REAL Hartford County substation locations from
OpenStreetMap (Overpass API).

Replaces the synthetic k-means substation placement with actual substation
point data, keeping the real substation names and voltages — per advisor
feedback ("the substations exist as point data; you don't need to simulate;
keep names of real substations"). Synthetic feeders/laterals are then grown
FROM these real anchor points in the interactive.

Method:
    1. Query Overpass for power=substation nodes + ways in the Hartford County
       bounding box.
    2. Filter to those whose location falls inside the real county polygon
       (data/hartford_boundary.json), since the bbox spills into neighbouring
       counties.
    3. Write data/hartford_substations.json (array of {name, lat, lon, voltage})
       and data/hartford_substations.js (window.HARTFORD_SUBSTATIONS = [...])
       so the interactive can load it without a live API hit.

Usage:
    python 08_fetch_substations.py

Source: OpenStreetMap, power=substation. Note OSM coverage is strongest for
transmission/sub-transmission substations (115 kV / 345 kV); smaller
distribution substations may be under-mapped. This is real, named,
reproducible data and a strict improvement over synthetic placement.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
BOUNDARY = HERE / "data" / "hartford_boundary.json"
OUT_JSON = HERE / "data" / "hartford_substations.json"
OUT_JS = HERE / "data" / "hartford_substations.js"

# Hartford County bounding box (south, west, north, east) — generous; we filter
# to the real polygon afterward.
BBOX = "41.49,-73.04,42.05,-72.40"
OVERPASS = "https://overpass-api.de/api/interpreter"


def point_in_polygon(lon: float, lat: float, ring: list) -> bool:
    """Ray-casting point-in-polygon. ring is a list of [lon, lat] pairs."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
                (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def load_boundary_rings() -> list:
    """Return list of outer rings ([[lon,lat],...]) from the cached boundary."""
    data = json.loads(BOUNDARY.read_text())
    obj = data[0] if isinstance(data, list) else data
    gj = obj["geojson"]
    t = gj["type"]
    coords = gj["coordinates"]
    if t == "Polygon":
        return [coords[0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in coords]
    raise SystemExit(f"Unexpected geojson type: {t}")


def main() -> None:
    q = f"""[out:json][timeout:90];
(
  node["power"="substation"]({BBOX});
  way["power"="substation"]({BBOX});
);
out center tags;"""
    req = urllib.request.Request(
        OVERPASS,
        data=("data=" + urllib.parse.quote(q)).encode(),
        headers={"User-Agent": "hartford-grid-resilience/1.0"},
    )
    print("Querying Overpass for power=substation in Hartford County bbox…")
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
    elements = d.get("elements", [])
    print(f"  bbox returned {len(elements)} substations")

    rings = load_boundary_rings()

    subs = []
    for e in elements:
        tags = e.get("tags", {})
        if e["type"] == "node":
            lat, lon = e.get("lat"), e.get("lon")
        else:  # way → use computed center
            c = e.get("center", {})
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        # Keep only substations inside the real county polygon.
        if not any(point_in_polygon(lon, lat, ring) for ring in rings):
            continue
        name = tags.get("name") or f"Substation {e['id']}"
        subs.append({
            "name": name,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "voltage": tags.get("voltage", ""),
            "operator": tags.get("operator", ""),
        })

    # De-duplicate by (name, rounded location).
    seen = set()
    uniq = []
    for s in subs:
        key = (s["name"], round(s["lat"], 4), round(s["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    uniq.sort(key=lambda s: s["name"])

    OUT_JSON.write_text(json.dumps(uniq, indent=2))
    OUT_JS.write_text("window.HARTFORD_SUBSTATIONS = " +
                      json.dumps(uniq) + ";\n")
    named = sum(1 for s in uniq if not s["name"].startswith("Substation "))
    print(f"Wrote {len(uniq)} substations inside Hartford County "
          f"({named} with real names)")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_JS}")


if __name__ == "__main__":
    main()
