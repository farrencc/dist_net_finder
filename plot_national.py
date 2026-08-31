"""National map of OSM sub-110 kV distribution lines for the Republic of Ireland.

Scope note: the Geofabrik extract covers the whole island, but the analysis
boundaries, the county attribution and the ESB comparison are all Republic-only
(ESB Networks is the DSO for the Republic; Northern Ireland is NIE Networks).
This map is clipped to the 26 counties for the same reason, so the totals on it
match the figures in FINDINGS.md.

Colour: voltage band is an ordered quantity, so the bands take a single-hue
ordinal ramp (light = low voltage, dark = high) rather than a categorical set
of hues. Untagged features are off that scale entirely and take the neutral
muted ink, which also keeps them recessive - they are an absence of data, not a
voltage class. Line weight repeats the same ordering so band is never carried
by colour alone.
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
from national_check import load_national_lines

warnings.filterwarnings("ignore")

OUT_PNG = "data/national_distribution.png"
OUT_GPKG = "data/national_distribution.gpkg"
DPI = 160

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
HAIRLINE = "#e1e0d9"
COAST = "#c3c2b7"

# Single-hue ordinal ramp, validated light-mode: monotone lightness, adjacent
# dL >= 0.06, light end 2.06:1 against the surface, hue spread 4 degrees.
BANDS = [
    (m.UNKNOWN_BAND,  "#898781", 0.28, "no voltage tag"),
    ("LV (<1 kV)",    "#86b6ef", 0.35, "LV (<1 kV)"),
    ("MV (1-<38 kV)", "#3987e5", 0.45, "MV (1-38 kV)"),
    ("38 kV",         "#1c5cab", 0.85, "38 kV"),
]


def main():
    lines = load_national_lines()
    counties = gpd.read_file("data/raw/counties.gpkg").to_crs(m.ITM)
    # Full coastline detail makes point-in-polygon against 550k midpoints
    # intractable; 100 m simplification is far below map scale here. The
    # undetailed copy is used only for the containment test - the drawn
    # outlines keep their real geometry.
    coarse = counties.copy()
    coarse["geometry"] = coarse.geometry.simplify(100).buffer(0)
    roi = counties.union_all()

    lines = lines.to_crs(m.ITM)
    dist = lines[lines["voltage_v"].isna() | (lines["voltage_v"] < 110_000)].copy()
    # Midpoint containment, not clipping: keeps whole features and avoids
    # slicing every line that crosses a county edge.
    mids = gpd.GeoDataFrame(geometry=dist.geometry.interpolate(0.5, normalized=True),
                            crs=m.ITM)
    inside = gpd.sjoin(mids, coarse[["geometry"]], how="inner", predicate="within")
    dist = dist.loc[dist.index.isin(inside.index)].copy()

    fig, ax = plt.subplots(figsize=(10.5, 11.6))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    counties.boundary.plot(ax=ax, color=HAIRLINE, lw=0.5, zorder=1)
    gpd.GeoSeries([roi], crs=m.ITM).boundary.plot(ax=ax, color=COAST, lw=0.7, zorder=2)

    handles = []
    for i, (band, colour, lw, label) in enumerate(BANDS):
        sel = dist[dist["band"] == band]
        if len(sel) == 0:
            continue
        sel.plot(ax=ax, color=colour, lw=lw, zorder=3 + i)
        handles.append(Line2D([0], [0], color=colour, lw=2.2,
                              label=f"{label}   {sel['length_km'].sum():,.0f} km"))

    leg = ax.legend(handles=handles[::-1], loc="upper left", fontsize=9,
                    frameon=False, labelcolor=INK_SECONDARY,
                    title="voltage band", title_fontsize=9,
                    handlelength=1.6, borderpad=0.9, labelspacing=0.75)
    leg.get_title().set_color(INK_MUTED)

    total_km = float(dist["length_km"].sum())
    tagged = float(dist.loc[dist["voltage_v"].notna(), "length_km"].sum())
    ax.set_title(
        "Sub-110 kV electricity network mapped in OpenStreetMap\n"
        "Republic of Ireland",
        fontsize=15, color=INK, loc="left", pad=16)
    ax.text(0.0, 1.005,
            f"{len(dist):,} line features, {total_km:,.0f} km, "
            f"{tagged / total_km:.0%} carrying a voltage tag  ·  "
            "ESB Networks reports 172,000 km of distribution network",
            transform=ax.transAxes, fontsize=9, color=INK_SECONDARY, va="bottom")
    ax.text(0.0, -0.018,
            "Blank areas are unmapped, not unserved. Every part of the state is "
            "served; OpenStreetMap holds about a fifth of the network.",
            transform=ax.transAxes, fontsize=9, color=INK_SECONDARY, va="top")
    ax.text(0.0, -0.042,
            "Geofabrik ireland-and-northern-ireland extract, 2026-08-28  ·  "
            "EPSG:2157 Irish Transverse Mercator  ·  110 kV and above excluded",
            transform=ax.transAxes, fontsize=8, color=INK_MUTED, va="top")

    ax.set_aspect("equal")
    ax.set_axis_off()

    os.makedirs("data", exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=DPI, facecolor=SURFACE, bbox_inches="tight",
                pad_inches=0.35)
    plt.close(fig)

    out = dist.copy()
    for c in out.columns:
        if c != "geometry" and out[c].dtype == object:
            out[c] = out[c].astype(str)
    if os.path.exists(OUT_GPKG):
        os.remove(OUT_GPKG)
    out.to_file(OUT_GPKG, layer="lines", driver="GPKG")

    print(f"{OUT_PNG}  |  {OUT_GPKG}")
    print(dist.groupby("band")["length_km"].agg(["size", "sum"]).round(1).to_string())


if __name__ == "__main__":
    main()
