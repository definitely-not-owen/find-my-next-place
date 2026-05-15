from pathlib import Path
from find_my_next_place.scrapers.zillow import ZillowScraper

FIXTURE = Path(__file__).parent / "fixtures" / "zillow" / "sample_search.html"


def test_parses_next_data_into_listings():
    html = FIXTURE.read_text()
    listings = ZillowScraper.parse(html)
    assert len(listings) == 2
    a = listings[0]
    assert a.source == "zillow"
    assert a.source_id == "123456"
    assert a.price == 3400
    assert a.beds == 1
    assert abs(a.lat - 37.7599) < 1e-6
    assert "washer" in a.raw_text.lower()
    assert a.photos == ["https://photos.zillowstatic.com/x.jpg"]


def test_skips_listing_without_price():
    html = """<!doctype html><html><body>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"searchPageState":{"cat1":{"searchResults":{"listResults":[
      {"zpid":"x","detailUrl":"u","address":"a","beds":1,"baths":1,
       "latLong":{"latitude":1,"longitude":2}}
    ]}}}}}}
    </script></body></html>"""
    assert ZillowScraper.parse(html) == []


def test_returns_empty_when_no_next_data():
    assert ZillowScraper.parse("<html><body>nope</body></html>") == []
