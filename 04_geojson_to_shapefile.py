"""
geojson_to_shapefile.py — Convert a Hartford simulation export to Esri Shapefiles.

Usage:
    python geojson_to_shapefile.py path/to/hartford_grid_seed42_*.zip
    python geojson_to_shapefile.py path/to/hartford_grid_seed42_*.json
    python geojson_to_shapefile.py path/to/folder_of_geojsons

Outputs a folder of shapefiles next to the input, one .shp/.shx/.dbf/.prj per layer.

Requirements:
    pip install geopandas

This script exists for users who prefer the offline conversion path. The
simulation HTML itself can also produce a shapefile zip directly via the
"Download Shapefile" button — this script is an alternative if the in-browser
path fails or if you want to script bulk conversion.
"""
from __future__ import annotations

import json
import sys
import os
import zipfile
from pathlib import Path

try:
    import geopandas as gpd
except ImportError:
    sys.exit("geopandas not installed. Run: pip install geopandas")


LAYERS = ["substations", "feeders", "laterals", "outages", "restoration_plan"]


def load_input(path: Path) -> tuple[dict, dict]:
    """Return (manifest, {layer_name: feature_collection_dict})."""
    layers: dict[str, dict] = {}
    manifest: dict = {}

    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                stem = Path(name).stem
                if name.endswith(".geojson") and stem in LAYERS:
                    layers[stem] = json.loads(zf.read(name))
                elif name.endswith("manifest.json"):
                    manifest = json.loads(zf.read(name))
        return manifest, layers

    if path.suffix == ".json":
        with path.open() as f:
            bundle = json.load(f)
        manifest = bundle.get("manifest", {})
        for layer in LAYERS:
            if layer in bundle:
                layers[layer] = bundle[layer]
        return manifest, layers

    if path.is_dir():
        for layer in LAYERS:
            p = path / f"{layer}.geojson"
            if p.exists():
                layers[layer] = json.loads(p.read_text())
        mp = path / "manifest.json"
        if mp.exists():
            manifest = json.loads(mp.read_text())
        return manifest, layers

    sys.exit(f"Unrecognized input: {path}. Pass a .zip, .json, or folder.")


def convert(input_path: Path, out_dir: Path) -> None:
    manifest, layers = load_input(input_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    if manifest:
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"Manifest: seed={manifest.get('inputs', {}).get('seed')} "
              f"k={manifest.get('inputs', {}).get('substations')}")

    for name, fc in layers.items():
        feats = fc.get("features", [])
        if not feats:
            print(f"  skip {name}: empty")
            continue
        gdf = gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
        # Shapefile attribute names are capped at 10 chars; verify upstream.
        too_long = [c for c in gdf.columns if c != "geometry" and len(c) > 10]
        if too_long:
            print(f"  warn  {name}: attribute names exceed 10 chars: {too_long}")
        shp_path = out_dir / f"{name}.shp"
        gdf.to_file(shp_path, driver="ESRI Shapefile")
        print(f"  wrote {shp_path.name}  ({len(gdf)} features)")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python geojson_to_shapefile.py <input.zip|.json|folder>")
    in_path = Path(sys.argv[1]).expanduser().resolve()
    if not in_path.exists():
        sys.exit(f"Not found: {in_path}")
    out_dir = in_path.parent / f"{in_path.stem}_shp"
    convert(in_path, out_dir)
    print(f"\nDone. Shapefiles in: {out_dir}")


if __name__ == "__main__":
    main()
