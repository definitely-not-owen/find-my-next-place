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
