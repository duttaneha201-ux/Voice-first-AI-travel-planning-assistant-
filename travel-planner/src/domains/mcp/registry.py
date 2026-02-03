"""
LLM function-calling schemas for MCP tools. OpenAI-compatible format.

Moved from `src.mcp.registry` to make the tool registry part of the MCP domain.
"""

from typing import Any, Callable

from src.domains.mcp.tools.poi_search import poi_search
from src.domains.mcp.tools.itinerary_builder import itinerary_builder
from src.domains.mcp.tools.travel_calculator import travel_calculate, travel_calculator

# OpenAI/Grok function calling format: list of tool definitions
GROK_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "poi_search",
            "description": "Search for points of interest (restaurants, museums, heritage sites, etc.) in a city. Use when the user asks for places to visit, eat, or explore.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. Udaipur"},
                    "interests": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Interest categories: food, heritage, nature, culture, shopping, etc.",
                    },
                    "constraints": {
                        "type": "object",
                        "description": "Optional: max_results (int), radius_km (float), indoor_only (bool)",
                        "properties": {
                            "max_results": {"type": "integer"},
                            "radius_km": {"type": "number"},
                            "indoor_only": {"type": "boolean"},
                        },
                    },
                },
                "required": ["city", "interests"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "itinerary_builder",
            "description": "Build a day-wise itinerary from a list of places (attractions, restaurants, etc.). Call after poi_search. Use when the user wants a multi-day plan or schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pois": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of places from poi_search. Pass full POI objects including name, type, lat, lon so reference links (Maps, OSM, Wiki) and travel times are correct.",
                    },
                    "duration_days": {"type": "integer", "description": "Number of days (2-4)"},
                    "pace": {
                        "type": "string",
                        "enum": ["relaxed", "moderate", "packed"],
                        "description": "Pace of the trip",
                    },
                    "daily_hours": {"type": "integer", "description": "Available hours per day (default 8)"},
                },
                "required": ["pois", "duration_days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "travel_calculator",
            "description": "Calculate travel time and distance between two places. Use when estimating transit between locations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_poi": {"type": "object", "description": "Place dict with lat, lon"},
                    "to_poi": {"type": "object", "description": "Place dict with lat, lon"},
                    "mode": {
                        "type": "string",
                        "enum": ["walk", "auto", "both"],
                        "description": "Travel mode",
                    },
                },
                "required": ["from_poi", "to_poi"],
            },
        },
    },
]


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return Grok/OpenAI-compatible tool definitions for function calling."""
    return [t.copy() for t in GROK_TOOLS]


def get_tool_registry() -> dict[str, Callable[..., Any]]:
    """Map tool name -> callable for execute_tool_call."""
    return {
        "poi_search": poi_search,
        "itinerary_builder": itinerary_builder,
        "travel_calculator": travel_calculator,
        "travel_calculate": travel_calculate,
    }

