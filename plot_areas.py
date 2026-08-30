"""Step 4 - maps and GeoPackages, one per analysis area.

Everything is projected to EPSG:2157 (Irish Transverse Mercator) so distances
on the page are metres on the ground.  Lines are coloured by voltage band;
substations, transformers and poles are drawn as distinct point symbols.
"""

from __future__ import annotations

import os
import warnings

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

import ie_distribution_osm as m

warnings.filterwarnings("ignore")

OUT_DIR = "data"
DPI = 160

BAND_STYLE = {
    "LV (<1 kV)":                  {"color": "#7f8c8d", "lw": 0.4},
    "MV (1-<38 kV)":               {"color": "#2f7fd1", "lw": 0.5},
    "38 kV":                       {"color": "#e08214", "lw": 1.0},
    "HV >=110 kV (transmission)":  {"color": "#c0392b", "lw": 1.6},
    m.UNKNOWN_BAND:                {"color": "#b9c4cc", "lw": 0.4},
}
# Drawn in this order so the sparse high-voltage lines sit on top.
BAND_DRAW_ORDER = [m.UNKNOWN_BAND, "LV (<1 kV)", "MV (1-<38 kV)",
                   "38 kV", "HV >=110 kV (transmission)"]

POINT_STYLE = {
    "substation":  {"color": "#111111", "marker": "s", "size": 26, "z": 6},
    "transformer": {"color": "#7b2cbf", "marker": "^", "size": 14, "z": 5},
    "pole":        {"color": "#95a5a6", "marker": ".", "size": 0.7, "z": 3},
}


def write_gpkg(data: dict, path: str) -> None:
    """Write `lines` and `nodes` layers in EPSG:2157."""
    if os.path.exists(path):
        os.remove(path)
    drop = ("tags",)  # dict/JSON blob, not writable to GPKG

    lines = data["lines"]
    if not lines.empty:
        out = lines.drop(columns=[c for c in drop if c in lines.columns])
        out = out.to_crs(m.ITM)
        for c in out.columns:
            if c != "geometry" and out[c].dtype == object:
                out[c] = out[c].astype(str)
        out.to_file(path, layer="lines", driver="GPKG")

    # `nodes` = point assets, plus substation/transformer polygons reduced to
    # their representative point so the layer is a single geometry type.
    parts = []
    if not data["nodes"].empty:
        parts.append(data["nodes"])
    polys = data["areas"]
    if not polys.empty:
        rp = polys.copy()
        rp["geometry"] = rp.geometry.representative_point()
        parts.append(rp)
    if parts:
        nodes = pd.concat(parts, ignore_index=True)
        nodes = gpd.GeoDataFrame(nodes, geometry="geometry", crs=m.WGS84)
        nodes = nodes.drop(columns=[c for c in drop if c in nodes.columns])
        nodes = nodes.to_crs(m.ITM)
        for c in nodes.columns:
            if c != "geometry" and nodes[c].dtype == object:
                nodes[c] = nodes[c].astype(str)
        nodes.to_file(path, layer="nodes", driver="GPKG")


def plot_area(key: str) -> None:
    area = m.AREAS_BY_KEY[key]
    data = m.load_area(key)
    lines, nodes, polys = data["lines"], data["nodes"], data["areas"]

    boundary = gpd.GeoSeries([data["boundary"]], crs=m.WGS84).to_crs(m.ITM)
    fig, ax = plt.subplots(figsize=(9.5, 10.5))
    boundary.boundary.plot(ax=ax, color="#333333", lw=0.9, zorder=1)
    boundary.plot(ax=ax, color="#fbfbfa", zorder=0)

    lines_itm = lines.to_crs(m.ITM) if not lines.empty else lines
    present_bands = []
    for band in BAND_DRAW_ORDER:
        sel = lines_itm[lines_itm["band"] == band] if not lines_itm.empty else lines_itm
        if len(sel) == 0:
            continue
        st = BAND_STYLE[band]
        sel.plot(ax=ax, color=st["color"], lw=st["lw"], zorder=2 + BAND_DRAW_ORDER.index(band))
        present_bands.append((band, st, float(sel["length_km"].sum()), len(sel)))

    # Point assets. Substation polygons are collapsed to a point so a
    # substation reads the same whether it was mapped as a node or an area.
    pt_parts = []
    if not nodes.empty:
        pt_parts.append(nodes)
    if not polys.empty:
        rp = polys.copy()
        rp["geometry"] = rp.geometry.representative_point()
        pt_parts.append(rp)
    present_points = []
    if pt_parts:
        allpts = gpd.GeoDataFrame(pd.concat(pt_parts, ignore_index=True),
                                  geometry="geometry", crs=m.WGS84).to_crs(m.ITM)
        for kind in ("pole", "transformer", "substation"):
            sel = allpts[allpts["power"] == kind]
            if len(sel) == 0:
                continue
            st = POINT_STYLE[kind]
            sel.plot(ax=ax, color=st["color"], marker=st["marker"],
                     markersize=st["size"], zorder=st["z"],
                     linewidth=0.3 if kind == "substation" else 0)
            present_points.append((kind, st, len(sel)))

    handles = [Line2D([0], [0], color=st["color"], lw=max(st["lw"], 1.4),
                      label=f"{band}  -  {km:,.0f} km ({n:,})")
               for band, st, km, n in reversed(present_bands)]
    handles += [Line2D([0], [0], color=st["color"], marker=st["marker"], lw=0,
                       markersize=7 if kind != "pole" else 4,
                       label=f"{kind}  ({n:,})")
                for kind, st, n in reversed(present_points)]
    ax.legend(handles=handles, loc="upper left", fontsize=7.5, frameon=True,
              framealpha=0.93, title="voltage band / asset", title_fontsize=8)

    total_km = float(lines["length_km"].sum()) if not lines.empty else 0.0
    frac = (float(lines["voltage_v"].notna().mean()) if not lines.empty else 0.0)
    ax.set_title(
        f"{area.label}\n"
        f"OpenStreetMap power features - {len(lines):,} line features, "
        f"{total_km:,.0f} km, {frac:.0%} voltage-tagged\n"
        f"Geofabrik ireland-and-northern-ireland extract - EPSG:2157",
        fontsize=10.5)
    ax.set_xlabel("ITM easting (m)", fontsize=8)
    ax.set_ylabel("ITM northing (m)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_aspect("equal")

    os.makedirs(OUT_DIR, exist_ok=True)
    png = os.path.join(OUT_DIR, f"{key}_power.png")
    fig.tight_layout()
    fig.savefig(png, dpi=DPI)
    plt.close(fig)

    gpkg = os.path.join(OUT_DIR, f"{key}_power.gpkg")
    write_gpkg(data, gpkg)
    print(f"  {png}  |  {gpkg}", flush=True)


if __name__ == "__main__":
    for a in m.AREAS:
        print(a.label, flush=True)
        plot_area(a.key)
