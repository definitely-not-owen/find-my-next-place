from datetime import datetime, timezone
from shapely.geometry import Polygon
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.pipeline.rules import RuleFilter, RuleResult


def L(**overrides) -> Listing:
    base = dict(
        source="craigslist", source_id="x", url="u", title="t",
        price=3000, beds=1.0, baths=1.0, sqft=600,
        lat=37.76, lng=-122.41,
        posted_at=datetime.now(timezone.utc),
        raw_text="", photos=[],
    )
    base.update(overrides)
    return Listing(**base)


SF_POLY = Polygon([(-122.42, 37.75), (-122.42, 37.77),
                   (-122.40, 37.77), (-122.40, 37.75)])


def test_passes_a_good_listing():
    f = RuleFilter(min_price=2000, max_price=3500,
                   min_beds=1, max_beds=2, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(), seen=set())
    assert r.passes is True


def test_drops_out_of_price():
    f = RuleFilter(min_price=2000, max_price=2500,
                   min_beds=1, max_beds=2, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(price=3000), seen=set())
    assert r.passes is False
    assert "price" in r.reason


def test_drops_out_of_beds():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=2, max_beds=3, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(beds=1.0), seen=set())
    assert r.passes is False
    assert "beds" in r.reason


def test_missing_beds_passes():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=2, max_beds=3, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(beds=None), seen=set())
    assert r.passes is True


def test_drops_already_seen():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10, polygons=[SF_POLY], radius=None)
    listing = L()
    r = f.evaluate(listing, seen={listing.dedup_key()})
    assert r.passes is False
    assert "seen" in r.reason


def test_drops_outside_polygons():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(lat=40.0, lng=-74.0), seen=set())
    assert r.passes is False
    assert "geo" in r.reason


def test_missing_coords_passes_with_flag():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(lat=None, lng=None), seen=set())
    assert r.passes is True
    assert r.coords_missing is True


def test_radius_mode():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10,
                   polygons=[],
                   radius=(37.76, -122.41, 0.5))
    assert f.evaluate(L(lat=37.762, lng=-122.41), seen=set()).passes is True
    assert f.evaluate(L(lat=38.0, lng=-122.41), seen=set()).passes is False
