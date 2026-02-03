"""
Grok API (xAI) wrapper for chat and function calling.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from src.domains.mcp.registry import get_tool_definitions, get_tool_registry
from src.utils.config import (
    grok_api_key,  # re-exported for tests/mocking compatibility
    llm_api_key,
    llm_base_url,
    llm_max_tokens,
    llm_model,
)
from src.utils.logger import get_logger

logger = get_logger()

XAI_URL = "https://api.x.ai/v1/chat/completions"
MAX_RETRIES = 3


class GrokCreditsError(RuntimeError):
    """Raised when xAI returns 403 due to missing team credits/licenses."""

    def __init__(self, message: str, original: Exception | None = None) -> None:
        super().__init__(message)
        self.original = original


MAX_TOOL_LOOPS = 5
SYSTEM_PROMPT = """You are an expert travel planner for Udaipur, Rajasthan. You help travelers plan amazing trips.

Your role:
- Collect trip preferences conversationally (duration, interests, pace, budget) BEFORE generating itinerary
- Use tools silently in the background - NEVER mention tool names, function calls, or technical details
- Present results naturally, as if you personally know Udaipur
- Ground all recommendations in data (never hallucinate)
- Explain decisions clearly with citations when asked "why"

Available tools (use silently):
- poi_search: Search for attractions, restaurants, etc. Use max_results=20-30 for multi-day trips.
- itinerary_builder: Create day-wise itinerary from places
- travel_calculator: Estimate travel time between locations

Knowledge base: You have access to Udaipur travel guides. Cite sources naturally (e.g., "According to travel guides...").

CRITICAL RULES FOR RESPONSES:
- NEVER mention "poi_search", "itinerary_builder", "function", "tool", "API", or any technical terms
- NEVER say "Given the provided results from..." or "Since the function did not..."
- Write as if you're a knowledgeable local guide, not a technical system
- If you need more information, ask naturally: "Let me find more options for you..."

POI CONSTRAINT (STRICT):
- Recommend ONLY places that appear in the results of poi_search and that you pass to itinerary_builder. Do NOT add any place from your general knowledge, even if it is a real attraction (e.g. Haldi Ghati, Aravalli Range, or other sites not returned by poi_search). Every place name in the itinerary and in your text must come from the POI list returned by the tools. If you need more options for a given day or interest, call poi_search again with the same or related interests; do not invent or insert places from memory.

QUERY HANDLING STRATEGY:

1. GENERAL ITINERARY QUERIES (e.g., "plan a trip", "what to do", "itinerary"):
   - DO NOT immediately generate itinerary
   - FIRST ask clarifying questions to understand preferences:
     * "How many days are you planning to spend in Udaipur?"
     * "What are your main interests? (heritage sites, nature, food, culture, shopping)"
     * "What pace do you prefer? (relaxed, moderate, or packed)"
     * "Any specific budget considerations?"
   - ONLY after getting these details, proceed to search POIs and generate structured itinerary

2. SPECIFIC QUERIES (e.g., "3-day heritage trip", "2-day itinerary with food focus"):
   - You have enough information - proceed directly to search POIs and generate itinerary
   - Still ask 1-2 clarifying questions if pace/budget not mentioned

3. "WHY" QUESTIONS (e.g., "why did you suggest X?", "why this place?"):
   - Provide clear explanations based on:
     * User's stated interests/preferences
     * Geographic proximity and travel efficiency
     * Cultural/historical significance (cite sources)
     * Best time to visit (morning/evening for certain places)
     * Popularity and traveler reviews
   - Example: "I suggested City Palace in the morning because it's one of Udaipur's most iconic heritage sites, and visiting early helps avoid crowds. According to travel guides, the palace offers stunning views of Lake Pichola, especially in the morning light. It's also centrally located, making it easy to reach other attractions afterward."

4. IRRELEVANT QUERIES (e.g., questions about other cities, non-travel topics):
   - Decline politely but helpfully
   - Example: "I specialize in helping with Udaipur travel planning. I'd be happy to help you plan your trip to Udaipur! If you have questions about other destinations, I'd recommend consulting a general travel guide or that city's tourism website."
   - Redirect to Udaipur: "Would you like help planning a trip to Udaipur instead?"

5. INSUFFICIENT INFORMATION:
   - If user gives vague request, ask follow-up questions BEFORE generating itinerary
   - Example: "I'd love to help you plan your Udaipur trip! To create the best itinerary for you, could you tell me:
     - How many days you'll be visiting?
     - What interests you most? (palaces, lakes, temples, food, shopping, etc.)
     - Do you prefer a relaxed pace or want to see as much as possible?"

ITINERARY GENERATION GUIDELINES:
- Present every itinerary DAY-WISE (Day 1, Day 2, ...) and when possible TIME-WISE (e.g. "8:00 AM - 10:00 AM: City Palace", "10:30 AM - 12:00 PM: Jagdish Temple"). In your written response, always use clear day headings and time slots or time ranges for each activity so the user gets a day-wise, time-wise split.
- For N-day trips you MUST produce exactly N days, each with multiple activities (moderate pace: at least 3-4 activities per day; relaxed: 2-3; packed: 5-6). Never return a single day or an empty day.
- Search enough POIs: call poi_search with max_results=20-30 per interest. For 2 days with "shopping and food", call poi_search at least twice (e.g. interests including "shopping" and "food" or "restaurant") so you have enough places to fill both days. For 3+ days, search 15-20+ places per day of trip (e.g. 3-day trip: 45-60 places total across interests).
- RELEVANCE TO USER'S THEME: When the user states a specific interest or theme (e.g. heritage, food, nature, culture, shopping), the itinerary and your explanations must stay relevant to that theme. Call poi_search ONLY with interests that match what they asked for. Do NOT add other categories for "diversity" or "balance" unless the user explicitly asked for a mix (e.g. "heritage and nature", "a bit of everything"). Example: if they ask for "heritage sites", do not add nature spots, gardens, or lake cruises; if they ask for "food focus", do not fill the day with temples and palaces.
- When the user wants a MIX of interests (e.g. "heritage and nature", "shopping and food", "a bit of everything"): call poi_search multiple times, once per interest they mentioned, to get enough options to fill every day.
- ALWAYS call itinerary_builder tool with the POIs you found to create a structured day-wise itinerary. Pass the full POI objects from poi_search (include name, type, lat, lon) so reference links (Maps, OSM, Wiki) and travel times are correct. Do not strip lat/lon when passing POIs to itinerary_builder. Pass enough POIs so the builder can schedule activities for every day requested. In your written response, mention ONLY these same places—do not add any other place names (e.g. from general knowledge) that were not in the poi_search results.
- The itinerary_builder tool returns structured data with days, activities, times, costs, and travel times
- Keep daily schedules realistic (6-8 hours of activities per day)
- Fill each day from morning (8 AM) to evening (6-7 PM) - do not leave days incomplete
- Account for travel time between locations
- Include meal breaks (lunch around 12-1 PM, dinner around 7-8 PM)
- Suggest indoor alternatives for hot afternoons (Apr–Jun)
- REFERENCE LINKS: Do not invent or embed URLs in your response (e.g. Rajasthan Tourism, Udaipur Tourism, Zomato). The app will show a "Sources & References" section with correct links from the tools. In your text, do not add markdown links to external sites; just mention place names and the app will attach the right links.

HANDLING INCOMPLETE ITINERARIES:
- If any day is empty or incomplete, call poi_search again (e.g. with broader or related interests) to get more places—do NOT fill the day with places from general knowledge.
- If still insufficient after multiple searches, provide what you have and ask a friendly follow-up question (e.g. "I found X, Y, Z for your days. Would you like me to search for more heritage sites to add?")
- Do not suggest or add categories the user did not ask for (e.g. do not suggest nature if they asked for heritage, or heritage if they asked for food)
- NEVER expose that a tool returned empty results - just say you're finding more options
- Always maintain a helpful, conversational tone"""


class GrokClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        overpass_client: Any = None,
    ) -> None:
        self._base_url = base_url or llm_base_url()
        self.api_key = api_key or llm_api_key()
        self.model = model or llm_model()
        self.max_tokens = llm_max_tokens()
        self._registry = get_tool_registry()
        self._overpass_client = overpass_client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _chat_request(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        last_err: Exception | None = None
        last_body: str | None = None
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.post(
                    self._base_url,
                    headers=self._headers(),
                    json=payload,
                    timeout=60,
                )
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                last_err = e
                status = None
                if hasattr(e, "response") and e.response is not None:
                    status = getattr(e.response, "status_code", None)
                    try:
                        last_body = e.response.text
                    except Exception:
                        last_body = None
                else:
                    last_body = None
                
                logger.warning("LLM API attempt %d failed: %s", attempt + 1, e)
                
                if attempt < MAX_RETRIES - 1:
                    delay = 2 ** attempt  # Default exponential backoff
                    
                    # Handle rate limits (429) - extract wait time from response
                    if status == 429 and last_body:
                        wait_time = None
                        is_daily_limit = False
                        try:
                            # Try to parse JSON error response
                            error_data = json.loads(last_body)
                            error_msg = error_data.get("error", {}).get("message", "")
                            
                            # Check if it's a daily limit (TPD) - don't retry immediately
                            if "tokens per day" in error_msg.lower() or "TPD" in error_msg:
                                is_daily_limit = True
                                # Extract wait time (could be in minutes)
                                match = re.search(r"try again in ([\d.]+)s", error_msg, re.IGNORECASE)
                                if match:
                                    wait_seconds = float(match.group(1))
                                    wait_minutes = wait_seconds / 60
                                    logger.warning(
                                        "Daily rate limit reached. Need to wait %.1f minutes (%.0f seconds). "
                                        "Skipping retries.",
                                        wait_minutes, wait_seconds
                                    )
                                    # Don't retry for daily limits - user needs to wait
                                    break
                            
                            # For per-minute limits, extract wait time
                            if not is_daily_limit:
                                match = re.search(r"try again in ([\d.]+)s", error_msg, re.IGNORECASE)
                                if match:
                                    wait_time = float(match.group(1))
                                    # Add a small buffer (0.5s) to be safe
                                    wait_time = max(wait_time + 0.5, 1.0)
                                    logger.info("Rate limit detected. Waiting %.1f seconds...", wait_time)
                        except (json.JSONDecodeError, ValueError, AttributeError):
                            pass
                        
                        if is_daily_limit:
                            # Break out of retry loop for daily limits
                            break
                        elif wait_time:
                            delay = wait_time
                        else:
                            # If we can't parse wait time, use longer delay for 429
                            delay = max(5.0, delay * 2)
                    
                    if not is_daily_limit:
                        time.sleep(delay)
        status = None
        if hasattr(last_err, "response") and last_err.response is not None:
            status = getattr(last_err.response, "status_code", None)
        is_xai = XAI_URL in self._base_url or "api.x.ai" in self._base_url
        is_groq = "api.groq.com" in self._base_url
        
        # Handle xAI credits error
        if (
            is_xai
            and status == 403
            and last_body
            and ("credits" in last_body.lower() or "licenses" in last_body.lower())
        ):
            hint = (
                "Your xAI team has no credits or licenses. "
                "Add credits at https://console.x.ai → your team → Billing, then retry."
            )
            raise GrokCreditsError(hint, last_err) from last_err
        
        # Handle Groq rate limit with helpful message
        if is_groq and status == 429 and last_body:
            try:
                error_data = json.loads(last_body)
                error_msg = error_data.get("error", {}).get("message", "")
                error_type = error_data.get("error", {}).get("type", "")
                
                if "rate_limit" in error_msg.lower() or error_type == "tokens":
                    # Extract wait time if available
                    wait_time = None
                    wait_match = re.search(r"try again in ([\d.]+)s", error_msg, re.IGNORECASE)
                    if wait_match:
                        wait_seconds = float(wait_match.group(1))
                        wait_minutes = wait_seconds / 60
                        if wait_minutes >= 1:
                            wait_time = f"{int(wait_minutes)} minute{'s' if wait_minutes >= 2 else ''}"
                        else:
                            wait_time = f"{int(wait_seconds)} second{'s' if wait_seconds >= 2 else ''}"
                    
                    # Determine limit type
                    if "tokens per day" in error_msg.lower() or "TPD" in error_msg:
                        limit_type = "daily (100,000 tokens/day)"
                        hint = (
                            f"Groq daily rate limit reached (free tier: {limit_type}). "
                        )
                    elif "tokens per minute" in error_msg.lower() or "TPM" in error_msg:
                        limit_type = "per minute (12,000 tokens/minute)"
                        hint = (
                            f"Groq rate limit reached (free tier: {limit_type}). "
                        )
                    else:
                        hint = "Groq rate limit reached. "
                    
                    if wait_time:
                        hint += f"Please wait {wait_time} and try again. "
                    else:
                        hint += "Please wait a moment and try again. "
                    
                    hint += "Upgrade at https://console.groq.com/settings/billing for higher limits."
                    
                    raise RuntimeError(f"Rate limit: {hint}\n\nDetails: {error_msg}") from last_err
            except (json.JSONDecodeError, KeyError, AttributeError):
                pass
        
        # Handle Groq function calling errors (model generating wrong format)
        if is_groq and status == 400 and last_body:
            try:
                error_data = json.loads(last_body)
                error_code = error_data.get("error", {}).get("code", "")
                if error_code == "tool_use_failed":
                    failed_gen = error_data.get("error", {}).get("failed_generation", "")
                    hint = (
                        "The model generated an invalid function call format. "
                        "This is a known issue with some Groq models. "
                        "Try rephrasing your request or wait a moment and try again."
                    )
                    logger.warning("Groq tool_use_failed: %s", failed_gen[:200])
                    raise RuntimeError(f"Function call error: {hint}") from last_err
            except (json.JSONDecodeError, KeyError, AttributeError):
                pass
        
        msg = f"LLM API failed after {MAX_RETRIES} retries: {last_err}"
        if last_body:
            msg += f"\n\nAPI response body:\n{last_body}"
        raise RuntimeError(msg) from last_err

    def execute_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        fn = self._registry.get(tool_name)
        if not fn:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            if tool_name == "poi_search":
                city = arguments.get("city", "Udaipur")
                interests = arguments.get("interests") or []
                constraints = arguments.get("constraints") or {}
                return fn(city, interests, constraints, client=self._overpass_client)
            if tool_name == "itinerary_builder":
                pois = arguments.get("pois") or []
                duration_days = int(arguments.get("duration_days") or 2)
                pace = str(arguments.get("pace") or "moderate")
                daily_hours = int(arguments.get("daily_hours") or 8)
                return fn(pois, duration_days, pace, daily_hours)
            if tool_name == "travel_calculator":
                from_poi = arguments.get("from_poi") or {}
                to_poi = arguments.get("to_poi") or {}
                mode = str(arguments.get("mode") or "auto")
                return fn(from_poi, to_poi, mode)
            if tool_name == "travel_calculate":
                fl = float(arguments.get("from_lat", 0))
                flon = float(arguments.get("from_lon", 0))
                tl = float(arguments.get("to_lat", 0))
                tlon = float(arguments.get("to_lon", 0))
                mode = str(arguments.get("mode") or "auto")
                return fn(fl, flon, tl, tlon, mode)
            return {"error": f"Tool {tool_name} not mapped in execute_tool_call"}
        except Exception as e:
            logger.exception("Tool %s failed: %s", tool_name, e)
            return {"error": str(e)}

    @staticmethod
    def _merge_itinerary_sources(
        itinerary_result: dict[str, Any] | None,
        sources_pois: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge itinerary POIs into sources so 'Places referenced' shows itinerary order with correct links."""
        if not itinerary_result or not itinerary_result.get("days") or not sources_pois:
            return sources_pois
        from src.utils.link_generator import generate_poi_links
        sources_by_name = {(p.get("name") or "").strip().lower(): p for p in sources_pois}
        merged: list[dict[str, Any]] = []
        seen_lower: set[str] = set()
        for day in itinerary_result.get("days", []):
            for act in day.get("activities", []):
                poi = act.get("poi") or {}
                name = (poi.get("name") or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key in seen_lower:
                    continue
                seen_lower.add(key)
                if key in sources_by_name:
                    merged.append(sources_by_name[key])
                else:
                    poi_dict = {"name": name, "type": poi.get("type", ""), "lat": poi.get("lat"), "lon": poi.get("lon")}
                    links = generate_poi_links(poi_dict)
                    if links:
                        poi_dict["links"] = links
                    merged.append(poi_dict)
        for p in sources_pois:
            k = (p.get("name") or "").strip().lower()
            if k and k not in seen_lower:
                merged.append(p)
        return merged

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Send chat request to Grok. If response contains tool_calls, execute them,
        append results, and call again (loop up to MAX_TOOL_LOOPS). Return final
        assistant message or last tool-call request info.
        """
        if not tools:
            tools = get_tool_definitions()
        msgs = list(messages)
        if msgs and msgs[0].get("role") != "system":
            msgs.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        elif not msgs:
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}]

        itinerary_result = None  # Track itinerary_builder results
        sources_pois: list[dict[str, Any]] = []  # Track POIs from poi_search calls
        
        for _ in range(MAX_TOOL_LOOPS):
            out = self._chat_request(msgs, tools)
            choices = out.get("choices") or []
            if not choices:
                return {"message": {"role": "assistant", "content": "No response from Grok."}, "usage": out.get("usage", {}), "itinerary": itinerary_result, "sources": {"pois": sources_pois}}
            msg = choices[0].get("message") or {}
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                sources_pois = self._merge_itinerary_sources(itinerary_result, sources_pois)
                return {"message": msg, "usage": out.get("usage", {}), "itinerary": itinerary_result, "sources": {"pois": sources_pois}}

            msgs.append(msg)
            for tc in tool_calls:
                fid = tc.get("id") or ""
                fn_name = (tc.get("function") or {}).get("name") or ""
                args_str = (tc.get("function") or {}).get("arguments") or "{}"
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                result = self.execute_tool_call(fn_name, args)
                
                # Track itinerary_builder results
                if fn_name == "itinerary_builder" and isinstance(result, dict) and "days" in result:
                    itinerary_result = result
                
                # Track POIs from poi_search calls
                if fn_name == "poi_search":
                    try:
                        if isinstance(result, str):
                            result_data = json.loads(result)
                        else:
                            result_data = result
                        
                        # poi_search returns a list directly, or could be wrapped
                        pois = []
                        if isinstance(result_data, list):
                            pois = result_data
                        elif isinstance(result_data, dict) and "results" in result_data:
                            pois = result_data.get("results", [])
                        
                        # Add unique POIs (by name) to sources with links
                        existing_names = {p.get("name", "").lower() for p in sources_pois}
                        from src.utils.link_generator import generate_poi_links
                        for poi in pois:
                            if not isinstance(poi, dict):
                                continue
                            poi_name = (poi.get("name") or "").strip()
                            if poi_name and poi_name.lower() not in existing_names:
                                poi_dict = {
                                    "name": poi_name,
                                    "type": poi.get("type", ""),
                                    "lat": poi.get("lat"),
                                    "lon": poi.get("lon"),
                                }
                                # Generate links for this POI
                                links = generate_poi_links(poi_dict)
                                if links:
                                    poi_dict["links"] = links
                                sources_pois.append(poi_dict)
                                existing_names.add(poi_name.lower())
                    except (json.JSONDecodeError, TypeError, KeyError, AttributeError) as e:
                        logger.debug("Failed to track POI sources: %s", e)
                        pass  # Ignore parsing errors
                
                if not isinstance(result, str):
                    result = json.dumps(result, ensure_ascii=False)
                msgs.append({
                    "role": "tool",
                    "tool_call_id": fid,
                    "content": result,
                })

        sources_pois = self._merge_itinerary_sources(itinerary_result, sources_pois)
        return {"message": {"role": "assistant", "content": "Tool loop limit reached."}, "usage": {}, "itinerary": itinerary_result, "sources": {"pois": sources_pois}}
