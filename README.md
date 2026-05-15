# find-my-next-place

A small apartment-hunting pipeline that scrapes rental sites, applies a rule
filter, asks Claude whether each survivor matches my taste, and pings me on
Telegram when it finds something worth a viewing.

My friend [Gabor wrote a great post](https://gaborcsapo.substack.com/p/what-does-apartment-hunting-in-sf)
about doing this for himself in SF.


This is my version — same architecture, narrower scope, configurable for any
US city, and with a tiny localhost review queue instead of a Telegram-only flow.

The premise Gabor nailed in his writeup is that **AI is great at surfacing
candidates and useless at winning apartments**. Viewings, applications, and
landlord rapport still depend entirely on you showing up. This tool aims to do
nothing more than save you the hours of refreshing Craigslist.

## How it works

```
scrapers → rule filter → Claude Haiku filter → SQLite → Telegram + web UI
   ▲
scheduler (runs every N minutes)
   ▲
config.json (city, neighborhoods, budget, must-haves, deal-breakers)
```

Each cycle:

1. Each enabled scraper fetches listings (Craigslist RSS, Zillow via Camoufox).
   One scraper crashing doesn't stop the others.
2. Deterministic rules drop anything out of price/bed band, outside your
   neighborhoods, or already seen.
3. Survivors get evaluated by Claude Haiku against your must-haves and
   deal-breakers from config.
4. Approved + unsure listings get a Telegram ping and land in the review queue
   at `http://127.0.0.1:8765`.

Rejected listings stay rejected forever. Snoozed listings come back after seven
days. Approved listings hang around as bookmarks for the next viewing trip.

## Setup

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m camoufox fetch   # one-time, downloads the stealth Firefox binary
```

Then create your `config.json`:

```bash
cp config.example.json config.json
$EDITOR config.json
```

You need three environment variables:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export TELEGRAM_BOT_TOKEN=...   # from @BotFather
export TELEGRAM_CHAT_ID=...     # your numeric chat id; @userinfobot will tell you
```

For Telegram: talk to [@BotFather](https://t.me/BotFather) on Telegram, run
`/newbot`, get the token. Send your new bot a message, then visit
`https://api.telegram.org/bot<TOKEN>/getUpdates` to read your chat id from the
response.

## Configuration

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
  "source_urls": {
    "craigslist": {"rss_url": "https://sfbay.craigslist.org/search/apa?format=rss"},
    "zillow": {"search_url": "https://www.zillow.com/san-francisco-ca/rentals/"}
  },
  ...
}
```

A few notes:

- `neighborhoods` are resolved to polygons via OpenStreetMap at startup and
  cached to `data/geo_cache.json`. If a name doesn't resolve, startup fails
  loudly rather than silently dropping listings.
- Use `radius_miles_from: {"lat": ..., "lng": ..., "miles": ...}` instead of
  neighborhoods if you'd rather a circle. They're mutually exclusive.
- `source_urls` is where you point the scrapers at your city. The example file
  is SF; for NYC you'd swap to `https://newyork.craigslist.org/search/apa?format=rss`
  and `https://www.zillow.com/new-york-ny/rentals/`.
- `must_haves` and `deal_breakers` are free text fed to the LLM, so anything
  Claude can reasonably infer from a listing description will work — "natural
  light", "no fluorescent kitchen", "exposed brick", whatever you care about.

## Running it

```bash
# One cycle, no web UI — good for smoke-testing your config
python -m find_my_next_place --config config.json --once

# Long-running: scheduler + web UI on http://127.0.0.1:8765
python -m find_my_next_place --config config.json
```

The review queue is at `http://127.0.0.1:8765` once the long-running form is up.
Approve, snooze, or reject each card.

## Tests

```bash
. .venv/bin/activate
pytest -v
```

54 tests, ~0.5s. No live network calls — scrapers use saved HTML/RSS fixtures,
the LLM and Telegram are mocked.

## Honest limitations

- **LLM prompt caching isn't enabled.** Cost runs maybe 2-3x what it should
  under heavy use. Fix would be wiring `cache_control` headers on the system
  prompt. Not done yet.
- **Zillow fingerprint rotation on bot-block isn't implemented.** When Zillow
  catches the scraper, it backs off for an hour with the same Camoufox profile.
  Probably needs profile rotation in practice.
- **No alert if all scrapers silently return zero for a while.** The spec calls
  for a "N consecutive empty cycles → Telegram ping" but I haven't built it.
  Check the logs if Telegram goes quiet.
- **Snooze sweep runs on web-page-load**, not per cycle. If you never open the
  queue page, snoozed listings stay snoozed forever.
- **City support is configurable but you do supply the URLs.** No magic
  city-to-Craigslist subdomain lookup — you pass in the RSS feed you want.

## Acknowledgements

Architecture, pipeline shape, and most of the good ideas come from
[Gabor Csapo's writeup](https://gaborcsapo.substack.com/p/what-does-apartment-hunting-in-sf)
and [`ai-real-estate-agent`](https://github.com/gaborcsapo/ai-real-estate-agent).
Go read his post — it's better than this README.
