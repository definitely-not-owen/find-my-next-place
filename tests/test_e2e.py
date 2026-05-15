"""End-to-end test running the full pipeline against fixtures + mocks."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from shapely.geometry import Polygon
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.scrapers.craigslist import CraigslistScraper
from find_my_next_place.storage.db import Database
from find_my_next_place.pipeline.rules import RuleFilter
from find_my_next_place.pipeline.llm import LLMFilter, Verdict
from find_my_next_place.pipeline.cycle import run_cycle


FIXTURE = Path(__file__).parent / "scrapers" / "fixtures" / "craigslist" / "sample_rss.xml"


def test_full_cycle_against_fixture(tmp_path):
    db = Database(tmp_path / "e2e.db")

    scraper = CraigslistScraper()
    rss = FIXTURE.read_text()
    scraper.fetch = lambda search: CraigslistScraper.parse(rss, source="craigslist")

    poly = Polygon([(-180, -90), (-180, 90), (180, 90), (180, -90)])
    rule = RuleFilter(min_price=2000, max_price=4000, min_beds=0, max_beds=10,
                      polygons=[poly], radius=None)

    llm = MagicMock(spec=LLMFilter)
    llm.evaluate.side_effect = [
        Verdict("approve", "has laundry"),
        Verdict("reject", "top floor"),
    ]
    notifier = MagicMock()

    summary = run_cycle(db=db, scrapers=[scraper], search=None,
                       rule_filter=rule, llm_filter=llm, notifier=notifier)

    assert summary.scraped == 2
    assert summary.llm_approved == 1
    assert summary.llm_rejected == 1
    assert summary.notified == 1
