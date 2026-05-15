# find-my-next-place — Design Spec

**Date:** 2026-05-15
**Status:** Draft, awaiting approval
**Inspiration:** [Gabor Csapo's AI real estate agent](https://github.com/gaborcsapo/ai-real-estate-agent) and [accompanying write-up](https://gaborcsapo.substack.com/p/what-does-apartment-hunting-in-sf)

## Problem

Apartment hunting requires monitoring many platforms, filtering listings by hard constraints (price, beds, area), and then judging subjective qualities (light, layout, noise, building reputation). The mechanical parts waste hours; the human parts — viewings, applications, rapport with landlords — actually win the apartment.

`find-my-next-place` automates only the mechanical parts. It scrapes a configurable set of sources, applies deterministic rules, asks an LLM about subjective preferences, and surfaces survivors in a review queue with Telegram pings. The user does everything that matters: viewings, applications, and follow-up.

## Non-Goals

- ML-based ranking or learned preferences from user feedback
- Auto-applying, auto-contacting landlords, or any outbound action on the user's behalf
- Multi-tenant hosting or shared deployment
- A mobile app — the Telegram bot is the mobile surface
- Hard-coded city support — the tool is city-agnostic from day one

## Success Criteria

- A user can clone the repo, write a `config.json` for any US city with named neighborhoods, and within an hour have a pipeline running on a schedule.
- A full scrape → filter → LLM → notify cycle for two enabled sources completes in under 5 minutes on a laptop.
- A scraper failure on one source does not prevent other sources from running in that cycle.
- LLM cost stays under $1/day at default settings (Claude Haiku, two sources, 30-minute cadence) for a typical SF-sized market.
- The review queue UI lets the user approve, reject, or snooze listings; rejections feed back into the dedup set so they never re-appear.

## Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Scrapers   │ ──> │ Rule Filter  │ ──> │  LLM Filter  │ ──> │ Review Queue │
│ (per source)│     │(price, geo,  │     │(Claude Haiku │     │ (SQLite +    │
│             │     │ beds, dedup) │     │ subjective)  │     │ web UI +     │
└─────────────┘     └──────────────┘     └──────────────┘     │  Telegram)   │
       ▲                                                       └──────────────┘
       │
   Scheduler (APScheduler, runs every N minutes)
       │
   config.json (city, neighborhoods, budget, beds, preferences, sources, notify)
```

The pipeline is a one-way data flow. Each stage has a small, stable interface so stages can be developed and tested in isolation.

## Module Layout

```
find_my_next_place/
  __init__.py
  __main__.py              # `python -m find_my_next_place`
  config.py                # Pydantic models for config.json
  scheduler.py             # APScheduler wiring + cycle entry point
  pipeline/
    __init__.py
    cycle.py               # Orchestrates one scrape→filter→llm→notify cycle
    rules.py               # Deterministic filters
    llm.py                 # Claude Haiku call + prompt construction
    geo.py                 # Neighborhood polygon resolution via Nominatim
  scrapers/
    __init__.py
    base.py                # Scraper protocol + Listing dataclass
    craigslist.py
    zillow.py              # Camoufox-backed
  storage/
    __init__.py
    db.py                  # SQLite schema + DAO functions
    migrations.py          # Forward-only schema migrations
  notify/
    __init__.py
    telegram.py
  web/
    __init__.py
    app.py                 # FastAPI app for the review queue UI
    templates/             # Jinja templates for listing cards
    static/
docs/
tests/
config.example.json
```

## Components

### Scrapers (`scrapers/`)

Each scraper exports a class implementing the `Scraper` protocol:

```python
class Scraper(Protocol):
    name: str
    def fetch(self, search: SearchConfig) -> list[Listing]: ...
```

`Listing` is a normalized dataclass:

```python
@dataclass
class Listing:
    source: str
    source_id: str           # stable per-source ID for dedup
    url: str
    title: str
    price: int               # USD/month
    beds: float | None
    baths: float | None
    sqft: int | None
    lat: float | None
    lng: float | None
    posted_at: datetime
    raw_text: str            # full description; fed to the LLM
    photos: list[str]        # absolute URLs
```

**MVP scrapers:**

- **Craigslist** — RSS feed per city per category. No JS needed, no auth. The most portable source across cities. Uses `httpx`.
- **Zillow** — Requires stealth. Uses `Camoufox` (a hardened Firefox) to load search results, parses listing cards, follows links to detail pages for full descriptions. Has explicit anti-bot detection (CAPTCHA / soft-block pages) and backs off when detected.

A new scraper is one new file plus an entry in the source registry. The `Scraper` protocol is the only contract; everything else (HTTP client, parsing strategy) is per-source.

### Rule filter (`pipeline/rules.py`)

Pure functions, no I/O. Drops a listing if any of:

- Price outside `[min_price, max_price]`
- Beds outside `[min_bedrooms, max_bedrooms]` (a missing bed count survives — Craigslist often omits it)
- Already seen (composite key: `source` + `source_id`) and either currently in the queue or previously rejected
- Geo: when neighborhoods are configured, the listing's coordinates must fall inside at least one neighborhood polygon. When `radius_miles_from` is configured instead, the listing must be within radius of the named point. Missing coordinates pass through to the LLM stage with a `coords_missing` flag rather than being dropped — Gabor found dropping these loses too many real listings.

### Geo resolution (`pipeline/geo.py`)

Neighborhood names from config are resolved to polygons via OpenStreetMap's Nominatim API at startup. Results are cached to `data/geo_cache.json` so subsequent runs are offline. Polygons are stored as Shapely `Polygon` objects; the point-in-polygon check is plain Shapely.

If Nominatim can't find a named neighborhood, startup fails loudly with a message listing the unresolved names — better than silently dropping listings.

### LLM filter (`pipeline/llm.py`)

For each listing surviving the rule filter, build a prompt of the form:

```
Listing:
  Title: <title>
  Price: <price>
  Beds/Baths: <beds>/<baths>
  Description: <raw_text>

User must-haves: <must_haves from config>
User deal-breakers: <deal_breakers from config>

Return strict JSON: {"verdict": "approve" | "reject" | "unsure",
                     "reasons": "<one or two sentences>"}
```

Uses Claude Haiku via the Anthropic SDK with prompt caching on the system prompt (the user's preferences rarely change within a cycle). Failures fall back to `unsure` so the listing still reaches the review queue. The `verdict` and `reasons` are stored alongside the listing.

### Storage (`storage/db.py`)

SQLite, single file at `data/fmnp.db`. Schema:

```sql
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

CREATE TABLE verdicts (
  listing_id INTEGER PRIMARY KEY REFERENCES listings(id),
  llm_verdict TEXT,             -- approve|reject|unsure
  llm_reasons TEXT,
  user_action TEXT,             -- pending|approved|rejected|snoozed
  user_action_at TIMESTAMP
);

CREATE TABLE notifications (
  id INTEGER PRIMARY KEY,
  listing_id INTEGER REFERENCES listings(id),
  channel TEXT,                 -- telegram
  sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

A thin DAO layer wraps these — no ORM. Migrations are forward-only numbered SQL files in `storage/migrations.py`.

### Notify (`notify/telegram.py`)

For each listing whose LLM verdict is `approve` or `unsure` and which has no row in `notifications`, send a Telegram message with: thumbnail photo, title, price, beds/baths, neighborhood (reverse-geocoded if available), LLM rationale, and a deep link to the listing's page in the local web UI. Records the send in `notifications` so we never double-ping.

### Web UI (`web/app.py`)

FastAPI app served on `127.0.0.1:8765`. Routes:

- `GET /` — Review queue: cards for `user_action='pending'`, newest first. Each card has Approve / Reject / Snooze buttons.
- `GET /listing/{id}` — Detail view with all photos, full description, LLM rationale.
- `POST /listing/{id}/action` — Updates `user_action` to `approved`, `rejected`, or `snoozed`. `rejected` persists so the listing won't re-surface even if the source still lists it. `snoozed` hides the listing from the queue for 7 days, then returns it to `pending`. `approved` is a user-visible bookmark for listings the user wants to act on next.
- `GET /healthz` — For local liveness checks.

No auth — bound to localhost only. Templated with Jinja, styled with a single small CSS file. The point is utility, not polish.

### Scheduler (`scheduler.py`)

Uses APScheduler's `BlockingScheduler`. On startup:

1. Load and validate config.
2. Resolve neighborhood polygons (cached).
3. Initialize DB (run pending migrations).
4. Start the FastAPI app in a background thread.
5. Schedule `pipeline.cycle.run` every `schedule_minutes`.
6. Run one cycle immediately on startup so the user sees output without waiting.

`python -m find_my_next_place --config config.json` is the entry point. `--once` runs a single cycle and exits (for testing / cron use).

## Configuration

Validated with Pydantic on startup. Any unknown keys cause a hard error so typos don't silently disable behavior.

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

`env:VARNAME` is resolved from the environment at startup; literal strings are used as-is. This keeps secrets out of the repo while still letting the config file be the single source of truth.

`neighborhoods` and `radius_miles_from` are mutually exclusive; supplying both is a startup error. At least one of the two must be set.

## Data Flow Per Cycle

1. Scheduler fires `cycle.run()`.
2. Each enabled scraper is invoked in a thread pool with a per-source timeout (default 90s). Exceptions are caught, logged, and counted; they do not abort the cycle.
3. Each raw listing is upserted into `listings` (insert-or-ignore on `(source, source_id)`).
4. The rule filter runs on listings that are new this cycle (i.e., insert succeeded), producing a survivor set.
5. Each survivor is sent to the LLM; the verdict is written to `verdicts` with `user_action='pending'`.
6. For each row where `llm_verdict in ('approve', 'unsure')` and `notifications` has no row yet, send a Telegram message and record the send.
7. Log a one-line cycle summary: `cycle: scraped=N filtered=M llm_approved=K llm_unsure=J notified=I errors=...`.

## Error Handling

| Failure mode | Behavior |
| --- | --- |
| One scraper raises | Logged with source name and traceback; cycle proceeds with the rest. |
| All scrapers raise | Cycle completes with zero listings; alert via Telegram if N consecutive cycles see zero listings (default N=4). |
| Nominatim unreachable on startup | Use cached polygons if present; hard-fail only if no cache and neighborhoods are configured. |
| LLM call fails (timeout, 5xx, rate limit) | Retry with backoff (3 attempts); on final failure store `llm_verdict='unsure'` with reason `"llm_error"` so the listing still reaches the user. |
| Telegram send fails | Log; retry next cycle. The `notifications` table is the source of truth for "already sent". |
| Camoufox detects bot block on Zillow | Exponential backoff per source (capped at 4 hours), rotate Camoufox fingerprint, log the block. |
| Config invalid | Pydantic validation error printed; process exits non-zero. |

## Testing Strategy

- **Per-scraper unit tests** with saved HTML/RSS fixtures in `tests/fixtures/<source>/`. Each test loads a fixture, runs the parser, and asserts the resulting `Listing` fields. Fixtures are regenerated manually when a site's markup changes.
- **`pipeline/rules.py`** has property-style unit tests covering all rule combinations on synthetic `Listing` objects.
- **`pipeline/llm.py`** has tests against a mocked Anthropic client that returns canned responses, including malformed JSON and timeouts.
- **`pipeline/geo.py`** has tests with hand-built Shapely polygons; no Nominatim calls in tests.
- **End-to-end test**: a single `test_cycle.py` runs `cycle.run()` against fixture-backed scrapers, a temp SQLite DB, a mocked LLM, and a mocked Telegram client. Asserts that the right rows appear in `listings`, `verdicts`, and `notifications`.
- **No live network in tests.** Hitting Craigslist or Zillow during CI is explicitly prohibited.

## Open Questions Deferred to Implementation

These don't change the architecture; they're decisions for the plan/implementation step.

1. Exact Camoufox bootstrap (installed binary vs. `playwright install firefox`-style first-run).
2. Whether the review-queue UI gets a single-page-app feel (htmx) or stays full-page reloads. Default: full-page reloads — simpler and the queue is short.
3. Whether to persist Camoufox session state between runs (cookies, fingerprint) or start fresh each cycle.
4. Exact prompt wording for the LLM filter — will be iterated on real listings.

## Risks

- **Zillow anti-bot escalation** is an arms race. If Camoufox stops working, the design degrades gracefully — Zillow becomes a disabled source until fixed, and Craigslist keeps running. The pluggable scraper model means a Zillow alternative (e.g., a property-management aggregator) is a swap, not a rewrite.
- **LLM cost** could spike if a source dumps hundreds of listings per cycle. The rule filter is the cost guard; if a misconfiguration lets too many through, the daily-cost log line will surface it.
- **Geocoding gaps**: not all sources include coordinates. The `coords_missing` pathway means these reach the LLM and human, which is correct but slightly more expensive. Acceptable for MVP.

## Out of Scope (Restated for Clarity)

These are intentionally not in the design. Adding them is a future spec, not an in-flight change:

- Multiple users, accounts, or hosted deployment
- Auto-applying, auto-contacting, calendar integration, or scheduling viewings
- Email or Slack notifications (Telegram only for now)
- Ranking or scoring beyond the LLM's binary `approve/unsure/reject`
- Historical price analytics or market trend dashboards
- iOS / Android / desktop client beyond the localhost web UI
