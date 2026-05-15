from datetime import datetime, timezone
import pytest
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.storage.db import Database


def make_listing(source_id="a1", source="craigslist"):
    return Listing(
        source=source, source_id=source_id, url="u", title="t",
        price=3000, beds=1.0, baths=1.0, sqft=600,
        lat=37.76, lng=-122.41,
        posted_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        raw_text="r", photos=["p1"],
    )


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


def test_inserts_listing_and_returns_id(db):
    inserted = db.upsert_listing(make_listing())
    assert inserted is True
    inserted2 = db.upsert_listing(make_listing())
    assert inserted2 is False  # idempotent


def test_records_llm_verdict(db):
    db.upsert_listing(make_listing())
    db.record_verdict(("craigslist", "a1"), "approve", "Looks great")
    v = db.get_verdict(("craigslist", "a1"))
    assert v.llm_verdict == "approve"
    assert v.user_action == "pending"


def test_user_action_update(db):
    db.upsert_listing(make_listing())
    db.record_verdict(("craigslist", "a1"), "approve", "ok")
    db.set_user_action(("craigslist", "a1"), "rejected")
    v = db.get_verdict(("craigslist", "a1"))
    assert v.user_action == "rejected"


def test_seen_set_includes_pending_and_rejected(db):
    db.upsert_listing(make_listing("a1"))
    db.upsert_listing(make_listing("a2"))
    db.record_verdict(("craigslist", "a1"), "approve", "")  # pending
    db.record_verdict(("craigslist", "a2"), "reject", "")
    db.set_user_action(("craigslist", "a2"), "rejected")
    seen = db.seen_keys("craigslist")
    assert ("craigslist", "a1") in seen
    assert ("craigslist", "a2") in seen


def test_notifications_dedup(db):
    db.upsert_listing(make_listing())
    db.record_verdict(("craigslist", "a1"), "approve", "")
    pending = list(db.pending_notifications("telegram"))
    assert len(pending) == 1
    db.record_notification(pending[0].listing_id, "telegram")
    assert list(db.pending_notifications("telegram")) == []


def test_database_can_be_reopened(tmp_path):
    """Regression: opening the same database file twice must not crash."""
    path = tmp_path / "reopen.db"
    db1 = Database(path)
    db1.upsert_listing(make_listing())
    db2 = Database(path)  # this used to crash with "table schema_version already exists"
    assert db2.seen_keys("craigslist") == {("craigslist", "a1")}
