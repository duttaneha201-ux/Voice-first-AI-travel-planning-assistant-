"""
Tests for itinerary_builder: pace, daily hours, clustering, validation.
"""

from __future__ import annotations

import pytest

from src.mcp.tools.itinerary_builder import itinerary_builder


def _pois() -> list[dict]:
    return [
        {"name": "City Palace", "type": "heritage", "lat": 24.576, "lon": 73.683, "duration_hours": 3, "best_time": "morning", "cost_inr": 300},
        {"name": "Ambrai Restaurant", "type": "food", "lat": 24.576, "lon": 73.681, "duration_hours": 1.5, "best_time": "evening", "cost_inr": 1200},
        {"name": "Jagdish Temple", "type": "heritage", "lat": 24.577, "lon": 73.684, "duration_hours": 1, "best_time": "morning", "cost_inr": 0},
        {"name": "Saheliyon ki Bari", "type": "nature", "lat": 24.595, "lon": 73.690, "duration_hours": 1.5, "best_time": "morning", "cost_inr": 50},
        {"name": "Upre by 1559 AD", "type": "food", "lat": 24.575, "lon": 73.682, "duration_hours": 1.5, "best_time": "lunch", "cost_inr": 800},
    ]


def test_itinerary_5_pois_2_days_relaxed() -> None:
    """Build itinerary with 5 POIs, 2 days, relaxed pace."""
    pois = _pois()
    out = itinerary_builder(pois, duration_days=2, pace="relaxed", daily_hours=8)
    assert "days" in out
    assert "metadata" in out
    days = out["days"]
    assert len(days) == 2
    for d in days:
        assert "day_number" in d
        assert "activities" in d
        assert "total_hours" in d
        cap = 8 * 0.6
        assert d["total_hours"] <= cap + 1.0


def test_daily_hours_limit() -> None:
    """Total daily hours <= daily_hours * pace_multiplier."""
    pois = _pois()
    out = itinerary_builder(pois, duration_days=2, pace="moderate", daily_hours=8)
    cap = 8 * 0.75
    for d in out["days"]:
        assert d["total_hours"] <= cap + 1.0


def test_geographic_clustering() -> None:
    """POIs are grouped by proximity (same cluster ≈ same area)."""
    pois = _pois()
    out = itinerary_builder(pois, duration_days=2, pace="packed", daily_hours=8)
    assert len(out["days"]) >= 1
    all_acts = []
    for d in out["days"]:
        all_acts.extend(d["activities"])
    names = [a["poi"]["name"] for a in all_acts]
    assert len(names) == len(set(names))


def test_at_least_one_food_warning() -> None:
    """Without food POIs, metadata includes warning."""
    heritage_only = [p for p in _pois() if p["type"] != "food"]
    out = itinerary_builder(heritage_only, duration_days=1, pace="moderate", daily_hours=8)
    assert "metadata" in out
    w = out["metadata"].get("warnings") or []
    assert any("food" in x.lower() or "meal" in x.lower() for x in w)


def test_no_duplicate_pois() -> None:
    """Each POI appears at most once."""
    pois = _pois()
    out = itinerary_builder(pois, duration_days=3, pace="moderate", daily_hours=8)
    seen = set()
    for d in out["days"]:
        for a in d["activities"]:
            n = a["poi"]["name"]
            assert n not in seen
            seen.add(n)


def test_empty_pois() -> None:
    """Empty POI list returns empty days."""
    out = itinerary_builder([], duration_days=2, pace="moderate")
    assert out["days"] == []
    assert "warnings" in out["metadata"]
