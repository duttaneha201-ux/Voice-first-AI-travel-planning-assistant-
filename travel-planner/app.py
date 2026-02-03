"""
Udaipur Travel Planner — Streamlit UI entry point.
"""

import streamlit as st
from streamlit_mic_recorder import speech_to_text

# Load .env first so updated API keys are used (e.g. after changing GROQ_API_KEY)
from src.utils.config import load_config, llm_provider, llm_api_key
load_config()

from src.infrastructure.data.sources.overpass_client import OverpassClient
from src.orchestration.conversation_manager import ConversationManager
from src.utils.logger import setup_logger, get_logger
from src.ui.itinerary_display import (
    extract_itinerary,
    parse_text_itinerary,
    _extract_intro_from_response,
    render_itinerary,
    render_sources,
    render_evaluations_block,
)

setup_logger("travel_planner", level=__import__("logging").INFO)
log = get_logger()

st.set_page_config(page_title="Udaipur Travel Planner", layout="wide")
st.title("Udaipur Travel Planner")

# Initialize clients - use cache_resource to avoid serialization issues
@st.cache_resource
def get_overpass_client():
    return OverpassClient()

overpass_client = get_overpass_client()

# Initialize conversation manager in session state
# Pass overpass_client but ConversationManager will handle serialization
if "conversation" not in st.session_state:
    st.session_state.conversation = ConversationManager(overpass_client=overpass_client)
else:
    # After deserialization, reconnect to overpass client
    if hasattr(st.session_state.conversation, '_overpass') and st.session_state.conversation._overpass is None:
        st.session_state.conversation._overpass = overpass_client

if "last_debug_error" not in st.session_state:
    st.session_state.last_debug_error = None
if "voice_transcript" not in st.session_state:
    st.session_state.voice_transcript = None
if "last_sources" not in st.session_state:
    st.session_state.last_sources = None
if "last_itinerary" not in st.session_state:
    st.session_state.last_itinerary = None
if "previous_itinerary" not in st.session_state:
    st.session_state.previous_itinerary = None
if "last_user_message" not in st.session_state:
    st.session_state.last_user_message = None

with st.sidebar:
    st.header("Settings")
    # Show which LLM and key are in use (so you can confirm updated Groq key is loaded)
    try:
        provider = llm_provider()
        key = llm_api_key()
        key_hint = f"…{key[-4:]}" if len(key) >= 4 else "…"
        st.caption(f"LLM: **{provider}** · Key: `{key_hint}`")
        if provider == "groq":
            st.caption("_Key from travel-planner/.env — restart app after changing._")
    except Exception:
        st.caption("LLM: key not loaded (check .env)")
    if st.button("Clear chat"):
        st.session_state.conversation.clear()
        st.session_state.last_debug_error = None
        st.session_state.voice_transcript = None
        st.session_state.last_itinerary = None
        st.session_state.previous_itinerary = None
        st.session_state.last_response = None
        st.session_state.last_sources = None
        st.session_state.last_user_message = None
        st.session_state.eval_results = None
        st.rerun()
    
    st.subheader("🎤 Voice Input")
    st.caption("Click the mic to speak, or use text input below")
    
    # Speech-to-text using Web Speech API (browser-based, free)
    transcript = speech_to_text(
        language='en',
        start_prompt="🎤 Start speaking",
        stop_prompt="⏹️ Stop",
        just_once=True,
        use_container_width=True,
        key="voice_input",
    )
    
    # Store transcript in session state when available
    if transcript:
        st.session_state.voice_transcript = transcript
    
    # Show live transcript prominently
    if st.session_state.voice_transcript:
        st.markdown("#### 📝 Live Transcript")
        st.success(f"**Understood:** {st.session_state.voice_transcript}")
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ Use this as input", key="use_voice_input", use_container_width=True):
                st.session_state.pending_voice_input = st.session_state.voice_transcript
                st.session_state.voice_transcript = None
                st.rerun()
        with col2:
            if st.button("🗑️ Clear", key="clear_transcript", use_container_width=True):
                st.session_state.voice_transcript = None
                st.rerun()
    
    with st.expander("Debug & settings"):
        if st.session_state.last_debug_error:
            st.error("Planner fell back to RAG due to an error:")
            st.code(st.session_state.last_debug_error, language="text")
        else:
            st.caption("No error recorded. Errors appear here when Grok init or chat fails.")
        st.divider()
        if st.button("Clear chat", key="sidebar_clear_chat", use_container_width=True):
            st.session_state.conversation.clear()
            st.session_state.last_debug_error = None
            st.session_state.voice_transcript = None
            st.session_state.last_itinerary = None
            st.session_state.previous_itinerary = None
            st.session_state.last_response = None
            st.session_state.last_sources = None
            st.session_state.last_user_message = None
            st.session_state.eval_results = None
            st.rerun()

conv = st.session_state.conversation
for msg in conv.messages:
    if msg["role"] == "system":
        continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Always render chat input (required for Streamlit to show it)
text_input = st.chat_input("Describe your Udaipur trip… (or use voice input in sidebar)")

# Check for pending voice input first, then use text input
user_input = None
if "pending_voice_input" in st.session_state and st.session_state.pending_voice_input:
    user_input = st.session_state.pending_voice_input
    del st.session_state.pending_voice_input
elif "pending_followup" in st.session_state and st.session_state.pending_followup:
    user_input = st.session_state.pending_followup
    del st.session_state.pending_followup
elif text_input:
    user_input = text_input

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    with st.spinner("Planning…"):
        response, debug_error, itinerary_data, sources = conv.process_with_tools(user_input)
    if debug_error:
        st.session_state.last_debug_error = debug_error
    else:
        st.session_state.last_debug_error = None

    with st.chat_message("assistant"):
        # Store response and user message for evaluations (grounding, edit correctness)
        st.session_state.last_response = response
        st.session_state.last_sources = sources
        st.session_state.last_user_message = user_input
        
        # Try to get itinerary from tool execution first, then fall back to text parsing
        it = itinerary_data
        if not it or not (it.get("days") or []):
            it = extract_itinerary(response)
        # Keep previous itinerary for edit-correctness whenever we had a structured itinerary before
        # (so even prose-only second response gets edit correctness vs first itinerary)
        if st.session_state.get("last_itinerary") and st.session_state.last_itinerary.get("days"):
            st.session_state.previous_itinerary = st.session_state.last_itinerary
        st.session_state.last_itinerary = it
        # If response was prose-only (no structured days), parse day-wise text so eval/export have structure
        if (not it or not (it.get("days") or [])) and response:
            parsed = parse_text_itinerary(response)
            extracted = extract_itinerary(response)
            for candidate in (parsed, extracted):
                if candidate and (candidate.get("days") or []):
                    st.session_state.last_itinerary = candidate
                    break
        
        # If we have structured itinerary data, render it properly
        if it and it.get("days") and len(it.get("days", [])) > 0:
            # We have structured data - render it in formatted way
            # Show brief intro text if response has useful context
            intro_text = _extract_intro_from_response(response)
            if intro_text:
                st.markdown(intro_text)
            render_itinerary(it, sources=sources)
        else:
            # No structured itinerary - show the text response as fallback
            st.markdown(response)
            # Show sources if available
            if sources and (sources.get("pois") or sources.get("kb_sections")):
                render_sources(sources)
        
        if debug_error:
            with st.expander("Error details (debug)"):
                st.code(debug_error, language="text")
        
        # (Follow-up UI is rendered outside this block so it works on reruns.)

# Show Evaluations CTA after any assistant response (so it's always visible after itinerary generation).
if st.session_state.get("last_response") is not None:
    last_it = st.session_state.get("last_itinerary")
    last_res = st.session_state.get("last_response") or ""
    # Use structured itinerary, or JSON from response, or parse day-wise text (Day 1, Day 2, places)
    it_for_eval = last_it if (last_it and last_it.get("days")) else None
    if not it_for_eval and last_res:
        extracted = extract_itinerary(last_res)
        parsed = parse_text_itinerary(last_res)
        # Prefer whichever has non-empty days (extract can return {"days": []} from empty JSON block)
        if extracted and (extracted.get("days") or []):
            it_for_eval = extracted
        elif parsed and (parsed.get("days") or []):
            it_for_eval = parsed
        else:
            it_for_eval = extracted or parsed
    # If still no days, try parsing the last assistant message from chat (in case last_response differs)
    if (not it_for_eval or not (it_for_eval.get("days") or [])) and conv.messages:
        for msg in reversed(conv.messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                content = msg["content"]
                if isinstance(content, str) and "Day " in content:
                    parsed_from_chat = parse_text_itinerary(content)
                    if parsed_from_chat and (parsed_from_chat.get("days") or []):
                        it_for_eval = parsed_from_chat
                        break
    render_evaluations_block(it_for_eval, st.session_state.get("last_sources"))

# Always render follow-up actions based on the last response/itinerary.
if st.session_state.get("last_response") is not None:
    from src.ui.itinerary_display import _show_followup_questions

    _show_followup_questions(
        st.session_state.get("last_itinerary"),
        st.session_state.get("last_response") or "",
        st,
        sources=st.session_state.get("last_sources"),
    )