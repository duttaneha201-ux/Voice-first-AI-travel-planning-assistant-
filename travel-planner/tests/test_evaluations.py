"""
Tests for evaluations: feasibility, edit correctness, grounding.
"""

from __future__ import annotations

import pytest

from src.evaluations.feasibility_eval import evaluate_feasibility
from src.evaluations.edit_correctness_eval import evaluate_edit_correctness
from src.evaluations.grounding_eval import evaluate_grounding


def test_feasibility_eval() -> None:
    """Feasibility eval passes when within hours limit."""
    it = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "City Palace", "duration_hours": 3},
                    "travel_time_from_previous": 0,
                },
                {
                    "time": "11:30 AM",
                    "poi": {"name": "Restaurant", "duration_hours": 1.5, "type": "food"},
                    "travel_time_from_previous": 15,
                },
            ],
        },
        {
            "day_number": 2,
            "activities": [
                {
                    "time": "9:00 AM",
                    "poi": {"name": "Museum", "duration_hours": 2},
                    "travel_time_from_previous": 0,
                },
            ],
        },
    ]
    r = evaluate_feasibility(it, daily_hours=8, pace="moderate")
    assert "passed" in r
    assert "score" in r
    assert "total_hours" in r
    assert "issues" in r
    assert r["total_hours"] > 0


def test_feasibility_eval_exceeds_limit() -> None:
    """Feasibility eval fails when exceeds daily limit."""
    it = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "POI 1", "duration_hours": 10},  # Exceeds 8h * 0.75 = 6h
                    "travel_time_from_previous": 0,
                },
            ],
        },
    ]
    r = evaluate_feasibility(it, daily_hours=8, pace="moderate")
    assert r["passed"] is False
    assert len(r["issues"]) > 0


def test_edit_correctness_eval() -> None:
    """Edit correctness checks structure and POI references."""
    orig = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "City Palace", "type": "heritage"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
    ]
    edited = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "City Palace", "type": "heritage"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
    ]
    known_pois = [{"name": "City Palace", "type": "heritage"}]
    r = evaluate_edit_correctness(orig, edited, known_pois=known_pois)
    assert r["passed"] is True
    assert "score" in r
    assert "issues" in r


def test_edit_correctness_invalid_poi() -> None:
    """Edit correctness fails when POI doesn't exist."""
    orig = [{"day_number": 1, "activities": []}]
    edited = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "NonExistent Place"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
    ]
    known_pois = [{"name": "City Palace"}]
    r = evaluate_edit_correctness(orig, edited, known_pois=known_pois)
    assert r["passed"] is False
    assert len(r["issues"]) > 0


def test_edit_correctness_intended_sections_only() -> None:
    """Edit correctness passes when only the intended day (Day 2) is modified."""
    orig = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "City Palace", "type": "heritage"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
        {
            "day_number": 2,
            "activities": [
                {
                    "time": "9:00 AM",
                    "poi": {"name": "Lake Pichola", "type": "nature"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
    ]
    edited = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "City Palace", "type": "heritage"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
        {
            "day_number": 2,
            "activities": [
                {
                    "time": "9:00 AM",
                    "poi": {"name": "Lake Pichola", "type": "nature"},
                    "travel_time_from_previous": 0,
                },
                {
                    "time": "2:00 PM",
                    "poi": {"name": "Monsoon Palace", "type": "heritage"},
                    "travel_time_from_previous": 20,
                },
            ],
        },
    ]
    known_pois = [
        {"name": "City Palace"},
        {"name": "Lake Pichola"},
        {"name": "Monsoon Palace"},
    ]
    r = evaluate_edit_correctness(
        orig, edited, known_pois=known_pois, user_edit_message="Add Monsoon Palace to Day 2"
    )
    assert r["passed"] is True
    assert "Unintended change elsewhere" not in str(r.get("issues", []))


def test_edit_correctness_unintended_change_elsewhere() -> None:
    """Edit correctness fails when a day not mentioned in the edit was modified."""
    orig = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "City Palace", "type": "heritage"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
        {
            "day_number": 2,
            "activities": [
                {
                    "time": "9:00 AM",
                    "poi": {"name": "Lake Pichola", "type": "nature"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
    ]
    # User asked to change Day 2 only, but Day 1 was also changed (different POI)
    edited = [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "8:00 AM",
                    "poi": {"name": "Jagdish Temple", "type": "heritage"},
                    "travel_time_from_previous": 0,
                },
            ],
        },
        {
            "day_number": 2,
            "activities": [
                {
                    "time": "9:00 AM",
                    "poi": {"name": "Lake Pichola", "type": "nature"},
                    "travel_time_from_previous": 0,
                },
                {
                    "time": "2:00 PM",
                    "poi": {"name": "Monsoon Palace", "type": "heritage"},
                    "travel_time_from_previous": 20,
                },
            ],
        },
    ]
    known_pois = [
        {"name": "City Palace"},
        {"name": "Jagdish Temple"},
        {"name": "Lake Pichola"},
        {"name": "Monsoon Palace"},
    ]
    r = evaluate_edit_correctness(
        orig, edited, known_pois=known_pois, user_edit_message="Add Monsoon Palace to day 2"
    )
    assert r["passed"] is False
    issues_str = str(r.get("issues", []))
    assert "Unintended change elsewhere" in issues_str
    assert "Day 1" in issues_str


def test_grounding_eval() -> None:
    """Grounding checks POI names and claims."""
    response = "Visit City Palace and Lake Pichola. Udaipur is known for its palaces."
    known_pois = [
        {"name": "City Palace", "type": "heritage"},
        {"name": "Lake Pichola", "type": "nature"},
    ]
    r = evaluate_grounding(response, known_pois=known_pois)
    assert "passed" in r
    assert "score" in r
    assert "issues" in r
    assert "details" in r


def test_grounding_unverified_poi() -> None:
    """Grounding flags when 2+ unverified POI names are mentioned (lenient for one alternate spelling)."""
    response = "Visit the Made Up Palace, Fake Garden, and City Palace."
    known_pois = [{"name": "City Palace"}]
    r = evaluate_grounding(response, known_pois=known_pois)
    # Should flag "Made Up Palace" and "Fake Garden" as unverified (2+ triggers issue)
    assert len(r["issues"]) > 0 or r["score"] < 1.0
