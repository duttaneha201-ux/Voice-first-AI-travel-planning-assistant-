"""
Overpass API client for fetching POIs. Supports caching and rate limiting.

Moved from `src.data.sources.overpass_client` to keep IO/integration code in the
infrastructure layer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import requests

from src.utils.config import project_root, overpass_max_requests
from src.utils.logger import get_logger

logger = get_logger()

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

# City name -> (lat, lon) for known cities. Extend as needed.
CITY_COORDS: dict[str, tuple[float, float]] = {
    "udaipur": (24.5854, 73.7125),
    "Udaipur": (24.5854, 73.7125),
}


def _normalize_city(city: str) -> str:
    return city.strip() or "Udaipur"


def _coords_for_city(city: str) -> tuple[float, float]:
    n = _normalize_city(city)
    if n in CITY_COORDS:
        return CITY_COORDS[n]
    if n.lower() == "udaipur":
        return CITY_COORDS["udaipur"]
    return CITY_COORDS["Udaipur"]


def _poi_type_to_overpass(poi_type: str) -> list[tuple[str, str]]:
    """
    Map high-level poi_type to Overpass tag filters.
    Returns list of (key, value) for use in Overpass QL.
    """
    t = (poi_type or "").strip().lower()
    if t in ("restaurant", "food", "dining"):
        return [("amenity", "restaurant"), ("amenity", "cafe"), ("amenity", "fast_food")]
    if t in ("museum", "heritage", "monument", "history"):
        return [
            ("tourism", "museum"),
            ("historic", "monument"),
            ("historic", "castle"),
            ("tourism", "attraction"),
        ]
    if t in ("park", "nature", "lake"):
        return [("leisure", "park"), ("natural", "water")]
    if t in ("temple", "religious", "culture"):
        return [("amenity", "place_of_worship")]
    if t in ("market", "shopping"):
        return [("shop", "mall"), ("amenity", "marketplace")]
    if t in ("all", "*", "any"):
        return [
            ("amenity", "restaurant"),
            ("amenity", "cafe"),
            ("tourism", "museum"),
            ("tourism", "attraction"),
            ("historic", "monument"),
            ("leisure", "park"),
        ]
    # Default: general amenities + tourism
    return [("amenity", "restaurant"), ("tourism", "attraction"), ("tourism", "museum")]


def _cache_dir() -> Path:
    d = project_root() / "data" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(city: str, poi_type: str, radius_km: float) -> str:
    raw = f"{_normalize_city(city)}|{poi_type}|{radius_km}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"overpass_{h}.json"


def _parse_element(el: dict[str, Any]) -> dict[str, Any] | None:
    lat = el.get("lat")
    lon = el.get("lon")
    if lat is None or lon is None:
        # Way/relation: use center if present
        c = el.get("center", {})
        lat, lon = c.get("lat"), c.get("lon")
    if lat is None or lon is None:
        return None

    tags = el.get("tags") or {}
    name = tags.get("name") or tags.get("name:en") or "Unnamed"
    amenity = tags.get("amenity") or ""
    tourism = tags.get("tourism") or ""
    historic = tags.get("historic") or ""
    typ = amenity or tourism or historic or "poi"

    return {
        "name": str(name),
        "lat": float(lat),
        "lon": float(lon),
        "type": typ,
        "amenity": amenity or tourism or historic or "unknown",
    }


def _parse_overpass_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for el in data.get("elements", []):
        p = _parse_element(el)
        if p:
            out.append(p)
    return out


class OverpassClient:
    """
    Overpass API wrapper with disk caching and per-session rate limiting.

    Rate limit: max N Overpass requests per session (default 2).
    Cache: stored under data/cache/; reused across sessions.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self._max_requests = max_requests if max_requests is not None else overpass_max_requests()
        self._cache_dir = cache_dir or _cache_dir()
        self._request_count = 0

    def _read_cache(self, key: str) -> list[dict[str, Any]] | None:
        path = self._cache_dir / key
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else None
        except Exception as e:
            logger.warning("Overpass cache read failed for %s: %s", key, e)
            return None

    def _write_cache(self, key: str, pois: list[dict[str, Any]]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / key
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(pois, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Overpass cache write failed for %s: %s", key, e)

    def _build_query(self, lat: float, lon: float, radius_km: float, poi_type: str) -> str:
        radius_m = int(radius_km * 1000)
        tag_filters = _poi_type_to_overpass(poi_type)
        # Build union of tag conditions
        parts = []
        for k, v in tag_filters:
            parts.append(f'node["{k}"="{v}"](around:{radius_m},{lat},{lon});')
        union = " ".join(parts)
        return f"""[out:json][timeout:25];
(
  {union}
);
out body 200;
"""

    def search_pois(
        self,
        city: str,
        poi_type: str,
        radius_km: float = 5.0,
    ) -> list[dict[str, Any]]:
        """
        Search POIs for a city by type, with optional radius.

        Args:
            city: City name (e.g. "Udaipur"). Uses known coords or fallback.
            poi_type: One of restaurant, museum, heritage, nature, etc.
            radius_km: Search radius in km. Default 5.

        Returns:
            List of POI dicts with keys: name, lat, lon, type, amenity.

        Raises:
            RuntimeError: If rate limit exceeded (no cache hit).
        """
        city = _normalize_city(city)
        lat, lon = _coords_for_city(city)
        key = _cache_key(city, poi_type, radius_km)
        cached = self._read_cache(key)
        if cached is not None:
            logger.info("Overpass cache hit: %s", key)
            return cached

        if self._request_count >= self._max_requests:
            raise RuntimeError(
                f"Overpass rate limit reached ({self._max_requests} requests per session). "
                "Use cached data or try again later."
            )

        query = self._build_query(lat, lon, radius_km, poi_type)
        try:
            r = requests.post(
                OVERPASS_ENDPOINT,
                data={"data": query},
                timeout=30,
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.exception("Overpass API request failed: %s", e)
            return []
        except json.JSONDecodeError as e:
            logger.exception("Overpass API invalid JSON: %s", e)
            return []

        pois = _parse_overpass_response(data)
        self._request_count += 1
        self._write_cache(key, pois)
        logger.info("Overpass fetched %d POIs for %s/%s", len(pois), city, poi_type)
        return pois

