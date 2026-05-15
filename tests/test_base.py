from datetime import datetime, timezone
from find_my_next_place.scrapers.base import Listing


def test_listing_has_required_fields():
    listing = Listing(
        source="craigslist",
        source_id="abc123",
        url="https://example.com/abc123",
        title="1BR in Mission",
        price=3200,
        beds=1.0,
        baths=1.0,
        sqft=650,
        lat=37.7599,
        lng=-122.4148,
        posted_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        raw_text="Bright 1BR near 16th St BART",
        photos=["https://example.com/1.jpg"],
    )
    assert listing.source == "craigslist"
    assert listing.dedup_key() == ("craigslist", "abc123")


def test_listing_tolerates_missing_optionals():
    listing = Listing(
        source="zillow",
        source_id="z1",
        url="u",
        title="t",
        price=2500,
        beds=None,
        baths=None,
        sqft=None,
        lat=None,
        lng=None,
        posted_at=datetime.now(timezone.utc),
        raw_text="r",
        photos=[],
    )
    assert listing.coords_missing() is True
