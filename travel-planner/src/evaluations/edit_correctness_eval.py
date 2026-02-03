"""
Edit correctness evaluation: verify edits only modify intended sections.
Voice/text edits should only change what the user asked to change; no unintended changes elsewhere.
"""

from __future__ import annotations

import re
from typing import Any


def _parse_time(time_str: str) -> int:
    """Parse time string (e.g., '8:00 AM') to minutes since midnight."""
    if not time_str:
        return 0
    time_str = time_str.strip().upper()
    try:
        parts = time_str.replace(":", " ").split()
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if "PM" in time_str and hour != 12:
            hour += 12
        elif "AM" in time_str and hour == 12:
            hour = 0
        return hour * 60 + minute
    except (ValueError, IndexError):
        return 0


def _intended_days_from_message(user_edit_message: str | None) -> set[int] | None:
    """Parse user edit message for day references (e.g. 'day 2', 'Day 1'). Returns None if no days mentioned (whole itinerary in scope)."""
    if not user_edit_message or not user_edit_message.strip():
        return None
    msg = user_edit_message.strip().lower()
    # Match "day 1", "day 2", "day 3", etc.
    matches = re.findall(r"day\s*(\d+)", msg)
    if not matches:
        return None
    return {int(m) for m in matches}


def _poi_names_for_day(day: dict[str, Any]) -> list[str]:
    """Return list of POI names (order preserved) for a day."""
    names: list[str] = []
    for act in day.get("activities") or []:
        poi = act.get("poi") or {}
        name = (poi.get("name") or "").strip()
        if name:
            names.append(name.lower())
    return names


def evaluate_edit_correctness(
    original: list[dict[str, Any]],
    edited: list[dict[str, Any]],
    known_pois: list[dict[str, Any]] | None = None,
    user_edit_message: str | None = None,
) -> dict[str, Any]:
    """
    Check that an edited itinerary only modifies intended sections (voice/edit correctness).
    
    When user_edit_message is provided:
    - Infers which days were "intended" to be edited (e.g. "add X to day 2" -> day 2).
    - Fails if days not mentioned in the edit were changed (unintended changes elsewhere).
    
    Always validates:
    - Structure (days, activities), POI references (if known_pois given), time conflicts.
    - Day count change is only flagged when user message doesn't imply a day-count change.
    
    Args:
        original: Original itinerary (list of day dicts).
        edited: Edited itinerary (list of day dicts).
        known_pois: Optional list of valid POIs to check references against.
        user_edit_message: Optional user message (voice or text) that requested the edit.
    
    Returns:
        Dict with passed (bool), score (0.0-1.0), and issues (list).
    """
    issues: list[str] = []
    o_days = len(original)
    e_days = len(edited)
    
    # Check structure
    if not isinstance(edited, list):
        return {"passed": False, "score": 0.0, "issues": ["Edited itinerary is not a list"]}
    
    if len(edited) == 0:
        issues.append("Edited itinerary has no days")
    
    # Day count: only flag as issue if user didn't ask for a different number of days
    if o_days > 0 and not issues:
        change_ratio = abs(e_days - o_days) / o_days
        msg_lower = (user_edit_message or "").strip().lower()
        asks_more_days = bool(re.search(r"\d+\s*days?|more\s*days?|add\s*(a\s*)?day|extra\s*day", msg_lower))
        asks_fewer_days = bool(re.search(r"fewer\s*days?|less\s*days?|1\s*day|single\s*day", msg_lower))
        if change_ratio > 0.5 and not (asks_more_days or asks_fewer_days):
            issues.append(f"Day count changed significantly: {o_days} → {e_days} days")
    
    # Intended sections: only modify what the user asked to change
    intended_days = _intended_days_from_message(user_edit_message)
    if intended_days is not None and len(intended_days) > 0:
        for i, orig_day in enumerate(original):
            day_num = i + 1
            if day_num in intended_days:
                continue
            orig_names = _poi_names_for_day(orig_day)
            if day_num <= len(edited):
                edited_day = edited[day_num - 1]
                edited_names = _poi_names_for_day(edited_day)
                if orig_names != edited_names:
                    issues.append(
                        f"Unintended change elsewhere: Day {day_num} was modified but the edit request did not mention it"
                    )
    
    # Build POI name set if provided
    known_poi_names: set[str] = set()
    if known_pois:
        for poi in known_pois:
            name = (poi.get("name") or "").strip()
            if name:
                known_poi_names.add(name.lower())
    
    # Validate each day
    for day_idx, day in enumerate(edited, 1):
        if not isinstance(day, dict):
            issues.append(f"Day {day_idx}: Not a dict")
            continue
        
        activities = day.get("activities", [])
        if not isinstance(activities, list):
            issues.append(f"Day {day_idx}: Activities is not a list")
            continue
        
        # Track times to detect conflicts
        activity_times: list[tuple[int, int, str]] = []  # (start, end, name)
        
        for act_idx, act in enumerate(activities):
            if not isinstance(act, dict):
                issues.append(f"Day {day_idx}, Activity {act_idx + 1}: Not a dict")
                continue
            
            # Check POI reference
            poi = act.get("poi", {})
            if not isinstance(poi, dict):
                issues.append(f"Day {day_idx}, Activity {act_idx + 1}: POI is not a dict")
                continue
            
            poi_name = (poi.get("name") or "").strip()
            if not poi_name:
                issues.append(f"Day {day_idx}, Activity {act_idx + 1}: Missing POI name")
            elif known_poi_names and poi_name.lower() not in known_poi_names:
                issues.append(f"Day {day_idx}, Activity {act_idx + 1}: POI '{poi_name}' not found in known POIs")
            
            # Check time (optional for prose-derived itineraries that have name + duration but no time field)
            time_str = act.get("time", "")
            if not time_str:
                # Only flag missing time if we're strict; for prose itineraries, name + duration is enough
                duration = float(poi.get("duration_hours", 0) or act.get("duration_hours", 0))
                if not poi_name or duration <= 0:
                    issues.append(f"Day {day_idx}, Activity {act_idx + 1}: Missing time")
            else:
                start_minutes = _parse_time(time_str)
                if start_minutes == 0:
                    issues.append(f"Day {day_idx}, Activity {act_idx + 1}: Invalid time format '{time_str}'")
                else:
                    duration = float(poi.get("duration_hours", 0) or act.get("duration_hours", 0))
                    travel_min = int(act.get("travel_time_from_previous", 0))
                    end_minutes = start_minutes + int(round(duration * 60)) + travel_min
                    activity_times.append((start_minutes, end_minutes, poi_name or f"Activity {act_idx + 1}"))
        
        # Check for time conflicts within the day; allow 15 min tolerance for rounding
        activity_times.sort()  # Sort by start time
        for i in range(len(activity_times) - 1):
            start1, end1, name1 = activity_times[i]
            start2, end2, name2 = activity_times[i + 1]
            if end1 > start2:
                overlap = end1 - start2
                if overlap > 15:
                    issues.append(
                        f"Day {day_idx}: Time conflict - '{name1}' overlaps with '{name2}' by {overlap} minutes"
                    )
    
    # Calculate score
    passed = len(issues) == 0
    if passed:
        score = 1.0
    else:
        # Penalize based on number and severity of issues
        score = max(0.0, 1.0 - (len(issues) * 0.1))
    
    details: dict[str, Any] = {
        "original_days": o_days,
        "edited_days": e_days,
        "issues_count": len(issues),
    }
    if user_edit_message is not None:
        details["user_edit_message"] = user_edit_message[:200]  # truncate for display
    return {
        "passed": passed,
        "score": round(score, 2),
        "issues": issues,
        "details": details,
    }
