"""A lower bound on missing MV cable, derived only from OSM's own data.

No external reference is needed for this one. OSM maps a certain number of
MV/LV transformers and substations in each area. Whatever the real network
looks like, every one of those has to be reached by cable. The minimum
spanning tree over the mapped point assets is therefore a hard lower bound
on the conductor length required to connect just the assets OSM itself
believes exist - and a very generous one, since a real distribution network
is longer than an MST (it follows streets, and it is built with open points
and ring capacity rather than as a minimal tree).

Comparing that bound with the sub-38 kV line length actually mapped gives a
completeness figure that cannot be argued away as a disagreement about ESB's
published statistics.
"""

from __future__ import annotations

import json
import warnings

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import ie_distribution_osm as m

warnings.filterwarnings("ignore")

OUT = "data/missing_cable.json"
ASSET_KINDS = ("transformer", "substation")


def mst_km(xy: np.ndarray, k: int = 12) -> float:
    """MST length in km over points, via a k-nearest-neighbour candidate graph."""
    n = len(xy)
    if n < 2:
        return 0.0
    k = min(k, n - 1)
    tree = cKDTree(xy)
    dist, idx = tree.query(xy, k=k + 1)
    g = nx.Graph()
    g.add_nodes_from(range(n))
    for i in range(n):
        for j, d in zip(idx[i][1:], dist[i][1:]):
            g.add_edge(i, int(j), weight=float(d))
    # If kNN left the graph disconnected, bridge components by nearest pair so
    # the bound stays valid rather than silently dropping assets.
    while not nx.is_connected(g):
        comps = list(nx.connected_components(g))
        base = comps[0]
        rest = [i for c in comps[1:] for i in c]
        bt = cKDTree(xy[rest])
        d, j = bt.query(xy[list(base)], k=1)
        a = list(base)[int(np.argmin(d))]
        b = rest[int(j[int(np.argmin(d))])]
        g.add_edge(a, b, weight=float(np.min(d)))
    return float(sum(d["weight"] for _, _, d in
                     nx.minimum_spanning_tree(g).edges(data=True)) / 1000.0)


def main():
    res = {}
    print(f"{'area':<38} {'assets':>7} {'MST km':>8} {'mapped':>8} {'ratio':>7}")
    for area in m.AREAS:
        d = m.load_area(area.key)
        parts = []
        if not d["nodes"].empty:
            parts.append(d["nodes"][d["nodes"]["power"].isin(ASSET_KINDS)])
        if not d["areas"].empty:
            p = d["areas"][d["areas"]["power"].isin(ASSET_KINDS)].copy()
            if len(p):
                p["geometry"] = p.geometry.representative_point()
                parts.append(p)
        if not parts:
            continue
        assets = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True),
                                  geometry="geometry", crs=m.WGS84).to_crs(m.ITM)
        xy = np.column_stack([assets.geometry.x.values, assets.geometry.y.values])
        need = mst_km(xy)

        L = d["lines"]
        mapped = float(L.loc[L["voltage_v"].isna() | (L["voltage_v"] < 38_000),
                             "length_km"].sum())
        ratio = mapped / need if need else None
        res[area.key] = {
            "label": area.label, "n_assets": int(len(assets)),
            "mst_lower_bound_km": round(need, 1),
            "mapped_sub38kV_km": round(mapped, 1),
            "mapped_over_lower_bound": round(ratio, 3) if ratio else None,
        }
        print(f"{area.label:<38} {len(assets):>7,} {need:>8,.1f} "
              f"{mapped:>8,.1f} {ratio:>6.1%}")

    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"\nwrote {OUT}")
    print("\nratio > 1 means more line is mapped than the bare minimum needed to")
    print("reach the mapped assets; ratio < 1 means the mapped network cannot")
    print("even reach the assets OSM itself contains.")


if __name__ == "__main__":
    main()
