"""
11_fetch_census_tracts.py — Cache REAL Connecticut census tract population/
centroid data, and REAL per-town population/centroid data, both statewide.

Unlike the original hand-typed hartford_census_tracts.js (148 records with
10-digit "GEOIDs" that don't match the real 11-digit Census format, and an
embedded county-FIPS substring that doesn't match Hartford County's real FIPS
code -- strong evidence it was fabricated, not pulled from an API), this
downloads the actual 2020 Census P.L. 94-171 Redistricting Data Summary File
for Connecticut directly from the Census Bureau's public FTP mirror. This is
the exact same underlying data api.census.gov serves, as a static keyless
flat file -- no API key needed.

The geographic header file (ctgeo2020.pl) carries POP100 (2020 100% count
population), INTPTLAT/INTPTLON (real geometric centroids), and NAME for every
summary level in one pass, so a single file gives us both:
  - SUMLEV=140 rows -> census tracts (real GEOID, real population, real centroid)
  - SUMLEV=060 rows -> towns/county subdivisions (real population, real centroid)
    -- verified to name-match all 169 of the real town boundaries fetched by
    02_fetch_town_boundaries.py exactly (after stripping the " town" suffix
    Census appends to every Connecticut county subdivision name).

Source: US Census Bureau, 2020 Census P.L. 94-171 Redistricting Data
        https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Connecticut/ct2020.pl.zip
        Record layout: Chapter 6, 2020Census_PL94_171Redistricting_StatesTechDoc_English.pdf

Writes:
    data/connecticut_census_tracts.json / .js   window.CONNECTICUT_CENSUS_TRACTS = [...]
    data/connecticut_towns_population.json / .js  window.CONNECTICUT_TOWNS_POPULATION = [...]

Usage:
    python 11_fetch_census_tracts.py
"""
from __future__ import annotations
import io
import json
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
OUT_TRACTS_JSON = HERE / "data" / "connecticut_census_tracts.json"
OUT_TRACTS_JS = HERE / "data" / "connecticut_census_tracts.js"
OUT_TOWNS_JSON = HERE / "data" / "connecticut_towns_population.json"
OUT_TOWNS_JS = HERE / "data" / "connecticut_towns_population.js"

ZIP_URL = ("https://www2.census.gov/programs-surveys/decennial/2020/data/"
           "01-Redistricting_File--PL_94-171/Connecticut/ct2020.pl.zip")
UA = {"User-Agent": "connecticut-grid-resilience/1.0"}

# Field indices in ctgeo2020.pl (pipe-delimited), verified against the
# official 2020 PL94-171 geographic header layout AND cross-checked directly
# against real rows (e.g. Bridgeport town POP100=148654, Greenwich town
# POP100=63518 -- both match published 2020 Census figures).
SUMLEV, COUNTY, COUSUB, TRACT = 2, 14, 17, 32
NAME, POP100, INTPTLAT, INTPTLON, GEOID = 87, 90, 92, 93, 8

COUNTY_FIPS_TO_NAME = {
    "001": "Fairfield", "003": "Hartford", "005": "Litchfield",
    "007": "Middlesex", "009": "New Haven", "011": "New London",
    "013": "Tolland", "015": "Windham",
}


def fetch_geo_lines() -> list[str]:
    print(f"Downloading {ZIP_URL} ...")
    req = urllib.request.Request(ZIP_URL, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        zip_bytes = r.read()
    print(f"  got {len(zip_bytes)} bytes")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        with zf.open("ctgeo2020.pl") as f:
            return io.TextIOWrapper(f, encoding="utf-8").readlines()


def parse(lines: list[str]):
    tracts, towns = [], []
    for ln in lines:
        p = ln.rstrip("\n").split("|")
        if p[SUMLEV] == "140":  # census tract
            tracts.append({
                "geoid": p[GEOID].split("US")[-1],
                "name": p[NAME],
                "county": COUNTY_FIPS_TO_NAME.get(p[COUNTY], p[COUNTY]),
                "pop": int(p[POP100]),
                "lat": float(p[INTPTLAT]),
                "lon": float(p[INTPTLON]),
            })
        elif p[SUMLEV] == "060" and p[COUSUB] != "00000":  # town
            name = p[NAME]
            if name.endswith(" town"):
                name = name[:-5]
            towns.append({
                "name": name,
                "county": COUNTY_FIPS_TO_NAME.get(p[COUNTY], p[COUNTY]),
                "pop": int(p[POP100]),
                "lat": float(p[INTPTLAT]),
                "lon": float(p[INTPTLON]),
            })
    return tracts, towns


def main() -> None:
    lines = fetch_geo_lines()
    tracts, towns = parse(lines)

    if len(tracts) < 700:
        raise SystemExit(f"Too few tracts parsed ({len(tracts)}); check the geo header layout.")
    if len(towns) < 160:
        raise SystemExit(f"Too few towns parsed ({len(towns)}); check the geo header layout.")

    OUT_TRACTS_JSON.write_text(json.dumps(tracts, indent=2))
    OUT_TRACTS_JS.write_text(
        "// Connecticut 2020 Census tracts -- GEOID, population, and real centroid.\n"
        "// Source: US Census Bureau 2020 P.L. 94-171 Redistricting Data (11_fetch_census_tracts.py)\n\n"
        "window.CONNECTICUT_CENSUS_TRACTS = " + json.dumps(tracts) + ";\n"
    )
    OUT_TOWNS_JSON.write_text(json.dumps(towns, indent=2))
    OUT_TOWNS_JS.write_text(
        "// Connecticut town (county subdivision) 2020 population and real centroid.\n"
        "// Source: US Census Bureau 2020 P.L. 94-171 Redistricting Data (11_fetch_census_tracts.py)\n\n"
        "window.CONNECTICUT_TOWNS_POPULATION = " + json.dumps(towns) + ";\n"
    )

    total_pop = sum(t["pop"] for t in towns)
    print(f"\nWrote {len(tracts)} census tracts -> {OUT_TRACTS_JSON}")
    print(f"Wrote {len(towns)} towns (total population {total_pop:,}) -> {OUT_TOWNS_JSON}")


if __name__ == "__main__":
    main()
