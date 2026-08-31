"""Is the 38 kV-and-above subnetwork usable, even though MV/LV is not?

SWIS-100-IE aggregates buses to regional nodes, so it does not need MV
feeders. The question that actually decides the OSM-vs-ESB choice is
narrower: is the sub-transmission layer (38 kV, 110 kV, 220 kV, 400 kV)
mapped completely and connectedly enough to place regional nodes and
constrain inter-node transfer?
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd

import ie_distribution_osm as m

warnings.filterwarnings("ignore")

OUT = "data/subtransmission.json"


def main():
    res = {}
    for area in m.AREAS:
        d = m.load_area(area.key)
        L = d["lines"]
        row = {"label": area.label}
        for name, sel in (
            ("ge_38kV", L[L["voltage_v"].notna() & (L["voltage_v"] >= 38_000)]),
            ("ge_110kV", L[L["voltage_v"].notna() & (L["voltage_v"] >= 110_000)]),
            ("mv_only", L[L["voltage_v"].notna()
                          & (L["voltage_v"] >= 1_000) & (L["voltage_v"] < 38_000)]),
            ("untagged", L[L["voltage_v"].isna()]),
        ):
            g = m.to_graph(sel, snap_m=1.0)
            st = m.component_stats(g)
            sizes = st.pop("sizes", [])
            st["km"] = round(float(sel["length_km"].sum()), 1) if len(sel) else 0.0
            st["n_features"] = int(len(sel))
            st["top_5_sizes"] = sizes[:5]
            row[name] = st
        res[area.key] = row

        print(f"\n{area.label}")
        print(f"  {'layer':<10} {'feats':>7} {'km':>9} {'nodes':>7} {'comps':>7} "
              f"{'largest':>8} {'largest%':>9}")
        for name in ("ge_110kV", "ge_38kV", "mv_only", "untagged"):
            s = row[name]
            if s["n_nodes"] == 0:
                print(f"  {name:<10} {s['n_features']:>7} {s['km']:>9} "
                      f"{'-':>7} {'-':>7} {'-':>8} {'-':>9}")
                continue
            print(f"  {name:<10} {s['n_features']:>7,} {s['km']:>9,.1f} "
                  f"{s['n_nodes']:>7,} {s['n_components']:>7,} "
                  f"{s['largest']:>8,} {s['largest_share']:>8.1%}")

    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2, default=str)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
