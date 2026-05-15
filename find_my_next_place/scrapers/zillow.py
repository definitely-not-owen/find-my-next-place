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
