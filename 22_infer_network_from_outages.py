"""
22_infer_network_from_outages.py -- Can you recover the distribution network
from outage LOCATIONS alone?

The premise: a real distribution grid is a radial tree rooted at substations,
and outages only happen ON that tree. So a dense enough scatter of outage
points is a noisy sample of the network's geometry, and the network should be
recoverable from the points alone -- no topology data needed.

Method (uses ONLY substation positions + outage lat/lon):
  1. Assign each outage to its nearest substation -> inferred service territory.
  2. Per territory, build the exact Euclidean MST over {substation} u {outages}.
     A radial network IS a tree, and the MST is the cheapest tree spanning the
     sampled points, so it is the natural estimator of that tree.
  3. Root the MST at the substation and count each node's SUBTREE SIZE (how many
     outages sit downstream of it) as a feeder/lateral discriminator.

Why this is checkable rather than hand-wavy: the simulator places every outage
on a real segment and records the truth on the point (kind/fi/li/sub_id -- see
outages.push() in 03_grid_simulation.html). We infer using lat/lon only, then
score against that withheld truth.

RESULT -- the answer is HALF yes, and the negative half is the interesting one:

  * SERVICE TERRITORIES: ~89% recoverable. Nearest-substation assignment nearly
    reproduces which substation the simulator actually fed each outage from,
    because territories are big contiguous regions and the real assignment is
    close to Voronoi. This part genuinely works.

  * FEEDER vs LATERAL: NOT recoverable. Measured, not assumed -- every geometric
    feature tried is at chance:
        MST subtree size   medians identical (5.0 vs 5.0); NO threshold beats
                           the always-guess-"lateral" baseline of 73.8%
        dist to substation AUC 0.485  (worse than chance)
        local 5-NN density AUC 0.550  (barely above chance)
    The reason is structural: feeders and laterals are spatially INTERLEAVED --
    a lateral hangs off its feeder in the same street -- so the two classes
    occupy the same space and no purely geometric feature can separate them.
    The MST connects nearest neighbours regardless of which real line they sit
    on, so its subtree size measures local point density, not electrical
    hierarchy. Recovering feeder-vs-lateral needs non-geometric signal
    (customers-per-outage, restoration order, switching//protection behaviour).

So: outage locations are enough to recover WHERE the territories are, but not
the hierarchy WITHIN one. Reported rather than tuned away -- a magic threshold
here would only be fitting noise.

NOTE ON DATA: the REAL Eversource live feed (17_fetch_live_outages.py) only ever
captured blue-sky days -- 21-24 outage points statewide. That is far too sparse
to recover anything, so this runs on the simulator's own storm, where ground
truth exists. Point it at a real dense storm snapshot when one is captured.

Usage:
    python 22_infer_network_from_outages.py --storm isaias_2020 --outages 20450
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "data"
OUT_DIR = HERE / "output"

FEEDER_MIN_SUBTREE = 8   # subtree size at/above which an outage reads as trunk


def _harness():
    """Reuse 16_calibrate's V8 harness verbatim (module name starts with a digit)."""
    spec = importlib.util.spec_from_file_location("_cal", HERE / "16_calibrate_against_real_storms.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def generate_truth(track: str, n_out: int, seed_crews: int = 300):
    """Run the real simulator headless and pull back the network + outages."""
    from py_mini_racer import py_mini_racer
    m = _harness()
    script = m._extract_script()
    data_inject = m._load_data_inject()
    land_geo = json.loads((DATA / "connecticut_land_boundary.json").read_text(encoding="utf-8"))[0]["geojson"]
    shim = m._SHIM_TEMPLATE % {"n_out": n_out, "m_crew": seed_crews, "track": track}

    ctx = py_mini_racer.MiniRacer()
    ctx.eval(shim + "\n" + data_inject + "\n" + script)
    ctx.eval(f"countyGeo = {json.dumps(land_geo)}; buildInsideBitmap(countyGeo);")
    ctx.eval("var _g=false; generateGrid().then(()=>{_g=true;}).catch(e=>{__log.push('GRID '+e);});",
             timeout=120_000)
    ctx.eval("var _s=false; simulateStorm().then(()=>{_s=true;}).catch(e=>{__log.push('STORM '+e);});",
             timeout=120_000)

    subs = json.loads(ctx.eval("JSON.stringify(substations.map(s=>[s.lat,s.lon]))"))
    # Only the fields we need -- the full outage objects are far larger.
    outs = json.loads(ctx.eval(
        "JSON.stringify(storm.outages.map(o=>[o.lat,o.lon,o.kind,o.fi,o.li,o.sub_id]))"))
    return np.array(subs, dtype=float), outs


def mst_edges(pts: np.ndarray):
    """Exact Euclidean MST over a small point set. Returns list of (i,j)."""
    from scipy.sparse.csgraph import minimum_spanning_tree
    from scipy.spatial.distance import squareform, pdist
    n = len(pts)
    if n < 2:
        return []
    d = squareform(pdist(pts))
    t = minimum_spanning_tree(d).tocoo()
    return list(zip(t.row.tolist(), t.col.tolist()))


def subtree_sizes(n: int, edges, root: int = 0) -> np.ndarray:
    """Outages downstream of each node once the MST is rooted at the substation."""
    adj = [[] for _ in range(n)]
    for i, j in edges:
        adj[i].append(j); adj[j].append(i)
    order, parent, seen = [], [-1]*n, [False]*n
    stack = [root]; seen[root] = True
    while stack:                                  # iterative DFS: recursion blows up at 20k
        u = stack.pop(); order.append(u)
        for v in adj[u]:
            if not seen[v]:
                seen[v] = True; parent[v] = u; stack.append(v)
    size = np.ones(n, dtype=int)
    for u in reversed(order):                     # children settle before parents
        if parent[u] >= 0:
            size[parent[u]] += size[u]
    return size


def infer(subs: np.ndarray, outs) -> dict:
    from scipy.spatial import cKDTree
    lat = np.array([o[0] for o in outs]); lon = np.array([o[1] for o in outs])
    # The simulator tags segments 'f'/'l' (see allSegs in 03_grid_simulation.html).
    true_kind = np.array(["feeder" if o[2] == "f" else "lateral" for o in outs])
    true_sub = np.array([o[5] for o in outs])

    # 1. nearest substation -> inferred territory (lon/lat scaled so degrees are
    #    roughly isotropic at CT's latitude; otherwise east-west is overweighted)
    kx = np.cos(np.radians(41.6))
    P = np.column_stack((lon * kx, lat))
    S = np.column_stack((subs[:, 1] * kx, subs[:, 0]))
    _d, inferred_sub = cKDTree(S).query(P)

    pred_kind = np.empty(len(outs), dtype=object)
    subtree = np.zeros(len(outs), dtype=int)
    inferred_edges = []
    for s in range(len(subs)):
        idx = np.flatnonzero(inferred_sub == s)
        if len(idx) == 0:
            continue
        # node 0 = the substation itself; nodes 1.. = its outages
        pts = np.vstack((S[s][None, :], P[idx]))
        e = mst_edges(pts)
        size = subtree_sizes(len(pts), e, root=0)
        for k, oi in enumerate(idx, start=1):
            subtree[oi] = size[k]
            pred_kind[oi] = "feeder" if size[k] >= FEEDER_MIN_SUBTREE else "lateral"
        for i, j in e:                            # keep geometry for the plot
            a = subs[s][::-1] if i == 0 else np.array([lon[idx[i-1]], lat[idx[i-1]]])
            b = subs[s][::-1] if j == 0 else np.array([lon[idx[j-1]], lat[idx[j-1]]])
            hi = max(size[i], size[j])
            inferred_edges.append((a, b, hi))

    # Rival geometric features, scored in report() so the negative result is
    # measured across several candidates rather than pinned on one.
    dsub, _ = cKDTree(S).query(P)
    dknn, _ = cKDTree(P).query(P, k=6)
    dens = dknn[:, 1:].mean(axis=1)
    return dict(lat=lat, lon=lon, true_kind=true_kind, true_sub=true_sub,
                inferred_sub=inferred_sub, pred_kind=pred_kind, edges=inferred_edges,
                subtree=subtree, dsub=dsub, dens=dens)


def _auc(x: np.ndarray, y: np.ndarray) -> float:
    """Rank-based AUC (no sklearn dependency). 0.5 == feature carries no signal."""
    r = np.argsort(np.argsort(x))
    n1 = int(y.sum()); n0 = int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((r[y].sum() - n1 * (n1 - 1) / 2) / (n1 * n0))


def report(r: dict) -> None:
    n = len(r["lat"])
    sub_acc = float(np.mean(r["inferred_sub"] == r["true_sub"]))
    tk, pk = r["true_kind"], r["pred_kind"]
    base = max(float(np.mean(tk == "feeder")), float(np.mean(tk == "lateral")))
    print(f"\noutages: {n:,}")
    print(f"true mix: feeder {100*np.mean(tk=='feeder'):.1f}% / lateral {100*np.mean(tk=='lateral'):.1f}%")

    print(f"\n1) SERVICE TERRITORY -- nearest substation vs the sub the sim actually fed from")
    print(f"   accuracy: {100*sub_acc:.1f}%   <- RECOVERABLE")

    print(f"\n2) FEEDER-vs-LATERAL -- is there ANY geometric signal?")
    isf = tk == "feeder"
    for name, feat in (("MST subtree size", r["subtree"]),
                       ("dist to nearest substation", r["dsub"]),
                       ("local density (5-NN dist)", r["dens"])):
        print(f"   AUC[{name:26s}] = {_auc(feat, isf):.4f}")
    print(f"   (0.50 = no information. Feeders/laterals are spatially interleaved,")
    print(f"    so no purely geometric feature separates them.)")
    # Best achievable over ALL thresholds, to show tuning cannot rescue it.
    sz = r["subtree"]
    best_t, best_acc = None, 0.0
    for t in range(2, 301):
        acc = float(np.mean((sz >= t) == isf))
        if acc > best_acc:
            best_acc, best_t = acc, t
    print(f"   best subtree threshold over 2..300: t={best_t} -> {100*best_acc:.1f}%")
    print(f"   always-guess-'lateral' baseline:          {100*base:.1f}%")
    # A hair over baseline is not a win: the "best" threshold gets there only by
    # pushing every point to the majority class. Demand a real margin.
    MARGIN = 0.02
    beats = best_acc > base + MARGIN
    print(f"   VERDICT: {'beats' if beats else 'ties/loses to'} the baseline"
          f" (needs > +{100*MARGIN:.0f}pts to count) ->")
    print(f"            feeder/lateral is {'RECOVERABLE' if beats else 'NOT recoverable'}"
          f" from outage locations alone.")


def make_plot(subs, r, track):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(15, 6.4))
    sub_acc = 100 * float(np.mean(r["inferred_sub"] == r["true_sub"]))
    fig.suptitle(f"Recovering the distribution network from outage LOCATIONS alone — {track}",
                 fontsize=13, weight="bold")

    # LEFT: the half that works -- territory recovery. Colour by inferred
    # substation; mark the outages where that guess disagrees with the truth.
    rng = np.random.default_rng(3)
    palette = rng.random((len(subs), 3)) * 0.75 + 0.15
    axL.scatter(r["lon"], r["lat"], s=1.2, c=palette[r["inferred_sub"]])
    wrong = r["inferred_sub"] != r["true_sub"]
    axL.scatter(r["lon"][wrong], r["lat"][wrong], s=3.5, facecolor="none",
                edgecolor="#111", linewidths=0.35, label=f"mis-assigned ({wrong.sum():,})")
    axL.scatter(subs[:, 1], subs[:, 0], s=16, marker="s", c="#dc2626",
                edgecolor="k", linewidths=0.3, label="substations", zorder=5)
    axL.set_title(f"WORKS — inferred service territories (nearest substation)\n"
                  f"{sub_acc:.1f}% match the substation the simulator actually used", fontsize=9)
    axL.legend(fontsize=7, markerscale=3)

    # RIGHT: the inferred skeleton. Coloured by TRUE class to show the point --
    # trunk-vs-twig doesn't line up with feeder-vs-lateral at all.
    segs = [(tuple(a), tuple(b)) for a, b, _h in r["edges"]]
    hi = np.array([h for _a, _b, h in r["edges"]])
    lc = LineCollection(segs, linewidths=np.clip(0.2 + hi / 60.0, 0.2, 2.0),
                        colors="#64748b", alpha=0.55)
    axR.add_collection(lc)
    tk = r["true_kind"]
    axR.scatter(r["lon"][tk == "lateral"], r["lat"][tk == "lateral"], s=1.0,
                c="#93c5fd", label="truly on a lateral")
    axR.scatter(r["lon"][tk == "feeder"], r["lat"][tk == "feeder"], s=1.0,
                c="#1d4ed8", label="truly on a feeder")
    axR.scatter(subs[:, 1], subs[:, 0], s=16, marker="s", c="#dc2626", zorder=5)
    axR.set_xlim(axL.get_xlim()); axR.set_ylim(axL.get_ylim())
    axR.set_title("FAILS — inferred MST skeleton (width = downstream load).\n"
                  "Feeder/lateral truth is interleaved, so no threshold recovers it "
                  "(AUC ~0.5)", fontsize=9)
    axR.legend(fontsize=7, markerscale=5)
    for ax in (axL, axR):
        ax.set_aspect(1 / np.cos(np.radians(41.6))); ax.grid(alpha=0.25)
        ax.set_xlabel("lon"); ax.set_ylabel("lat")

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "inferred_network.png"
    fig.savefig(out, dpi=115, facecolor="white")
    print(f"\nWrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storm", default="isaias_2020")
    ap.add_argument("--outages", type=int, default=20450)
    a = ap.parse_args()
    print(f"Generating ground-truth network + outages for {a.storm} (n={a.outages})...")
    subs, outs = generate_truth(a.storm, a.outages)
    print(f"  {len(subs)} substations, {len(outs):,} outages placed on real segments")
    r = infer(subs, outs)
    report(r)
    make_plot(subs, r, a.storm)


if __name__ == "__main__":
    main()
