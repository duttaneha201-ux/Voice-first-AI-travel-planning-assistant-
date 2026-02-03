"""
MCP Tool: Calculate travel time and distance between two POIs.
Uses haversine distance and speed heuristics (walk/auto).
"""

from __future__ import annotations

import math
from typing import Any

# Haversine Earth radius in km
_EARTH_RADIUS_KM = 6371.0

# Speeds: km/h
_WALK_KMH = 4.0
_AUTO_KMH = 20.0

# Base time (waiting/boarding) in minutes
_BASE_MINUTES = 5


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km."""
    a = math.radians(lat2 - lat1)
    b = math.radians(lon2 - lon1)
    x = math.sin(a / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(b / 2) ** 2
    d = 2 * math.asin(math.sqrt(x))
    return _EARTH_RADIUS_KM * d


def travel_calculate(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    mode: str = "auto",
) -> dict[str, Any]:
    """
    Estimate travel time and distance between two points.

    Uses haversine distance. Speed heuristics: walking 4 km/h, auto 20 km/h.
    Adds 5 min base time. Returns both walk and auto when mode="both".
    """
    dist = _haversine_km(from_lat, from_lon, to_lat, to_lon)
    walk_min = _BASE_MINUTES + int(round(60 * dist / _WALK_KMH))
    auto_min = _BASE_MINUTES + int(round(60 * dist / _AUTO_KMH))
    rec = "walk" if dist <= 1.5 else "auto"
    notes = "Walking not recommended for >1.5 km in Udaipur heat." if dist > 1.5 else ""

    out: dict[str, Any] = {
        "distance_km": round(dist, 2),
        "walk_time_minutes": walk_min,
        "auto_time_minutes": auto_min,
        "recommended_mode": rec,
        "notes": notes,
    }
    return out


def travel_calculator(
    from_poi: dict[str, Any],
    to_poi: dict[str, Any],
    mode: str = "auto",
) -> dict[str, Any]:
    """
    Calculate travel time/distance between two POI dicts.

    Expects from_poi / to_poi with lat, lon. Delegates to travel_calculate.
    """
    fl = float(from_poi.get("lat", 0))
    fn = float(from_poi.get("lon", 0))
    tl = float(to_poi.get("lat", 0))
    tn = float(to_poi.get("lon", 0))
    return travel_calculate(fl, fn, tl, tn, mode=mode)

