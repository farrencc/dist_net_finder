"""Build the two committed data files for the graph workshop.

Run once, by the instructor, with a network connection, before the workshop:

    python data/prepare_data.py

Outputs
    data/dublin_eds.gpkg   Dublin City Electoral Divisions, EPSG:2157, one
                           census attribute attached, ready for Queen contiguity.
    data/streets.graphml   One district's drive network, for the OSMnx cameo in
                           Session 1 section 6 and the Braess block.

Neither notebook touches the network. If either output is missing at workshop
time, this script is the only thing that regenerates it.

Sources
    CSO Electoral Divisions 2022, generalised 20 m, via the Tailte Eireann
    open data ArcGIS service (data-osi.opendata.arcgis.com).
    SAPS 2022 at Electoral Division level, via cso.ie.
    OpenStreetMap via Overpass, through OSMnx.
"""

from __future__ import annotations

import argparse
import io
import sys
import time

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import requests
from libpysal.weights import Queen
from scipy.stats import skew

# --------------------------------------------------------------------------
# Configuration. Everything the instructor might want to change lives here.
# --------------------------------------------------------------------------

ED_SERVICE = (
    "https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/"
    "CSO_ELECTORAL_DIVISIONS_2022_Genralised_20m_view/FeatureServer/5/query"
)
SA_SERVICE = (
    "https://services-eu1.arcgis.com/BuS9rtTsYEV5C0xh/arcgis/rest/services/"
    "SMALL_AREA_2022_Genralised_20m_view/FeatureServer/0/query"
)
SAPS_ED_CSV = "https://www.cso.ie/en/media/csoie/census/census2022/SAPS_2022_CSOED3270923.csv"

COUNTY = "DUBLIN CITY"
ITM = 2157  # Irish Transverse Mercator
NODE_RANGE = (50, 300)

# Fallback geography if the ED count lands outside NODE_RANGE: Small Areas
# inside these Dublin City local electoral areas.
FALLBACK_LEAS = ["NORTH INNER CITY", "SOUTH EAST INNER CITY", "CABRA-GLASNEVIN"]

# Rathmines / Ranelagh. Two parallel radials into the same canal bridges, with
# side streets joining them - a network with genuine route choice, which the
# Braess block needs. A uniform grid or a single spine would not do.
STREETS_BBOX = (-6.2720, 53.3205, -6.2455, 53.3335)  # west, south, east, north
STREETS_NAME = "Rathmines / Ranelagh, Dublin"

OUT_GPKG = "dublin_eds.gpkg"
OUT_GRAPHML = "streets.graphml"

# Highest education completed, persons aged 15+. Third level here is Higher
# Certificate and above; the denominator drops "not stated" rather than
# treating it as a category. Chosen over population density because it needs
# no log transform - see the skew printed at the end.
THIRD_LEVEL = ["T10_4_HCT", "T10_4_ODNDT", "T10_4_HDPQT", "T10_4_PDT", "T10_4_DT"]
EDU_TOTAL = "T10_4_TT"
EDU_NOT_STATED = "T10_4_NST"
ATTR = "pct_third_level"
ATTR_LABEL = "% of persons 15+ with third-level education"


def _query_arcgis(service: str, where: str, timeout: int = 300) -> gpd.GeoDataFrame:
    params = {
        "where": where,
        "outFields": "*",
        "outSR": str(ITM),
        "returnGeometry": "true",
        "f": "geojson",
        "resultRecordCount": "5000",
    }
    r = requests.get(service, params=params, timeout=timeout)
    r.raise_for_status()
    payload = r.json()
    if payload.get("properties", {}).get("exceededTransferLimit"):
        raise RuntimeError(f"ArcGIS paged the response for where={where!r}; add paging")
    gdf = gpd.GeoDataFrame.from_features(payload["features"], crs=payload["crs"]["properties"]["name"])
    return gdf


def _count_arcgis(service: str, where: str) -> int:
    r = requests.get(
        service,
        params={"where": where, "returnCountOnly": "true", "f": "json"},
        timeout=120,
    )
    r.raise_for_status()
    return int(r.json()["count"])


# --------------------------------------------------------------------------
# 1. Boundaries
# --------------------------------------------------------------------------


def fetch_boundaries() -> tuple[gpd.GeoDataFrame, str]:
    national = _count_arcgis(ED_SERVICE, "1=1")
    print(f"national ED 2022 count            : {national}")

    gdf = _query_arcgis(ED_SERVICE, f"COUNTY_ENGLISH='{COUNTY}'")
    print(f"{COUNTY} EDs                  : {len(gdf)}")

    lo, hi = NODE_RANGE
    if lo <= len(gdf) <= hi:
        return gdf, "ED_GUID"

    print(
        f"\n{COUNTY} ED count {len(gdf)} is outside the {lo}-{hi} target.\n"
        f"Falling back to CSO Small Areas inside {FALLBACK_LEAS}."
    )
    quoted = ",".join(f"'{lea}'" for lea in FALLBACK_LEAS)
    gdf = _query_arcgis(SA_SERVICE, f"COUNTY_ENGLISH='{COUNTY}' AND CSO_LEA IN ({quoted})")
    print(f"fallback Small Area count         : {len(gdf)}")
    if not (lo <= len(gdf) <= hi):
        sys.exit(
            f"\nSTOP: fallback Small Area count {len(gdf)} is also outside "
            f"{lo}-{hi}. Adjust FALLBACK_LEAS and re-run."
        )
    return gdf, "SA_GUID_2022"


# --------------------------------------------------------------------------
# 2. Reproject. Centroids and distances taken in EPSG:4326 are angles, not
#    metres, and every one of them would be quietly wrong.
# --------------------------------------------------------------------------


def reproject(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print(f"CRS in                            : {gdf.crs.to_string()}")
    gdf = gdf.to_crs(ITM)
    print(f"CRS out                           : {gdf.crs.to_string()} ({gdf.crs.name})")
    return gdf.reset_index(drop=True)


# --------------------------------------------------------------------------
# 3. Attribute
# --------------------------------------------------------------------------


def attach_attribute(gdf: gpd.GeoDataFrame, key: str) -> gpd.GeoDataFrame:
    r = requests.get(SAPS_ED_CSV, timeout=600)
    r.raise_for_status()
    # The CSO file is latin-1: a couple of Irish-language place names blow up
    # a utf-8 read.
    saps = pd.read_csv(io.BytesIO(r.content), encoding="latin-1", dtype={"GUID": str})

    if key not in gdf.columns:
        raise KeyError(f"join key {key!r} missing from boundaries")
    join_on = "ED_GUID" if key.startswith("ED") else key
    merged = gdf.merge(saps, left_on=join_on, right_on="GUID", how="left", validate="m:1")

    missing = merged[EDU_TOTAL].isna().sum()
    if missing:
        sys.exit(f"\nSTOP: {missing} areas got no SAPS row on {join_on}. Check the join key.")

    denom = merged[EDU_TOTAL] - merged[EDU_NOT_STATED]
    merged[ATTR] = 100.0 * merged[THIRD_LEVEL].sum(axis=1) / denom

    keep = [c for c in gdf.columns if c != "geometry"] + [ATTR, "geometry"]
    out = gpd.GeoDataFrame(merged[keep], geometry="geometry", crs=gdf.crs)

    v = out[ATTR].to_numpy(float)
    print(f"attribute                         : {ATTR} ({ATTR_LABEL})")
    print(f"  range                           : {v.min():.1f} to {v.max():.1f}")
    print(f"  mean / sd                       : {v.mean():.1f} / {v.std(ddof=1):.1f}")
    print(f"  skew                            : {skew(v):+.2f}")
    return out


# --------------------------------------------------------------------------
# 4. Contiguity graph
# --------------------------------------------------------------------------


def build_graph(gdf: gpd.GeoDataFrame, name_col: str) -> nx.Graph:
    w = Queen.from_dataframe(gdf, use_index=False)
    G = w.to_networkx()
    nx.set_node_attributes(G, dict(enumerate(gdf[name_col])), "name")

    degs = np.array([d for _, d in G.degree()])
    print(f"nodes / edges                     : {G.number_of_nodes()} / {G.number_of_edges()}")
    print(f"mean degree                       : {degs.mean():.2f}")

    if not nx.is_connected(G):
        comps = sorted((sorted(c) for c in nx.connected_components(G)), key=len, reverse=True)
        print("\nSTOP: the Queen contiguity graph is disconnected.")
        print(f"  {len(comps)} components, sizes {[len(c) for c in comps]}")
        for c in comps[1:]:
            names = [gdf[name_col].iloc[i] for i in c]
            print(f"  detached: {names}")
        sys.exit(
            "\nA disconnected graph makes lambda_2 zero and silently breaks the\n"
            "Fiedler, diffusion and Moran blocks. Decide by hand whether to add\n"
            "bridging edges (river crossings, coastal neighbours) before shipping\n"
            "this file. Not taking the largest component automatically."
        )
    print("connected                         : yes")
    return G


# --------------------------------------------------------------------------
# 5. Street network
# --------------------------------------------------------------------------


def fetch_streets(attempts: int = 8) -> nx.MultiDiGraph:
    import osmnx as ox

    ox.settings.requests_timeout = 300
    ox.settings.overpass_rate_limit = True

    last = None
    for attempt in range(attempts):
        try:
            return ox.graph_from_bbox(
                bbox=STREETS_BBOX, network_type="drive", truncate_by_edge=True
            )
        except Exception as exc:  # Overpass rate-limits and drops connections
            last = exc
            wait = 15 * (attempt + 1)
            print(f"  Overpass attempt {attempt + 1} failed ({type(exc).__name__}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {attempts} attempts: {last}")


# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-streets", action="store_true", help="rebuild the .gpkg only")
    ap.add_argument("--out", default=".", help="output directory (default: this one)")
    args = ap.parse_args()

    gdf, key = fetch_boundaries()
    gdf = reproject(gdf)
    name_col = "ED_ENGLISH" if key.startswith("ED") else "SA_PUB2022"
    gdf = gdf.sort_values(name_col).reset_index(drop=True)  # stable row order
    gdf = attach_attribute(gdf, key)
    G = build_graph(gdf, name_col)

    gpkg = f"{args.out.rstrip('/')}/{OUT_GPKG}"
    gdf.to_file(gpkg, layer="eds", driver="GPKG")

    streets = None
    if not args.skip_streets:
        print(f"\nfetching {STREETS_NAME} drive network from Overpass ...")
        streets = fetch_streets()
        graphml = f"{args.out.rstrip('/')}/{OUT_GRAPHML}"
        import osmnx as ox

        ox.save_graphml(streets, graphml)

    print("\n" + "=" * 62)
    print("SUMMARY")
    print("=" * 62)
    degs = np.array([d for _, d in G.degree()])
    v = gdf[ATTR].to_numpy(float)
    print(f"  areas (nodes)      {G.number_of_nodes()}")
    print(f"  contiguity edges   {G.number_of_edges()}")
    print(f"  mean degree        {degs.mean():.2f}  (min {degs.min()}, max {degs.max()})")
    print(f"  connected          {nx.is_connected(G)}")
    print(f"  attribute          {ATTR}")
    print(f"  attribute skew     {skew(v):+.2f}")
    print(f"  CRS                {gdf.crs.to_string()}")
    print(f"  written            {gpkg}")
    if streets is not None:
        print(f"  street network     {streets.number_of_nodes()} nodes, "
              f"{streets.number_of_edges()} edges ({STREETS_NAME})")
        print(f"  written            {graphml}")
    print("=" * 62)


if __name__ == "__main__":
    main()
