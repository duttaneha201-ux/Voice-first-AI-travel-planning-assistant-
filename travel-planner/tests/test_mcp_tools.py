"""
Tests for MCP tools: poi_search, itinerary_builder, travel_calculator.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.mcp.tools.poi_search import poi_search
from src.mcp.tools.itinerary_builder import itinerary_builder
from src.mcp.tools.travel_calculator import travel_calculate, travel_calculator


def test_poi_search_uses_client() -> None:
    """poi_search returns results from OverpassClient."""
    mock_client = MagicMock()
    mock_client.search_pois.return_value = [
        {"name": "X", "lat": 24.0, "lon": 73.0, "type": "restaurant", "amenity": "restaurant"},
    ]
    out = poi_search("Udaipur", ["food"], {"max_results": 5}, client=mock_client)
    assert len(out) == 1
    assert out[0]["name"] == "X"
    mock_client.search_pois.assert_called_once()


def test_itinerary_builder() -> None:
    """itinerary_builder returns days with activities."""
    pois = [
        {"name": "A", "type": "heritage", "lat": 24.57, "lon": 73.68, "duration_hours": 2, "best_time": "morning", "cost_inr": 100},
        {"name": "B", "type": "food", "lat": 24.576, "lon": 73.682, "duration_hours": 1, "best_time": "lunch", "cost_inr": 500},
    ]
    out = itinerary_builder(pois, duration_days=1, pace="moderate", daily_hours=8)
    assert "days" in out
    assert len(out["days"]) == 1
    assert "activities" in out["days"][0]


def test_travel_calculate() -> None:
    """travel_calculate returns distance and times."""
    out = travel_calculate(24.0, 73.0, 24.1, 73.1, "auto")
    assert "distance_km" in out
    assert "walk_time_minutes" in out
    assert "auto_time_minutes" in out
    assert "recommended_mode" in out


def test_travel_calculator() -> None:
    """travel_calculator accepts POI dicts."""
    a = {"lat": 24.576, "lon": 73.683}
    b = {"lat": 24.578, "lon": 73.686}
    out = travel_calculator(a, b, "auto")
    assert "distance_km" in out
    assert "auto_time_minutes" in out
