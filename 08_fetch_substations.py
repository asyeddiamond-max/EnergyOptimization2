"""
08_fetch_substations.py — Cache REAL Hartford County substation locations.

Primary source: HIFLD (Homeland Infrastructure Foundation-Level Data) "Electric
Substations" — the U.S. federal dataset, the most complete and authoritative
public substation layer. It carries explicit COUNTY attribution (so no polygon
filtering is needed), plus city, status, line count, and voltage where known.

Per advisor feedback: "the substations exist as point data; you don't need to
simulate; keep names of real substations." Synthetic feeders/laterals are grown
FROM these real anchor points in the interactive.

Writes:
    data/hartford_substations.json  — array of {name, lat, lon, voltage, city, lines}
    data/hartford_substations.js    — window.HARTFORD_SUBSTATIONS = [...]

Usage:
    python 08_fetch_substations.py

HIFLD labels some substations "UNKNOWN<id>" when the operator name isn't public;
we relabel those as "<City> substation" so the map stays readable while the
location stays exact. Falls back to OpenStreetMap (Overpass) if HIFLD is
unreachable.

Source: HIFLD Electric Substations (services5.arcgis.com/HDRa0B57OVrv2E1q).
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
OUT_JSON = HERE / "data" / "hartford_substations.json"
OUT_JS = HERE / "data" / "hartford_substations.js"

HIFLD = ("https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/"
         "Electric_Substations/FeatureServer/0/query")
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "41.49,-73.04,42.05,-72.40"  # Hartford County, for the OSM fallback


import re
_PLACEHOLDER = re.compile(r"[A-Za-z]*\d{4,}")  # UNKNOWN133259, Deadend167077, Tap12345…


def _clean_name(name: str, city: str) -> str:
    """HIFLD uses ID-style placeholders ('UNKNOWN<id>', 'Deadend<id>', etc.)
    when the operator name isn't public. Relabel those with the city so the
    marker is meaningful; keep real names as-is."""
    n = (name or "").strip()
    if not n or _PLACEHOLDER.fullmatch(n) or n.upper().startswith("UNKNOWN"):
        c = (city or "").strip().title()
        return f"{c} substation" if c else "Unnamed substation"
    return n.title() if n.isupper() else n


def fetch_hifld() -> list:
    params = {
        "where": "STATE='CT' AND COUNTY='HARTFORD'",
        "outFields": "NAME,CITY,STATUS,LINES,MAX_VOLT,LATITUDE,LONGITUDE",
        "returnGeometry": "true", "outSR": "4326", "f": "json",
    }
    url = HIFLD + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hartford-grid-resilience/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read())
    if "error" in d:
        raise RuntimeError(f"HIFLD error: {d['error']}")
    subs = []
    for f in d.get("features", []):
        a = f.get("attributes", {})
        g = f.get("geometry", {})
        lon = g.get("x", a.get("LONGITUDE"))
        lat = g.get("y", a.get("LATITUDE"))
        if lat is None or lon is None:
            continue
        mv = a.get("MAX_VOLT")
        voltage = "" if (mv is None or mv < 0) else f"{int(mv)} kV"
        subs.append({
            "name": _clean_name(a.get("NAME", ""), a.get("CITY", "")),
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
            "voltage": voltage,
            "city": (a.get("CITY") or "").title(),
            "lines": a.get("LINES", 0) or 0,
        })
    return subs


def fetch_osm_fallback() -> list:
    """OpenStreetMap fallback (power=substation in the county bbox)."""
    q = f"""[out:json][timeout:90];
(
  node["power"="substation"]({BBOX});
  way["power"="substation"]({BBOX});
);
out center tags;"""
    req = urllib.request.Request(
        OVERPASS, data=("data=" + urllib.parse.quote(q)).encode(),
        headers={"User-Agent": "hartford-grid-resilience/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read())
    subs = []
    for e in d.get("elements", []):
        t = e.get("tags", {})
        if e["type"] == "node":
            lat, lon = e.get("lat"), e.get("lon")
        else:
            c = e.get("center", {}); lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        subs.append({
            "name": t.get("name") or "Unnamed substation",
            "lat": round(lat, 6), "lon": round(lon, 6),
            "voltage": t.get("voltage", ""), "city": "", "lines": 0,
        })
    return subs


def main() -> None:
    try:
        print("Querying HIFLD Electric Substations (Hartford County, CT)…")
        subs = fetch_hifld()
        src = "HIFLD"
    except Exception as ex:
        print(f"  HIFLD failed ({ex}); falling back to OpenStreetMap")
        subs = fetch_osm_fallback()
        src = "OSM"

    # De-duplicate by rounded location.
    seen, uniq = set(), []
    for s in sorted(subs, key=lambda x: x["name"]):
        key = (round(s["lat"], 4), round(s["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)

    OUT_JSON.write_text(json.dumps(uniq, indent=2))
    OUT_JS.write_text("window.HARTFORD_SUBSTATIONS = " + json.dumps(uniq) + ";\n")
    named = sum(1 for s in uniq if "substation" not in s["name"].lower()
                or not s["name"].lower().endswith("substation")
                and "unnamed" not in s["name"].lower())
    print(f"Wrote {len(uniq)} substations from {src}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_JS}")


if __name__ == "__main__":
    main()
