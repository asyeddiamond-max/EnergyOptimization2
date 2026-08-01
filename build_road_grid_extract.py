"""
build_road_grid_extract.py -- road-snap all 299 substations' feeders/laterals from a BULK OSM
extract (no per-substation Overpass calls). Parses data/connecticut-latest.osm.pbf once (pyosmium),
builds the statewide road graph, then for each substation extracts a local ~2.5km subgraph and runs
27_road_snapped_laterals.py's Dijkstra road_network() to route feeders (major roads) + laterals
(residential). Writes data/road_grid.json for 03_grid_simulation.html to load in place of the
synthetic radial/random-walk geometry.

Usage:  python build_road_grid_extract.py
"""
from __future__ import annotations
import importlib.util, json
from pathlib import Path
from collections import defaultdict
import osmium

HERE = Path(__file__).parent
DATA = HERE / "data"
PBF = DATA / "connecticut-latest.osm.pbf"
OUT = DATA / "road_grid.json"
RADIUS_M = 2500

spec = importlib.util.spec_from_file_location("rs27", HERE / "27_road_snapped_laterals.py")
rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
ROAD_CLASSES = set(rs.CLASS_W.keys())   # primary, secondary, tertiary, unclassified, residential, living_street

# ---- 1) parse the PBF: road ways with node coordinates ----
print("parsing PBF (highways)...", flush=True)
nodes = {}          # osm node id -> (lat, lon)
ways = []           # ([node ids], highway class)
fp = osmium.FileProcessor(str(PBF)).with_locations().with_filter(osmium.filter.KeyFilter("highway"))
for obj in fp:
    if not obj.is_way():
        continue
    hc = obj.tags.get("highway")
    if hc not in ROAD_CLASSES:
        continue
    ids = []
    for n in obj.nodes:
        if n.location.valid():
            nodes[n.ref] = (n.location.lat, n.location.lon)
            ids.append(n.ref)
    if len(ids) >= 2:
        ways.append((ids, hc))
print(f"  {len(nodes):,} road nodes, {len(ways):,} road ways", flush=True)

# ---- 2) adjacency (class-weighted, same weights as 27_) + ~1.1km spatial grid index ----
adj = defaultdict(list)
for ids, hc in ways:
    w = rs.CLASS_W.get(hc, 1.0)
    for a, b in zip(ids, ids[1:]):
        if a in nodes and b in nodes and a != b:
            km = rs.haversine_km(nodes[a], nodes[b])
            if km <= 0:
                continue
            adj[a].append((b, km * w, km, hc)); adj[b].append((a, km * w, km, hc))
grid = defaultdict(list)
for nid, (la, lo) in nodes.items():
    grid[(round(la, 2), round(lo, 2))].append(nid)
print(f"  graph built: {len(adj):,} connected nodes", flush=True)

# ---- 3) per-substation local subgraph -> road_network() ----
txt = (DATA / "connecticut_substations.js").read_text(encoding="utf-8")
subs = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
DEG = RADIUS_M / 111320.0
RC = int(DEG / 0.01) + 1
results = []
for i, s in enumerate(subs):
    lat, lon = s["lat"], s["lon"]
    clat, clon = round(lat, 2), round(lon, 2)
    local = set()
    for dla in range(-RC, RC + 1):
        for dlo in range(-RC, RC + 1):
            local.update(grid.get((round(clat + dla * 0.01, 2), round(clon + dlo * 0.01, 2)), []))
    if not local:
        results.append({"name": s["name"], "slat": lat, "slon": lon, "feeders": [], "laterals": []}); continue
    lnodes = {n: nodes[n] for n in local}
    ladj = defaultdict(list)
    for n in local:
        for (v, wt, km, hc) in adj.get(n, []):
            if v in local:
                ladj[n].append((v, wt, km, hc))
    src = min(lnodes, key=lambda n: (lnodes[n][0] - lat) ** 2 + (lnodes[n][1] - lon) ** 2)
    slat, slon = lnodes[src]
    try:
        feeders, laterals = rs.road_network(lnodes, ladj, src)
    except Exception:
        feeders, laterals = [], []
    results.append({"name": s["name"], "slat": round(slat, 6), "slon": round(slon, 6),
        "feeders": [[[round(p[0], 6), round(p[1], 6)] for p in f] for f in feeders],
        "laterals": [[[round(p[0], 6), round(p[1], 6)] for p in l] for l in laterals]})
    if (i + 1) % 25 == 0:
        print(f"  routed [{i+1}/{len(subs)}]", flush=True)

OUT.write_text(json.dumps({"radius": RADIUS_M, "subs": results}))
snapped = sum(1 for r in results if r["feeders"])
tf = sum(len(r["feeders"]) for r in results); tl = sum(len(r["laterals"]) for r in results)
print(f"DONE: {snapped}/{len(subs)} substations road-snapped | {tf} feeders, {tl} laterals -> {OUT}", flush=True)
