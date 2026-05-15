from unittest.mock import MagicMock, patch
from find_my_next_place.scheduler import build_scrapers, build_search_arg
from find_my_next_place.config import SourceConfig


def test_build_scrapers_filters_by_config():
    cfg = MagicMock()
    cfg.sources = ["craigslist"]
    scrapers = build_scrapers(cfg)
    names = [s.name for s in scrapers]
    assert names == ["craigslist"]


def test_build_scrapers_includes_zillow():
    cfg = MagicMock()
    cfg.sources = ["craigslist", "zillow"]
    scrapers = build_scrapers(cfg)
    names = sorted(s.name for s in scrapers)
    assert names == ["craigslist", "zillow"]


def test_build_search_arg_returns_search_section():
    cfg = MagicMock()
    cfg.search.city = "SF"
    arg = build_search_arg(cfg)
    assert arg.city == "SF"


def test_build_scrapers_passes_custom_urls():
    cfg = MagicMock()
    cfg.sources = ["craigslist", "zillow"]
    cfg.source_urls = {
        "craigslist": SourceConfig(rss_url="https://nyc.example/rss"),
        "zillow": SourceConfig(search_url="https://example.com/nyc"),
    }
    scrapers = build_scrapers(cfg)
    cl = next(s for s in scrapers if s.name == "craigslist")
    zl = next(s for s in scrapers if s.name == "zillow")
    assert cl.rss_url == "https://nyc.example/rss"
    assert zl.search_url == "https://example.com/nyc"


def test_build_scrapers_without_url_overrides():
    cfg = MagicMock()
    cfg.sources = ["craigslist"]
    cfg.source_urls = {}
    [scraper] = build_scrapers(cfg)
    assert scraper.rss_url is None
