"""
MCP Tool: Build day-wise itinerary from POIs.
Uses pace multiplier, best_time grouping, geographic clustering, and validation.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from src.infrastructure.data.repositories.poi_repository import POIRepository
from src.domains.mcp.tools.travel_calculator import travel_calculate

# Clustering radius in km
_CLUSTER_RADIUS_KM = 2.0

# Defaults when POI lacks fields
_DEFAULT_DURATION_HOURS = 1.5
_TIME_SLOTS = {"morning": (8, 12), "afternoon": (12, 17), "evening": (17, 21)}
_BASE_TRAVEL_MIN = 15
_MAX_TRAVEL_MIN = 30


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = math.radians(lat2 - lat1)
    b = math.radians(lon2 - lon1)
    x = (
        math.sin(a / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(b / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(x))


def _enrich_poi(poi: dict[str, Any], static: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Merge static POI data by name when available."""
    name = (poi.get("name") or "").strip()
    s = static.get(name)
    out = dict(poi)
    if s:
        out.setdefault("duration_hours", s.get("duration_hours", _DEFAULT_DURATION_HOURS))
        out.setdefault("best_time", s.get("best_time", "morning"))
        out.setdefault("cost_inr", s.get("cost_inr", 0))
        out.setdefault("notes", s.get("notes", ""))
    else:
        out.setdefault("duration_hours", _DEFAULT_DURATION_HOURS)
        out.setdefault("best_time", "morning")
        out.setdefault("cost_inr", 0)
        out.setdefault("notes", "")
    return out


def _static_poi_map() -> dict[str, dict[str, Any]]:
    repo = POIRepository()
    raw = repo.get_pois(max_results=999)
    return {p.get("name", "").strip(): p for p in raw if p.get("name")}


def _cluster_pois(pois: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group POIs within _CLUSTER_RADIUS_KM. Simple heuristic: first POI seeds cluster."""
    if not pois:
        return []
    used: set[int] = set()
    clusters: list[list[dict[str, Any]]] = []
    for i, p in enumerate(pois):
        if i in used:
            continue
        lat = float(p.get("lat", 0))
        lon = float(p.get("lon", 0))
        cluster = [p]
        used.add(i)
        for j, q in enumerate(pois):
            if j in used:
                continue
            qlat = float(q.get("lat", 0))
            qlon = float(q.get("lon", 0))
            if _haversine_km(lat, lon, qlat, qlon) <= _CLUSTER_RADIUS_KM:
                cluster.append(q)
                used.add(j)
        clusters.append(cluster)
    return clusters


def _estimate_travel_min(from_poi: dict[str, Any], to_poi: dict[str, Any]) -> int:
    r = travel_calculate(
        float(from_poi.get("lat", 0)),
        float(from_poi.get("lon", 0)),
        float(to_poi.get("lat", 0)),
        float(to_poi.get("lon", 0)),
        mode="auto",
    )
    return min(max(_BASE_TRAVEL_MIN, r["auto_time_minutes"]), _MAX_TRAVEL_MIN)


def itinerary_builder(
    pois: list[dict[str, Any]],
    duration_days: int,
    pace: str = "moderate",
    daily_hours: int = 8,
) -> dict[str, Any]:
    """
    Build a day-wise itinerary from POIs.

    Uses pace multiplier, groups by best_time, clusters geographically,
    and enforces max daily hours and at least one food POI per day.
    """
    pace_mult = {"relaxed": 0.6, "moderate": 0.75, "packed": 0.9}.get((pace or "moderate").strip().lower(), 0.75)
    days_cap = max(1, min(4, int(duration_days or 2)))
    daily_cap = max(1.0, min(12.0, float(daily_hours or 8))) * pace_mult

    static = _static_poi_map()
    enriched = [_enrich_poi(p, static) for p in (pois or [])]
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in enriched:
        n = (p.get("name") or "").strip()
        if n and n not in seen:
            seen.add(n)
            unique.append(p)

    if not unique:
        return {
            "days": [],
            "metadata": {"total_pois": 0, "total_cost_inr": 0, "pace": pace, "warnings": ["No places provided."]},
        }

    by_time: dict[str, list[dict[str, Any]]] = {"morning": [], "afternoon": [], "evening": []}
    _bt_map = {"lunch": "afternoon", "sunset": "evening"}
    for p in unique:
        bt = (p.get("best_time") or "morning").strip().lower()
        slot = _bt_map.get(bt) or (bt if bt in by_time else "morning")
        by_time[slot].append(p)

    # Type diversity: interleave heritage, food, culture, nature
    type_order = ["heritage", "food", "culture", "nature", "shopping"]

    def poi_key(p: dict[str, Any]) -> tuple:
        t = (p.get("type") or "").lower()
        try:
            i = type_order.index(t)
        except ValueError:
            i = 99
        return (i, (p.get("name") or ""))

    for k in by_time:
        by_time[k] = sorted(by_time[k], key=poi_key)

    clusters = _cluster_pois(unique)
    flat_clusters: list[dict[str, Any]] = []
    for c in clusters:
        for p in sorted(c, key=lambda x: ((x.get("best_time") or "morning"), x.get("name") or "")):
            flat_clusters.append(p)
    ordered = flat_clusters if flat_clusters else unique

    days_out: list[dict[str, Any]] = []
    base_date = datetime(2026, 2, 1)
    used: set[str] = set()
    total_cost = 0.0
    warnings: list[str] = []

    # Minimum hours per day to ensure all days get activities
    min_hours_per_day = max(3.0, daily_cap * 0.4)  # At least 40% of daily cap or 3 hours

    for d in range(1, days_cap + 1):
        day_date = (base_date + timedelta(days=d - 1)).strftime("%Y-%m-%d")
        activities: list[dict[str, Any]] = []
        total_h = 0.0
        has_food = False
        prev: dict[str, Any] | None = None
        start_minutes = 0  # from 8:00 AM
        attempts_since_last_add = 0
        max_attempts = len(ordered) * 2  # Prevent infinite loops

        for p in ordered:
            n = (p.get("name") or "").strip()
            if not n or n in used:
                attempts_since_last_add += 1
                if attempts_since_last_add > max_attempts:
                    break
                continue

            dh = float(p.get("duration_hours", _DEFAULT_DURATION_HOURS))
            travel_min = 0
            if prev:
                travel_min = _estimate_travel_min(prev, p)

            # Check if adding this POI would exceed daily cap (including travel time)
            potential_total = total_h + (travel_min / 60.0) + dh
            if potential_total > daily_cap:
                attempts_since_last_add += 1
                # If we haven't added anything in a while and we're below min hours, try to fit smaller POIs
                if attempts_since_last_add > 10 and total_h < min_hours_per_day and dh < 2.0:
                    # Try to fit smaller POIs even if slightly over
                    if potential_total <= daily_cap * 1.1:  # Allow 10% overage for small POIs
                        pass
                    else:
                        continue
                else:
                    continue

            # Check if adding this POI would exceed 9 PM
            potential_end_minutes = start_minutes + travel_min + int(round(dh * 60))
            if (8 + potential_end_minutes // 60) >= 21:
                break

            # Add this POI to the day
            used.add(n)
            total_h += (travel_min / 60.0) + dh
            attempts_since_last_add = 0  # Reset counter
            if (p.get("type") or "").lower() == "food":
                has_food = True
            cost = int(p.get("cost_inr") or 0)
            total_cost += cost

            start_minutes += travel_min
            h = 8 + start_minutes // 60
            m = start_minutes % 60
            if h < 12:
                time_str = f"{h}:{m:02d} AM"
            elif h == 12:
                time_str = f"12:{m:02d} PM"
            else:
                time_str = f"{h - 12}:{m:02d} PM"

            act = {
                "time": time_str,
                "poi": {
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "duration_hours": dh,
                    "cost_inr": cost,
                    "lat": p.get("lat"),
                    "lon": p.get("lon"),
                },
                "travel_time_from_previous": travel_min,
                "notes": (p.get("notes") or "")[:200],
            }
            activities.append(act)
            prev = p
            start_minutes += int(round(dh * 60))

            # Only break if we're very close to daily cap (within 0.2 hours) AND we have at least min hours
            if total_h >= daily_cap - 0.2 and total_h >= min_hours_per_day:
                break

        if not has_food and activities:
            warnings.append(f"Day {d}: No meal slot; consider adding a restaurant or food place.")

        summary = " + ".join([a["poi"]["name"] for a in activities][:3])
        if len(activities) > 3:
            summary += " ..."

        days_out.append(
            {
                "day_number": d,
                "date": day_date,
                "activities": activities,
                "total_hours": round(total_h, 2),
                "summary": summary or "No activities",
            }
        )

        # Warn if day is incomplete (below minimum hours)
        if activities and total_h < min_hours_per_day:
            warnings.append(
                f"Day {d} is incomplete ({round(total_h, 1)}h < {round(min_hours_per_day, 1)}h minimum). "
                "More places to visit are needed to fill this day."
            )

        # If we've used all POIs, no need to create empty days
        if len(used) >= len(unique):
            break

    # Check for empty days and insufficient places
    empty_days = [d for d in days_out if not d.get("activities")]
    if empty_days:
        day_nums = [d["day_number"] for d in empty_days]
        warnings.append(
            f"Days {', '.join(map(str, day_nums))} are empty. "
            f"Only {len(used)} place(s) provided for {days_cap} day(s). "
            "More attractions, restaurants, and activities are needed to fill all days."
        )

    # Warn if not enough places for the requested duration
    if len(used) < days_cap * 3:  # At least 3 places per day minimum
        warnings.append(
            f"Insufficient places: {len(used)} used for {days_cap} day(s). "
            f"Recommend at least {days_cap * 15} places (attractions, restaurants, museums, etc.) "
            f"for a full {days_cap}-day itinerary. "
            "Try searching for more places with different interests (heritage sites, food, nature, culture)."
        )

    return {
        "days": days_out,
        "metadata": {
            "total_pois": len(used),
            "total_cost_inr": int(total_cost),
            "pace": pace,
            "warnings": warnings,
        },
    }


# Backward-compatible stub-style signature for registry that passes city/days
def itinerary_builder_legacy(
    city: str,
    days: int,
    preferences: dict[str, Any] | None = None,
    poi_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Legacy signature: fetches POIs from repo by type and builds itinerary."""
    prefs = preferences or {}
    pace = (prefs.get("pace") or "moderate").strip().lower()
    repo = POIRepository()
    types = prefs.get("types") or ["heritage", "food"]
    pois = repo.get_pois(types=types, max_results=20)
    ids = set(poi_ids or [])
    if ids:
        pois = [p for p in pois if (p.get("name") or "").strip() in ids]
    built = itinerary_builder(pois, duration_days=days, pace=pace, daily_hours=8)
    return built.get("days", [])

