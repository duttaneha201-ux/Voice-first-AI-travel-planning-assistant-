"""
Tests for Grok integration: API mock, tool execution, conversation flow.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.orchestration.grok_client import GrokClient, SYSTEM_PROMPT
from src.mcp.registry import get_tool_definitions, get_tool_registry


@patch("src.orchestration.grok_client.grok_api_key")
def test_grok_client_init(mock_key: MagicMock) -> None:
    mock_key.return_value = "test-key"
    client = GrokClient(api_key="xai-fake")
    assert client.api_key == "xai-fake"
    assert client.model
    assert client._registry


def test_tool_registry() -> None:
    reg = get_tool_registry()
    assert "poi_search" in reg
    assert "itinerary_builder" in reg
    assert "travel_calculator" in reg


def test_tool_definitions() -> None:
    tools = get_tool_definitions()
    assert len(tools) >= 3
    names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
    assert "poi_search" in names
    assert "itinerary_builder" in names


@patch("src.orchestration.grok_client.grok_api_key")
def test_execute_tool_call_poi_search(mock_key: MagicMock) -> None:
    mock_key.return_value = "x"
    mock_overpass = MagicMock()
    mock_overpass.search_pois.return_value = [{"name": "A", "lat": 24.0, "lon": 73.0, "type": "restaurant", "amenity": "restaurant"}]
    client = GrokClient(api_key="x", overpass_client=mock_overpass)
    out = client.execute_tool_call("poi_search", {"city": "Udaipur", "interests": ["food"], "constraints": {"max_results": 5}})
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["name"] == "A"


@patch("src.orchestration.grok_client.grok_api_key")
def test_execute_tool_call_itinerary_builder(mock_key: MagicMock) -> None:
    mock_key.return_value = "x"
    client = GrokClient(api_key="x")
    pois = [{"name": "City Palace", "type": "heritage", "lat": 24.576, "lon": 73.683, "duration_hours": 2, "best_time": "morning", "cost_inr": 300}]
    out = client.execute_tool_call("itinerary_builder", {"pois": pois, "duration_days": 1, "pace": "relaxed", "daily_hours": 8})
    assert isinstance(out, dict)
    assert "days" in out
    assert "metadata" in out


@patch("src.orchestration.grok_client.grok_api_key")
def test_execute_tool_call_travel_calculator(mock_key: MagicMock) -> None:
    mock_key.return_value = "x"
    client = GrokClient(api_key="x")
    a = {"lat": 24.576, "lon": 73.683}
    b = {"lat": 24.578, "lon": 73.686}
    out = client.execute_tool_call("travel_calculator", {"from_poi": a, "to_poi": b, "mode": "auto"})
    assert "distance_km" in out
    assert "walk_time_minutes" in out
    assert "auto_time_minutes" in out


@patch("src.orchestration.grok_client.requests.post")
@patch("src.orchestration.grok_client.grok_api_key")
def test_chat_mock_response(mock_key: MagicMock, mock_post: MagicMock) -> None:
    mock_key.return_value = "x"
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"role": "assistant", "content": "Here are some tips for Udaipur."}}],
            "usage": {"total_tokens": 50},
        },
    )
    mock_post.return_value.raise_for_status = MagicMock()
    client = GrokClient(api_key="x")
    msgs = [{"role": "user", "content": "Best time to visit?"}]
    out = client.chat(msgs, tools=[])
    assert "message" in out
    assert out["message"]["content"] == "Here are some tips for Udaipur."


@patch("src.orchestration.grok_client.requests.post")
@patch("src.orchestration.grok_client.grok_api_key")
def test_chat_tool_call_loop(mock_key: MagicMock, mock_post: MagicMock) -> None:
    mock_key.return_value = "x"
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            r = MagicMock(
                status_code=200,
                json=lambda: {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": "tc1",
                                "type": "function",
                                "function": {"name": "poi_search", "arguments": '{"city":"Udaipur","interests":["food"]}'},
                            }],
                        },
                    }],
                    "usage": {},
                },
            )
        else:
            r = MagicMock(
                status_code=200,
                json=lambda: {
                    "choices": [{"message": {"role": "assistant", "content": "I found these restaurants."}}],
                    "usage": {},
                },
            )
        r.raise_for_status = MagicMock()
        return r

    mock_post.side_effect = side_effect
    mock_overpass = MagicMock()
    mock_overpass.search_pois.return_value = [{"name": "Test Cafe", "lat": 24.57, "lon": 73.68, "type": "restaurant", "amenity": "restaurant"}]
    client = GrokClient(api_key="x", overpass_client=mock_overpass)
    msgs = [{"role": "user", "content": "Find restaurants"}]
    out = client.chat(msgs)
    assert "message" in out
    assert out["message"]["content"] == "I found these restaurants."
    assert call_count == 2
