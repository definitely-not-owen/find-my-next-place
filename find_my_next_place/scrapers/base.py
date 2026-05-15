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
