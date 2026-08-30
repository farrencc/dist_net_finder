"""Regression tests for the voltage-handling path.

The motivating bug: code that reached for the voltage column as

    v = gdf.get("voltage")
    if v:
        ...

is wrong in both directions.  With the column absent, ``gdf.get`` returns
``None`` and the branch is silently skipped, so an area with thousands of
voltage-tagged lines is reported as having none.  With the column present,
``if v:`` raises ``ValueError: The truth value of a Series is ambiguous``.

On top of that, pyrosm does not promote ``voltage`` to a DataFrame column
unless it is named in ``tags_as_columns`` - it leaves it inside a JSON ``tags``
blob.  So the "column absent" case is the *normal* case with a default pyrosm
read, not a rare edge case, and the silent-skip branch would have reported 0%
voltage coverage nationally.
"""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

import ie_distribution_osm as m


def _gdf(rows, with_voltage=True):
    data = {"power": [r[0] for r in rows],
            "geometry": [LineString([(0, i), (1, i)]) for i, _ in enumerate(rows)]}
    if with_voltage:
        data["voltage"] = [r[1] for r in rows]
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


def test_get_returns_none_when_column_missing():
    """Documents the trap itself: .get() does not raise, it returns None."""
    gdf = _gdf([("minor_line", "20000")], with_voltage=False)
    assert gdf.get("voltage") is None


def test_truthiness_of_present_column_raises():
    """The same branch blows up when the column *is* there."""
    gdf = _gdf([("minor_line", "20000")])
    with pytest.raises(ValueError):
        bool(gdf.get("voltage"))


def test_voltage_series_missing_column_is_all_na_not_none():
    gdf = _gdf([("minor_line", None), ("cable", None)], with_voltage=False)
    s = m.voltage_series(gdf)
    assert isinstance(s, pd.Series)
    assert len(s) == len(gdf)
    assert s.isna().all()


def test_voltage_series_present_column_passes_through():
    gdf = _gdf([("minor_line", "20000"), ("cable", "10000")])
    assert list(m.voltage_series(gdf)) == ["20000", "10000"]


@pytest.mark.parametrize("raw,expected", [
    (None, None), ("", None), ("nan", None), ("yes", None), ("-1", None),
    ("400", 400.0), ("20000", 20000.0), ("38000 V", 38000.0),
    ("10000;20000", 20000.0), ("110000;38000", 110000.0),
    ("0.4", 0.4),
])
def test_parse_voltage(raw, expected):
    assert m.parse_voltage(raw) == expected


@pytest.mark.parametrize("volts,band", [
    (None, m.UNKNOWN_BAND), (230.0, "LV (<1 kV)"), (400.0, "LV (<1 kV)"),
    (10_000.0, "MV (1-<38 kV)"), (20_000.0, "MV (1-<38 kV)"),
    (38_000.0, "38 kV"), (110_000.0, "HV >=110 kV (transmission)"),
    (400_000.0, "HV >=110 kV (transmission)"),
])
def test_voltage_band(volts, band):
    assert m.voltage_band(volts) == band


def test_expand_tags_recovers_voltage_from_blob():
    """The pyrosm-specific half of the bug."""
    gdf = _gdf([("minor_line", None), ("cable", None)], with_voltage=False)
    gdf["tags"] = ['{"voltage":"20000","location":"overhead"}',
                   '{"voltage":"10000","location":"underground"}']
    out = m._expand_tags(gdf)
    assert list(out["voltage"]) == ["20000", "10000"]
    assert list(out["location"]) == ["overhead", "underground"]


def test_expand_tags_does_not_clobber_existing_values():
    gdf = _gdf([("minor_line", "20000")])
    gdf["tags"] = ['{"voltage":"999"}']
    out = m._expand_tags(gdf)
    assert list(out["voltage"]) == ["20000"]


def test_to_graph_on_empty_frame_returns_empty_graph():
    empty = gpd.GeoDataFrame({"power": [], "geometry": []}, crs="EPSG:4326")
    g = m.to_graph(empty, snap_m=1.0)
    assert g.number_of_nodes() == 0


def test_to_graph_snapping_joins_near_endpoints():
    """Two lines 3 m apart: disconnected at 1 m tolerance, joined at 5 m."""
    lines = gpd.GeoDataFrame({
        "power": ["minor_line", "minor_line"],
        "geometry": [LineString([(0, 0), (0, 100)]),
                     LineString([(0, 103), (0, 200)])],
    }, crs=m.ITM).to_crs("EPSG:4326")
    assert m.component_stats(m.to_graph(lines, snap_m=1.0))["n_components"] == 2
    assert m.component_stats(m.to_graph(lines, snap_m=5.0))["n_components"] == 1


def test_to_graph_splits_at_t_junction():
    """A feeder ending mid-way along another line must connect, not orphan."""
    lines = gpd.GeoDataFrame({
        "power": ["minor_line", "minor_line"],
        "geometry": [LineString([(0, 0), (200, 0)]),
                     LineString([(100, 0), (100, 80)])],
    }, crs=m.ITM).to_crs("EPSG:4326")
    stats = m.component_stats(m.to_graph(lines, snap_m=0.1))
    assert stats["n_components"] == 1
    assert stats["n_nodes"] == 4
