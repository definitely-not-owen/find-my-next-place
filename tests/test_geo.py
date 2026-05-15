import json
from unittest.mock import MagicMock
import pytest
from shapely.geometry import Polygon, Point
from find_my_next_place.pipeline.geo import (
    GeoResolver, point_in_any, point_within_radius,
)


def test_point_in_any_true():
    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    assert point_in_any(0.5, 0.5, [poly]) is True


def test_point_in_any_false():
    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    assert point_in_any(2, 2, [poly]) is False


def test_point_within_radius():
    # 1 degree latitude ≈ 69 miles. 0.01 degrees ≈ 0.69 miles.
    assert point_within_radius(37.76, -122.41, 37.77, -122.41, 1.0) is True
    assert point_within_radius(37.76, -122.41, 38.00, -122.41, 1.0) is False


def test_resolver_caches_results(tmp_path):
    cache = tmp_path / "geo.json"
    client = MagicMock()
    client.get.return_value.json.return_value = [{
        "geojson": {"type": "Polygon", "coordinates": [[
            [-122.42, 37.75], [-122.42, 37.77],
            [-122.40, 37.77], [-122.40, 37.75], [-122.42, 37.75]
        ]]}
    }]
    client.get.return_value.raise_for_status = lambda: None

    r = GeoResolver(cache_path=cache, http=client)
    polys = r.resolve(city="SF", neighborhoods=["Mission"])
    assert len(polys) == 1
    assert client.get.call_count == 1

    # Second call uses cache; no new HTTP call.
    polys2 = r.resolve(city="SF", neighborhoods=["Mission"])
    assert len(polys2) == 1
    assert client.get.call_count == 1


def test_resolver_raises_on_unresolved(tmp_path):
    client = MagicMock()
    client.get.return_value.json.return_value = []
    client.get.return_value.raise_for_status = lambda: None
    r = GeoResolver(cache_path=tmp_path / "g.json", http=client)
    with pytest.raises(RuntimeError, match="could not resolve"):
        r.resolve(city="SF", neighborhoods=["Nowhere"])
