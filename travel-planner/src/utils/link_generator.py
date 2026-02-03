"""
Generate resource links for POIs and knowledge base sources.
"""

from __future__ import annotations

from urllib.parse import quote
from typing import Any


# Default city for link context (avoids wrong "City Palace" etc. resolving to other cities)
DEFAULT_POI_CITY = "Udaipur"


def generate_poi_links(poi: dict[str, Any], city: str | None = None) -> dict[str, str]:
    """
    Generate resource links for a POI. Uses city (default Udaipur) in search so links resolve correctly.
    
    Args:
        poi: POI dict with name, lat, lon (optional).
        city: City name for disambiguation in Maps/Wiki (default Udaipur).
    
    Returns:
        Dict with link_type -> URL (e.g., {"google_maps": "...", "osm": "..."}).
    """
    links: dict[str, str] = {}
    name = (poi.get("name") or "").strip()
    lat = poi.get("lat")
    lon = poi.get("lon")
    city = (city or DEFAULT_POI_CITY).strip()
    
    if not name:
        return links
    
    # Google Maps: search "Name, City" so results are correct (e.g. City Palace, Udaipur)
    search_name = f"{name}, {city}" if city else name
    maps_query = quote(search_name.replace(" ", "+"), safe="+")
    links["google_maps"] = f"https://www.google.com/maps/search/?api=1&query={maps_query}"
    if lat is not None and lon is not None:
        links["google_maps_coords"] = f"https://www.google.com/maps?q={lat},{lon}"
        links["openstreetmap"] = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"
    
    # Wikipedia: "Name (Udaipur)" or "Name" for disambiguation when needed
    wiki_path = quote(name.replace(" ", "_"), safe="_")
    links["wikipedia"] = f"https://en.wikipedia.org/wiki/{wiki_path}"
    
    return links


def generate_kb_section_link(section: str) -> str | None:
    """
    Generate a link for a knowledge base section.
    
    Args:
        section: KB section name (e.g., "overview", "attractions").
    
    Returns:
        URL string or None if no link available.
    """
    # Map KB sections to relevant external resources
    section_links = {
        "overview": "https://en.wikipedia.org/wiki/Udaipur",
        "attractions": "https://en.wikipedia.org/wiki/Udaipur#Tourism",
        "tips": "https://wikitravel.org/en/Udaipur",
        "weather": "https://en.wikipedia.org/wiki/Udaipur#Climate",
        "getting_around": "https://wikitravel.org/en/Udaipur#Get_around",
        "neighborhoods": "https://wikitravel.org/en/Udaipur#Districts",
    }
    return section_links.get(section.lower())


def format_source_links(poi: dict[str, Any] | None = None, kb_section: str | None = None) -> list[dict[str, str]]:
    """
    Format links for display in UI.
    
    Args:
        poi: Optional POI dict.
        kb_section: Optional KB section name.
    
    Returns:
        List of dicts with "label" and "url" keys.
    """
    links: list[dict[str, str]] = []
    
    if poi:
        poi_links = generate_poi_links(poi)
        if "google_maps" in poi_links:
            links.append({"label": "Maps", "url": poi_links["google_maps"]})
        if "openstreetmap" in poi_links:
            links.append({"label": "OSM", "url": poi_links["openstreetmap"]})
        if "wikipedia" in poi_links:
            links.append({"label": "Wiki", "url": poi_links["wikipedia"]})
    
    if kb_section:
        kb_url = generate_kb_section_link(kb_section)
        if kb_url:
            section_labels = {
                "overview": "City Overview",
                "attractions": "Attractions Guide",
                "tips": "Travel Tips",
                "weather": "Weather Info",
                "getting_around": "Transportation",
                "neighborhoods": "Neighborhoods",
            }
            label = section_labels.get(kb_section.lower(), kb_section.title())
            links.append({"label": f"📚 {label}", "url": kb_url})
    
    return links
