"""
17_fetch_live_outages.py -- Fetch REAL, CURRENT Eversource CT power outages
from the live public outage map backend, for the simulator's "live mode."

Source: outagemap.eversource.com, which is an iFactor/StormCenter deployment
(confirmed live 2026-07-12 by reading the site's own iFactor.config.js -- see
DEVELOPMENT notes below). The map's data layer is plain JSON over HTTPS, no
auth:

  1. {IGD}/metadata.json                     -> {"directory": "<timestamped dir>"}
  2. {IGD}/{dir}/data.json                   -> territory-wide summary (ALL of
     Eversource: CT+MA+NH combined -- NOT CT-only; CT totals are computed here
     from the filtered points instead)
  3. {IGD}/{dir}/outages/{quadkey}.json      -> outage points, tiled by Bing
     quadkey. HTTP 403 = empty tile (not an error). Each entry is either:
       - a single outage: desc.cluster == false, with inc_id, cause,
         cust_a.val (masked:true means "fewer than 5", value reported as 4),
         start, etr; geom.p[0] is a Google *encoded polyline* string that
         decodes to one (lat, lon) point.
       - a cluster: desc.cluster == true with n_out -- resolved by descending
         into the tile's 4 quadkey children until singles appear (singles are
         deduped globally by inc_id since the same outage re-appears at every
         zoom level).

Filters the collected points to Connecticut using the real state boundary
polygon (data/connecticut_boundary.json + shapely), since Eversource's map
covers CT, MA, and NH in one territory.

United Illuminating (the other CT utility, ~340K customers around Bridgeport/
New Haven) is NOT included -- its map is a separate deployment, and this
project's entire historical calibration dataset is Eversource-centric anyway,
so an Eversource-only live feed is the apples-to-apples choice.

Writes:
    data/connecticut_live_outages.js    -- window.CONNECTICUT_LIVE_OUTAGES
    data/connecticut_live_outages.json  -- same payload, plain JSON
    data/live_snapshots/live_outages_<UTC timestamp>.json -- archive copy, so
        predictions made during an event can later be compared against how
        long restoration ACTUALLY took (the whole point of live mode).

Usage:
    python 17_fetch_live_outages.py            # fetch + write everything
    python 17_fetch_live_outages.py --max-zoom 15
"""
from __future__ import annotations
import argparse
import gzip
import json
import math
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
IGD = "https://outagemap.eversource.com/resources/data/external/interval_generation_data"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) connecticut-grid-resilience/1.0"}

OUT_JS = HERE / "data" / "connecticut_live_outages.js"
OUT_JSON = HERE / "data" / "connecticut_live_outages.json"
SNAP_DIR = HERE / "data" / "live_snapshots"

# CT bounding box (small buffer) -- used to seed the tile walk and as a cheap
# pre-filter before the exact polygon test.
LAT_MIN, LAT_MAX = 40.90, 42.10
LON_MIN, LON_MAX = -73.80, -71.70

BASE_ZOOM = 8       # coarsest tiles the walk starts from
REQUEST_SLEEP = 0.12  # politeness delay between tile requests
MAX_REQUESTS = 400    # hard cap; a real mega-storm cluster tree stays well under this


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def decode_polyline_point(s: str) -> tuple[float, float]:
    """Decode the FIRST point of a Google encoded polyline (iFactor stores
    exactly one point per outage geometry). Standard 1e-5 precision."""
    result = []
    index = 0
    value = 0
    for _coord in range(2):
        shift = 0
        acc = 0
        while True:
            b = ord(s[index]) - 63
            index += 1
            acc |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        delta = ~(acc >> 1) if (acc & 1) else (acc >> 1)
        value = delta  # first point: value == delta
        result.append(value / 1e5)
    return result[0], result[1]  # (lat, lon)


def latlon_to_tilexy(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    sin = math.sin(lat * math.pi / 180)
    x = (lon + 180) / 360
    y = 0.5 - math.log((1 + sin) / (1 - sin)) / (4 * math.pi)
    n = 2 ** zoom
    return (max(0, min(n - 1, int(x * n))), max(0, min(n - 1, int(y * n))))


def tilexy_to_quadkey(tx: int, ty: int, zoom: int) -> str:
    qk = ""
    for i in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if tx & mask:
            digit += 1
        if ty & mask:
            digit += 2
        qk += str(digit)
    return qk


def ct_seed_quadkeys(zoom: int) -> list[str]:
    tx0, ty1 = latlon_to_tilexy(LAT_MAX, LON_MIN, zoom)  # NW corner
    tx1, ty0 = latlon_to_tilexy(LAT_MIN, LON_MAX, zoom)  # SE corner
    qks = []
    for tx in range(min(tx0, tx1), max(tx0, tx1) + 1):
        for ty in range(min(ty0, ty1), max(ty0, ty1) + 1):
            qks.append(tilexy_to_quadkey(tx, ty, zoom))
    return sorted(qks)


def fetch_all_outages(directory: str, max_zoom: int) -> tuple[list[dict], int]:
    """BFS the quadkey tile tree. Returns (outages, n_requests).

    Singles are deduped globally by inc_id (the same outage appears in its
    tile at every zoom level). Clusters trigger a descent into the tile's 4
    children; clusters still unresolved at max_zoom are kept as one synthetic
    outage each (real co-located incidents, e.g. one pole feeding 3 circuits).
    """
    singles: dict[str, dict] = {}
    leaf_clusters: list[dict] = []
    n_req = 0
    frontier = ct_seed_quadkeys(BASE_ZOOM)
    seen_tiles: set[str] = set()

    while frontier:
        qk = frontier.pop(0)
        if qk in seen_tiles or len(qk) > max_zoom:
            continue
        seen_tiles.add(qk)
        if n_req >= MAX_REQUESTS:
            print(f"  WARNING: hit request cap ({MAX_REQUESTS}); results may be partial")
            break
        n_req += 1
        time.sleep(REQUEST_SLEEP)
        try:
            body = _get(f"{IGD}/{directory}/outages/{qk}.json")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                continue  # empty tile -- normal
            raise
        tile = json.loads(body)
        had_cluster = False
        for entry in tile.get("file_data", []):
            desc = entry.get("desc", {})
            geom_p = (entry.get("geom", {}).get("p") or [None])[0]
            if not geom_p:
                continue
            lat, lon = decode_polyline_point(geom_p)
            if desc.get("cluster"):
                had_cluster = True
                if len(qk) >= max_zoom:
                    leaf_clusters.append({
                        "lat": round(lat, 5), "lon": round(lon, 5),
                        "customers": int(desc.get("cust_a", {}).get("val") or 0),
                        "n_incidents": int(desc.get("n_out") or 1),
                        "masked": bool(desc.get("cust_a", {}).get("masked")),
                        "cause": None,
                        "start": desc.get("start"),
                        "etr": desc.get("etr"),
                        "inc_id": None,
                        "cluster_leaf": True,
                    })
            else:
                inc = desc.get("inc_id") or f"noid_{round(lat,5)}_{round(lon,5)}"
                if inc not in singles:
                    singles[inc] = {
                        "lat": round(lat, 5), "lon": round(lon, 5),
                        "customers": int(desc.get("cust_a", {}).get("val") or 0),
                        "n_incidents": 1,
                        "masked": bool(desc.get("cust_a", {}).get("masked")),
                        "cause": desc.get("cause"),
                        "start": desc.get("start"),
                        "etr": desc.get("etr"),
                        "inc_id": desc.get("inc_id"),
                        "cluster_leaf": False,
                    }
        if had_cluster and len(qk) < max_zoom:
            frontier.extend(qk + c for c in "0123")

    # Deduplicate leaf clusters (same cluster can appear via multiple parents).
    dedup: dict[tuple, dict] = {}
    for c in leaf_clusters:
        dedup[(c["lat"], c["lon"], c["customers"], c["n_incidents"])] = c
    return list(singles.values()) + list(dedup.values()), n_req


def filter_to_ct(outages: list[dict]) -> list[dict]:
    from shapely.geometry import shape, Point
    boundary = json.loads((HERE / "data" / "connecticut_boundary.json").read_text())
    # ~200m buffer for points snapped to a road hugging the border. (Was
    # 0.01 deg ~1.1km, which let an Agawam-MA-area outage through -- caught
    # by reverse-geocoding every fetched point to CT town polygons during
    # fact-checking.)
    ct_poly = shape(boundary[0]["geojson"]).buffer(0.002)
    out = []
    for o in outages:
        if not (LAT_MIN <= o["lat"] <= LAT_MAX and LON_MIN <= o["lon"] <= LON_MAX):
            continue
        if ct_poly.contains(Point(o["lon"], o["lat"])):
            out.append(o)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-zoom", type=int, default=14,
                    help="Deepest quadkey level to descend clusters into (default 14)")
    args = ap.parse_args()

    print("Fetching Eversource outage map metadata...")
    directory = json.loads(_get(f"{IGD}/metadata.json"))["directory"]
    summary = json.loads(_get(f"{IGD}/{directory}/data.json")).get("summaryFileData", {})
    print(f"  directory: {directory}")
    print(f"  territory-wide (CT+MA+NH): {summary.get('total_outages')} outages, "
          f"{(summary.get('total_cust_a') or {}).get('val')} customers, "
          f"mode={((summary.get('page_mode') or {}).get('mode'))}")

    print("Walking outage tiles over Connecticut...")
    all_outages, n_req = fetch_all_outages(directory, args.max_zoom)
    print(f"  {n_req} tile requests, {len(all_outages)} unique outage points territory-wide (in walked tiles)")

    ct = filter_to_ct(all_outages)
    ct.sort(key=lambda o: -o["customers"])
    ct_customers = sum(o["customers"] for o in ct)
    ct_incidents = sum(o["n_incidents"] for o in ct)
    # PLAN = planned maintenance work, present in the feed alongside real
    # unplanned outages (found during fact-checking). Kept in the data file
    # (it IS a real outage) but counted separately so the simulator's
    # restoration planner can exclude scheduled work from the storm queue.
    ct_planned = sum(1 for o in ct if o.get("cause") == "PLAN")
    print(f"  Connecticut only: {len(ct)} outage points ({ct_incidents} incidents, "
          f"{ct_planned} planned-maintenance), {ct_customers} customers affected")

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "fetched_at": fetched_at,
        "source": "outagemap.eversource.com (iFactor StormCenter public data layer)",
        "directory": directory,
        "utility": "Eversource CT only (UI excluded; see 17_fetch_live_outages.py)",
        "territory_summary": {
            "total_outages": summary.get("total_outages"),
            "total_cust_a": (summary.get("total_cust_a") or {}).get("val"),
            "total_cust_served": summary.get("total_cust_s"),
            "date_generated": summary.get("date_generated"),
            "page_mode": (summary.get("page_mode") or {}).get("mode"),
        },
        "ct_total_outage_points": len(ct),
        "ct_total_incidents": ct_incidents,
        "ct_total_customers": ct_customers,
        "ct_planned_maintenance_points": ct_planned,
        "outages": ct,
    }

    header = (
        "// LIVE Eversource CT outages -- generated by 17_fetch_live_outages.py.\n"
        "// Do not hand-edit; re-run the script to refresh. fetched_at is UTC.\n"
        "// cust masked:true means Eversource reports 'fewer than 5' (value 4).\n\n"
    )
    OUT_JS.write_text(header + "window.CONNECTICUT_LIVE_OUTAGES = "
                      + json.dumps(payload) + ";\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    SNAP_DIR.mkdir(exist_ok=True)
    snap = SNAP_DIR / f"live_outages_{fetched_at.replace(':', '').replace('-', '')}.json"
    snap.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nWrote {OUT_JS}")
    print(f"Wrote {OUT_JSON}")
    print(f"Archived snapshot: {snap}")


if __name__ == "__main__":
    main()
