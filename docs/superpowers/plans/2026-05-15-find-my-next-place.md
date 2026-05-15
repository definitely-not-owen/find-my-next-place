# find-my-next-place Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a configurable, city-agnostic apartment-hunting pipeline that scrapes rental listings, applies deterministic and LLM-based filters, and surfaces survivors in a localhost review queue with Telegram pings.

**Architecture:** Single-process Python app. Scrapers (Craigslist, Zillow) → rule filter → Claude Haiku filter → SQLite → Telegram notify + FastAPI review UI. Scheduled by APScheduler. Per-source isolation so one failing source doesn't break a cycle. Spec: `docs/superpowers/specs/2026-05-15-find-my-next-place-design.md`.

**Tech Stack:** Python 3.11+, Pydantic v2, sqlite3 (stdlib), httpx, shapely, anthropic SDK, camoufox, APScheduler, FastAPI + Jinja2, pytest.

---

## File Structure

```
find_my_next_place/
  __init__.py
  __main__.py
  config.py
  scheduler.py
  pipeline/
    __init__.py
    cycle.py
    rules.py
    llm.py
    geo.py
  scrapers/
    __init__.py
    base.py
    craigslist.py
    zillow.py
  storage/
    __init__.py
    db.py
    migrations.py
  notify/
    __init__.py
    telegram.py
  web/
    __init__.py
    app.py
    templates/
      base.html
      queue.html
      listing.html
    static/
      style.css
tests/
  __init__.py
  conftest.py
  test_config.py
  test_rules.py
  test_geo.py
  test_llm.py
  test_storage.py
  test_telegram.py
  test_cycle.py
  test_web.py
  scrapers/
    __init__.py
    test_craigslist.py
    test_zillow.py
    fixtures/
      craigslist/sample_rss.xml
      zillow/sample_search.html
data/                    # gitignored, created at runtime
pyproject.toml
config.example.json
.gitignore               # already exists; extend
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `find_my_next_place/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`
- Modify: `.gitignore` (append data/ and venv lines)

- [ ] **Step 1: Write the failing smoke test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import find_my_next_place
    assert find_my_next_place.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL (module not found or no `__version__`).

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "find-my-next-place"
version = "0.1.0"
description = "Apartment-hunting pipeline."
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2.5",
  "httpx>=0.27",
  "shapely>=2.0",
  "anthropic>=0.39",
  "apscheduler>=3.10",
  "fastapi>=0.110",
  "uvicorn>=0.27",
  "jinja2>=3.1",
  "feedparser>=6.0",
  "camoufox[geoip]>=0.4",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx[testing]"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["find_my_next_place*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Create package init**

`find_my_next_place/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Create test scaffolding**

`tests/__init__.py`: empty file.

`tests/conftest.py`:
```python
import pytest
```

- [ ] **Step 6: Extend `.gitignore`**

Append to existing `.gitignore`:
```
# find-my-next-place
data/
.venv/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 7: Install and run smoke test**

Run:
```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml find_my_next_place/ tests/ .gitignore
git commit -m "scaffold: pyproject, package layout, smoke test"
```

---

### Task 2: Listing dataclass and Scraper protocol

**Files:**
- Create: `find_my_next_place/scrapers/__init__.py` (empty)
- Create: `find_my_next_place/scrapers/base.py`
- Create: `tests/scrapers/__init__.py` (empty)
- Create: `tests/test_base.py`

- [ ] **Step 1: Write the failing test**

`tests/test_base.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_base.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `base.py`**

`find_my_next_place/scrapers/base.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class Listing:
    source: str
    source_id: str
    url: str
    title: str
    price: int
    beds: float | None
    baths: float | None
    sqft: int | None
    lat: float | None
    lng: float | None
    posted_at: datetime
    raw_text: str
    photos: list[str]

    def dedup_key(self) -> tuple[str, str]:
        return (self.source, self.source_id)

    def coords_missing(self) -> bool:
        return self.lat is None or self.lng is None


class Scraper(Protocol):
    name: str

    def fetch(self, search) -> list[Listing]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_base.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add find_my_next_place/scrapers/ tests/scrapers/ tests/test_base.py
git commit -m "feat: Listing dataclass and Scraper protocol"
```

---

### Task 3: Config module

**Files:**
- Create: `find_my_next_place/config.py`
- Create: `tests/test_config.py`
- Create: `config.example.json`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:
```python
import json
import os
import pytest
from find_my_next_place.config import load_config, ConfigError


def write_config(tmp_path, data):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    return p


def base_data():
    return {
        "search": {
            "city": "San Francisco, CA",
            "neighborhoods": ["Mission"],
            "radius_miles_from": None,
            "min_price": 2000, "max_price": 3800,
            "min_bedrooms": 1, "max_bedrooms": 2,
        },
        "preferences": {"must_haves": ["laundry"], "deal_breakers": ["top floor"]},
        "sources": ["craigslist"],
        "schedule_minutes": 30,
        "notify": {"telegram": {"bot_token": "literal-tok", "chat_id": "123"}},
        "llm": {"model": "claude-haiku-4-5-20251001", "api_key": "literal-key"},
    }


def test_loads_valid_config(tmp_path):
    cfg = load_config(write_config(tmp_path, base_data()))
    assert cfg.search.city == "San Francisco, CA"
    assert cfg.notify.telegram.bot_token == "literal-tok"
    assert cfg.llm.api_key == "literal-key"


def test_resolves_env_references(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-env")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-from-env")
    data = base_data()
    data["notify"]["telegram"]["bot_token"] = "env:TELEGRAM_BOT_TOKEN"
    data["llm"]["api_key"] = "env:ANTHROPIC_API_KEY"
    cfg = load_config(write_config(tmp_path, data))
    assert cfg.notify.telegram.bot_token == "from-env"
    assert cfg.llm.api_key == "key-from-env"


def test_rejects_both_neighborhoods_and_radius(tmp_path):
    data = base_data()
    data["search"]["radius_miles_from"] = {"lat": 37.7, "lng": -122.4, "miles": 2.0}
    with pytest.raises(ConfigError, match="mutually exclusive"):
        load_config(write_config(tmp_path, data))


def test_requires_neighborhoods_or_radius(tmp_path):
    data = base_data()
    data["search"]["neighborhoods"] = []
    with pytest.raises(ConfigError, match="at least one"):
        load_config(write_config(tmp_path, data))


def test_rejects_unknown_keys(tmp_path):
    data = base_data()
    data["search"]["mystery_key"] = "x"
    with pytest.raises(ConfigError):
        load_config(write_config(tmp_path, data))


def test_missing_env_var_errors(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    data = base_data()
    data["llm"]["api_key"] = "env:MISSING_VAR"
    with pytest.raises(ConfigError, match="MISSING_VAR"):
        load_config(write_config(tmp_path, data))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: ImportError on `find_my_next_place.config`.

- [ ] **Step 3: Implement `config.py`**

`find_my_next_place/config.py`:
```python
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator, ValidationError


class ConfigError(Exception):
    pass


class RadiusFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float
    lng: float
    miles: float


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str
    neighborhoods: list[str] = []
    radius_miles_from: RadiusFrom | None = None
    min_price: int
    max_price: int
    min_bedrooms: float
    max_bedrooms: float

    @model_validator(mode="after")
    def _exactly_one_geo(self):
        if self.neighborhoods and self.radius_miles_from:
            raise ValueError("neighborhoods and radius_miles_from are mutually exclusive")
        if not self.neighborhoods and not self.radius_miles_from:
            raise ValueError("at least one of neighborhoods or radius_miles_from required")
        return self


class PreferencesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_haves: list[str] = []
    deal_breakers: list[str] = []


class TelegramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot_token: str
    chat_id: str


class NotifyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telegram: TelegramConfig


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    api_key: str


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: SearchConfig
    preferences: PreferencesConfig
    sources: list[Literal["craigslist", "zillow"]]
    schedule_minutes: int
    notify: NotifyConfig
    llm: LLMConfig


def _resolve_env(value):
    if isinstance(value, str) and value.startswith("env:"):
        var = value[4:]
        resolved = os.environ.get(var)
        if resolved is None:
            raise ConfigError(f"environment variable {var} is not set")
        return resolved
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_config(path: str | Path) -> AppConfig:
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"failed to read config: {e}") from e
    resolved = _resolve_env(raw)
    try:
        return AppConfig.model_validate(resolved)
    except ValidationError as e:
        raise ConfigError(str(e)) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: 6 passed.

- [ ] **Step 5: Write `config.example.json`**

```json
{
  "search": {
    "city": "San Francisco, CA",
    "neighborhoods": ["Mission", "Hayes Valley", "Castro"],
    "radius_miles_from": null,
    "min_price": 2000,
    "max_price": 3800,
    "min_bedrooms": 1,
    "max_bedrooms": 2
  },
  "preferences": {
    "must_haves": ["in-unit laundry", "natural light"],
    "deal_breakers": ["top floor", "north-facing", "no windows in bedroom"]
  },
  "sources": ["craigslist", "zillow"],
  "schedule_minutes": 30,
  "notify": {
    "telegram": {
      "bot_token": "env:TELEGRAM_BOT_TOKEN",
      "chat_id": "env:TELEGRAM_CHAT_ID"
    }
  },
  "llm": {
    "model": "claude-haiku-4-5-20251001",
    "api_key": "env:ANTHROPIC_API_KEY"
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add find_my_next_place/config.py tests/test_config.py config.example.json
git commit -m "feat: config loader with env: resolution and Pydantic validation"
```

---

### Task 4: Storage layer (SQLite schema + DAO)

**Files:**
- Create: `find_my_next_place/storage/__init__.py` (empty)
- Create: `find_my_next_place/storage/migrations.py`
- Create: `find_my_next_place/storage/db.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_storage.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: ImportError on storage module.

- [ ] **Step 3: Write migrations**

`find_my_next_place/storage/migrations.py`:
```python
MIGRATIONS = [
    """
    CREATE TABLE listings (
      id INTEGER PRIMARY KEY,
      source TEXT NOT NULL,
      source_id TEXT NOT NULL,
      url TEXT NOT NULL,
      title TEXT,
      price INTEGER,
      beds REAL,
      baths REAL,
      sqft INTEGER,
      lat REAL,
      lng REAL,
      posted_at TIMESTAMP,
      raw_text TEXT,
      photos_json TEXT,
      first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(source, source_id)
    );
    """,
    """
    CREATE TABLE verdicts (
      listing_id INTEGER PRIMARY KEY REFERENCES listings(id),
      llm_verdict TEXT,
      llm_reasons TEXT,
      user_action TEXT NOT NULL DEFAULT 'pending',
      user_action_at TIMESTAMP
    );
    """,
    """
    CREATE TABLE notifications (
      id INTEGER PRIMARY KEY,
      listing_id INTEGER REFERENCES listings(id),
      channel TEXT,
      sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(listing_id, channel)
    );
    """,
    """
    CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
    """,
]
```

- [ ] **Step 4: Implement `db.py`**

`find_my_next_place/storage/db.py`:
```python
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
            if "schema_version" in sql and current == 0 and i < len(MIGRATIONS):
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add find_my_next_place/storage/ tests/test_storage.py
git commit -m "feat: SQLite storage with listings, verdicts, notifications"
```

---

### Task 5: Geo module (Nominatim + polygons)

**Files:**
- Create: `find_my_next_place/pipeline/__init__.py` (empty)
- Create: `find_my_next_place/pipeline/geo.py`
- Create: `tests/test_geo.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_geo.py`:
```python
import json
from unittest.mock import MagicMock
import pytest
from shapely.geometry import Polygon, Point
from find_my_next_place.pipeline.geo import (
    GeoResolver, point_in_any, point_within_radius,
)


def test_point_in_any_true():
    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    assert point_in_any(0.5, 0.5, [poly]) is True


def test_point_in_any_false():
    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    assert point_in_any(2, 2, [poly]) is False


def test_point_within_radius():
    # 1 degree latitude ≈ 69 miles. 0.01 degrees ≈ 0.69 miles.
    assert point_within_radius(37.76, -122.41, 37.77, -122.41, 1.0) is True
    assert point_within_radius(37.76, -122.41, 38.00, -122.41, 1.0) is False


def test_resolver_caches_results(tmp_path):
    cache = tmp_path / "geo.json"
    client = MagicMock()
    client.get.return_value.json.return_value = [{
        "geojson": {"type": "Polygon", "coordinates": [[
            [-122.42, 37.75], [-122.42, 37.77],
            [-122.40, 37.77], [-122.40, 37.75], [-122.42, 37.75]
        ]]}
    }]
    client.get.return_value.raise_for_status = lambda: None

    r = GeoResolver(cache_path=cache, http=client)
    polys = r.resolve(city="SF", neighborhoods=["Mission"])
    assert len(polys) == 1
    assert client.get.call_count == 1

    # Second call uses cache; no new HTTP call.
    polys2 = r.resolve(city="SF", neighborhoods=["Mission"])
    assert len(polys2) == 1
    assert client.get.call_count == 1


def test_resolver_raises_on_unresolved(tmp_path):
    client = MagicMock()
    client.get.return_value.json.return_value = []
    client.get.return_value.raise_for_status = lambda: None
    r = GeoResolver(cache_path=tmp_path / "g.json", http=client)
    with pytest.raises(RuntimeError, match="could not resolve"):
        r.resolve(city="SF", neighborhoods=["Nowhere"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_geo.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `geo.py`**

`find_my_next_place/pipeline/geo.py`:
```python
from __future__ import annotations
import json
import math
from pathlib import Path
import httpx
from shapely.geometry import Polygon, MultiPolygon, shape, Point

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "find-my-next-place/0.1 (https://github.com/)"


def point_in_any(lat: float, lng: float, polygons: list[Polygon]) -> bool:
    p = Point(lng, lat)
    return any(poly.contains(p) for poly in polygons)


def point_within_radius(lat1: float, lng1: float, lat2: float, lng2: float, miles: float) -> bool:
    # Haversine
    r = 3958.8  # earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    d = 2 * r * math.asin(math.sqrt(a))
    return d <= miles


class GeoResolver:
    def __init__(self, cache_path: Path, http: httpx.Client | None = None):
        self.cache_path = Path(cache_path)
        self.http = http or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            return json.loads(self.cache_path.read_text())
        return {}

    def _save_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache))

    def resolve(self, city: str, neighborhoods: list[str]) -> list[Polygon]:
        polys: list[Polygon] = []
        unresolved: list[str] = []
        for name in neighborhoods:
            key = f"{city}|{name}"
            geoj = self._cache.get(key)
            if geoj is None:
                geoj = self._fetch(city, name)
                if geoj is None:
                    unresolved.append(name)
                    continue
                self._cache[key] = geoj
                self._save_cache()
            geom = shape(geoj)
            if isinstance(geom, MultiPolygon):
                polys.extend(list(geom.geoms))
            elif isinstance(geom, Polygon):
                polys.append(geom)
        if unresolved:
            raise RuntimeError(f"could not resolve neighborhoods: {unresolved}")
        return polys

    def _fetch(self, city: str, name: str):
        resp = self.http.get(
            NOMINATIM_URL,
            params={"q": f"{name}, {city}", "format": "json", "polygon_geojson": 1, "limit": 1},
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        return results[0].get("geojson")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_geo.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add find_my_next_place/pipeline/ tests/test_geo.py
git commit -m "feat: geo resolver with Nominatim + polygon/radius checks"
```

---

### Task 6: Rule filter

**Files:**
- Create: `find_my_next_place/pipeline/rules.py`
- Create: `tests/test_rules.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_rules.py`:
```python
from datetime import datetime, timezone
from shapely.geometry import Polygon
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.pipeline.rules import RuleFilter, RuleResult


def L(**overrides) -> Listing:
    base = dict(
        source="craigslist", source_id="x", url="u", title="t",
        price=3000, beds=1.0, baths=1.0, sqft=600,
        lat=37.76, lng=-122.41,
        posted_at=datetime.now(timezone.utc),
        raw_text="", photos=[],
    )
    base.update(overrides)
    return Listing(**base)


SF_POLY = Polygon([(-122.42, 37.75), (-122.42, 37.77),
                   (-122.40, 37.77), (-122.40, 37.75)])


def test_passes_a_good_listing():
    f = RuleFilter(min_price=2000, max_price=3500,
                   min_beds=1, max_beds=2, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(), seen=set())
    assert r.passes is True


def test_drops_out_of_price():
    f = RuleFilter(min_price=2000, max_price=2500,
                   min_beds=1, max_beds=2, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(price=3000), seen=set())
    assert r.passes is False
    assert "price" in r.reason


def test_drops_out_of_beds():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=2, max_beds=3, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(beds=1.0), seen=set())
    assert r.passes is False
    assert "beds" in r.reason


def test_missing_beds_passes():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=2, max_beds=3, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(beds=None), seen=set())
    assert r.passes is True


def test_drops_already_seen():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10, polygons=[SF_POLY], radius=None)
    listing = L()
    r = f.evaluate(listing, seen={listing.dedup_key()})
    assert r.passes is False
    assert "seen" in r.reason


def test_drops_outside_polygons():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(lat=40.0, lng=-74.0), seen=set())
    assert r.passes is False
    assert "geo" in r.reason


def test_missing_coords_passes_with_flag():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10, polygons=[SF_POLY], radius=None)
    r = f.evaluate(L(lat=None, lng=None), seen=set())
    assert r.passes is True
    assert r.coords_missing is True


def test_radius_mode():
    f = RuleFilter(min_price=0, max_price=10000,
                   min_beds=0, max_beds=10,
                   polygons=[],
                   radius=(37.76, -122.41, 0.5))
    assert f.evaluate(L(lat=37.762, lng=-122.41), seen=set()).passes is True
    assert f.evaluate(L(lat=38.0, lng=-122.41), seen=set()).passes is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rules.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `rules.py`**

`find_my_next_place/pipeline/rules.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from shapely.geometry import Polygon
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.pipeline.geo import point_in_any, point_within_radius


@dataclass
class RuleResult:
    passes: bool
    reason: str = ""
    coords_missing: bool = False


class RuleFilter:
    def __init__(
        self,
        min_price: int,
        max_price: int,
        min_beds: float,
        max_beds: float,
        polygons: list[Polygon],
        radius: tuple[float, float, float] | None,
    ):
        self.min_price = min_price
        self.max_price = max_price
        self.min_beds = min_beds
        self.max_beds = max_beds
        self.polygons = polygons
        self.radius = radius

    def evaluate(self, listing: Listing, seen: set[tuple[str, str]]) -> RuleResult:
        if listing.dedup_key() in seen:
            return RuleResult(False, "already seen")
        if not (self.min_price <= listing.price <= self.max_price):
            return RuleResult(False, f"price {listing.price} out of band")
        if listing.beds is not None and not (self.min_beds <= listing.beds <= self.max_beds):
            return RuleResult(False, f"beds {listing.beds} out of band")
        if listing.coords_missing():
            return RuleResult(True, coords_missing=True)
        if self.polygons and not point_in_any(listing.lat, listing.lng, self.polygons):
            return RuleResult(False, "geo: outside neighborhoods")
        if self.radius is not None:
            clat, clng, miles = self.radius
            if not point_within_radius(listing.lat, listing.lng, clat, clng, miles):
                return RuleResult(False, "geo: outside radius")
        return RuleResult(True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rules.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add find_my_next_place/pipeline/rules.py tests/test_rules.py
git commit -m "feat: deterministic rule filter (price, beds, geo, dedup)"
```

---

### Task 7: LLM filter

**Files:**
- Create: `find_my_next_place/pipeline/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_llm.py`:
```python
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.pipeline.llm import LLMFilter, Verdict


def L(text="Bright 1BR with in-unit laundry"):
    return Listing(
        source="craigslist", source_id="x", url="u", title="1BR",
        price=3000, beds=1.0, baths=1.0, sqft=None,
        lat=None, lng=None,
        posted_at=datetime.now(timezone.utc),
        raw_text=text, photos=[],
    )


def mock_response(text: str):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def test_parses_approve_verdict():
    client = MagicMock()
    client.messages.create.return_value = mock_response(
        '{"verdict":"approve","reasons":"Has laundry; matches taste"}'
    )
    f = LLMFilter(client=client, model="m", must_haves=["laundry"], deal_breakers=["top floor"])
    v = f.evaluate(L())
    assert v.verdict == "approve"
    assert "laundry" in v.reasons


def test_parses_reject_verdict():
    client = MagicMock()
    client.messages.create.return_value = mock_response(
        '{"verdict":"reject","reasons":"top floor"}'
    )
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=["top floor"])
    v = f.evaluate(L("Penthouse on the top floor"))
    assert v.verdict == "reject"


def test_unsure_on_malformed_json():
    client = MagicMock()
    client.messages.create.return_value = mock_response("not json at all")
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=[])
    v = f.evaluate(L())
    assert v.verdict == "unsure"
    assert v.reasons == "llm_error: malformed response"


def test_unsure_on_api_exception():
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=[],
                  max_retries=2, sleep=lambda s: None)
    v = f.evaluate(L())
    assert v.verdict == "unsure"
    assert v.reasons.startswith("llm_error")
    assert client.messages.create.call_count == 2


def test_extracts_json_from_surrounding_prose():
    client = MagicMock()
    client.messages.create.return_value = mock_response(
        'Sure thing! {"verdict":"approve","reasons":"ok"} Hope this helps.'
    )
    f = LLMFilter(client=client, model="m", must_haves=[], deal_breakers=[])
    assert f.evaluate(L()).verdict == "approve"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `llm.py`**

`find_my_next_place/pipeline/llm.py`:
```python
from __future__ import annotations
import json
import re
import time
from dataclasses import dataclass
from find_my_next_place.scrapers.base import Listing


SYSTEM_PROMPT = """You evaluate rental listings against a user's preferences.
Reply with strict JSON only: {"verdict":"approve"|"reject"|"unsure","reasons":"..."}
- "approve": clearly matches must-haves and violates no deal-breakers
- "reject": clearly violates a deal-breaker
- "unsure": ambiguous or insufficient information
Keep reasons under 200 characters."""


@dataclass
class Verdict:
    verdict: str
    reasons: str


def _build_user_prompt(listing: Listing, must_haves: list[str], deal_breakers: list[str]) -> str:
    return (
        f"Listing:\n"
        f"  Title: {listing.title}\n"
        f"  Price: {listing.price}\n"
        f"  Beds/Baths: {listing.beds}/{listing.baths}\n"
        f"  Description: {listing.raw_text}\n\n"
        f"User must-haves: {must_haves}\n"
        f"User deal-breakers: {deal_breakers}\n"
    )


_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_verdict(text: str) -> Verdict:
    match = _JSON_RE.search(text)
    if not match:
        return Verdict("unsure", "llm_error: malformed response")
    try:
        data = json.loads(match.group(0))
        v = data.get("verdict")
        r = data.get("reasons", "")
        if v not in ("approve", "reject", "unsure"):
            return Verdict("unsure", "llm_error: bad verdict")
        return Verdict(v, str(r))
    except json.JSONDecodeError:
        return Verdict("unsure", "llm_error: malformed response")


class LLMFilter:
    def __init__(self, client, model: str, must_haves: list[str], deal_breakers: list[str],
                 max_retries: int = 3, sleep=time.sleep):
        self.client = client
        self.model = model
        self.must_haves = must_haves
        self.deal_breakers = deal_breakers
        self.max_retries = max_retries
        self.sleep = sleep

    def evaluate(self, listing: Listing) -> Verdict:
        user = _build_user_prompt(listing, self.must_haves, self.deal_breakers)
        backoff = 1.0
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=300,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user}],
                )
                text = resp.content[0].text
                return _parse_verdict(text)
            except Exception as e:
                last_err = e
                self.sleep(backoff)
                backoff *= 2
        return Verdict("unsure", f"llm_error: {last_err}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add find_my_next_place/pipeline/llm.py tests/test_llm.py
git commit -m "feat: LLM filter with Claude Haiku, retry, robust JSON parsing"
```

---

### Task 8: Craigslist scraper

**Files:**
- Create: `find_my_next_place/scrapers/craigslist.py`
- Create: `tests/scrapers/test_craigslist.py`
- Create: `tests/scrapers/fixtures/craigslist/sample_rss.xml`

- [ ] **Step 1: Capture a fixture**

Manually save a Craigslist RSS sample to `tests/scrapers/fixtures/craigslist/sample_rss.xml`. Use this minimal fixture so tests don't depend on external content:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns="http://purl.org/rss/1.0/"
         xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <item rdf:about="https://sfbay.craigslist.org/sfc/apa/d/example/7700000001.html">
    <title>$3200 / 1br - Sunny 1BR Mission near BART</title>
    <link>https://sfbay.craigslist.org/sfc/apa/d/example/7700000001.html</link>
    <description>Bright 1BR with in-unit laundry. Hardwood floors. 16th St BART.</description>
    <dc:date>2026-05-14T08:30:00-07:00</dc:date>
  </item>
  <item rdf:about="https://sfbay.craigslist.org/sfc/apa/d/example/7700000002.html">
    <title>$2800 / 2br - Hayes Valley 2BR top floor</title>
    <link>https://sfbay.craigslist.org/sfc/apa/d/example/7700000002.html</link>
    <description>Top-floor 2BR. No washer/dryer. Quiet block.</description>
    <dc:date>2026-05-14T09:00:00-07:00</dc:date>
  </item>
</rdf:RDF>
```

- [ ] **Step 2: Write the failing tests**

`tests/scrapers/test_craigslist.py`:
```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/scrapers/test_craigslist.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `craigslist.py`**

`find_my_next_place/scrapers/craigslist.py`:
```python
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional
import feedparser
import httpx
from find_my_next_place.scrapers.base import Listing

PRICE_RE = re.compile(r"\$(\d[\d,]*)")
BEDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*br\b", re.IGNORECASE)
ID_RE = re.compile(r"/(\d+)\.html")


def _city_to_rss(city: str) -> str:
    # Default URL pattern; the engineer should pass it in via search config in real use.
    # For SF: https://sfbay.craigslist.org/search/apa?format=rss
    return "https://sfbay.craigslist.org/search/apa?format=rss"


class CraigslistScraper:
    name = "craigslist"

    def __init__(self, http: Optional[httpx.Client] = None, rss_url: Optional[str] = None):
        self.http = http or httpx.Client(timeout=30, headers={"User-Agent": "fmnp/0.1"})
        self.rss_url = rss_url

    def fetch(self, search) -> list[Listing]:
        url = self.rss_url or _city_to_rss(search.city)
        resp = self.http.get(url)
        resp.raise_for_status()
        return self.parse(resp.text, source=self.name)

    @staticmethod
    def parse(rss: str, source: str) -> list[Listing]:
        feed = feedparser.parse(rss)
        out: list[Listing] = []
        for e in feed.entries:
            title = getattr(e, "title", "") or ""
            link = getattr(e, "link", "") or ""
            desc = getattr(e, "summary", "") or getattr(e, "description", "") or ""
            posted = _parse_date(getattr(e, "date", None) or getattr(e, "dc_date", None))
            price = _extract_int(PRICE_RE, title)
            beds = _extract_float(BEDS_RE, title)
            id_match = ID_RE.search(link)
            source_id = id_match.group(1) if id_match else link
            if price is None:
                continue
            out.append(Listing(
                source=source, source_id=source_id, url=link, title=title.strip(),
                price=price, beds=beds, baths=None, sqft=None,
                lat=None, lng=None,
                posted_at=posted, raw_text=desc.strip(), photos=[],
            ))
        return out


def _extract_int(rx, s):
    m = rx.search(s)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def _extract_float(rx, s):
    m = rx.search(s)
    if not m:
        return None
    return float(m.group(1))


def _parse_date(s):
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/scrapers/test_craigslist.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add find_my_next_place/scrapers/craigslist.py tests/scrapers/
git commit -m "feat: Craigslist RSS scraper"
```

---

### Task 9: Telegram notify

**Files:**
- Create: `find_my_next_place/notify/__init__.py` (empty)
- Create: `find_my_next_place/notify/telegram.py`
- Create: `tests/test_telegram.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_telegram.py`:
```python
from unittest.mock import MagicMock
from find_my_next_place.notify.telegram import TelegramNotifier


def test_sends_formatted_message():
    http = MagicMock()
    http.post.return_value.raise_for_status = lambda: None
    n = TelegramNotifier(bot_token="tok", chat_id="42", http=http)
    n.send(
        title="1BR Mission",
        price=3200,
        url="https://example.com/x",
        rationale="Has laundry, good light",
        photo_url="https://example.com/p.jpg",
    )
    http.post.assert_called_once()
    args, kwargs = http.post.call_args
    assert "tok" in args[0]
    payload = kwargs["json"]
    assert payload["chat_id"] == "42"
    assert "1BR Mission" in payload["caption"]
    assert "$3200" in payload["caption"]
    assert "example.com/x" in payload["caption"]


def test_falls_back_to_text_when_no_photo():
    http = MagicMock()
    http.post.return_value.raise_for_status = lambda: None
    n = TelegramNotifier(bot_token="tok", chat_id="42", http=http)
    n.send(title="t", price=2000, url="u", rationale="r", photo_url=None)
    args, _ = http.post.call_args
    assert "sendMessage" in args[0]


def test_raises_on_http_error():
    http = MagicMock()
    http.post.return_value.raise_for_status.side_effect = RuntimeError("400")
    n = TelegramNotifier(bot_token="tok", chat_id="42", http=http)
    import pytest
    with pytest.raises(RuntimeError):
        n.send(title="t", price=1, url="u", rationale="r", photo_url=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_telegram.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `telegram.py`**

`find_my_next_place/notify/telegram.py`:
```python
from __future__ import annotations
import httpx


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, http: httpx.Client | None = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.http = http or httpx.Client(timeout=15)

    def send(self, *, title: str, price: int, url: str, rationale: str, photo_url: str | None):
        caption = f"*{title}*\n${price}\n{url}\n\n_{rationale}_"
        if photo_url:
            api = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            payload = {"chat_id": self.chat_id, "photo": photo_url,
                       "caption": caption, "parse_mode": "Markdown"}
        else:
            api = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": caption,
                       "parse_mode": "Markdown", "disable_web_page_preview": False}
        resp = self.http.post(api, json=payload)
        resp.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add find_my_next_place/notify/ tests/test_telegram.py
git commit -m "feat: Telegram notifier (sendPhoto with caption)"
```

---

### Task 10: Pipeline cycle orchestrator

**Files:**
- Create: `find_my_next_place/pipeline/cycle.py`
- Create: `tests/test_cycle.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cycle.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cycle.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `cycle.py`**

`find_my_next_place/pipeline/cycle.py`:
```python
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from find_my_next_place.scrapers.base import Listing
from find_my_next_place.pipeline.rules import RuleFilter
from find_my_next_place.pipeline.llm import LLMFilter
from find_my_next_place.storage.db import Database
from find_my_next_place.notify.telegram import TelegramNotifier


log = logging.getLogger(__name__)


@dataclass
class CycleSummary:
    scraped: int = 0
    rule_passed: int = 0
    llm_approved: int = 0
    llm_unsure: int = 0
    llm_rejected: int = 0
    notified: int = 0
    errors: dict[str, str] = field(default_factory=dict)


def run_cycle(*, db: Database, scrapers, search,
              rule_filter: RuleFilter, llm_filter: LLMFilter,
              notifier: TelegramNotifier | None) -> CycleSummary:
    summary = CycleSummary()
    seen = set()
    for s in scrapers:
        seen.update(db.seen_keys(s.name))
    for scraper in scrapers:
        try:
            listings = scraper.fetch(search)
        except Exception as e:
            log.exception("scraper %s failed", scraper.name)
            summary.errors[scraper.name] = str(e)
            continue
        for listing in listings:
            summary.scraped += 1
            inserted = db.upsert_listing(listing)
            if not inserted:
                continue
            decision = rule_filter.evaluate(listing, seen=seen)
            if not decision.passes:
                continue
            summary.rule_passed += 1
            verdict = llm_filter.evaluate(listing)
            db.record_verdict(listing.dedup_key(), verdict.verdict, verdict.reasons)
            if verdict.verdict == "approve":
                summary.llm_approved += 1
            elif verdict.verdict == "unsure":
                summary.llm_unsure += 1
            else:
                summary.llm_rejected += 1
    if notifier is not None:
        for row in db.pending_notifications("telegram"):
            listing = db.get_listing(row.listing_id)
            verdict = db.get_verdict((row.source, row.source_id))
            photo = None
            try:
                import json
                photos = json.loads(listing["photos_json"] or "[]")
                photo = photos[0] if photos else None
            except (ValueError, KeyError, TypeError):
                pass
            try:
                notifier.send(
                    title=listing["title"], price=listing["price"],
                    url=listing["url"], rationale=verdict.llm_reasons or "",
                    photo_url=photo,
                )
                db.record_notification(row.listing_id, "telegram")
                summary.notified += 1
            except Exception as e:
                log.warning("telegram send failed for %s: %s", row.listing_id, e)
    log.info("cycle: %s", summary)
    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cycle.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add find_my_next_place/pipeline/cycle.py tests/test_cycle.py
git commit -m "feat: pipeline cycle orchestrator with per-source isolation"
```

---

### Task 11: Zillow scraper (Camoufox)

**Files:**
- Create: `find_my_next_place/scrapers/zillow.py`
- Create: `tests/scrapers/test_zillow.py`
- Create: `tests/scrapers/fixtures/zillow/sample_search.html`

- [ ] **Step 1: Capture a fixture**

Save a small representative chunk of Zillow's search-results HTML to `tests/scrapers/fixtures/zillow/sample_search.html`. The parser will look for the embedded JSON in the `__NEXT_DATA__` script tag — this is Zillow's standard pattern. Use a minimal fixture for tests:

```html
<!doctype html>
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"searchPageState":{"cat1":{"searchResults":{"listResults":[
  {"zpid":"123456","detailUrl":"https://www.zillow.com/homedetails/123456_zpid/",
   "address":"123 Mission St, San Francisco, CA","price":"$3,400/mo","beds":1,"baths":1,
   "area":650,"latLong":{"latitude":37.7599,"longitude":-122.4148},
   "imgSrc":"https://photos.zillowstatic.com/x.jpg",
   "statusText":"For Rent","hdpData":{"homeInfo":{"description":"Bright apartment with washer/dryer"}}},
  {"zpid":"123457","detailUrl":"https://www.zillow.com/homedetails/123457_zpid/",
   "address":"456 Hayes St, San Francisco, CA","price":"$2,950/mo","beds":2,"baths":1,
   "area":850,"latLong":{"latitude":37.7765,"longitude":-122.4243},
   "imgSrc":"https://photos.zillowstatic.com/y.jpg","statusText":"For Rent","hdpData":{}}
]}}}}}}
</script>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/scrapers/test_zillow.py`:
```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/scrapers/test_zillow.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `zillow.py`**

`find_my_next_place/scrapers/zillow.py`:
```python
from __future__ import annotations
import json
import re
import time
from datetime import datetime, timezone
from typing import Optional
from find_my_next_place.scrapers.base import Listing


NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
PRICE_RE = re.compile(r"\$([\d,]+)")


class ZillowAntiBotError(RuntimeError):
    pass


class ZillowScraper:
    name = "zillow"

    def __init__(self, search_url: Optional[str] = None):
        self.search_url = search_url
        self._block_until: float = 0.0

    def fetch(self, search) -> list[Listing]:
        if time.time() < self._block_until:
            return []
        try:
            html = self._load_html(search)
        except ZillowAntiBotError:
            self._block_until = time.time() + 60 * 60  # 1 hour back-off
            return []
        return self.parse(html)

    def _load_html(self, search) -> str:
        from camoufox.sync_api import Camoufox
        url = self.search_url or _build_search_url(search)
        with Camoufox(headless=True) as browser:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            html = page.content()
        if "Press &amp; Hold" in html or "captcha" in html.lower():
            raise ZillowAntiBotError("anti-bot detected")
        return html

    @staticmethod
    def parse(html: str) -> list[Listing]:
        m = NEXT_DATA_RE.search(html)
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []
        try:
            results = (data["props"]["pageProps"]["searchPageState"]
                       ["cat1"]["searchResults"]["listResults"])
        except (KeyError, TypeError):
            return []
        out: list[Listing] = []
        for r in results:
            price_raw = r.get("price")
            if not price_raw:
                continue
            pm = PRICE_RE.search(price_raw)
            if not pm:
                continue
            ll = r.get("latLong") or {}
            hdp = (r.get("hdpData") or {}).get("homeInfo") or {}
            out.append(Listing(
                source="zillow",
                source_id=str(r.get("zpid")),
                url=r.get("detailUrl") or "",
                title=r.get("address") or "",
                price=int(pm.group(1).replace(",", "")),
                beds=_to_float(r.get("beds")),
                baths=_to_float(r.get("baths")),
                sqft=_to_int(r.get("area")),
                lat=_to_float(ll.get("latitude")),
                lng=_to_float(ll.get("longitude")),
                posted_at=datetime.now(timezone.utc),
                raw_text=hdp.get("description") or r.get("statusText") or "",
                photos=[r.get("imgSrc")] if r.get("imgSrc") else [],
            ))
        return out


def _build_search_url(search) -> str:
    # The engineer should refine this per-city; safe default for SF rentals.
    return "https://www.zillow.com/san-francisco-ca/rentals/"


def _to_float(v):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None


def _to_int(v):
    if v is None: return None
    try: return int(v)
    except (TypeError, ValueError): return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/scrapers/test_zillow.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add find_my_next_place/scrapers/zillow.py tests/scrapers/test_zillow.py tests/scrapers/fixtures/zillow/
git commit -m "feat: Zillow scraper via Camoufox + __NEXT_DATA__ parsing"
```

---

### Task 12: Review queue web UI

**Files:**
- Create: `find_my_next_place/web/__init__.py` (empty)
- Create: `find_my_next_place/web/app.py`
- Create: `find_my_next_place/web/templates/base.html`
- Create: `find_my_next_place/web/templates/queue.html`
- Create: `find_my_next_place/web/templates/listing.html`
- Create: `find_my_next_place/web/static/style.css`
- Create: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_web.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement templates**

`find_my_next_place/web/templates/base.html`:
```html
<!doctype html>
<html><head>
<meta charset="utf-8"><title>find-my-next-place</title>
<link rel="stylesheet" href="/static/style.css">
</head><body>
<header><h1><a href="/">find-my-next-place</a></h1></header>
<main>{% block content %}{% endblock %}</main>
</body></html>
```

`find_my_next_place/web/templates/queue.html`:
```html
{% extends "base.html" %}
{% block content %}
<h2>Review queue ({{ listings|length }})</h2>
{% for l in listings %}
  <article class="card">
    <h3><a href="/listing/{{ l.id }}">{{ l.title }}</a></h3>
    <p>${{ l.price }} · {{ l.beds }}BR / {{ l.baths }}BA · <a href="{{ l.url }}" target="_blank">source</a></p>
    <p class="rationale">{{ l.llm_verdict }}: {{ l.llm_reasons }}</p>
    <form method="post" action="/listing/{{ l.id }}/action" class="actions">
      <button name="action" value="approved">Approve</button>
      <button name="action" value="snoozed">Snooze 7d</button>
      <button name="action" value="rejected">Reject</button>
    </form>
  </article>
{% else %}
  <p>Queue is empty.</p>
{% endfor %}
{% endblock %}
```

`find_my_next_place/web/templates/listing.html`:
```html
{% extends "base.html" %}
{% block content %}
<h2>{{ listing.title }}</h2>
<p>${{ listing.price }} · {{ listing.beds }}BR / {{ listing.baths }}BA · {{ listing.sqft or "?" }} sqft</p>
<p><a href="{{ listing.url }}" target="_blank">Open source listing</a></p>
<p class="rationale">{{ verdict.llm_verdict }}: {{ verdict.llm_reasons }}</p>
<pre class="raw">{{ listing.raw_text }}</pre>
{% endblock %}
```

`find_my_next_place/web/static/style.css`:
```css
body{font-family:system-ui,sans-serif;max-width:840px;margin:2rem auto;padding:0 1rem;color:#222}
.card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}
.rationale{color:#555;font-style:italic}
.actions button{margin-right:.5rem}
pre.raw{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border-radius:6px}
```

- [ ] **Step 4: Implement `app.py`**

`find_my_next_place/web/app.py`:
```python
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from find_my_next_place.storage.db import Database

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=ROOT / "templates")


def create_app(db: Database) -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def queue(request: Request):
        listings = _surface_pending(db)
        return templates.TemplateResponse(
            "queue.html", {"request": request, "listings": listings},
        )

    @app.get("/listing/{listing_id}")
    def detail(request: Request, listing_id: int):
        listing = db.get_listing(listing_id)
        verdict = db.get_verdict((listing["source"], listing["source_id"]))
        return templates.TemplateResponse(
            "listing.html",
            {"request": request, "listing": listing, "verdict": verdict},
        )

    @app.post("/listing/{listing_id}/action")
    def action(listing_id: int, action: str = Form(...)):
        listing = db.get_listing(listing_id)
        key = (listing["source"], listing["source_id"])
        db.set_user_action(key, action)
        return RedirectResponse("/", status_code=303)

    return app


def _surface_pending(db: Database):
    rows = db.list_pending()
    # Re-include snoozed rows whose snooze has expired.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    db._conn.execute(  # noqa: SLF001
        """
        UPDATE verdicts SET user_action='pending', user_action_at=NULL
        WHERE user_action='snoozed' AND user_action_at < ?
        """,
        (cutoff,),
    )
    db._conn.commit()
    return rows
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_web.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add find_my_next_place/web/ tests/test_web.py
git commit -m "feat: FastAPI review-queue UI with approve/snooze/reject"
```

---

### Task 13: Scheduler and entry point

**Files:**
- Create: `find_my_next_place/scheduler.py`
- Create: `find_my_next_place/__main__.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_scheduler.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scheduler.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `scheduler.py`**

`find_my_next_place/scheduler.py`:
```python
from __future__ import annotations
import logging
import threading
from pathlib import Path
from anthropic import Anthropic
from apscheduler.schedulers.blocking import BlockingScheduler
from find_my_next_place.config import AppConfig
from find_my_next_place.notify.telegram import TelegramNotifier
from find_my_next_place.pipeline.cycle import run_cycle
from find_my_next_place.pipeline.geo import GeoResolver
from find_my_next_place.pipeline.llm import LLMFilter
from find_my_next_place.pipeline.rules import RuleFilter
from find_my_next_place.scrapers.craigslist import CraigslistScraper
from find_my_next_place.scrapers.zillow import ZillowScraper
from find_my_next_place.storage.db import Database


log = logging.getLogger(__name__)


def build_scrapers(cfg: AppConfig) -> list:
    registry = {"craigslist": CraigslistScraper, "zillow": ZillowScraper}
    return [registry[name]() for name in cfg.sources]


def build_search_arg(cfg: AppConfig):
    return cfg.search


def build_rule_filter(cfg: AppConfig, geo: GeoResolver) -> RuleFilter:
    if cfg.search.neighborhoods:
        polys = geo.resolve(cfg.search.city, cfg.search.neighborhoods)
        radius = None
    else:
        polys = []
        r = cfg.search.radius_miles_from
        radius = (r.lat, r.lng, r.miles)
    return RuleFilter(
        min_price=cfg.search.min_price, max_price=cfg.search.max_price,
        min_beds=cfg.search.min_bedrooms, max_beds=cfg.search.max_bedrooms,
        polygons=polys, radius=radius,
    )


def start_web(db: Database, host: str = "127.0.0.1", port: int = 8765):
    import uvicorn
    from find_my_next_place.web.app import create_app
    app = create_app(db)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()


def run(cfg: AppConfig, *, data_dir: Path, once: bool = False):
    db = Database(data_dir / "fmnp.db")
    geo = GeoResolver(cache_path=data_dir / "geo_cache.json")
    rule_filter = build_rule_filter(cfg, geo)
    llm_client = Anthropic(api_key=cfg.llm.api_key)
    llm_filter = LLMFilter(
        client=llm_client, model=cfg.llm.model,
        must_haves=cfg.preferences.must_haves,
        deal_breakers=cfg.preferences.deal_breakers,
    )
    notifier = TelegramNotifier(
        bot_token=cfg.notify.telegram.bot_token,
        chat_id=cfg.notify.telegram.chat_id,
    )
    scrapers = build_scrapers(cfg)
    search = build_search_arg(cfg)

    def job():
        run_cycle(db=db, scrapers=scrapers, search=search,
                  rule_filter=rule_filter, llm_filter=llm_filter,
                  notifier=notifier)

    if once:
        job()
        return

    start_web(db)
    job()  # immediate run

    scheduler = BlockingScheduler()
    scheduler.add_job(job, "interval", minutes=cfg.schedule_minutes)
    log.info("scheduler started; cadence=%dm", cfg.schedule_minutes)
    scheduler.start()
```

- [ ] **Step 4: Implement `__main__.py`**

`find_my_next_place/__main__.py`:
```python
from __future__ import annotations
import argparse
import logging
from pathlib import Path
from find_my_next_place.config import load_config
from find_my_next_place.scheduler import run


def main():
    parser = argparse.ArgumentParser(prog="find-my-next-place")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--data-dir", default=Path("data"), type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config(args.config)
    run(cfg, data_dir=args.data_dir, once=args.once)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add find_my_next_place/scheduler.py find_my_next_place/__main__.py tests/test_scheduler.py
git commit -m "feat: scheduler + CLI entry point"
```

---

### Task 14: End-to-end smoke run + README pointers

**Files:**
- Create: `tests/test_e2e.py`
- Modify: existing files as needed (no source changes expected if previous tasks are correct)

- [ ] **Step 1: Write the end-to-end test**

`tests/test_e2e.py`:
```python
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
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full suite one more time**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Smoke-run the app**

```bash
ANTHROPIC_API_KEY=sk-... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \
  python -m find_my_next_place --config config.example.json --once --log-level INFO
```
Expected: a single cycle runs, logs a `cycle: ...` summary, and exits cleanly. (May log scraper errors against live sources; that's acceptable for a smoke run.)

- [ ] **Step 5: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: end-to-end cycle against Craigslist fixture + mocks"
```

---

## Self-Review Checklist (already executed)

- **Spec coverage:** every section of the spec maps to at least one task — scrapers (Tasks 8, 11), rules (6), LLM (7), geo (5), storage (4), config (3), notify (9), web UI (12), scheduler (13), cycle orchestrator (10), end-to-end test (14).
- **Placeholders:** none — every task has executable code and exact commands.
- **Type consistency:** `Listing.dedup_key()` returns `(source, source_id)` and is used consistently as the dict/set key throughout. `Verdict.verdict` ∈ `{approve, reject, unsure}` consistently. `RuleResult.passes` is the boolean predicate. `Database` constructor accepts a path; tests use `tmp_path / "...db"`.
- **Out of order:** Tasks 1–10 form the core. Task 11 (Zillow) is independent of 12–14 and can be deferred if Camoufox setup blocks progress. Task 12 (web) requires 4 (storage). Task 13 (scheduler) requires everything above it.
