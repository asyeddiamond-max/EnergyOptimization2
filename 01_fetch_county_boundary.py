"""
01_fetch_county_boundary.py — Cache the Connecticut state polygon from OpenStreetMap.

Writes data/connecticut_boundary.json in the same shape Nominatim returns
so the interactive can `fetch('./data/connecticut_boundary.json')` without a live
API hit. Re-run this once if OSM updates the state boundary; otherwise the
cached file is sufficient.

Usage:
    python 01_fetch_county_boundary.py
"""
from __future__ import annotations
import sys
import urllib.request
import json
from pathlib import Path

URL = (
    "https://nominatim.openstreetmap.org/search.php"
    "?q=Connecticut%2C+United+States"
    "&format=json"
    "&polygon_geojson=1"
    "&limit=1"
)

OUT = Path(__file__).parent / "data" / "connecticut_boundary.json"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "connecticut-grid-resilience/1.0"})
    print(f"Fetching {URL}")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
    data = json.loads(body)
    if not data or "geojson" not in data[0]:
        sys.exit("Nominatim returned no geojson for Connecticut")
    OUT.write_bytes(body)
    print(f"Wrote {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
