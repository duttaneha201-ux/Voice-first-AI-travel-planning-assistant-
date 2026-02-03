"""Compatibility shim for Overpass client.

The implementation moved to `src.infrastructure.data.sources.overpass_client`.
"""

import requests  # kept for backwards-compatible mocking in tests

from src.infrastructure.data.sources.overpass_client import (  # noqa: F401
    CITY_COORDS,
    OVERPASS_ENDPOINT,
    OverpassClient,
    _cache_dir,
    _cache_key,
    _coords_for_city,
    _normalize_city,
    _parse_overpass_response,
    _poi_type_to_overpass,
)
