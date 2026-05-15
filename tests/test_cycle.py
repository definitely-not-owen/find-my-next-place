from datetime import datetime, timezone
from unittest.mock import MagicMock
from shapely.geometry import Polygon
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.storage.db import Database
from find_my_next_place.pipeline.rules import RuleFilter
from find_my_next_place.pipeline.llm import LLMFilter, Verdict
from find_my_next_place.pipeline.cycle import run_cycle


def fake_listing(sid="a1", price=3000):
    return Listing(
        source="craigslist", source_id=sid, url="u", title="t",
        price=price, beds=1.0, baths=1.0, sqft=None,
        lat=37.76, lng=-122.41,
        posted_at=datetime.now(timezone.utc), raw_text="r", photos=["p"],
    )


def test_cycle_happy_path(tmp_path):
    db = Database(tmp_path / "t.db")
    scraper_good = MagicMock(name="craigslist")
    scraper_good.name = "craigslist"
    scraper_good.fetch.return_value = [fake_listing("a1"), fake_listing("a2", price=99999)]

    poly = Polygon([(-122.42, 37.75), (-122.42, 37.77),
                    (-122.40, 37.77), (-122.40, 37.75)])
    rule = RuleFilter(min_price=2000, max_price=4000, min_beds=0, max_beds=10,
                      polygons=[poly], radius=None)

    llm = MagicMock(spec=LLMFilter)
    llm.evaluate.return_value = Verdict("approve", "looks good")

    notifier = MagicMock()

    summary = run_cycle(db=db, scrapers=[scraper_good], search=None,
                       rule_filter=rule, llm_filter=llm, notifier=notifier)

    assert summary.scraped == 2
    assert summary.rule_passed == 1
    assert summary.llm_approved == 1
    assert summary.notified == 1
    notifier.send.assert_called_once()


def test_cycle_isolates_failing_scraper(tmp_path):
    db = Database(tmp_path / "t.db")
    good = MagicMock(); good.name = "good"
    good.fetch.return_value = [fake_listing("g1")]
    bad = MagicMock(); bad.name = "bad"
    bad.fetch.side_effect = RuntimeError("kaboom")

    poly = Polygon([(-122.42, 37.75), (-122.42, 37.77),
                    (-122.40, 37.77), (-122.40, 37.75)])
    rule = RuleFilter(min_price=0, max_price=10000, min_beds=0, max_beds=10,
                      polygons=[poly], radius=None)
    llm = MagicMock(); llm.evaluate.return_value = Verdict("approve", "ok")
    notifier = MagicMock()

    summary = run_cycle(db=db, scrapers=[good, bad], search=None,
                       rule_filter=rule, llm_filter=llm, notifier=notifier)
    assert summary.scraped == 1
    assert "bad" in summary.errors


def test_cycle_does_not_renotify(tmp_path):
    db = Database(tmp_path / "t.db")
    scraper = MagicMock(); scraper.name = "s"
    scraper.fetch.return_value = [fake_listing("a1")]
    rule = RuleFilter(min_price=0, max_price=10000, min_beds=0, max_beds=10,
                      polygons=[], radius=None)
    llm = MagicMock(); llm.evaluate.return_value = Verdict("approve", "ok")
    notifier = MagicMock()

    run_cycle(db=db, scrapers=[scraper], search=None,
              rule_filter=rule, llm_filter=llm, notifier=notifier)
    notifier.reset_mock()
    # Second cycle: same listing, already in DB; should not re-notify.
    run_cycle(db=db, scrapers=[scraper], search=None,
              rule_filter=rule, llm_filter=llm, notifier=notifier)
    notifier.send.assert_not_called()
