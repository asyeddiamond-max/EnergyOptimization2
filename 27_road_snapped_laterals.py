"""
27_road_snapped_laterals.py -- PROTOTYPE: route distribution feeders + laterals
along REAL OpenStreetMap road segments instead of the app's synthetic random
walks (03_grid_simulation.html:generateGrid, "feeders (radial backbones) +
laterals (random walks)").

Real distribution lines overwhelmingly run along road rights-of-way (poles line
the street). The production model instead grows each feeder as a wobbling radial
spoke and each lateral as a short random walk off a feeder midpoint, clipped only
to land -- topologically fine (right hierarchy + density) but geometrically the
lines cut across blocks and ignore the street grid. Utilities don't publish their
distribution GIS, so OSM roads are the best free proxy for where the lines run.

This prototype, for one real substation:
  1. pulls the OSM street network around it (Overpass, cached),
  2. builds a road graph and grows a road-following network:
       feeders = major-road shortest paths outward (one per angular sector),
       laterals = short branches along residential streets off the feeders,
  3. reproduces the app's synthetic random-walk network from the same substation,
  4. plots them side by side over the real streets, and reports how far each
     network's vertices sit from the nearest actual road (0 m = on a street).

Output: output/road_snapped_laterals.png  +  a printed offset comparison.

Usage:
    python 27_road_snapped_laterals.py                 # Newington substation
    python 27_road_snapped_laterals.py --lat 41.72 --lon -72.75 --radius 2000
"""
from __future__ import annotations
import argparse, heapq, json, math, time, urllib.request
from collections import defaultdict
from pathlib import Path

# Overpass mirrors, tried in order (the main .de endpoint is often overloaded).
OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT = HERE / "output"
CACHE = DATA / "_osm_cache"

# Distribution lines favor bigger roads for backbones; weight = length x factor
# so Dijkstra prefers primary/secondary for feeders, residential for laterals.
CLASS_W = {"primary": 0.4, "secondary": 0.5, "tertiary": 0.7,
           "unclassified": 0.9, "residential": 1.0, "living_street": 1.1}
LATERAL_CLASSES = ("residential", "living_street", "unclassified", "service")


def haversine_km(a, b):
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def fetch_roads(lat, lon, radius_m):
    CACHE.mkdir(exist_ok=True)
    key = CACHE / f"roads_{lat:.4f}_{lon:.4f}_{radius_m}.json"
    if key.exists():
        return json.loads(key.read_text())
    # Drop 'service' (driveways/parking aisles) to keep the payload light so the
    # server doesn't time out; residential+ are what distribution lines follow.
    q = (f'[out:json][timeout:120];way(around:{radius_m},{lat},{lon})'
         f'[highway~"^(primary|secondary|tertiary|unclassified|residential|living_street)$"];'
         f'(._;>;);out;')
    last = None
    for ep in OVERPASS_ENDPOINTS:
        for attempt in range(2):
            try:
                print(f"Fetching OSM roads from {ep} (attempt {attempt + 1}) ...")
                req = urllib.request.Request(ep, data=("data=" + q).encode(),
                                             headers={"User-Agent": "ct-grid-road-prototype/1.0"})
                d = json.loads(urllib.request.urlopen(req, timeout=150).read())
                if d.get("elements"):
                    key.write_text(json.dumps(d))
                    return d
            except Exception as e:
                last = e
                print(f"  {type(e).__name__}: {str(e)[:90]}")
                time.sleep(3)
    raise SystemExit(f"All Overpass endpoints failed: {last}")


def build_graph(osm):
    nodes, ways = {}, []
    for e in osm["elements"]:
        if e["type"] == "node":
            nodes[e["id"]] = (e["lat"], e["lon"])
        elif e["type"] == "way" and e.get("nodes"):
            ways.append((e["nodes"], e.get("tags", {}).get("highway", "residential")))
    adj = defaultdict(list)  # node -> [(nbr, weighted_len, real_km, hclass)]
    segs = []                # (p1, p2) for road rendering + offset metric
    for nds, hc in ways:
        w = CLASS_W.get(hc, 1.0)
        for a, b in zip(nds, nds[1:]):
            if a in nodes and b in nodes and a != b:
                km = haversine_km(nodes[a], nodes[b])
                if km <= 0:
                    continue
                adj[a].append((b, km * w, km, hc))
                adj[b].append((a, km * w, km, hc))
                segs.append((nodes[a], nodes[b]))
    return nodes, adj, segs


def dijkstra(adj, src):
    dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        for v, w, _km, _hc in adj[u]:
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v], prev[v] = nd, u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def path_to(prev, src, tgt):
    p = [tgt]
    while p[-1] != src:
        if p[-1] not in prev:
            return None
        p.append(prev[p[-1]])
    return p[::-1]


def road_network(nodes, adj, src, n_feeders=6, laterals_per_feeder=5):
    dist, prev = dijkstra(adj, src)
    slat, slon = nodes[src]
    sectors = {}   # angular sector -> (road_dist, farthest node)
    for n, d in dist.items():
        if d <= 0:
            continue
        ang = math.atan2(nodes[n][0] - slat, nodes[n][1] - slon)
        sec = int((ang + math.pi) / (2 * math.pi) * n_feeders) % n_feeders
        if d > sectors.get(sec, (0, None))[0]:
            sectors[sec] = (d, n)
    feeder_paths, feeder_nodes = [], {src}
    for _, tgt in sectors.values():
        p = path_to(prev, src, tgt)
        if p and len(p) > 3:
            feeder_paths.append([nodes[n] for n in p])
            feeder_nodes.update(p)
    used = set(feeder_nodes)
    lateral_paths = []
    for p in [path_to(prev, src, sectors[s][1]) for s in sectors]:
        if not p:
            continue
        count = 0
        for u in p[1:]:
            if count >= laterals_per_feeder:
                break
            for v, w, km, hc in adj[u]:
                if hc not in LATERAL_CLASSES or v in used:
                    continue
                lp, cur, pr = [u, v], v, u
                used.add(v)
                for _ in range(7):
                    nxt = [vv for vv, ww, kk, hh in adj[cur]
                           if vv != pr and vv not in used and hh in LATERAL_CLASSES]
                    if not nxt:
                        break
                    nn = nxt[0]
                    used.add(nn)
                    lp.append(nn)
                    pr, cur = cur, nn
                if len(lp) >= 2:
                    lateral_paths.append([nodes[n] for n in lp])
                    count += 1
                if count >= laterals_per_feeder:
                    break
    return feeder_paths, lateral_paths


# --- app's current synthetic algorithm (ported from generateGrid) --------------
def mulberry32(seed):
    s = [seed & 0xFFFFFFFF]
    def r():
        s[0] = (s[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = s[0]
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return r


def synthetic_network(slat, slon, seed=42, n_feeders=6):
    rnd = mulberry32(seed + 1)
    feeders, laterals = [], []
    for f in range(n_feeders):
        ang = (f / n_feeders) * math.pi * 2 + rnd() * 0.4
        lat, lon = slat, slon
        pts = [(lat, lon)]
        for _ in range(8 + int(rnd() * 8)):
            ang += (rnd() - 0.5) * 0.5
            step = 0.004 + rnd() * 0.005
            lon += math.cos(ang) * step
            lat += math.sin(ang) * step
            pts.append((lat, lon))
        feeders.append(pts)
        for _ in range(4 + int(rnd() * 5)):
            a = pts[1 + int(rnd() * (len(pts) - 1))]
            lLat, lLon, lAng = a[0], a[1], rnd() * math.pi * 2
            lp = [(lLat, lLon)]
            for _ in range(3 + int(rnd() * 5)):
                lAng += (rnd() - 0.5) * 1.0
                ls = 0.0015 + rnd() * 0.0025
                lLon += math.cos(lAng) * ls
                lLat += math.sin(lAng) * ls
                lp.append((lLat, lLon))
            laterals.append(lp)
    return feeders, laterals


def offset_m(paths, segs, lat0):
    """Median distance (m) from each path vertex to the nearest road segment."""
    from shapely.geometry import MultiLineString, Point
    ky, kx = 111320.0, 111320.0 * math.cos(math.radians(lat0))
    roads = MultiLineString([[(p1[1] * kx, p1[0] * ky), (p2[1] * kx, p2[0] * ky)] for p1, p2 in segs])
    ds = []
    for path in paths:
        for (la, lo) in path:
            ds.append(Point(lo * kx, la * ky).distance(roads))
    ds.sort()
    return ds[len(ds) // 2] if ds else float("nan")


def make_plot(slat, slon, segs, syn, road, extent):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    (sf, sl), (rf, rl) = syn, road
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 7.4))
    fig.suptitle("Distribution laterals: synthetic random walks vs snapped to real OSM streets "
                 "(one substation, Newington CT)", fontsize=12, weight="bold")
    for ax, (fens, lats, ttl, col) in zip(
        (axL, axR),
        [(sf, sl, "CURRENT — synthetic random walks (cut across the street grid)", "#2563eb"),
         (rf, rl, "ROAD-SNAPPED — feeders/laterals follow real streets", "#dc2626")]):
        for p1, p2 in segs:                      # real street network (context)
            ax.plot([p1[1], p2[1]], [p1[0], p2[0]], color="#c9d2dc", lw=0.8, zorder=1)
        for f in fens:
            xs = [p[1] for p in f]; ys = [p[0] for p in f]
            ax.plot(xs, ys, color=col, lw=2.3, zorder=3)
        for l in lats:
            xs = [p[1] for p in l]; ys = [p[0] for p in l]
            ax.plot(xs, ys, color=col, lw=1.0, alpha=0.8, zorder=2)
        ax.scatter([slon], [slat], s=120, marker="*", color="#111", zorder=5,
                   edgecolor="#fff", linewidths=0.6)
        ax.set_title(ttl, fontsize=9.5)
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_aspect(1 / math.cos(math.radians(slat)))
        ax.set_xticks([]); ax.set_yticks([])
    axR.plot([], [], color="#c9d2dc", lw=1.2, label="real OSM streets")
    axR.plot([], [], color="#dc2626", lw=2.3, label="feeder")
    axR.plot([], [], color="#dc2626", lw=1.0, label="lateral")
    axR.scatter([], [], marker="*", color="#111", s=90, label="substation")
    axR.legend(fontsize=8, loc="lower right")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    OUT.mkdir(exist_ok=True)
    out = OUT / "road_snapped_laterals.png"
    fig.savefig(out, dpi=120, facecolor="white")
    print(f"Wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, default=41.7178)   # Newington substation
    ap.add_argument("--lon", type=float, default=-72.7510)
    ap.add_argument("--radius", type=int, default=2000)
    a = ap.parse_args()

    osm = fetch_roads(a.lat, a.lon, a.radius)
    nodes, adj, segs = build_graph(osm)
    print(f"OSM: {len(nodes)} nodes, {len(segs)} road segments")
    src = min(nodes, key=lambda n: (nodes[n][0] - a.lat) ** 2 + (nodes[n][1] - a.lon) ** 2)
    slat, slon = nodes[src]

    road = road_network(nodes, adj, src)
    syn = synthetic_network(slat, slon)
    print(f"road-snapped: {len(road[0])} feeders, {len(road[1])} laterals")
    print(f"synthetic   : {len(syn[0])} feeders, {len(syn[1])} laterals")

    syn_off = offset_m(syn[0] + syn[1], segs, slat)
    road_off = offset_m(road[0] + road[1], segs, slat)
    print(f"\nMedian distance of each network's vertices to the nearest real road:")
    print(f"  synthetic (current) : {syn_off:6.0f} m  <- lines sit off the streets")
    print(f"  road-snapped        : {road_off:6.0f} m  <- lines lie on the streets")

    las = [p[0] for _, p in nodes.items()]; los = [p[1] for _, p in nodes.items()]
    pad = 0.004
    extent = (min(los) - pad, max(los) + pad, min(las) - pad, max(las) + pad)
    make_plot(slat, slon, segs, syn, road, extent)


if __name__ == "__main__":
    main()
