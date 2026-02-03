"""
Test serialization of ConversationManager to ensure it works with Streamlit session state.
"""

from __future__ import annotations

import pickle
import pytest

from src.orchestration.conversation_manager import ConversationManager
from src.data.sources.overpass_client import OverpassClient


def test_conversation_manager_serialization() -> None:
    """Test that ConversationManager can be pickled (required for Streamlit session state)."""
    manager = ConversationManager()
    manager._messages.append({"role": "user", "content": "Test message"})
    manager._messages.append({"role": "assistant", "content": "Test response"})
    manager._last_itinerary = {
        "days": [{"day_number": 1, "activities": []}],
        "metadata": {"total_cost_inr": 100}
    }
    
    # Test serialization
    try:
        pickled = pickle.dumps(manager)
        assert len(pickled) > 0
        
        # Test deserialization
        unpickled = pickle.loads(pickled)
        assert len(unpickled._messages) == len(manager._messages)
        assert unpickled._last_itinerary is not None
        assert unpickled._grok is None  # Should be None after deserialization
        assert unpickled._overpass is None  # Should be None after deserialization
    except Exception as e:
        pytest.fail(f"Serialization failed: {e}")


def test_conversation_manager_large_data() -> None:
    """Test that ConversationManager handles large data gracefully."""
    manager = ConversationManager()
    # Add many messages
    for i in range(30):
        manager._messages.append({"role": "user", "content": f"Message {i}" * 100})
    
    # Add large itinerary
    manager._last_itinerary = {
        "days": [{"day_number": d, "activities": [{"poi": {"name": f"POI {i}"}} for i in range(50)]} for d in range(1, 15)],
        "metadata": {"total_cost_inr": 10000}
    }
    
    # Should serialize without error (data will be truncated in __getstate__)
    try:
        pickled = pickle.dumps(manager)
        unpickled = pickle.loads(pickled)
        # After deserialization, data should be limited by __getstate__
        assert len(unpickled._messages) <= 20, f"Expected <= 20 messages, got {len(unpickled._messages)}"
        if unpickled._last_itinerary:
            assert len(unpickled._last_itinerary.get("days", [])) <= 10, f"Expected <= 10 days, got {len(unpickled._last_itinerary.get('days', []))}"
    except Exception as e:
        pytest.fail(f"Serialization of large data failed: {e}")
