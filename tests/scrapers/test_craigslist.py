from pathlib import Path
from find_my_next_place.scrapers.craigslist import CraigslistScraper

FIXTURE = Path(__file__).parent / "fixtures" / "craigslist" / "sample_rss.xml"


def test_parses_rss_into_listings():
    rss = FIXTURE.read_text()
    listings = CraigslistScraper.parse(rss, source="craigslist")
    assert len(listings) == 2
    first = listings[0]
    assert first.source == "craigslist"
    assert first.source_id.endswith("7700000001")
    assert first.price == 3200
    assert first.beds == 1.0
    assert "Mission" in first.title
    assert "BART" in first.raw_text


def test_handles_price_without_beds():
    rss = """<?xml version="1.0"?>
    <rdf:RDF xmlns="http://purl.org/rss/1.0/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
      <item rdf:about="https://x/abc/777.html">
        <title>$2500 - Studio near park</title>
        <link>https://x/abc/777.html</link>
        <description>Studio</description>
      </item>
    </rdf:RDF>
    """
    listings = CraigslistScraper.parse(rss, source="craigslist")
    assert listings[0].price == 2500
    assert listings[0].beds is None
