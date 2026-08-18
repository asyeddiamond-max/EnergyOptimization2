"""Fetch auditable 2020 Connecticut Census block and town population inputs.

The Census P.L. 94-171 geographic header contains the official 2020 total
population (POP100) and Census internal latitude/longitude for every summary
level.  This script retains all Census blocks, including zero-population
blocks, so record counts and statewide totals can be audited independently of
the browser application.

An internal point is a Census-provided point inside a geography; it is not a
population-weighted location and must not be described as a geometric
centroid.  ``11_build_census_population_grid.js`` performs the deterministic
bilinear allocation from these points to the fixed HRRR analysis grid.

Source:
  U.S. Census Bureau, 2020 P.L. 94-171 Redistricting Data, Connecticut
  https://www2.census.gov/programs-surveys/decennial/2020/data/
  01-Redistricting_File--PL_94-171/Connecticut/ct2020.pl.zip

Writes:
  data/connecticut_census_blocks.json
  data/connecticut_towns_population.json
  data/connecticut_towns_population.js

Usage:
  python 11_fetch_census_population.py
  node 11_build_census_population_grid.js
"""
from __future__ import annotations

import argparse
import io
import json
import urllib.request
import zipfile
from pathlib import Path


HERE = Path(__file__).parent
OUT_BLOCKS_JSON = HERE / "data" / "connecticut_census_blocks.json"
OUT_TOWNS_JSON = HERE / "data" / "connecticut_towns_population.json"
OUT_TOWNS_JS = HERE / "data" / "connecticut_towns_population.js"

ZIP_URL = (
    "https://www2.census.gov/programs-surveys/decennial/2020/data/"
    "01-Redistricting_File--PL_94-171/Connecticut/ct2020.pl.zip"
)
USER_AGENT = {"User-Agent": "connecticut-grid-resilience/1.0"}

# Official 2020 Connecticut checks.  These make upstream format or filtering
# mistakes fail loudly instead of silently changing a scientific input.
EXPECTED_BLOCK_COUNT = 49_926
EXPECTED_STATE_POPULATION = 3_605_944

# Zero-based field indices in the pipe-delimited ctgeo2020.pl geographic
# header, verified against the official P.L. 94-171 technical documentation.
SUMLEV, COUNTY, COUSUB = 2, 14, 17
NAME, POP100, INTPTLAT, INTPTLON, GEOID = 87, 90, 92, 93, 8
BLOCK_SUMLEV = "750"
TOWN_SUMLEV = "060"

COUNTY_FIPS_TO_NAME = {
    "001": "Fairfield",
    "003": "Hartford",
    "005": "Litchfield",
    "007": "Middlesex",
    "009": "New Haven",
    "011": "New London",
    "013": "Tolland",
    "015": "Windham",
}


def fetch_geo_lines(archive_path: Path | None = None) -> list[str]:
    """Download and return the official Connecticut geographic-header rows."""
    if archive_path is None:
        print(f"Downloading {ZIP_URL} ...")
        request = urllib.request.Request(ZIP_URL, headers=USER_AGENT)
        with urllib.request.urlopen(request, timeout=180) as response:
            archive = response.read()
        print(f"  downloaded {len(archive):,} bytes")
    else:
        archive = archive_path.read_bytes()
        print(f"Reading {len(archive):,} bytes from {archive_path}")
    with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
        with zip_file.open("ctgeo2020.pl") as source:
            return io.TextIOWrapper(source, encoding="utf-8").readlines()


def parse(lines: list[str]) -> tuple[list[dict], list[dict]]:
    """Extract Census blocks and Connecticut county subdivisions (towns)."""
    blocks: list[dict] = []
    towns: list[dict] = []
    for line in lines:
        fields = line.rstrip("\n").split("|")
        if fields[SUMLEV] == BLOCK_SUMLEV:
            blocks.append({
                "geoid": fields[GEOID].split("US")[-1],
                "pop": int(fields[POP100]),
                "lat": float(fields[INTPTLAT]),
                "lon": float(fields[INTPTLON]),
            })
        elif fields[SUMLEV] == TOWN_SUMLEV and fields[COUSUB] != "00000":
            name = fields[NAME]
            if name.endswith(" town"):
                name = name[:-5]
            towns.append({
                "name": name,
                "county": COUNTY_FIPS_TO_NAME.get(fields[COUNTY], fields[COUNTY]),
                "pop": int(fields[POP100]),
                "lat": float(fields[INTPTLAT]),
                "lon": float(fields[INTPTLON]),
            })
    return blocks, towns


def validate(blocks: list[dict], towns: list[dict]) -> None:
    """Apply reproducible record, identifier, coordinate, and total checks."""
    if len(blocks) != EXPECTED_BLOCK_COUNT:
        raise SystemExit(
            f"Expected {EXPECTED_BLOCK_COUNT:,} blocks, parsed {len(blocks):,}; "
            "check the P.L. 94-171 layout or summary-level filter."
        )
    geoids = [block["geoid"] for block in blocks]
    if len(set(geoids)) != len(geoids):
        raise SystemExit("Census block GEOIDs are not unique.")
    if any(len(geoid) != 15 or not geoid.startswith("09") for geoid in geoids):
        raise SystemExit("Every Connecticut block must have a 15-digit GEOID beginning with 09.")
    if any(block["pop"] < 0 for block in blocks):
        raise SystemExit("Census block population cannot be negative.")
    if any(
        not (-90 <= block["lat"] <= 90 and -180 <= block["lon"] <= 180)
        for block in blocks
    ):
        raise SystemExit("A Census block has invalid internal-point coordinates.")
    block_population = sum(block["pop"] for block in blocks)
    town_population = sum(town["pop"] for town in towns)
    if block_population != EXPECTED_STATE_POPULATION:
        raise SystemExit(
            f"Block population {block_population:,} does not equal the official "
            f"Connecticut total {EXPECTED_STATE_POPULATION:,}."
        )
    if town_population != EXPECTED_STATE_POPULATION:
        raise SystemExit(
            f"Town population {town_population:,} does not equal the official "
            f"Connecticut total {EXPECTED_STATE_POPULATION:,}."
        )
    if len(towns) != 169:
        raise SystemExit(f"Expected 169 Connecticut towns, parsed {len(towns)}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        help="Use an already-downloaded ct2020.pl.zip instead of downloading it.",
    )
    args = parser.parse_args()
    blocks, towns = parse(fetch_geo_lines(args.archive))
    validate(blocks, towns)

    # Compact block JSON materially reduces repository and browser-tooling
    # overhead; the generating script is the human-readable provenance record.
    OUT_BLOCKS_JSON.write_text(json.dumps(blocks, separators=(",", ":")) + "\n")
    OUT_TOWNS_JSON.write_text(json.dumps(towns, indent=2) + "\n")
    OUT_TOWNS_JS.write_text(
        "// Connecticut towns: 2020 Census population and Census internal points.\n"
        "// Source and validation: 11_fetch_census_population.py\n\n"
        "window.CONNECTICUT_TOWNS_POPULATION = "
        + json.dumps(towns)
        + ";\n"
    )

    populated = sum(block["pop"] > 0 for block in blocks)
    print(
        f"Wrote {len(blocks):,} Census blocks ({populated:,} populated; "
        f"population {EXPECTED_STATE_POPULATION:,}) -> {OUT_BLOCKS_JSON}"
    )
    print(f"Wrote {len(towns)} towns -> {OUT_TOWNS_JSON}")


if __name__ == "__main__":
    main()
