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

# Voltage band is an ordered quantity, so the bands take a single-hue ordinal
# ramp (light = low voltage, dark = high) rather than a set of unrelated hues -
# a rainbow would imply the bands are unordered categories, which they are not.
# Validated light-mode: monotone lightness, adjacent dL >= 0.06, light end
# 2.06:1 against the surface. Untagged features are off that scale entirely and
# take the neutral muted ink; they are an absence of data, not a voltage class.
# Line weight repeats the ordering so band is never carried by colour alone.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
HAIRLINE = "#e1e0d9"

BAND_STYLE = {
    "LV (<1 kV)":                  {"color": "#86b6ef", "lw": 0.45},
    "MV (1-<38 kV)":               {"color": "#3987e5", "lw": 0.55},
    "38 kV":                       {"color": "#1c5cab", "lw": 1.0},
    "HV >=110 kV (transmission)":  {"color": "#0d366b", "lw": 1.5},
    m.UNKNOWN_BAND:                {"color": "#898781", "lw": 0.35},
}
# Drawn in this order so the sparse high-voltage lines sit on top.
BAND_DRAW_ORDER = [m.UNKNOWN_BAND, "LV (<1 kV)", "MV (1-<38 kV)",
                   "38 kV", "HV >=110 kV (transmission)"]

# Asset type is a genuine category, not a magnitude, so these take hues off the
# voltage ramp: orange for transformers reads clearly against every blue step,
# substations take primary ink, and poles take the recessive baseline tone since
# there are tens of thousands of them and they are context, not subject.
POINT_STYLE = {
    "substation":  {"color": "#0b0b0b", "marker": "s", "size": 24, "z": 6},
    "transformer": {"color": "#eb6834", "marker": "^", "size": 15, "z": 5},
    "pole":        {"color": "#c3c2b7", "marker": ".", "size": 0.8, "z": 3},
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
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    boundary.boundary.plot(ax=ax, color="#c3c2b7", lw=0.8, zorder=1)
    boundary.plot(ax=ax, color=SURFACE, zorder=0)

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
    leg = ax.legend(handles=handles, loc="upper left", fontsize=7.5, frameon=True,
                    framealpha=0.95, edgecolor=HAIRLINE, facecolor=SURFACE,
                    labelcolor=INK_SECONDARY, title="voltage band / asset",
                    title_fontsize=8)
    leg.get_title().set_color(INK_MUTED)

    total_km = float(lines["length_km"].sum()) if not lines.empty else 0.0
    frac = (float(lines["voltage_v"].notna().mean()) if not lines.empty else 0.0)
    ax.set_title(
        f"{area.label}\n"
        f"OpenStreetMap power features - {len(lines):,} line features, "
        f"{total_km:,.0f} km, {frac:.0%} voltage-tagged\n"
        f"Geofabrik ireland-and-northern-ireland extract - EPSG:2157",
        fontsize=10.5, color=INK)
    ax.set_xlabel("ITM easting (m)", fontsize=8, color=INK_MUTED)
    ax.set_ylabel("ITM northing (m)", fontsize=8, color=INK_MUTED)
    ax.tick_params(labelsize=7, colors=INK_MUTED)
    for spine in ax.spines.values():
        spine.set_edgecolor(HAIRLINE)
    ax.set_aspect("equal")

    os.makedirs(OUT_DIR, exist_ok=True)
    png = os.path.join(OUT_DIR, f"{key}_power.png")
    fig.tight_layout()
    fig.savefig(png, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)

    gpkg = os.path.join(OUT_DIR, f"{key}_power.gpkg")
    write_gpkg(data, gpkg)
    print(f"  {png}  |  {gpkg}", flush=True)


if __name__ == "__main__":
    for a in m.AREAS:
        print(a.label, flush=True)
        plot_area(a.key)
