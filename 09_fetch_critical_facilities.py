"""
09_fetch_critical_facilities.py — Cache REAL Connecticut (statewide) critical
facility locations: hospitals, fire stations, EMS stations, and wastewater
treatment plants.

Unlike the original hand-curated hartford_critical_facilities.js, this pulls
live from the actual HIFLD (and EPA, for water) ArcGIS FeatureServer endpoints
so every record is independently verifiable, not hand-typed from memory.

Sources (HIFLD ArcGIS Online org HDRa0B57OVrv2E1q):
    Hospitals: HIFLD_2020_Hospitals
    Fire stations: Fire_Stations
    EMS stations: Emergency_Medical_Service_Stations
    Wastewater treatment plants: EPA_Wastewater_Treatment_Plant

Writes:
    data/connecticut_critical_facilities.json
    data/connecticut_critical_facilities.js — window.CONNECTICUT_CRITICAL_FACILITIES = [...]

Usage:
    python 09_fetch_critical_facilities.py
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
OUT_JSON = HERE / "data" / "connecticut_critical_facilities.json"
OUT_JS = HERE / "data" / "connecticut_critical_facilities.js"

BASE = "https://services5.arcgis.com/HDRa0B57OVrv2E1q/ArcGIS/rest/services"
UA = {"User-Agent": "connecticut-grid-resilience/1.0"}


def _query(layer: str, where: str, out_fields: str) -> list:
    params = {
        "where": where, "outFields": out_fields,
        "returnGeometry": "true", "outSR": "4326", "f": "json",
    }
    url = f"{BASE}/{layer}/FeatureServer/0/query?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read())
    if "error" in d:
        raise RuntimeError(f"{layer}: {d['error']}")
    return d.get("features", [])


def fetch_hospitals() -> list:
    feats = _query("HIFLD_2020_Hospitals", "STATE='CT'",
                    "NAME,CITY,COUNTY,STATUS,BEDS,TRAUMA")
    out = []
    for f in feats:
        a, g = f["attributes"], f["geometry"]
        if a.get("STATUS") not in (None, "", "OPEN"):
            continue  # skip closed/temporarily-closed facilities
        out.append({
            "name": (a.get("NAME") or "").title(), "type": "hospital",
            "lat": round(g["y"], 6), "lon": round(g["x"], 6),
            "town": (a.get("CITY") or "").title(),
            "county": (a.get("COUNTY") or "").title(),
            "beds": a.get("BEDS") if (a.get("BEDS") or 0) > 0 else None,
        })
    return out


def fetch_fire() -> list:
    feats = _query("Fire_Stations", "STATE='CT'", "NAME,CITY")
    out = []
    for f in feats:
        a, g = f["attributes"], f["geometry"]
        out.append({
            "name": (a.get("NAME") or "Unnamed fire station").title(), "type": "fire",
            "lat": round(g["y"], 6), "lon": round(g["x"], 6),
            "town": (a.get("CITY") or "").title(),
        })
    return out


def fetch_ems() -> list:
    feats = _query("Emergency_Medical_Service_Stations", "STATE='CT'", "NAME,CITY,COUNTY")
    out = []
    for f in feats:
        a, g = f["attributes"], f["geometry"]
        out.append({
            "name": (a.get("NAME") or "Unnamed EMS station").title(), "type": "ems",
            "lat": round(g["y"], 6), "lon": round(g["x"], 6),
            "town": (a.get("CITY") or "").title(),
            "county": (a.get("COUNTY") or "").title(),
        })
    return out


def fetch_water() -> list:
    # NOTE: cwp_status is EPA *regulatory compliance* status ("Noncompliance" /
    # "No Violation"), not an operational open/closed flag -- a plant in
    # "Noncompliance" is still physically running (and still needs power).
    # Do not filter on it.
    feats = _query("EPA_Wastewater_Treatment_Plant", "cwp_state='CT'",
                    "cwp_name,cwp_city,cwp_county")
    out = []
    for f in feats:
        a, g = f["attributes"], f["geometry"]
        out.append({
            "name": (a.get("cwp_name") or "Unnamed water treatment plant").title(), "type": "water",
            "lat": round(g["y"], 6), "lon": round(g["x"], 6),
            "town": (a.get("cwp_city") or "").title(),
            "county": (a.get("cwp_county") or "").title(),
        })
    return out


def main() -> None:
    all_facilities = []
    for label, fn in [("hospitals", fetch_hospitals), ("fire stations", fetch_fire),
                       ("EMS stations", fetch_ems), ("wastewater plants", fetch_water)]:
        print(f"Querying {label} (Connecticut, statewide)…")
        recs = fn()
        print(f"  got {len(recs)}")
        all_facilities.extend(recs)

    # De-duplicate by rounded location + type (some layers overlap at shared sites).
    seen, uniq = set(), []
    for r in sorted(all_facilities, key=lambda x: (x["type"], x["name"])):
        key = (r["type"], round(r["lat"], 4), round(r["lon"], 4))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    OUT_JSON.write_text(json.dumps(uniq, indent=2))
    OUT_JS.write_text(
        "// Connecticut critical facilities — hospitals, fire stations, EMS stations,\n"
        "// and wastewater treatment plants. Live-fetched from HIFLD ArcGIS FeatureServer\n"
        "// endpoints (org HDRa0B57OVrv2E1q) and the EPA Wastewater Treatment Plant layer.\n"
        "// Coordinates are WGS-84. Source: 09_fetch_critical_facilities.py\n\n"
        "window.CONNECTICUT_CRITICAL_FACILITIES = " + json.dumps(uniq) + ";\n"
    )
    by_type = {}
    for r in uniq:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    print(f"\nWrote {len(uniq)} critical facilities")
    for t, n in sorted(by_type.items()):
        print(f"    {t}: {n}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_JS}")


if __name__ == "__main__":
    main()
