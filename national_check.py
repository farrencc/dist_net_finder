"""Island-wide graph by voltage layer, with no administrative clipping.

Clipping to a county cuts every line that crosses the boundary and inflates
the component count for exactly the layers that span counties - the 110 kV
and 38 kV networks. Running the whole island at once removes that artefact,
so the component counts here are the fair test of whether each voltage layer
is a network or a scattering.
"""

from __future__ import annotations

import json
import warnings

import geopandas as gpd
import pandas as pd
from pyrosm import OSM

import ie_distribution_osm as m

warnings.filterwarnings("ignore")

OUT = "data/national.json"
CACHE = "data/raw/national_lines.gpkg"


def load_national_lines() -> gpd.GeoDataFrame:
    import os
    if os.path.exists(CACHE):
        return gpd.read_file(CACHE)
    osm = OSM(m.POWER_PBF_PATH)
    raw = osm.get_data_by_custom_criteria(
        custom_filter={"power": True}, filter_type="keep",
        tags_as_columns=list(m.TAGS_AS_COLUMNS),
        keep_nodes=False, keep_ways=True, keep_relations=True,
    ).set_crs(m.WGS84, allow_override=True)
    raw = raw[~raw.geometry.is_empty & raw.geometry.notna()]
    raw = m._expand_tags(raw)
    lines = raw[raw.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    lines = lines.explode(index_parts=False, ignore_index=True)
    lines = lines[lines.geometry.geom_type == "LineString"].copy()
    lines = lines[lines["power"].isin(m.LINE_POWER_VALUES)].copy()
    lines["voltage_v"] = [m.parse_voltage(v) for v in m.voltage_series(lines)]
    lines["band"] = [m.voltage_band(v) for v in lines["voltage_v"]]
    lines["length_km"] = lines.to_crs(m.ITM).geometry.length / 1000.0
    keep = ["power", "voltage_v", "band", "length_km", "id", "geometry"]
    lines = lines[[c for c in keep if c in lines.columns]]
    lines.to_file(CACHE, driver="GPKG")
    return lines


LAYERS = (
    ("ge_220kV", lambda L: L["voltage_v"] >= 220_000),
    ("110kV", lambda L: (L["voltage_v"] >= 110_000) & (L["voltage_v"] < 220_000)),
    ("38kV", lambda L: (L["voltage_v"] >= 38_000) & (L["voltage_v"] < 110_000)),
    ("ge_38kV_all", lambda L: L["voltage_v"] >= 38_000),
    ("MV_1to38kV", lambda L: (L["voltage_v"] >= 1_000) & (L["voltage_v"] < 38_000)),
    ("LV_lt1kV", lambda L: L["voltage_v"] < 1_000),
    ("untagged", lambda L: L["voltage_v"].isna()),
    ("all_sub110kV", lambda L: L["voltage_v"].isna() | (L["voltage_v"] < 110_000)),
)


def main():
    L = load_national_lines()
    print(f"island-wide line features: {len(L):,}  "
          f"total {L['length_km'].sum():,.0f} km")
    print(L["power"].value_counts().to_dict())
    print(f"voltage-tagged: {L['voltage_v'].notna().mean():.1%} of features, "
          f"{L.loc[L['voltage_v'].notna(),'length_km'].sum()/L['length_km'].sum():.1%} of km")

    res = {"n_features": int(len(L)), "total_km": round(float(L["length_km"].sum()), 1)}
    print(f"\n{'layer':<14} {'feats':>8} {'km':>10} {'nodes':>8} {'comps':>7} "
          f"{'largest':>9} {'largest%':>9} {'comps<=5':>9}")
    for name, pred in LAYERS:
        mask = pred(L).fillna(False) if name != "untagged" else pred(L)
        sel = L[mask]
        g = m.to_graph(sel, snap_m=1.0)
        st = m.component_stats(g)
        sizes = st.pop("sizes", [])
        st["n_features"] = int(len(sel))
        st["km"] = round(float(sel["length_km"].sum()), 1)
        st["top_5_sizes"] = sizes[:5]
        res[name] = st
        if st["n_nodes"]:
            print(f"{name:<14} {len(sel):>8,} {st['km']:>10,.0f} {st['n_nodes']:>8,} "
                  f"{st['n_components']:>7,} {st['largest']:>9,} "
                  f"{st['largest_share']:>8.1%} {st['n_size_le_5']:>9,}")
        else:
            print(f"{name:<14} {len(sel):>8,} {st['km']:>10,.0f} {'-':>8} {'-':>7}")

    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2, default=str)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
