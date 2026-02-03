"""
MCP Tool: POI search. Uses OverpassClient to fetch POIs, filters by interests and constraints.
"""

from __future__ import annotations

from typing import Any

from src.infrastructure.data.sources.overpass_client import OverpassClient

# Interest -> Overpass poi_type
INTEREST_TO_TYPE: dict[str, str] = {
    "food": "restaurant",
    "dining": "restaurant",
    "restaurant": "restaurant",
    "heritage": "museum",
    "history": "museum",
    "museum": "museum",
    "monument": "museum",
    "nature": "park",
    "park": "park",
    "lake": "park",
    "culture": "temple",
    "temple": "temple",
    "religious": "temple",
    "shopping": "market",
    "market": "market",
}


def _pick_poi_type(interests: list[str]) -> str:
    """Choose single Overpass poi_type from interests. Prefer first mapped."""
    for i in (interests or []):
        t = (i or "").strip().lower()
        if t in INTEREST_TO_TYPE:
            return INTEREST_TO_TYPE[t]
    return "all"


def _filter_by_interests(pois: list[dict[str, Any]], interests: list[str]) -> list[dict[str, Any]]:
    """Keep POIs whose type/amenity matches any interest."""
    if not interests:
        return pois
    want = {INTEREST_TO_TYPE.get((i or "").strip().lower()) for i in interests}
    want.discard(None)
    if not want:
        return pois
    out = []
    for p in pois:
        typ = (p.get("type") or "").lower()
        amenity = (p.get("amenity") or "").lower()
        for w in want:
            if w in typ or w in amenity:
                out.append(p)
                break
    return out if out else pois


def poi_search(
    city: str,
    interests: list[str],
    constraints: dict[str, Any] | None = None,
    *,
    client: OverpassClient | None = None,
) -> list[dict[str, Any]]:
    """
    Search POIs for a city by interests and constraints.

    Uses OverpassClient to fetch POIs, filters by interests (food→restaurant,
    heritage→museum/monument, etc.) and applies constraints (max_results,
    indoor_only when available).
    """
    constraints = constraints or {}
    max_results = int(constraints.get("max_results") or 50)
    radius_km = float(constraints.get("radius_km") or 5.0)
    indoor_only = bool(constraints.get("indoor_only"))

    if client is None:
        client = OverpassClient()

    poi_type = _pick_poi_type(interests)
    raw = client.search_pois(city=city, poi_type=poi_type, radius_km=radius_km)
    filtered = _filter_by_interests(raw, interests)

    result: list[dict[str, Any]] = []
    for p in filtered:
        if indoor_only and not p.get("indoor", False):
            continue
        result.append(p)
        if len(result) >= max_results:
            break
    return result

