"""County-level national sweep: is OSM's mapped network a usable spatial prior?

Loads every power feature on the island once, then attributes it to Republic
of Ireland counties (OSM admin_level 6) and reports mapped sub-110 kV circuit
length, pole count and MV/LV transformer count per county, normalised by area.

The question this answers is not "is the topology right" (it is not - see
analyse.py) but "does the *density* of what has been mapped track anything a
capacity-expansion model would want to allocate, such as demand?"
"""

from __future__ import annotations

import json
import os
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from pyrosm import OSM

import ie_distribution_osm as m

warnings.filterwarnings("ignore")

OUT = "data/county_sweep.csv"


COUNTY_CACHE = "data/raw/counties.gpkg"


def load_counties() -> gpd.GeoDataFrame:
    # get_boundaries() re-parses every admin relation on the island and takes
    # ~6 minutes; cache the 30-odd county polygons we actually want.
    if os.path.exists(COUNTY_CACHE):
        return gpd.read_file(COUNTY_CACHE)
    osm = OSM(m.BOUNDS_PBF_PATH)
    b = osm.get_boundaries(boundary_type="administrative")
    b = b[b["admin_level"].astype(str) == "6"].copy()
    b = b[b["name"].astype(str).str.startswith("County ")
          | b["name"].astype(str).isin(["Dublin", "Cork", "Galway", "Limerick", "Waterford"])]
    rows = []
    for name, grp in b.groupby("name"):
        from shapely.ops import unary_union
        rows.append({"name": str(name), "geometry": unary_union(grp.geometry.values)})
    out = gpd.GeoDataFrame(rows, geometry="geometry", crs=m.WGS84)
    out["area_km2"] = out.to_crs(m.ITM).area / 1e6
    out = out[out["area_km2"] > 100].reset_index(drop=True)
    os.makedirs(os.path.dirname(COUNTY_CACHE), exist_ok=True)
    out.to_file(COUNTY_CACHE, driver="GPKG")
    return out


def main():
    osm = OSM(m.POWER_PBF_PATH)
    raw = osm.get_data_by_custom_criteria(
        custom_filter={"power": True}, filter_type="keep",
        tags_as_columns=list(m.TAGS_AS_COLUMNS),
        keep_nodes=True, keep_ways=True, keep_relations=True,
    ).set_crs(m.WGS84, allow_override=True)
    raw = raw[~raw.geometry.is_empty & raw.geometry.notna()]
    raw = m._expand_tags(raw)
    raw["voltage_v"] = [m.parse_voltage(v) for v in m.voltage_series(raw)]

    gt = raw.geometry.geom_type
    lines = raw[gt.isin(["LineString", "MultiLineString"])].explode(
        index_parts=False, ignore_index=True)
    lines = lines[lines.geometry.geom_type == "LineString"].copy()
    lines = lines[lines["power"].isin(m.LINE_POWER_VALUES)].copy()
    pts = raw[gt == "Point"].copy()
    polys = raw[gt.isin(["Polygon", "MultiPolygon"])].copy()

    counties = load_counties()

    # A single spatial join, not a per-county clip loop. Clipping every line
    # against every county polygon in turn ran for over 40 minutes; this runs
    # in seconds. Lines are attributed to the county containing their
    # midpoint - at county scale the few features straddling a boundary move
    # none of these numbers.
    lines_itm = lines.to_crs(m.ITM).reset_index(drop=True)
    lines_itm["km"] = lines_itm.geometry.length / 1000.0
    mids = gpd.GeoDataFrame(
        {"km": lines_itm["km"], "power": lines_itm["power"],
         "voltage_v": lines_itm["voltage_v"]},
        geometry=lines_itm.geometry.interpolate(0.5, normalized=True),
        crs=m.ITM,
    )
    cty_itm = counties.to_crs(m.ITM).reset_index(drop=True)
    # County outlines carry full coastline detail, which makes a
    # point-in-polygon join against 650k points far slower than it needs to
    # be. 100 m simplification is well below the scale of any question here.
    cty_itm["geometry"] = cty_itm.geometry.simplify(100).buffer(0)

    def tag(gdf):
        return gpd.sjoin(gdf, cty_itm[["name", "geometry"]], how="inner",
                         predicate="within")

    lj = tag(mids)
    lj = lj[lj["voltage_v"].isna() | (lj["voltage_v"] < m.DISTRIBUTION_MAX_V)]
    pj = tag(pts.to_crs(m.ITM)[["power", "geometry"]])
    qj = tag(gpd.GeoDataFrame(
        polys[["power"]].reset_index(drop=True),
        geometry=polys.to_crs(m.ITM).geometry.representative_point().values,
        crs=m.ITM))

    recs = []
    for _, cty in cty_itm.iterrows():
        name = cty["name"]
        d = lj[lj["name"] == name]
        p = pj[pj["name"] == name]
        q = qj[qj["name"] == name]
        km = float(d["km"].sum())
        recs.append({
            "county": name,
            "area_km2": round(float(cty["area_km2"]), 1),
            "dist_km": round(km, 1),
            "dist_km_per_1000km2": round(km / cty["area_km2"] * 1000, 1),
            "minor_line_km": round(float(d.loc[d["power"] == "minor_line", "km"].sum()), 1),
            "cable_km": round(float(d.loc[d["power"] == "cable", "km"].sum()), 1),
            "frac_km_with_voltage": round(
                float(d.loc[d["voltage_v"].notna(), "km"].sum()) / max(km, 1e-9), 3),
            "n_poles": int((p["power"] == "pole").sum()),
            "poles_per_km2": round(float((p["power"] == "pole").sum()) / cty["area_km2"], 2),
            "n_transformers": int((p["power"] == "transformer").sum()
                                  + (q["power"] == "transformer").sum()),
            "n_substations": int((p["power"] == "substation").sum()
                                 + (q["power"] == "substation").sum()),
        })

    df = pd.DataFrame(recs).sort_values("dist_km_per_1000km2", ascending=False)
    os.makedirs("data", exist_ok=True)
    df.to_csv(OUT, index=False)
    pd.set_option("display.width", 250)
    print(df.to_string(index=False))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
