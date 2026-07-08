"""
08_fetch_substations.py — Cache REAL Connecticut (statewide) substation locations.

Primary source: HIFLD (Homeland Infrastructure Foundation-Level Data) "Electric
Substations" — the U.S. federal dataset, the most complete and authoritative
public substation layer. It carries explicit COUNTY attribution, plus city,
status, line count, and voltage where known.

Per advisor feedback: "the substations exist as point data; you don't need to
simulate; keep names of real substations." Synthetic feeders/laterals are grown
FROM these real anchor points in the interactive.

Writes:
    data/connecticut_substations.json  — array of {name, lat, lon, voltage, city, lines, county}
    data/connecticut_substations.js    — window.CONNECTICUT_SUBSTATIONS = [...]

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
OUT_JSON = HERE / "data" / "connecticut_substations.json"
OUT_JS = HERE / "data" / "connecticut_substations.js"

HIFLD = ("https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services/"
         "Electric_Substations/FeatureServer/0/query")
OVERPASS = "https://overpass-api.de/api/interpreter"
BBOX = "40.95,-73.73,42.05,-71.79"  # Connecticut statewide, for the OSM fallback


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
        "where": "STATE='CT'",
        "outFields": "NAME,CITY,COUNTY,STATUS,LINES,MAX_VOLT,LATITUDE,LONGITUDE",
        "returnGeometry": "true", "outSR": "4326", "f": "json",
    }
    url = HIFLD + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "connecticut-grid-resilience/1.0"})
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
            "county": (a.get("COUNTY") or "").title(),
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
        headers={"User-Agent": "connecticut-grid-resilience/1.0"})
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
        print("Querying HIFLD Electric Substations (Connecticut, statewide)…")
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
    OUT_JS.write_text("window.CONNECTICUT_SUBSTATIONS = " + json.dumps(uniq) + ";\n")
    print(f"Wrote {len(uniq)} substations from {src}")
    by_county = {}
    for s in uniq:
        c = s.get("county") or "(unknown)"
        by_county[c] = by_county.get(c, 0) + 1
    for c, n in sorted(by_county.items(), key=lambda kv: -kv[1]):
        print(f"    {c}: {n}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_JS}")


if __name__ == "__main__":
    main()
