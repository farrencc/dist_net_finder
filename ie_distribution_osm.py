"""Distribution-level (sub-110 kV) electricity network features for Ireland from OpenStreetMap.

Data source
-----------
A Geofabrik ``ireland-and-northern-ireland-latest.osm.pbf`` extract, read with
``pyrosm``.  Overpass is deliberately not used: a single national extract gives
complete, reproducible coverage in one pass and is not subject to Overpass
timeouts, rate limits or per-query result caps.

Pipeline
--------
1. ``download_extract``   - fetch the Geofabrik extract and verify its MD5.
2. ``prefilter_extract``  - stream the 392 MB national file through pyosmium,
   keeping only objects carrying a ``power`` tag (plus the nodes/ways they
   reference).  This is a memory necessity, not a change of filter: pyrosm
   holds the whole node index in RAM and is OOM-killed on the full national
   file at 15 GB.  The prefiltered file is ~7 MB and pyrosm reads it in
   seconds.  The same ``power`` tag filter is then re-applied by pyrosm, so
   the selection is identical to filtering the full file directly.
3. ``load_area``          - read the prefiltered file with pyrosm, clip to an
   administrative boundary, and split into line / node / area GeoDataFrames.
4. ``to_graph``           - build a ``networkx.MultiGraph`` from the line
   features with a configurable snapping tolerance.

Voltage bands follow the Irish system: LV 230/400 V, MV 10 kV and 20 kV,
38 kV sub-transmission, and 110 kV and above which is transmission (ESB
Networks operates everything below 110 kV; EirGrid owns 110 kV+).
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

GEOFABRIK_URL = (
    "http://download.geofabrik.de/europe/ireland-and-northern-ireland-latest.osm.pbf"
)
RAW_DIR = "data/raw"
PBF_PATH = os.path.join(RAW_DIR, "ireland-and-northern-ireland-latest.osm.pbf")
POWER_PBF_PATH = os.path.join(RAW_DIR, "ireland-power.osm.pbf")
BOUNDS_PBF_PATH = os.path.join(RAW_DIR, "ireland-boundaries.osm.pbf")
BOUNDS_GPKG = os.path.join(RAW_DIR, "boundaries.gpkg")

# Irish Transverse Mercator - the national grid; metres, so lengths and
# snapping tolerances are directly interpretable.
ITM = "EPSG:2157"
WGS84 = "EPSG:4326"

#: ``power`` values that describe a conductor run.
LINE_POWER_VALUES = ("line", "minor_line", "cable")

#: ``power`` values that describe a point asset.
NODE_POWER_VALUES = (
    "pole",
    "tower",
    "transformer",
    "substation",
    "switch",
    "portal",
    "terminal",
    "insulator",
    "converter",
    "generator",
    "catenary_mast",
    "connection",
)

#: Tags we need as real columns.  pyrosm promotes only a fixed default set of
#: keys to DataFrame columns and buries everything else in a JSON ``tags``
#: blob, so asking for these explicitly - and expanding the blob as a fallback -
#: is the difference between measuring voltage coverage and reporting zero.
TAGS_AS_COLUMNS = (
    "power", "voltage", "cables", "circuits", "wires", "frequency",
    "location", "operator", "name", "ref", "substation", "transformer",
    "line", "minor_line", "switch",
)

#: Ordered (label, lower_bound_volts, upper_bound_volts) - upper bound exclusive.
VOLTAGE_BANDS = (
    ("LV (<1 kV)", 0.0, 1_000.0),
    ("MV (1-<38 kV)", 1_000.0, 38_000.0),
    ("38 kV", 38_000.0, 110_000.0),
    ("HV >=110 kV (transmission)", 110_000.0, math.inf),
)

UNKNOWN_BAND = "unknown (no voltage tag)"

#: Anything at or above this is EirGrid transmission, not distribution.
DISTRIBUTION_MAX_V = 110_000.0

BAND_ORDER = [b[0] for b in VOLTAGE_BANDS] + [UNKNOWN_BAND]

#: Areas analysed.  ``osm_id`` is the OSM relation id, pinned so the selection
#: is reproducible and does not depend on a geocoder.
@dataclass(frozen=True)
class Area:
    key: str
    label: str
    osm_id: int
    admin_level: str


AREAS = (
    Area("kilkenny", "County Kilkenny, Ireland", 285980, "6"),
    Area("mayo", "County Mayo, Ireland", 338539, "6"),
    Area("dublin_city", "Dublin, Ireland (Dublin City Council)", 1109531, "7"),
    Area("dublin_county", "County Dublin, Ireland", 282800, "6"),
)

AREAS_BY_KEY = {a.key: a for a in AREAS}


# --------------------------------------------------------------------------- #
# Stage 1 - fetch
# --------------------------------------------------------------------------- #

def _md5(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def download_extract(url: str = GEOFABRIK_URL, path: str = PBF_PATH) -> str:
    """Download the Geofabrik extract if absent and verify its published MD5."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        subprocess.run(
            ["curl", "-sS", "-L", "--retry", "8", "--retry-delay", "4",
             "--retry-all-errors", "-C", "-", "-o", path, url],
            check=True,
        )
    expected = subprocess.run(
        ["curl", "-sS", "--retry", "5", url + ".md5"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[0]
    actual = _md5(path)
    if actual != expected:
        raise RuntimeError(f"MD5 mismatch for {path}: {actual} != {expected}")
    return path


# --------------------------------------------------------------------------- #
# Stage 2 - prefilter
# --------------------------------------------------------------------------- #

def prefilter_extract(src: str = PBF_PATH, dst: str = POWER_PBF_PATH,
                      key: str = "power") -> str:
    """Write a small .osm.pbf holding every object tagged ``key`` plus referenced nodes."""
    import osmium

    if os.path.exists(dst):
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with osmium.BackReferenceWriter(dst, ref_src=src, overwrite=True) as writer:
        for obj in osmium.FileProcessor(src).with_filter(osmium.filter.KeyFilter(key)):
            writer.add(obj)
    return dst


def prefilter_boundaries(src: str = PBF_PATH, dst: str = BOUNDS_PBF_PATH) -> str:
    """Write a small .osm.pbf holding administrative boundary relations."""
    import osmium

    if os.path.exists(dst):
        return dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with osmium.BackReferenceWriter(dst, ref_src=src, overwrite=True) as writer:
        flt = osmium.filter.TagFilter(("boundary", "administrative"))
        for obj in osmium.FileProcessor(src).with_filter(flt):
            writer.add(obj)
    return dst


def build_boundary_cache(src: str = BOUNDS_PBF_PATH,
                         dst: str = BOUNDS_GPKG) -> gpd.GeoDataFrame:
    """Extract the analysis-area polygons once and cache them to a GeoPackage."""
    from pyrosm import OSM

    if os.path.exists(dst):
        return gpd.read_file(dst)

    osm = OSM(src)
    bounds = osm.get_boundaries(boundary_type="administrative")
    wanted = {a.osm_id: a for a in AREAS}
    sel = bounds[bounds["id"].astype("int64").isin(wanted)].copy()

    rows = []
    for osm_id, grp in sel.groupby(sel["id"].astype("int64")):
        area = wanted[int(osm_id)]
        geom = unary_union(grp.geometry.values)
        rows.append({"key": area.key, "label": area.label, "osm_id": int(osm_id),
                     "admin_level": area.admin_level, "geometry": geom})
    out = gpd.GeoDataFrame(rows, geometry="geometry", crs=WGS84)
    missing = {a.key for a in AREAS} - set(out["key"])
    if missing:
        raise RuntimeError(f"boundary relations not found in extract: {missing}")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.to_file(dst, driver="GPKG")
    return out


def get_boundary(key: str) -> gpd.GeoSeries:
    """Return the boundary polygon for one analysis area, in WGS84."""
    cache = build_boundary_cache()
    row = cache[cache["key"] == key]
    if row.empty:
        raise KeyError(f"unknown area {key!r}; known: {sorted(AREAS_BY_KEY)}")
    return row.geometry.iloc[0]


# --------------------------------------------------------------------------- #
# Voltage handling
# --------------------------------------------------------------------------- #

_NUM = re.compile(r"[-+]?\d*\.?\d+")


def parse_voltage(raw) -> float | None:
    """Parse an OSM ``voltage`` tag into volts.

    OSM allows several conductors on one way, written ``"20000;10000"``.  We
    take the maximum, because the band a line belongs to is set by its highest
    circuit.  Returns ``None`` for missing or unparseable values rather than
    raising - an unparseable voltage is a data-quality fact to be counted, not
    an error to abort on.
    """
    if raw is None:
        return None
    if isinstance(raw, float) and math.isnan(raw):
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "unknown", "yes", "no"}:
        return None
    values = []
    for part in re.split(r"[;,|/]", text):
        m = _NUM.search(part)
        if not m:
            continue
        try:
            v = float(m.group())
        except ValueError:
            continue
        if v <= 0:
            continue
        values.append(v)
    if not values:
        return None
    return max(values)


def voltage_band(volts: float | None) -> str:
    """Map volts to a band label."""
    if volts is None or (isinstance(volts, float) and math.isnan(volts)):
        return UNKNOWN_BAND
    for label, lo, hi in VOLTAGE_BANDS:
        if lo <= volts < hi:
            return label
    return UNKNOWN_BAND


def voltage_series(gdf: gpd.GeoDataFrame) -> pd.Series:
    """Return a ``voltage`` Series for ``gdf``, all-NA if the column is absent.

    This exists because of a real trap.  ``gdf.get("voltage")`` returns ``None``
    when the column is missing rather than raising, so the natural-looking

        v = gdf.get("voltage")
        if v:                      # <-- wrong
            ...

    is wrong in *both* directions.  When the column is missing ``v`` is ``None``
    and the branch silently skips - so every line in that area is quietly
    treated as having no voltage, which is indistinguishable in the output from
    the area genuinely having no voltage tags.  When the column *is* present,
    ``if v:`` raises ``ValueError: The truth value of a Series is ambiguous``.
    So the branch never behaves as intended: it either hides a real result or
    crashes.  The correct test is ``if "voltage" in gdf.columns``, and a
    missing column must produce an explicit all-NA Series so downstream counts
    report "0 of N tagged" instead of dropping the area.
    """
    if "voltage" not in gdf.columns:
        return pd.Series([pd.NA] * len(gdf), index=gdf.index, dtype="object")
    return gdf["voltage"]


# --------------------------------------------------------------------------- #
# Stage 3 - load
# --------------------------------------------------------------------------- #

def _expand_tags(gdf: gpd.GeoDataFrame,
                 keys: tuple = TAGS_AS_COLUMNS) -> gpd.GeoDataFrame:
    """Lift keys out of pyrosm's leftover ``tags`` JSON blob into real columns.

    ``tags_as_columns`` covers the common case, but relation members and some
    object types still come back with keys only in the blob.  Expanding it is
    cheap insurance against silently under-reporting tag coverage.
    """
    if gdf.empty or "tags" not in gdf.columns:
        return gdf
    import json

    parsed = []
    for blob in gdf["tags"]:
        if isinstance(blob, dict):
            parsed.append(blob)
        elif isinstance(blob, str) and blob:
            try:
                d = json.loads(blob)
                parsed.append(d if isinstance(d, dict) else {})
            except (ValueError, TypeError):
                parsed.append({})
        else:
            parsed.append({})

    gdf = gdf.copy()
    for key in keys:
        from_blob = pd.Series([d.get(key) for d in parsed], index=gdf.index,
                              dtype="object")
        if key in gdf.columns:
            existing = gdf[key].astype("object")
            gdf[key] = existing.where(existing.notna(), from_blob)
        elif from_blob.notna().any():
            gdf[key] = from_blob
    return gdf


def _explode_lines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep only (Multi)LineString rows, exploded to single LineStrings."""
    geom_type = gdf.geometry.geom_type
    lines = gdf[geom_type.isin(["LineString", "MultiLineString"])].copy()
    if lines.empty:
        return lines
    lines = lines.explode(index_parts=False, ignore_index=True)
    return lines[lines.geometry.geom_type == "LineString"].copy()


def _annotate(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add ``voltage_v``, ``band`` and ``length_km`` columns."""
    if gdf.empty:
        for col in ("voltage_v", "band", "length_km"):
            if col not in gdf.columns:
                gdf[col] = pd.Series(dtype="float64" if col != "band" else "object")
        return gdf
    raw = voltage_series(gdf)
    gdf = gdf.copy()
    gdf["voltage_v"] = [parse_voltage(v) for v in raw]
    gdf["band"] = [voltage_band(v) for v in gdf["voltage_v"]]
    if gdf.geometry.geom_type.isin(["LineString", "MultiLineString"]).any():
        gdf["length_km"] = gdf.to_crs(ITM).geometry.length / 1000.0
    return gdf


def load_area(key: str, pbf_path: str = POWER_PBF_PATH) -> dict:
    """Load power features for one analysis area.

    Returns a dict with ``lines`` (conductor runs), ``nodes`` (point assets),
    ``areas`` (polygon assets, chiefly substation footprints) and ``boundary``.
    All GeoDataFrames are in WGS84 with ``voltage_v``, ``band`` and (for lines)
    ``length_km`` added.
    """
    from pyrosm import OSM

    boundary = get_boundary(key)
    osm = OSM(pbf_path, bounding_box=boundary)
    raw = osm.get_data_by_custom_criteria(
        custom_filter={"power": True},
        filter_type="keep",
        tags_as_columns=list(TAGS_AS_COLUMNS),
        keep_nodes=True,
        keep_ways=True,
        keep_relations=True,
    )
    if raw is None or len(raw) == 0:
        empty = gpd.GeoDataFrame(geometry=[], crs=WGS84)
        return {"lines": empty.copy(), "nodes": empty.copy(),
                "areas": empty.copy(), "boundary": boundary, "key": key}

    raw = raw.set_crs(WGS84, allow_override=True)
    # pyrosm's bounding_box filter is applied per-object against the polygon,
    # but relation members can drag geometry outside it; clip explicitly so the
    # per-area figures are exact.
    raw = raw[~raw.geometry.is_empty & raw.geometry.notna()]
    raw = raw[raw.geometry.intersects(boundary)].copy()
    raw = _expand_tags(raw)

    geom_type = raw.geometry.geom_type
    lines = _annotate(_explode_lines(raw))
    nodes = _annotate(raw[geom_type == "Point"].copy())
    polys = _annotate(raw[geom_type.isin(["Polygon", "MultiPolygon"])].copy())

    # Keep only the portion of each line inside the boundary so length figures
    # are not inflated by lines that merely touch the county edge.
    if not lines.empty:
        clipped = lines.copy()
        clipped["geometry"] = clipped.geometry.intersection(boundary)
        clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()]
        clipped = _explode_lines(clipped)
        clipped["length_km"] = clipped.to_crs(ITM).geometry.length / 1000.0
        lines = clipped[clipped["length_km"] > 0].copy()

    return {"lines": lines, "nodes": nodes, "areas": polys,
            "boundary": boundary, "key": key}


def distribution_only(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop features known to be 110 kV and above (EirGrid transmission)."""
    if lines.empty:
        return lines
    keep = lines["voltage_v"].isna() | (lines["voltage_v"] < DISTRIBUTION_MAX_V)
    return lines[keep].copy()


# --------------------------------------------------------------------------- #
# Stage 4 - graph
# --------------------------------------------------------------------------- #

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        p = self.parent
        while p[a] != a:
            p[a] = p[p[a]]
            a = p[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def to_graph(lines: gpd.GeoDataFrame, snap_m: float = 1.0) -> nx.MultiGraph:
    """Build a MultiGraph from line features, snapping endpoints within ``snap_m``.

    Nodes are clusters of line endpoints (a cluster is a set of endpoints
    transitively within ``snap_m`` of each other).  A line is additionally
    split wherever another line's endpoint falls within ``snap_m`` of it, so
    T-junctions where one feeder ends part-way along another are captured
    rather than silently dropped - without that, component counts would be
    pessimistic for reasons that are an artefact of the graph builder rather
    than of the data.

    Node positions are stored as ``x``/``y`` in EPSG:2157 metres.
    """
    g = nx.MultiGraph()
    if lines is None or lines.empty:
        return g

    proj = lines.to_crs(ITM)
    geoms = list(proj.geometry.values)

    # 1. Endpoint candidates.
    coords = []
    for geom in geoms:
        cs = list(geom.coords)
        coords.append(cs[0])
        coords.append(cs[-1])
    pts = shapely.points(np.asarray(coords))

    # 2. Cluster endpoints that lie within snap_m of one another.
    tree = shapely.STRtree(pts)
    left, right = tree.query(pts, predicate="dwithin", distance=snap_m)
    uf = _UnionFind(len(pts))
    for a, b in zip(left, right):
        if a != b:
            uf.union(int(a), int(b))

    labels = np.array([uf.find(i) for i in range(len(pts))])
    uniq, inverse = np.unique(labels, return_inverse=True)
    xy = np.asarray(coords, dtype=float)
    cluster_xy = np.zeros((len(uniq), 2))
    np.add.at(cluster_xy, inverse, xy)
    counts = np.bincount(inverse, minlength=len(uniq)).reshape(-1, 1)
    cluster_xy /= counts
    cluster_pts = shapely.points(cluster_xy)
    cluster_tree = shapely.STRtree(cluster_pts)

    for cid, (x, y) in enumerate(cluster_xy):
        g.add_node(int(cid), x=float(x), y=float(y))

    # 3. Split each line at every cluster point lying within snap_m of it.
    cols = proj.columns
    have = {c: (c in cols) for c in ("power", "voltage_v", "band", "id")}
    records = proj.to_dict("records")

    for idx, geom in enumerate(geoms):
        near = cluster_tree.query(geom, predicate="dwithin", distance=snap_m)
        along = []
        for cid in near:
            along.append((geom.project(cluster_pts[cid]), int(cid)))
        # The line's own endpoints must be present even if snap_m is tiny.
        along.append((0.0, int(inverse[2 * idx])))
        along.append((geom.length, int(inverse[2 * idx + 1])))
        along.sort()

        rec = records[idx]
        attrs = {
            "power": rec.get("power") if have["power"] else None,
            "voltage_v": rec.get("voltage_v") if have["voltage_v"] else None,
            "band": rec.get("band") if have["band"] else None,
            "osm_id": rec.get("id") if have["id"] else None,
            "source_index": idx,
        }

        prev_d, prev_cid = along[0]
        for d, cid in along[1:]:
            if cid == prev_cid:
                continue
            seg_len = d - prev_d
            if seg_len <= 0:
                continue
            g.add_edge(prev_cid, cid, length_m=float(seg_len), **attrs)
            prev_d, prev_cid = d, cid

    g.remove_nodes_from(list(nx.isolates(g)))
    return g


def component_stats(g: nx.MultiGraph) -> dict:
    """Summarise the component-size distribution of a graph."""
    if g.number_of_nodes() == 0:
        return {"n_nodes": 0, "n_edges": 0, "n_components": 0, "sizes": []}
    comps = sorted((len(c) for c in nx.connected_components(g)), reverse=True)
    arr = np.array(comps)
    return {
        "n_nodes": g.number_of_nodes(),
        "n_edges": g.number_of_edges(),
        "n_components": len(comps),
        "sizes": comps,
        "largest": int(arr[0]),
        "largest_share": float(arr[0] / arr.sum()),
        "median": float(np.median(arr)),
        "mean": float(arr.mean()),
        "n_size_le_2": int((arr <= 2).sum()),
        "n_size_le_5": int((arr <= 5).sum()),
        "n_size_ge_50": int((arr >= 50).sum()),
        "share_nodes_in_comps_le_5": float(arr[arr <= 5].sum() / arr.sum()),
    }


def prepare(force: bool = False) -> None:
    """Run the fetch + prefilter + boundary-cache stages."""
    download_extract()
    prefilter_extract()
    prefilter_boundaries()
    build_boundary_cache()


if __name__ == "__main__":
    prepare()
    for area in AREAS:
        data = load_area(area.key)
        g = to_graph(data["lines"], snap_m=1.0)
        stats = component_stats(g)
        print(f"{area.label}: {len(data['lines'])} lines, "
              f"{len(data['nodes'])} nodes, {len(data['areas'])} areas, "
              f"graph {stats['n_nodes']} nodes / {stats['n_components']} components")
