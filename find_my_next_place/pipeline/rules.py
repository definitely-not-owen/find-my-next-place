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
