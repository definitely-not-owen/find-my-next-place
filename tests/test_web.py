from datetime import datetime, timezone
from fastapi.testclient import TestClient
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.storage.db import Database
from find_my_next_place.web.app import create_app


def seed(db):
    db.upsert_listing(Listing(
        source="craigslist", source_id="a1", url="https://e/a1",
        title="1BR Mission", price=3200, beds=1.0, baths=1.0, sqft=600,
        lat=37.76, lng=-122.41,
        posted_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        raw_text="bright", photos=[],
    ))
    db.record_verdict(("craigslist", "a1"), "approve", "looks good")


def test_queue_lists_pending(tmp_path):
    db = Database(tmp_path / "t.db")
    seed(db)
    client = TestClient(create_app(db))
    r = client.get("/")
    assert r.status_code == 200
    assert "1BR Mission" in r.text
    assert "looks good" in r.text


def test_action_rejects_listing(tmp_path):
    db = Database(tmp_path / "t.db")
    seed(db)
    client = TestClient(create_app(db))
    lid = db._listing_id(("craigslist", "a1"))
    r = client.post(f"/listing/{lid}/action", data={"action": "rejected"})
    assert r.status_code in (200, 303)
    assert db.get_verdict(("craigslist", "a1")).user_action == "rejected"


def test_healthz(tmp_path):
    db = Database(tmp_path / "t.db")
    client = TestClient(create_app(db))
    assert client.get("/healthz").json() == {"ok": True}
