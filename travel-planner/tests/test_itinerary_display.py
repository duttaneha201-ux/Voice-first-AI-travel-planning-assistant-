"""
Tests for itinerary_display: parse_text_itinerary, extract_itinerary.
"""

from __future__ import annotations

import pytest

from src.ui.itinerary_display import parse_text_itinerary


def test_parse_text_itinerary_slot_time_range_format() -> None:
    """parse_text_itinerary detects day-wise itinerary when using 'Morning (8:00 AM - 10:00 AM): Place' format."""
    text = """
Here is your 2-day itinerary for Udaipur.

Day 1:
Morning (8:00 AM - 10:00 AM): City Palace
Late Morning (10:30 AM - 12:30 PM): Jagdish Temple
Lunch Break (12:30 PM - 1:30 PM): Local restaurant
Afternoon (2:00 PM - 4:00 PM): Sahelion-ki-Bari
Evening (5:00 PM - 7:00 PM): Hathi Pol Bazaar

Day 2:
Morning (8:00 AM - 10:00 AM): Lake Pichola
Late Morning (10:30 AM - 12:30 PM): Jag Mandir
Afternoon (2:00 PM - 4:00 PM): Crystal Gallery
Evening (5:00 PM - 7:00 PM): Stroll along Lake Pichola
"""
    result = parse_text_itinerary(text)
    assert result is not None
    assert "days" in result
    days = result["days"]
    assert len(days) == 2

    day1 = next(d for d in days if d.get("day_number") == 1)
    day2 = next(d for d in days if d.get("day_number") == 2)

    names1 = [a.get("poi", {}).get("name") for a in day1.get("activities", [])]
    names2 = [a.get("poi", {}).get("name") for a in day2.get("activities", [])]

    assert "City Palace" in names1
    assert "Jagdish Temple" in names1
    assert "Sahelion-ki-Bari" in names1
    assert "Hathi Pol Bazaar" in names1

    assert "Lake Pichola" in names2
    assert "Jag Mandir" in names2
    assert "Crystal Gallery" in names2
    assert "Stroll along Lake Pichola" in names2


def test_parse_text_itinerary_returns_none_for_empty() -> None:
    """parse_text_itinerary returns None for empty or non-itinerary text."""
    assert parse_text_itinerary("") is None
    assert parse_text_itinerary("   ") is None
    assert parse_text_itinerary("Just some random text with no Day 1.") is None


def test_parse_text_itinerary_prose_format() -> None:
    """parse_text_itinerary detects day-wise itinerary when using prose format (visit to the X, head to the X, boat ride on X)."""
    text = """
For a 2-day trip to Udaipur, I've condensed the itinerary to focus on the most iconic heritage sites.

Day 1:

Start your day at 8:00 AM with a visit to the City Palace, one of Udaipur's most iconic heritage sites.
At 11:00 AM, head to the Jagdish Temple, a 16th-century temple dedicated to Lord Vishnu.
After lunch, visit the Sahelion-ki-Bari at 2:00 PM, a beautiful garden built for the royal ladies of Mewar.
End your day with a scenic boat ride on Lake Pichola at 5:00 PM.

Day 2:

Begin your day at 8:00 AM with a visit to the Bagore-ki-Haveli, an 18th-century haveli that features a museum.
At 10:00 AM, head to the Monsoon Palace, also known as the Sajjangarh Palace.
After lunch, visit the Crystal Gallery at 2:00 PM, located within the Fateh Prakash Palace.
End your day with a stroll through the old city at 4:00 PM, exploring its narrow streets.
"""
    result = parse_text_itinerary(text)
    assert result is not None
    assert "days" in result
    days = result["days"]
    assert len(days) == 2

    day1 = next(d for d in days if d.get("day_number") == 1)
    day2 = next(d for d in days if d.get("day_number") == 2)

    names1 = [a.get("poi", {}).get("name") for a in day1.get("activities", [])]
    names2 = [a.get("poi", {}).get("name") for a in day2.get("activities", [])]

    assert "City Palace" in names1
    assert "Jagdish Temple" in names1
    assert "Sahelion-ki-Bari" in names1
    assert "Lake Pichola" in names1

    assert "Bagore-ki-Haveli" in names2
    assert "Monsoon Palace" in names2
    assert "Crystal Gallery" in names2
    assert "old city" in names2


def test_parse_text_itinerary_exact_user_chat_2day() -> None:
    """Regression: exact 2-day prose response from user chat parses so Run Evaluations works."""
    text = """Relevant travel tips: Overview Udaipur, the "City of Lakes," is in southern Rajasthan.

For a 2-day trip to Udaipur, I've condensed the itinerary to focus on the most iconic heritage sites, while maintaining a moderate pace.

Day 1:

Start your day at 8:00 AM with a visit to the City Palace, one of Udaipur's most iconic heritage sites. According to travel guides, the palace offers stunning views of Lake Pichola, especially in the morning light.
At 11:00 AM, head to the Jagdish Temple, a 16th-century temple dedicated to Lord Vishnu and a beautiful example of Mewar architecture.
After lunch, visit the Sahelion-ki-Bari at 2:00 PM, a beautiful garden built for the royal ladies of Mewar. The garden features intricately designed fountains, lotus pools, and a variety of flora.
End your day with a scenic boat ride on Lake Pichola at 5:00 PM.
Day 2:

Begin your day at 8:00 AM with a visit to the Bagore-ki-Haveli, an 18th-century haveli that features a museum showcasing the region's history and culture.
At 10:00 AM, head to the Monsoon Palace, also known as the Sajjangarh Palace. The palace offers breathtaking views of the city and the surrounding landscape.
After lunch, visit the Crystal Gallery at 2:00 PM, located within the Fateh Prakash Palace. The gallery showcases a collection of crystal objects and is a must-visit for those interested in history and craftsmanship.
End your day with a stroll through the old city at 4:00 PM, exploring its narrow streets and historic buildings.
This 2-day itinerary should give you a good taste of Udaipur's heritage sites and culture.
"""
    result = parse_text_itinerary(text)
    assert result is not None, "parse_text_itinerary must return a day-wise structure for Run Evaluations to work"
    assert "days" in result
    days = result["days"]
    assert len(days) >= 2, "expected at least 2 days from 2-day itinerary"
    names_day1 = [a.get("poi", {}).get("name") for a in days[0].get("activities", [])]
    names_day2 = [a.get("poi", {}).get("name") for a in days[1].get("activities", [])]
    assert "City Palace" in names_day1
    assert "Jagdish Temple" in names_day1
    assert "Sahelion-ki-Bari" in names_day1
    assert "Lake Pichola" in names_day1
    assert "Bagore-ki-Haveli" in names_day2
    assert "Monsoon Palace" in names_day2
    assert "Crystal Gallery" in names_day2
    assert "old city" in names_day2


def test_parse_text_itinerary_for_day_suggest_recommend_format() -> None:
    """parse_text_itinerary detects day-wise itinerary when using 'For Day 1, I suggest:' / 'For Day 2, I recommend:' format."""
    text = """I'd be happy to modify the itinerary for you.

For Day 1, the plan remains the same: 8:00 AM - 10:00 AM: Start your day with a visit to Fateh Sagar Lake, a beautiful artificial lake. 10:30 AM - 12:30 PM: Head over to the Crystal Gallery. 1:00 PM - 2:30 PM: Take a break for lunch at a local restaurant near Lake Pichola. 3:00 PM - 5:00 PM: Visit the Sahelion ki Bari. 6:00 PM - 7:30 PM: End your day with a relaxing boat ride on Lake Pichola.

For Day 2, I recommend: 8:00 AM - 10:00 AM: Visit the City Palace, a historic palace. 10:30 AM - 12:30 PM: Head over to the Lake Pichola. 1:00 PM - 2:30 PM: Have lunch at a local restaurant. 3:00 PM - 5:00 PM: Visit the Kesar Kyari Bagh. 6:00 PM - 7:30 PM: End your day with a visit to the Doodh Talai Musical Garden.

This revised itinerary adds a heritage site to the morning slot on Day 2."""
    result = parse_text_itinerary(text)
    assert result is not None, "parse_text_itinerary must return a day-wise structure for Run Evaluations to work"
    assert "days" in result
    days = result["days"]
    assert len(days) == 2, "expected 2 days from For Day 1 / For Day 2 format"
    day1 = next(d for d in days if d.get("day_number") == 1)
    day2 = next(d for d in days if d.get("day_number") == 2)
    names1 = [a.get("poi", {}).get("name") for a in day1.get("activities", [])]
    names2 = [a.get("poi", {}).get("name") for a in day2.get("activities", [])]
    assert len(names1) >= 3, "Day 1 should have at least 3 activities"
    assert len(names2) >= 3, "Day 2 should have at least 3 activities"
    # Names may be short (e.g. Fateh Sagar Lake) or longer (e.g. Start your day with a visit to Fateh Sagar Lake)
    assert any("Fateh Sagar" in n or "Crystal Gallery" in n or "Sahelion" in n for n in names1)
    assert any("City Palace" in n or "Lake Pichola" in n or "Kesar" in n for n in names2)


def test_parse_text_itinerary_three_days() -> None:
    """parse_text_itinerary handles 3-day itinerary with slot): Place format."""
    text = """
Day 1:
Morning (8:00 AM - 10:00 AM): City Palace
Afternoon (2:00 PM - 4:00 PM): Jagdish Temple

Day 2:
Morning (9:00 AM - 11:00 AM): Lake Pichola
Evening (5:00 PM - 7:00 PM): Monsoon Palace

Day 3:
Morning (8:00 AM - 10:00 AM): Shilpgram
Afternoon (2:00 PM - 4:00 PM): Bada Bazaar
"""
    result = parse_text_itinerary(text)
    assert result is not None
    assert len(result["days"]) == 3
    day3 = next(d for d in result["days"] if d.get("day_number") == 3)
    names3 = [a.get("poi", {}).get("name") for a in day3.get("activities", [])]
    assert "Shilpgram" in names3
    assert "Bada Bazaar" in names3
