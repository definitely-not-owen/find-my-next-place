from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.storage.migrations import MIGRATIONS


@dataclass
class VerdictRow:
    listing_id: int
    llm_verdict: str | None
    llm_reasons: str | None
    user_action: str
    source: str
    source_id: str


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self):
        cur = self._conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        row = cur.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = row[0] or 0
        for i, sql in enumerate(MIGRATIONS, start=1):
            if i <= current:
                continue
            if "schema_version" in sql and current == 0 and i <= len(MIGRATIONS):
                continue
            cur.executescript(sql)
            cur.execute("INSERT INTO schema_version(version) VALUES (?)", (i,))
        self._conn.commit()

    def upsert_listing(self, listing: Listing) -> bool:
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO listings
              (source, source_id, url, title, price, beds, baths, sqft,
               lat, lng, posted_at, raw_text, photos_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                listing.source, listing.source_id, listing.url, listing.title,
                listing.price, listing.beds, listing.baths, listing.sqft,
                listing.lat, listing.lng, listing.posted_at,
                listing.raw_text, json.dumps(listing.photos),
            ),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def _listing_id(self, key: tuple[str, str]) -> int:
        row = self._conn.execute(
            "SELECT id FROM listings WHERE source=? AND source_id=?", key
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown listing {key}")
        return row["id"]

    def record_verdict(self, key, verdict: str, reasons: str):
        lid = self._listing_id(key)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO verdicts (listing_id, llm_verdict, llm_reasons, user_action)
            VALUES (?, ?, ?, COALESCE(
              (SELECT user_action FROM verdicts WHERE listing_id=?), 'pending'))
            """,
            (lid, verdict, reasons, lid),
        )
        self._conn.commit()

    def set_user_action(self, key, action: str):
        lid = self._listing_id(key)
        self._conn.execute(
            "UPDATE verdicts SET user_action=?, user_action_at=CURRENT_TIMESTAMP WHERE listing_id=?",
            (action, lid),
        )
        self._conn.commit()

    def get_verdict(self, key) -> VerdictRow | None:
        row = self._conn.execute(
            """
            SELECT v.listing_id, v.llm_verdict, v.llm_reasons, v.user_action,
                   l.source, l.source_id
            FROM verdicts v JOIN listings l ON l.id = v.listing_id
            WHERE l.source=? AND l.source_id=?
            """,
            key,
        ).fetchone()
        if row is None:
            return None
        return VerdictRow(**dict(row))

    def seen_keys(self, source: str) -> set[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT source, source_id FROM listings WHERE source=?", (source,)
        ).fetchall()
        return {(r["source"], r["source_id"]) for r in rows}

    def pending_notifications(self, channel: str):
        rows = self._conn.execute(
            """
            SELECT v.listing_id, l.source, l.source_id
            FROM verdicts v
            JOIN listings l ON l.id = v.listing_id
            LEFT JOIN notifications n
              ON n.listing_id = v.listing_id AND n.channel = ?
            WHERE v.llm_verdict IN ('approve','unsure')
              AND n.id IS NULL
            """,
            (channel,),
        ).fetchall()
        return [VerdictRow(listing_id=r["listing_id"], llm_verdict=None,
                           llm_reasons=None, user_action="pending",
                           source=r["source"], source_id=r["source_id"]) for r in rows]

    def record_notification(self, listing_id: int, channel: str):
        self._conn.execute(
            "INSERT OR IGNORE INTO notifications (listing_id, channel) VALUES (?, ?)",
            (listing_id, channel),
        )
        self._conn.commit()

    def get_listing(self, listing_id: int) -> dict:
        row = self._conn.execute(
            "SELECT * FROM listings WHERE id=?", (listing_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_pending(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT l.*, v.llm_verdict, v.llm_reasons
            FROM listings l JOIN verdicts v ON v.listing_id = l.id
            WHERE v.user_action = 'pending'
              AND v.llm_verdict IN ('approve','unsure')
            ORDER BY l.first_seen DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
