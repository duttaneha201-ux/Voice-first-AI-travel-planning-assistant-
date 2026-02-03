"""Compatibility shim for Streamlit itinerary UI.

The implementation moved to `src.ui.itinerary_display`.
"""

from src.ui.itinerary_display import (  # noqa: F401
    extract_itinerary,
    render_itinerary,
    render_sources,
    _extract_intro_from_response,
    _show_followup_questions,
)