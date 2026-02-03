"""
Conversation state and tool-augmented processing for the travel planner.
"""

from __future__ import annotations

import traceback
from typing import Any

from src.services.rag.retriever import retrieve_context
from src.domains.mcp.registry import get_tool_definitions
from src.utils.logger import get_logger

logger = get_logger()

try:
    from src.orchestration.grok_client import SYSTEM_PROMPT, GrokCreditsError
except Exception:
    SYSTEM_PROMPT = (
        "You are a helpful Udaipur travel planning assistant. "
        "Use POI search, itinerary builder, and travel calculator when relevant."
    )
    GrokCreditsError = RuntimeError  # type: ignore[misc, assignment]


class ConversationManager:
    def __init__(
        self,
        grok_client: Any | None = None,
        overpass_client: Any | None = None,
    ) -> None:
        # Don't store clients directly - they're not serializable
        # Store only a reference that we can use to recreate if needed
        self._grok = grok_client
        self._overpass = overpass_client
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        self._last_itinerary: dict[str, Any] | None = None
    
    def __getstate__(self) -> dict[str, Any]:
        """Custom serialization - exclude non-serializable clients and sanitize data."""
        # Limit message history during serialization
        MAX_MESSAGES = 20
        messages_to_serialize = self._messages
        if len(messages_to_serialize) > MAX_MESSAGES:
            system_msg = messages_to_serialize[0] if messages_to_serialize and messages_to_serialize[0].get("role") == "system" else None
            recent = messages_to_serialize[-(MAX_MESSAGES-1):]
            messages_to_serialize = ([system_msg] + recent) if system_msg else recent
        
        # Sanitize messages - ensure all content is strings and not too large
        sanitized_messages = []
        for msg in messages_to_serialize:
            msg_copy = dict(msg)
            # Ensure content is a string and limit size
            content = msg_copy.get("content", "")
            if isinstance(content, str):
                if len(content) > 5000:
                    msg_copy["content"] = content[:5000] + "... [truncated for serialization]"
            elif content is not None:
                # Convert non-string content to string
                msg_copy["content"] = str(content)[:5000]
            sanitized_messages.append(msg_copy)
        
        # Sanitize itinerary - limit size and ensure all values are serializable
        sanitized_itinerary = None
        if self._last_itinerary:
            sanitized_itinerary = {
                "days": self._last_itinerary.get("days", [])[:10],  # Max 10 days
                "metadata": self._last_itinerary.get("metadata", {})
            }
            # Ensure metadata values are serializable
            if sanitized_itinerary["metadata"]:
                clean_meta = {}
                for k, v in sanitized_itinerary["metadata"].items():
                    if isinstance(v, (str, int, float, bool, list, dict, type(None))):
                        clean_meta[k] = v
                sanitized_itinerary["metadata"] = clean_meta
        
        return {
            "_messages": sanitized_messages,
            "_last_itinerary": sanitized_itinerary,
        }
    
    def __setstate__(self, state: dict[str, Any]) -> None:
        """Custom deserialization - clients will be recreated lazily."""
        self._messages = state.get("_messages", [{"role": "system", "content": SYSTEM_PROMPT}])
        self._last_itinerary = state.get("_last_itinerary")
        self._grok = None  # Will be recreated on demand
        self._overpass = None  # Will be recreated on demand

    def _ensure_grok(self) -> tuple[Any | None, str | None]:
        """Return (client, error_detail). error_detail is set when init fails."""
        if self._grok is not None:
            return self._grok, None
        try:
            from src.orchestration.grok_client import GrokClient
            from src.data.sources.overpass_client import OverpassClient
            # Recreate overpass client if needed (after deserialization)
            if self._overpass is None:
                # Try to get from app's cached client if available
                # Otherwise create new one
                self._overpass = OverpassClient()
            self._grok = GrokClient(overpass_client=self._overpass)
            return self._grok, None
        except Exception as e:
            err_msg = f"Grok init failed: {type(e).__name__}: {e}\n\n{traceback.format_exc()}"
            logger.warning("Grok init failed: %s", e)
            return None, err_msg

    def process_with_tools(self, user_message: str) -> tuple[str, str | None, dict[str, Any] | None, dict[str, Any] | None]:
        """
        Process user message. Returns (response_text, error_detail, itinerary_data, sources).
        error_detail is non-None when we fall back to RAG (Grok init or chat failed).
        itinerary_data is the structured itinerary from itinerary_builder tool if available.
        sources is a dict with 'pois' (list of POIs used) and 'kb_sections' (list of KB sections retrieved).
        """
        # Limit conversation history to prevent serialization issues
        MAX_MESSAGES = 20  # Reduced to prevent serialization errors
        if len(self._messages) > MAX_MESSAGES:
            # Keep system message + last (MAX_MESSAGES-1) messages
            system_msg = self._messages[0] if self._messages and self._messages[0].get("role") == "system" else None
            recent = self._messages[-(MAX_MESSAGES-1):]
            # Truncate large tool results to prevent serialization issues
            for msg in recent:
                if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
                    content = msg["content"]
                    if len(content) > 5000:  # Limit tool result size
                        msg["content"] = content[:5000] + '... [truncated]'
            self._messages = ([system_msg] + recent) if system_msg else recent
            logger.info("Trimmed conversation history to %d messages", len(self._messages))
        
        # Track which KB sections were retrieved
        kb_sections_used: list[str] = []
        q = (user_message or "").strip().lower()
        if any(k in q for k in ("overview", "introduce", "about", "city")):
            kb_sections_used.append("overview")
        if any(k in q for k in ("when", "best time", "weather", "season")):
            kb_sections_used.append("weather")
        if any(k in q for k in ("get around", "transport", "auto", "bus")):
            kb_sections_used.append("getting_around")
        if any(k in q for k in ("attraction", "see", "visit", "place")):
            kb_sections_used.append("attractions")
        if any(k in q for k in ("neighborhood", "area", "where to stay")):
            kb_sections_used.append("neighborhoods")
        if any(k in q for k in ("tip", "etiquette", "food safety", "budget")):
            kb_sections_used.append("tips")
        if not kb_sections_used:
            kb_sections_used.append("overview")  # Default
        
        # Detect query type to help LLM respond appropriately
        q_lower = (user_message or "").strip().lower()
        
        # Check for irrelevant queries (other cities, non-travel topics)
        irrelevant_keywords = [
            "mumbai", "delhi", "goa", "kerala", "bangalore", "hyderabad", "chennai",
            "kolkata", "pune", "jaipur", "jodhpur", "jaisalmer", "mount everest",
            "paris", "london", "new york", "tokyo", "dubai", "singapore",
        ]
        is_irrelevant = any(keyword in q_lower for keyword in irrelevant_keywords) and "udaipur" not in q_lower
        
        # Check for "why" questions
        is_why_question = any(
            phrase in q_lower
            for phrase in ["why did you", "why this", "why that", "why suggest", "why recommend", "explain why"]
        )
        
        # Check for general itinerary queries (need more info)
        is_general_query = any(
            phrase in q_lower
            for phrase in ["plan a trip", "what to do", "itinerary", "visit udaipur", "travel to udaipur"]
        ) and not any(
            detail in q_lower
            for detail in ["day", "heritage", "food", "nature", "culture", "relaxed", "moderate", "packed"]
        )
        
        # Add context to help LLM understand query type
        context_hints = []
        if is_irrelevant:
            context_hints.append("USER_QUERY_TYPE: IRRELEVANT - User is asking about topics outside Udaipur travel planning. Politely decline and redirect to Udaipur.")
        if is_why_question:
            context_hints.append("USER_QUERY_TYPE: EXPLANATION_REQUEST - User wants to understand why specific recommendations were made. Provide detailed explanations with citations.")
        if is_general_query:
            context_hints.append("USER_QUERY_TYPE: GENERAL_ITINERARY_QUERY - User wants itinerary but hasn't provided enough details. Ask clarifying questions BEFORE generating itinerary.")
        
        ctx = retrieve_context(user_message)
        user_block = user_message
        if ctx.strip():
            user_block = f"{user_message}\n\nRelevant travel tips:\n{ctx[:3000]}"
        if context_hints:
            user_block = f"{user_block}\n\n[Context: {' | '.join(context_hints)}]"
        
        self._messages.append({"role": "user", "content": user_block})
        
        # Reset itinerary tracking for new request
        self._last_itinerary = None

        grok, init_err = self._ensure_grok()
        if grok is None:
            fallback = ctx.strip() or "I couldn't connect to the planner. Try asking for tips or POIs."
            self._messages.append({"role": "assistant", "content": fallback})
            sources = {"pois": [], "kb_sections": kb_sections_used}
            return fallback, init_err or "Grok client unavailable.", None, sources

        try:
            out = grok.chat(self._messages, tools=get_tool_definitions())
            msg = out.get("message") or {}
            content = msg.get("content") or ""
            
            # Get sources from chat response
            sources = out.get("sources", {})
            sources_pois = sources.get("pois", [])
            # Combine with KB sections
            sources = {
                "pois": sources_pois,
                "kb_sections": kb_sections_used,
            }
            
            # Get itinerary from chat response (preferred) or extract from messages
            itinerary_data = out.get("itinerary")
            if not itinerary_data:
                itinerary_data = self._extract_itinerary_from_messages()
            
            if itinerary_data:
                # Store a lightweight reference to avoid serialization issues
                # Limit days and activities to prevent huge data structures
                days = itinerary_data.get("days", [])[:10]  # Max 10 days
                # Limit activities per day
                limited_days = []
                for day in days:
                    day_copy = dict(day)
                    activities = day_copy.get("activities", [])
                    if len(activities) > 20:  # Max 20 activities per day
                        day_copy["activities"] = activities[:20]
                    limited_days.append(day_copy)
                
                self._last_itinerary = {
                    "days": limited_days,
                    "metadata": itinerary_data.get("metadata", {})
                }
                logger.info("Itinerary data available: %d days", len(limited_days))
            else:
                logger.warning("No itinerary data found in tool results")
            
            # Limit content length to prevent huge messages
            if len(content) > 10000:
                content = content[:10000] + "\n\n[... response truncated for display ...]"
            
            self._messages.append({"role": "assistant", "content": content})
            return content, None, itinerary_data, sources
        except RuntimeError as e:
            err_str = str(e)
            # If it's a function calling error, try once more without tools as fallback
            if "Function call error" in err_str or "tool_use_failed" in err_str:
                logger.warning("Function calling failed, retrying without tools as fallback")
                try:
                    # Retry without tools - just use RAG context
                    out = grok.chat(self._messages, tools=None)
                    msg = out.get("message") or {}
                    content = msg.get("content") or ""
                    if content:
                        content += "\n\n*Note: I encountered a technical issue with the itinerary builder. Here's what I can suggest based on available information:*"
                    self._messages.append({"role": "assistant", "content": content})
                    sources = {"pois": [], "kb_sections": kb_sections_used}
                    return content, f"Function calling error (retried without tools): {err_str}", None, sources
                except Exception as retry_err:
                    # If retry also fails, fall through to original error handling
                    pass
            # Re-raise original error for normal error handling
            raise
        except GrokCreditsError as e:
            hint = str(e)
            logger.warning("Grok credits error: %s", hint)
            fallback = (
                "**Grok is unavailable** — your xAI team has no credits or licenses.\n\n"
                "**What to do:** Add credits at [console.x.ai](https://console.x.ai) → your team → Billing, "
                "then retry. Meanwhile, here are some tips:\n\n" + (ctx[:2000] or "No context available.")
            )
            self._messages.append({"role": "assistant", "content": fallback})
            sources = {"pois": [], "kb_sections": kb_sections_used}
            return fallback, f"xAI credits required\n\n{hint}", None, sources
        except Exception as e:
            err_msg = f"Grok chat failed: {type(e).__name__}: {e}\n\n{traceback.format_exc()}"
            logger.exception("Grok chat failed: %s", e)
            fallback = (
                "I ran into an issue with the planner. Here are some tips:\n\n" + (ctx[:2000] or "No context available.")
            )
            self._messages.append({"role": "assistant", "content": fallback})
            sources = {"pois": [], "kb_sections": kb_sections_used}
            return fallback, err_msg, None, sources
    
    def _extract_itinerary_from_messages(self) -> dict[str, Any] | None:
        """Extract itinerary data from tool results in recent messages."""
        import json
        # Look through recent messages for tool results from itinerary_builder
        for msg in reversed(self._messages[-20:]):  # Check last 20 messages (more thorough)
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if not content:
                    continue
                try:
                    # Tool results are JSON strings
                    if isinstance(content, str):
                        data = json.loads(content)
                    else:
                        data = content
                    # Check if this looks like an itinerary (has "days" key)
                    if isinstance(data, dict) and "days" in data and isinstance(data.get("days"), list):
                        logger.info("Extracted itinerary from tool result: %d days", len(data.get("days", [])))
                        return data
                except (json.JSONDecodeError, TypeError, AttributeError) as e:
                    logger.debug("Failed to parse tool content as itinerary: %s", e)
                    continue
        logger.debug("No itinerary found in recent tool messages")
        return None
    
    @property
    def last_itinerary(self) -> dict[str, Any] | None:
        """Get the last itinerary data from tool execution."""
        return self._last_itinerary

    @property
    def messages(self) -> list[dict[str, Any]]:
        # Return messages for display (already limited in process_with_tools)
        # Truncate any overly long content to prevent display issues
        result = []
        for msg in self._messages:
            msg_copy = dict(msg)
            content = msg_copy.get("content", "")
            if isinstance(content, str) and len(content) > 8000:
                msg_copy["content"] = content[:8000] + "\n\n[... content truncated for display ...]"
            result.append(msg_copy)
        return result

    def clear(self) -> None:
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._last_itinerary = None


def init_messages() -> list[dict[str, Any]]:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def append_user(messages: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    out = list(messages)
    out.append({"role": "user", "content": text})
    return out


def append_assistant(messages: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    out = list(messages)
    out.append({"role": "assistant", "content": text})
    return out
