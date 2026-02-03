"""
Feasibility evaluation: check time constraints in itineraries.
Validates daily hours, travel time, pace constraints, and meal breaks.
"""

from __future__ import annotations

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


def evaluate_feasibility(
    itinerary: list[dict[str, Any]],
    daily_hours: int = 8,
    pace: str = "moderate",
) -> dict[str, Any]:
    """
    Evaluate whether an itinerary respects time constraints.
    
    Checks:
    - Daily hours don't exceed daily_hours * pace_multiplier
    - Travel time is accounted for
    - Activities don't overlap in time
    - Meal breaks are included (at least one food POI per day)
    - Day doesn't extend beyond reasonable hours (8 AM - 9 PM)
    
    Args:
        itinerary: List of day dicts with "activities" list.
        daily_hours: Available hours per day (default 8).
        pace: "relaxed" (0.6), "moderate" (0.75), or "packed" (0.9).
    
    Returns:
        Dict with passed (bool), score (0.0-1.0), and details (list of issues).
    """
    pace_multipliers = {"relaxed": 0.6, "moderate": 0.75, "packed": 0.9}
    pace_mult = pace_multipliers.get(pace.lower(), 0.75)
    daily_cap = daily_hours * pace_mult
    
    issues: list[str] = []
    total_hours = 0.0
    all_passed = True
    
    for day_idx, day in enumerate(itinerary, 1):
        # Handle both formats: {"day": X, "activities": [...]} and {"day_number": X, "activities": [...]}
        activities = day.get("activities", [])
        if not activities:
            issues.append(f"Day {day_idx}: No activities scheduled")
            all_passed = False
            continue
        
        day_total_hours = 0.0
        has_food = False
        prev_end_time = 8 * 60  # Start at 8 AM (in minutes)
        time_conflicts = []
        
        for act_idx, act in enumerate(activities):
            poi = act.get("poi", {})
            duration = float(poi.get("duration_hours", 0) or act.get("duration_hours", 0))
            travel_min = int(act.get("travel_time_from_previous", 0))
            time_str = act.get("time", "")
            
            # Check travel time is accounted for
            if act_idx > 0 and travel_min == 0:
                issues.append(f"Day {day_idx}, Activity {act_idx + 1}: Missing travel time from previous")
            
            # Parse start time
            start_minutes = _parse_time(time_str)
            if start_minutes == 0 and time_str:
                issues.append(f"Day {day_idx}, Activity {act_idx + 1}: Could not parse time '{time_str}'")
            
            # Check time conflicts (overlap with previous activity); allow 15 min tolerance for rounding
            if start_minutes > 0:
                overlap_min = prev_end_time - start_minutes if start_minutes < prev_end_time else 0
                if overlap_min > 15:
                    time_conflicts.append(f"Day {day_idx}, Activity {act_idx + 1}: Starts at {time_str} but previous ends later")
                prev_end_time = start_minutes + int(round(duration * 60)) + travel_min
            
            # Check if day extends beyond 9 PM (21:00)
            end_minutes = start_minutes + int(round(duration * 60)) + travel_min
            if end_minutes > 21 * 60:  # 9 PM
                issues.append(f"Day {day_idx}, Activity {act_idx + 1}: Extends beyond 9 PM")
                all_passed = False
            
            day_total_hours += duration + (travel_min / 60.0)
            total_hours += duration + (travel_min / 60.0)
            
            # Check for food POI (type or name indicating meal)
            poi_type = (poi.get("type") or "").lower()
            poi_name = (poi.get("name") or "").lower()
            if poi_type in ("food", "restaurant", "dining", "cafe"):
                has_food = True
            if not has_food and poi_name in ("lunch", "dinner", "breakfast", "lunch break", "dinner break", "break for lunch", "break for dinner"):
                has_food = True
            # Prose names (e.g. "Visit Cafe Edelweiss for a leisurely coffee break.") - substring match
            if not has_food and any(
                kw in poi_name
                for kw in ("cafe", "coffee", "coffee break", "lunch", "dinner", "breakfast", "restaurant", "meal")
            ):
                has_food = True
        
        # Check daily hours limit (0.5h tolerance so small exceedance doesn't fail)
        if day_total_hours > daily_cap + 0.5:
            issues.append(
                f"Day {day_idx}: Exceeds daily limit ({round(day_total_hours, 1)}h > {round(daily_cap, 1)}h for {pace} pace)"
            )
            all_passed = False
        
        # Check for meal breaks
        if not has_food and day_total_hours > 4:
            issues.append(f"Day {day_idx}: No meal break for {round(day_total_hours, 1)}h schedule")
            # Warning, not a failure
        
        # Check time conflicts
        if time_conflicts:
            issues.extend(time_conflicts)
            all_passed = False
    
    # Calculate score (0.0 to 1.0)
    if all_passed and not issues:
        score = 1.0
    elif all_passed:
        score = 0.8  # Passed but has warnings
    else:
        # Penalize based on number of issues
        score = max(0.0, 1.0 - (len(issues) * 0.15))
    
    return {
        "passed": all_passed,
        "score": round(score, 2),
        "total_hours": round(total_hours, 2),
        "issues": issues,
        "details": {
            "daily_cap": round(daily_cap, 1),
            "pace": pace,
            "days_evaluated": len(itinerary),
        },
    }
