"""
Tests for OverpassClient: POI search, caching, rate limiting.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.data.sources.overpass_client import OverpassClient, _cache_key, _parse_overpass_response


@pytest.fixture
def temp_cache(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def client(temp_cache: Path) -> OverpassClient:
    return OverpassClient(max_requests=2, cache_dir=temp_cache)


def test_poi_search_udaipur_restaurants(client: OverpassClient, temp_cache: Path) -> None:
    """Test POI search for Udaipur restaurants."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "elements": [
            {
                "type": "node",
                "lat": 24.58,
                "lon": 73.71,
                "tags": {"name": "Test Restaurant", "amenity": "restaurant"},
            },
            {
                "type": "node",
                "lat": 24.579,
                "lon": 73.712,
                "tags": {"name": "Cafe Lake", "amenity": "cafe"},
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.data.sources.overpass_client.requests.post", return_value=mock_response):
        pois = client.search_pois("Udaipur", "restaurant", radius_km=5.0)

    assert len(pois) == 2
    assert pois[0]["name"] == "Test Restaurant"
    assert pois[0]["lat"] == 24.58
    assert pois[0]["lon"] == 73.71
    assert pois[0]["type"] == "restaurant"
    assert pois[0]["amenity"] == "restaurant"
    assert pois[1]["name"] == "Cafe Lake"


def test_caching(client: OverpassClient, temp_cache: Path) -> None:
    """Test that results are cached and cache is used on second call."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "elements": [
            {"type": "node", "lat": 24.58, "lon": 73.71, "tags": {"name": "Cached POI", "amenity": "restaurant"}},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    post = patch("src.data.sources.overpass_client.requests.post", return_value=mock_response)
    with post as mock_post:
        a = client.search_pois("Udaipur", "restaurant", radius_km=5.0)
        b = client.search_pois("Udaipur", "restaurant", radius_km=5.0)

    assert len(a) == 1 and a[0]["name"] == "Cached POI"
    assert a == b
    assert mock_post.call_count == 1

    key = _cache_key("Udaipur", "restaurant", 5.0)
    cache_file = temp_cache / key
    assert cache_file.is_file()
    with open(cache_file, encoding="utf-8") as f:
        cached = json.load(f)
    assert len(cached) == 1 and cached[0]["name"] == "Cached POI"


def test_rate_limiting(client: OverpassClient, temp_cache: Path) -> None:
    """Test that rate limit is enforced after max_requests (no cache)."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"elements": []}
    mock_response.raise_for_status = MagicMock()

    with patch("src.data.sources.overpass_client.requests.post", return_value=mock_response):
        client.search_pois("Udaipur", "restaurant", radius_km=5.0)
        client.search_pois("Udaipur", "museum", radius_km=5.0)
        with pytest.raises(RuntimeError, match="rate limit"):
            client.search_pois("Udaipur", "park", radius_km=5.0)


def test_parse_overpass_response() -> None:
    """Test parsing of Overpass JSON response."""
    data = {
        "elements": [
            {"type": "node", "lat": 1.0, "lon": 2.0, "tags": {"name": "A", "amenity": "restaurant"}},
            {"type": "node", "lat": 3.0, "lon": 4.0, "tags": {}},
        ]
    }
    out = _parse_overpass_response(data)
    assert len(out) == 2
    assert out[0]["name"] == "A" and out[0]["lat"] == 1.0 and out[0]["lon"] == 2.0
    assert out[1]["name"] == "Unnamed"
