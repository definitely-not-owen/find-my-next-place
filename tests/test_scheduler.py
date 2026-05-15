from unittest.mock import MagicMock, patch
from find_my_next_place.scheduler import build_scrapers, build_search_arg


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
