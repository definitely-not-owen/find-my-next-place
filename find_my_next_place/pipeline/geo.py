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
