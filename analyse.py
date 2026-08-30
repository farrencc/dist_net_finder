"""Coverage and topology diagnostics for OSM Irish distribution network data.

Writes data/analysis.json and prints a readable report.  Answers, per area:
feature counts by power tag and by voltage band, the fraction of line
features carrying any voltage tag, circuit length by band, the underground
(power=cable) to overhead (power=minor_line) ratio, and the connected
component-size distribution of the graph.
"""

from __future__ import annotations

import json
import os
import warnings

import numpy as np
import pandas as pd

import ie_distribution_osm as m

warnings.filterwarnings("ignore")

OUT_JSON = "data/analysis.json"
SNAP_SWEEP = (0.1, 1.0, 5.0, 25.0, 100.0)


def hist_buckets(sizes):
    """Bucket component sizes so the shape of the distribution is visible."""
    arr = np.asarray(sizes)
    edges = [(1, 1), (2, 2), (3, 5), (6, 10), (11, 25), (26, 50),
             (51, 100), (101, 500), (501, 10**9)]
    out = {}
    for lo, hi in edges:
        sel = (arr >= lo) & (arr <= hi)
        label = f"{lo}" if lo == hi else (f"{lo}+" if hi == 10**9 else f"{lo}-{hi}")
        out[label] = {"n_components": int(sel.sum()),
                      "n_nodes": int(arr[sel].sum())}
    return out


def analyse_area(key: str) -> dict:
    area = m.AREAS_BY_KEY[key]
    data = m.load_area(key)
    lines, nodes, polys = data["lines"], data["nodes"], data["areas"]

    area_km2 = (
        m.gpd.GeoSeries([data["boundary"]], crs=m.WGS84)
        .to_crs(m.ITM).area.iloc[0] / 1e6
    )

    res = {"key": key, "label": area.label, "osm_relation": area.osm_id,
           "admin_level": area.admin_level, "area_km2": round(float(area_km2), 1)}

    # --- counts by power tag -------------------------------------------- #
    res["line_counts_by_power"] = (
        lines["power"].value_counts().to_dict() if not lines.empty else {}
    )
    res["node_counts_by_power"] = (
        nodes["power"].value_counts().to_dict() if not nodes.empty else {}
    )
    res["area_counts_by_power"] = (
        polys["power"].value_counts().to_dict() if not polys.empty else {}
    )

    # --- voltage tagging ------------------------------------------------- #
    n_lines = len(lines)
    n_volt = int(lines["voltage_v"].notna().sum()) if n_lines else 0
    res["n_line_features"] = n_lines
    res["n_line_features_with_voltage"] = n_volt
    res["frac_lines_with_voltage"] = round(n_volt / n_lines, 4) if n_lines else None

    # Same, weighted by length rather than by feature - a fairer measure,
    # since untagged features are often short stubs.
    if n_lines:
        tagged_km = float(lines.loc[lines["voltage_v"].notna(), "length_km"].sum())
        total_km = float(lines["length_km"].sum())
        res["total_km"] = round(total_km, 1)
        res["frac_km_with_voltage"] = round(tagged_km / total_km, 4) if total_km else None
    else:
        res["total_km"] = 0.0
        res["frac_km_with_voltage"] = None

    # Voltage tagging split by power tag, so overhead vs underground is visible.
    by_tag = {}
    for tag in ("minor_line", "line", "cable"):
        sub = lines[lines["power"] == tag] if n_lines else lines
        if len(sub) == 0:
            continue
        by_tag[tag] = {
            "n": int(len(sub)),
            "km": round(float(sub["length_km"].sum()), 1),
            "frac_with_voltage": round(float(sub["voltage_v"].notna().mean()), 4),
        }
    res["by_power_tag"] = by_tag

    # --- counts and length by band --------------------------------------- #
    if n_lines:
        g = lines.groupby("band")
        res["km_by_band"] = {k: round(float(v), 1)
                             for k, v in g["length_km"].sum().items()}
        res["count_by_band"] = {k: int(v) for k, v in g.size().items()}
        res["km_by_band_per_1000km2"] = {
            k: round(float(v) / area_km2 * 1000, 1)
            for k, v in g["length_km"].sum().items()
        }
        res["distinct_voltages"] = {
            str(int(k)): int(v)
            for k, v in lines["voltage_v"].dropna().value_counts().head(15).items()
        }
    else:
        res["km_by_band"] = {}
        res["count_by_band"] = {}
        res["km_by_band_per_1000km2"] = {}
        res["distinct_voltages"] = {}

    # --- underground vs overhead ----------------------------------------- #
    cable = lines[lines["power"] == "cable"] if n_lines else lines
    minor = lines[lines["power"] == "minor_line"] if n_lines else lines
    res["cable_vs_minor_line"] = {
        "n_cable": int(len(cable)),
        "n_minor_line": int(len(minor)),
        "count_ratio": round(len(cable) / len(minor), 5) if len(minor) else None,
        "km_cable": round(float(cable["length_km"].sum()), 2) if len(cable) else 0.0,
        "km_minor_line": round(float(minor["length_km"].sum()), 1) if len(minor) else 0.0,
        "km_ratio": (round(float(cable["length_km"].sum())
                           / float(minor["length_km"].sum()), 5)
                     if len(minor) and float(minor["length_km"].sum()) else None),
    }
    # location=underground is the other way underground plant is tagged.
    if n_lines and "location" in lines.columns:
        loc = lines["location"].astype("object")
        res["location_tag_counts"] = {
            str(k): int(v) for k, v in loc.value_counts().head(8).items()
        }
        res["n_lines_location_underground"] = int((loc == "underground").sum())
    else:
        res["location_tag_counts"] = {}
        res["n_lines_location_underground"] = 0

    # --- graph ------------------------------------------------------------ #
    dist = m.distribution_only(lines)
    res["n_distribution_line_features"] = int(len(dist))
    res["distribution_km"] = round(float(dist["length_km"].sum()), 1) if len(dist) else 0.0

    for label, frame in (("all_lines", lines), ("distribution_only", dist)):
        g = m.to_graph(frame, snap_m=1.0)
        st = m.component_stats(g)
        st["histogram"] = hist_buckets(st["sizes"]) if st["sizes"] else {}
        st["top_10_sizes"] = st["sizes"][:10] if st["sizes"] else []
        st.pop("sizes", None)
        res[f"graph_{label}_snap1m"] = st

    return res


def sweep_snapping(key: str) -> list:
    data = m.load_area(key)
    dist = m.distribution_only(data["lines"])
    rows = []
    for snap in SNAP_SWEEP:
        g = m.to_graph(dist, snap_m=snap)
        st = m.component_stats(g)
        sizes = st.pop("sizes", [])
        st["snap_m"] = snap
        st["top_5_sizes"] = sizes[:5]
        rows.append(st)
    return rows


def main():
    results = {}
    for area in m.AREAS:
        print(f"... {area.label}", flush=True)
        results[area.key] = analyse_area(area.key)
    print("... snapping sweep (Kilkenny)", flush=True)
    results["_snap_sweep_kilkenny"] = sweep_snapping("kilkenny")
    print("... snapping sweep (Dublin City)", flush=True)
    results["_snap_sweep_dublin_city"] = sweep_snapping("dublin_city")

    os.makedirs("data", exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
