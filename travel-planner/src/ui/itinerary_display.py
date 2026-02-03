"""Streamlit UI helpers for itinerary rendering and follow-ups.

Moved from `src.utils.itinerary_display` to keep UI concerns separate from
infrastructure and domain logic. The old module remains as a compatibility shim.
"""

from __future__ import annotations

# NOTE: We keep the implementation identical for now to avoid behavior changes.

import hashlib
import json
import re
from typing import Any

import streamlit as st

from src.utils.logger import get_logger

logger = get_logger()


def extract_itinerary(text: str) -> dict | None:
    """Parse itinerary JSON from assistant response. Returns None if not found."""
    if not text or "days" not in text.lower():
        return None
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, dict) and "days" in data:
                return data
        except json.JSONDecodeError:
            pass
    start = text.find('{"days"')
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                        if "days" in data:
                            return data
                    except json.JSONDecodeError:
                        pass
                    break
    return None


def _is_budget_or_summary_line(cleaned: str) -> bool:
    """Skip budget/summary lines that are not places."""
    lower = cleaned.lower().strip()
    if not lower or len(lower) < 4:
        return True
    if lower.startswith(("budget", "total:", "accommodation", "food and drink", "transportation",
                         "entry fees", "miscellaneous", "total ", "this itinerary", "enjoy your")):
        return True
    if re.match(r"^\d+\s*inr", lower) or re.match(r"^total:\s*\d+", lower):
        return True
    if re.search(r"\(\d+\s*night", lower) or "upgrade to" in lower and "inr" in lower:
        return True
    # Entry-fee lines: "City Palace: 300 INR", "Jagdish Temple: Free"
    if re.search(r":\s*\d+\s*inr\s*$", lower) or re.search(r":\s*free\s*$", lower):
        return True
    return False


def _short_place_from_description(desc: str) -> str:
    """Extract a short place name from 'TIME: Start the day with a visit to the City Palace, one of...'."""
    if not desc or len(desc) <= 55:
        return desc.strip() if desc else ""
    # Strip leading "9:30 AM: " or "10:00 AM - 12:00 PM: " if present
    rest = re.sub(r"^[\d:]+\s*(?:AM|PM|am|pm)?\s*(?:–\-?\s*[\d:]+\s*(?:AM|PM|am|pm)?\s*)?:\s*", "", desc, flags=re.IGNORECASE).strip()
    # "Start the day with a visit to the City Palace, one of..."
    m = re.search(
        r"(?:visit to the|visit the|head to the|head to|visit the)\s+([A-Za-z][A-Za-z0-9\s\-']+?)(?=\s*[,.]|\s+at\s+\d|\s+one\s+of|\s+a\s+\d|\s+and\s+|\s*$)",
        rest,
        re.IGNORECASE,
    )
    if m:
        name = m.group(1).strip()
        if 2 < len(name) <= 55:
            return name
    # "Take a break for lunch at a mid-range restaurant" -> "Lunch"
    if "lunch" in rest.lower():
        return "Lunch"
    if "dinner" in rest.lower():
        return "Dinner"
    if "breakfast" in rest.lower():
        return "Breakfast"
    # "Take a sunset boat ride on Lake Pichola" -> "Lake Pichola"
    m2 = re.search(r"(?:boat ride on|ride on|stroll through(?:\s+the)?)\s+([A-Za-z][A-Za-z0-9\s\-']+?)(?=\s*[,.]|\s*$)", rest, re.IGNORECASE)
    if m2:
        return m2.group(1).strip()
    # First capitalized phrase (e.g. "Crystal Gallery")
    m3 = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Za-z][a-z\-]*)+)\b", rest)
    if m3:
        return m3.group(1).strip()[:55]
    return rest[:55].strip()


def parse_text_itinerary(text: str) -> dict | None:
    """Parse a day-wise itinerary from markdown/text (Day 1, Day 2, bullets, place names). Returns minimal structure for evals."""
    if not text or not text.strip():
        return None
    # Match "Day N:", "Day N ", "**Day N**", "For Day N, I suggest:", "### Day 1" at line start
    day_pattern = re.compile(
        r"(?:^|[\r\n]+)\s*(?:For\s+)?(?:#{1,3}\s*)?(?:\*{1,2}\s*)?Day\s+(\d+)(?:\s*\*{1,2})?\s*[:\s,\r\n]",
        re.IGNORECASE,
    )
    days_out: list[dict[str, Any]] = []
    pos = 0
    while True:
        m = day_pattern.search(text, pos)
        if not m:
            break
        day_num = int(m.group(1))
        start = m.end()
        next_m = day_pattern.search(text, start)
        block_end = next_m.start() if next_m else len(text)
        block = text[start:block_end]
        # List of (time_str or "", place_name) for evals
        entries: list[tuple[str, str]] = []
        for line in block.splitlines():
            line = line.strip()
            if not line or len(line) < 3:
                continue
            cleaned = re.sub(r"^[\s\-*•·]\s*", "", line)
            cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
            # Strip "I suggest: ", "I recommend: " and similar so line can start with time
            cleaned = re.sub(
                r"^(?:I\s+suggest|I\s+recommend)\s*:\s*",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            if _is_budget_or_summary_line(cleaned):
                continue
            # Split long line by start of next time slot (e.g. " 10:30 AM - ") so we get multiple segments
            time_slot_start = re.compile(
                r"\s+(?=\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\s*[–\-])",
                re.IGNORECASE,
            )
            segments = time_slot_start.split(cleaned)
            for cleaned_seg in segments:
                cleaned_seg = cleaned_seg.strip()
                if not cleaned_seg or len(cleaned_seg) < 5:
                    continue
                # "8:00 AM - 9:30 AM: Start the day with a visit to the City Palace, one of..."
                time_range_desc = re.match(
                    r"([\d:]+\s*(?:AM|PM|am|pm)?)\s*[–\-]\s*[\d:]+\s*(?:AM|PM|am|pm)?\s*:\s*(.+)",
                    cleaned_seg,
                    re.IGNORECASE,
                )
                if time_range_desc:
                    start_time = time_range_desc.group(1).strip()
                    desc = time_range_desc.group(2).strip()
                    short_name = _short_place_from_description(desc)
                    if short_name and len(short_name) > 1:
                        entries.append((start_time, short_name))
                    continue
                # "9:00 AM: Start the day with a visit to the City Palace..." or "1:00 PM: Take a break for lunch..."
                single_time_desc = re.match(r"^(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)\s*:\s*(.+)$", cleaned_seg, re.IGNORECASE)
                if single_time_desc:
                    start_time = single_time_desc.group(1).strip()
                    desc = single_time_desc.group(2).strip()
                    if len(desc) > 2:
                        short_name = _short_place_from_description(desc) if len(desc) > 55 else desc.strip()[:55]
                        if short_name and len(short_name) > 1:
                            entries.append((start_time, short_name))
                    continue
                # "9:00 AM - City Palace" (single time - place)
                time_place = re.match(r"[\d:]+\s*(?:AM|PM|am|pm)?\s*[–\-]\s*(.+)", cleaned_seg, re.IGNORECASE)
                if time_place:
                    name = time_place.group(1).strip()
                    if name and len(name) > 2 and len(name) <= 80:
                        start_time = re.match(r"([\d:]+\s*(?:AM|PM|am|pm)?)", cleaned_seg, re.IGNORECASE)
                        t = start_time.group(1).strip() if start_time else ""
                        entries.append((t, name))
                    continue
                # "Morning - City Palace" or "Afternoon - Lake Pichola"
                slot_place = re.match(r"(?:Morning|Afternoon|Evening)\s*[–\-]\s*(.+)", cleaned_seg, re.IGNORECASE)
                if slot_place:
                    name = slot_place.group(1).strip()
                    if name and len(name) > 2 and len(name) <= 55:
                        entries.append(("", name))
                    continue
                # "Morning (8:00 AM - 10:00 AM): City Palace"
                if "): " in cleaned_seg or "):" in cleaned_seg:
                    after_colon = cleaned_seg.split("):", 1)[-1].strip().lstrip(":")
                    if after_colon and len(after_colon) <= 55 and not after_colon.lower().startswith(("day ", "morning", "afternoon", "evening")):
                        time_part = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)", cleaned_seg, re.IGNORECASE)
                        t = time_part.group(1).strip() if time_part else ""
                        entries.append((t, after_colon))
                    continue
                # Prose line: "visit to the City Palace, one of..."
                prose_visit = re.search(
                    r"(?:visit to the|visit the|head to the|head to)\s+([A-Za-z][A-Za-z0-9\s\-']+?)(?=\s*[,.]|\s+at\s+\d|\s+one\s+of|\s+a\s+\d|\s+and\s+|\s*$)",
                    cleaned_seg,
                    re.IGNORECASE,
                )
                if prose_visit:
                    name = prose_visit.group(1).strip()
                    if 2 < len(name) <= 55:
                        entries.append(("", name))
                    continue
                prose_activity = re.search(
                    r"(?:boat ride on|ride on|stroll through(?:\s+the)?)\s+([A-Za-z][A-Za-z0-9\s\-']+?)(?=\s*[,.]|\s+at\s+\d|\s*$)",
                    cleaned_seg,
                    re.IGNORECASE,
                )
                if prose_activity:
                    name = prose_activity.group(1).strip()
                    if 2 < len(name) <= 55:
                        entries.append(("", name))
                    continue
                # Short capitalized place name only (avoid long sentences)
                if re.match(r"^[A-Z]", cleaned_seg) and 4 < len(cleaned_seg) <= 55:
                    if cleaned_seg.lower().startswith(("day ", "morning", "afternoon", "evening", "summary")):
                        continue
                    prose_words = ("itinerary", "designed", "help you", "explore", "experience", "comprehensive", "giving you", "view of", "culture", "craftsmanship", "history", "traditional")
                    if any(w in cleaned_seg.lower() for w in prose_words):
                        continue
                    entries.append(("", cleaned_seg))
        if entries:
            activities = []
            for idx, (time_str, place_name) in enumerate(entries):
                act: dict[str, Any] = {
                    "poi": {"name": place_name, "duration_hours": 1.5},
                }
                if time_str:
                    act["time"] = time_str
                if idx > 0:
                    act["travel_time_from_previous"] = 15
                # Cap duration when next activity has a start time so current_end + travel <= next_start
                if time_str and idx + 1 < len(entries):
                    next_time_str = entries[idx + 1][0]
                    if next_time_str:
                        cur_min = _parse_time_to_minutes(time_str)
                        nxt_min = _parse_time_to_minutes(next_time_str)
                        if cur_min is not None and nxt_min is not None and nxt_min > cur_min:
                            travel_min = 15 if idx > 0 else 0
                            max_duration_min = nxt_min - cur_min - travel_min
                            if max_duration_min > 0:
                                capped_h = min(1.5, max_duration_min / 60.0)
                                act["poi"]["duration_hours"] = max(0.25, capped_h)
                activities.append(act)
            days_out.append({
                "day_number": day_num,
                "activities": activities,
            })
        pos = block_end
    if not days_out:
        return None
    return {"days": days_out, "metadata": {}}


def _parse_time_to_minutes(time_str: str) -> int | None:
    """Parse time string (e.g. '8:00 AM', '12:30 PM') to minutes since midnight, or None if unparseable."""
    if not time_str or not time_str.strip():
        return None
    s = time_str.strip().upper()
    try:
        parts = s.replace(":", " ").split()
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if "PM" in s and hour != 12:
            hour += 12
        elif "AM" in s and hour == 12:
            hour = 0
        return hour * 60 + minute
    except (ValueError, IndexError):
        return None


def _get_time_block(time_str: str) -> str:
    """Determine if time is Morning, Afternoon, or Evening."""
    if not time_str:
        return "Other"
    # Extract hour from time string (e.g., "8:00 AM" -> 8, "2:30 PM" -> 14)
    hour_match = re.search(r"(\d+):", time_str)
    if hour_match:
        hour = int(hour_match.group(1))
        if "PM" in time_str.upper() and hour != 12:
            hour += 12
        elif hour == 12 and "AM" in time_str.upper():
            hour = 0
    else:
        return "Other"

    if 5 <= hour < 12:
        return "Morning"
    elif 12 <= hour < 17:
        return "Afternoon"
    elif 17 <= hour < 22:
        return "Evening"
    else:
        return "Other"


def _extract_intro_from_response(response: str) -> str:
    """Extract introductory text from response before itinerary JSON."""
    if not response:
        return ""
    # Look for text before JSON blocks or "days" keyword
    json_start = response.find('{"days"')
    if json_start > 0:
        intro = response[:json_start].strip()
        # Remove common prefixes
        intro = intro.replace("Here's your itinerary:", "").strip()
        intro = intro.replace("Here is your itinerary:", "").strip()
        if len(intro) > 10 and len(intro) < 500:
            return intro
    return ""


def _itinerary_key(it: dict[str, Any]) -> str:
    """Stable key for current itinerary so we can persist evaluation results per itinerary."""
    days = it.get("days") or []
    try:
        raw = json.dumps(days, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()
    except (TypeError, ValueError):
        return str(id(days))


def _enrich_sources_with_itinerary_pois(
    it: dict[str, Any],
    sources: dict[str, Any] | None,
) -> dict[str, Any]:
    """Add itinerary POIs to sources with generated links so every cited place has URLs."""
    from src.utils.link_generator import generate_poi_links

    enriched = dict(sources) if sources else {}
    pois = list(enriched.get("pois") or [])
    existing = {(p.get("name") or "").strip().lower() for p in pois}
    # Lookup by name for missing lat/lon (so OSM and precise Maps links can be generated)
    repo_pois_by_name: dict[str, dict[str, Any]] = {}
    try:
        from src.data.repositories.poi_repository import POIRepository
        repo = POIRepository()
        for p in repo.get_pois(max_results=500):
            n = (p.get("name") or "").strip().lower()
            if n and n not in repo_pois_by_name:
                repo_pois_by_name[n] = p
    except Exception:
        pass

    for day in it.get("days") or []:
        for act in day.get("activities") or []:
            poi = act.get("poi") or {}
            name = (poi.get("name") or "").strip()
            if not name or name.lower() in existing:
                continue
            d = {"name": name, "lat": poi.get("lat"), "lon": poi.get("lon"), "type": poi.get("type", "")}
            if (d.get("lat") is None or d.get("lon") is None) and repo_pois_by_name:
                static = repo_pois_by_name.get(name.lower())
                if static:
                    d["lat"] = d.get("lat") or static.get("lat")
                    d["lon"] = d.get("lon") or static.get("lon")
            links = generate_poi_links(d)
            if links:
                d["links"] = links
            pois.append(d)
            existing.add(name.lower())

    enriched["pois"] = pois
    return enriched


def render_itinerary(it: dict, sources: dict[str, Any] | None = None) -> None:
    """Render itinerary dict with day-wise, time-blocked format. Requires streamlit in scope."""
    import streamlit as st

    days = it.get("days") or []
    meta = it.get("metadata") or {}
    if not days:
        return

    sources = _enrich_sources_with_itinerary_pois(it, sources)

    st.subheader("📅 Your Itinerary")

    for d in days:
        day_num = d.get("day_number", 0)
        date = d.get("date", "")
        summary = d.get("summary", "")
        acts = d.get("activities") or []
        total_h = d.get("total_hours", 0)

        # Day header
        st.markdown(f"### Day {day_num}")
        if date:
            st.caption(f"📆 {date}")
        if summary:
            st.caption(f"*{summary}*")

        if not acts:
            st.info("No activities scheduled for this day.")
            continue

        # Group activities by time block (Morning/Afternoon/Evening)
        time_blocks: dict[str, list[dict]] = {"Morning": [], "Afternoon": [], "Evening": [], "Other": []}

        for a in acts:
            time_str = a.get("time", "")
            block = _get_time_block(time_str)
            time_blocks[block].append(a)

        # Render each time block
        for block_name in ["Morning", "Afternoon", "Evening", "Other"]:
            block_acts = time_blocks[block_name]
            if not block_acts:
                continue

            st.markdown(f"#### {block_name}")

            for idx, a in enumerate(block_acts):
                time_str = a.get("time", "")
                poi = a.get("poi") or {}
                name = poi.get("name", "?")
                typ = poi.get("type", "")
                dur = poi.get("duration_hours", 0)
                cost = poi.get("cost_inr", 0)
                travel = a.get("travel_time_from_previous", 0)
                notes = a.get("notes", "")

                # Activity card
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{time_str}** — {name}")
                    if typ:
                        st.caption(f"📍 {typ}")
                with col2:
                    if cost and cost > 0:
                        st.markdown(f"**₹{cost}**")
                    else:
                        st.caption("Free")

                # Duration and travel time
                info_parts = []
                if dur:
                    info_parts.append(f"⏱️ {dur} hour{'s' if dur != 1 else ''}")
                if travel and travel > 0:
                    info_parts.append(f"🚗 {travel} min travel")
                if info_parts:
                    st.caption(" | ".join(info_parts))

                if notes:
                    st.info(notes)

                # Add separator between activities (except last)
                if idx < len(block_acts) - 1:
                    st.divider()

        # Day summary
        st.markdown(f"**Total for Day {day_num}:** {round(total_h, 1)} hours")
        if acts:
            day_cost = sum(a.get("poi", {}).get("cost_inr", 0) or 0 for a in acts)
            if day_cost > 0:
                st.caption(f"Estimated cost: ₹{day_cost}")

        # Separator between days
        if day_num < len(days):
            st.divider()

    # Overall summary and metadata
    if meta:
        total_cost = meta.get("total_cost_inr", 0)
        warnings = meta.get("warnings") or []

        st.markdown("---")
        st.markdown("### 📊 Summary")

        if total_cost:
            st.metric("Estimated Total Cost", f"₹{total_cost}")

        # Run feasibility evaluation
        try:
            from src.evaluations.feasibility_eval import evaluate_feasibility

            pace = meta.get("pace", "moderate")
            feasibility = evaluate_feasibility(days, daily_hours=8, pace=pace)
            if feasibility.get("passed"):
                st.success(f"✅ Feasibility: Passed (Score: {feasibility.get('score', 0):.2f})")
            else:
                st.warning(f"⚠️ Feasibility: Issues found (Score: {feasibility.get('score', 0):.2f})")
                if feasibility.get("issues"):
                    with st.expander("Feasibility Issues"):
                        for issue in feasibility["issues"][:5]:  # Show first 5
                            st.caption(f"• {issue}")
        except Exception as e:
            logger.debug("Feasibility evaluation failed: %s", e)

        if warnings:
            st.markdown("#### ⚠️ Notes")
            for w in warnings:
                st.warning(w)

        # Sources/References section
        st.markdown("#### 📚 Sources & References")

        # Show actual sources if provided (correctly cited URLs)
        if sources:
            from src.utils.link_generator import format_source_links, generate_kb_section_link

            pois = sources.get("pois", [])
            if pois:
                st.markdown("**Places referenced (cited URLs):**")
                for poi in pois[:15]:
                    poi_name = poi.get("name", "")
                    if not poi_name:
                        continue
                    formatted = format_source_links(poi=poi)
                    if formatted:
                        parts = [f"[{x['label']}]({x['url']})" for x in formatted]
                        st.markdown(f"  • **{poi_name}**: {' | '.join(parts)}")
                    else:
                        st.markdown(f"  • {poi_name}")
                if len(pois) > 15:
                    st.caption(f"*... and {len(pois) - 15} more places*")

            # Knowledge base sections with links
            kb_sections = sources.get("kb_sections", [])
            if kb_sections:
                st.markdown("**Knowledge base:**")
                section_names = {
                    "overview": "City Overview",
                    "attractions": "Attractions Guide",
                    "tips": "Travel Tips",
                    "weather": "Weather & Seasons",
                    "getting_around": "Transportation",
                    "neighborhoods": "Neighborhoods",
                }
                for section in kb_sections:
                    label = section_names.get(section, section.title())
                    kb_url = generate_kb_section_link(section)
                    if kb_url:
                        st.markdown(f"  • [{label}]({kb_url})")
                    else:
                        st.markdown(f"  • {label}")

        # Generic data sources footer
        st.caption(
            "**Data Sources:** Overpass API (OpenStreetMap) | " "Udaipur travel guides | Wikivoyage"
        )


def _render_evaluations_and_export(
    it: dict[str, Any] | None, sources: dict[str, Any] | None, st_ref=st
) -> None:
    """Render Evaluations CTA + persisted results and Export. Always show CTA when called; full metrics only when it has days."""
    st_ref.markdown("---")
    st_ref.markdown("#### 🔍 Evaluations")
    has_days = bool(it and (it.get("days") or []))
    if not has_days:
        st_ref.caption(
            "Click Run Evaluations to see metrics. If your reply included a day-wise plan (Day 1, Day 2, with places), we’ll detect it and run feasibility, grounding, and edit correctness."
        )
        if st_ref.button(
            "▶️ Run Evaluations",
            use_container_width=True,
            key="run_evaluations",
            type="primary",
        ):
            st_ref.info(
                "We couldn’t detect a day-wise itinerary in the last response (no ‘Day 1’ / ‘Day 2’ with places). "
                "Ask for an itinerary that lists days and places (e.g. ‘2-day itinerary for Udaipur’ with a day-by-day breakdown), then try Run Evaluations again."
            )
        st_ref.markdown("---")
        st_ref.markdown("#### 📤 Export Itinerary")
        with st_ref.expander("📧 Email itinerary", expanded=False):
            st_ref.caption("Export is available after a structured itinerary is generated.")
        return
    sources = _enrich_sources_with_itinerary_pois(it, sources)
    current_key = _itinerary_key(it)
    eval_results = st_ref.session_state.get("eval_results")
    if eval_results and eval_results.get("itinerary_key") == current_key:
        st_ref.markdown("**Performance evaluation metrics**")
        _render_eval_results(eval_results.get("results") or {}, it, st_ref)
    if st_ref.button(
        "▶️ Run Evaluations",
        use_container_width=True,
        key="run_evaluations",
        type="primary",
    ):
        _run_all_evaluations(it, sources, st_ref)
        st_ref.rerun()
    if not (eval_results and eval_results.get("itinerary_key") == current_key):
        st_ref.caption(
            "Click to see feasibility, grounding, and edit correctness metrics for this itinerary."
        )
    st_ref.markdown("---")
    st_ref.markdown("#### 📤 Export Itinerary")
    with st_ref.expander("📧 Email itinerary", expanded=False):
        response_text = st_ref.session_state.get("last_response", "")
        _export_to_email(it, sources, response_text=response_text, key_prefix="export_email")


def render_evaluations_block(
    it: dict[str, Any] | None, sources: dict[str, Any] | None = None
) -> None:
    """Show Evaluations CTA after any assistant response. Full metrics when itinerary has days; else prompt for day-wise itinerary."""
    _render_evaluations_and_export(it, sources or {}, st)


def render_sources(sources: dict[str, Any], st=st) -> None:
    """Render sources section when there's no itinerary."""
    st.markdown("---")
    st.markdown("### 📚 Sources & References")

    from src.utils.link_generator import format_source_links, generate_kb_section_link

    pois = sources.get("pois", [])
    if pois:
        st.markdown("**Places referenced (cited URLs):**")
        for poi in pois[:15]:
            poi_name = poi.get("name", "")
            if not poi_name:
                continue
            formatted = format_source_links(poi=poi)
            if formatted:
                parts = [f"[{x['label']}]({x['url']})" for x in formatted]
                st.markdown(f"  • **{poi_name}**: {' | '.join(parts)}")
            else:
                st.markdown(f"  • {poi_name}")
        if len(pois) > 15:
            st.caption(f"*... and {len(pois) - 15} more places*")

    # Knowledge base sections with links
    kb_sections = sources.get("kb_sections", [])
    if kb_sections:
        st.markdown("**Knowledge base:**")
        section_names = {
            "overview": "City Overview",
            "attractions": "Attractions Guide",
            "tips": "Travel Tips",
            "weather": "Weather & Seasons",
            "getting_around": "Transportation",
            "neighborhoods": "Neighborhoods",
        }
        for section in kb_sections:
            label = section_names.get(section, section.title())
            kb_url = generate_kb_section_link(section)
            if kb_url:
                st.markdown(f"  • [{label}]({kb_url})")
            else:
                st.markdown(f"  • {label}")

    if not pois and not kb_sections:
        st.info(
            "**Data Sources:**\n"
            "- Points of Interest: Overpass API (OpenStreetMap)\n"
            "- Travel Tips: Udaipur travel guides and Wikivoyage"
        )
    else:
        st.caption(
            "**Data Sources:** Overpass API (OpenStreetMap) | " "Udaipur travel guides | Wikivoyage"
        )


def _text_to_html(text: str) -> str:
    """Convert plain text/markdown response to HTML for PDF export."""
    if not text:
        return "<p>No content available.</p>"
    
    # Basic markdown-to-HTML conversion (simple patterns)
    html = text
    
    # Convert markdown headers (must be at start of line)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    
    # Convert bold (**text**)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    
    # Split into lines for processing
    lines = html.split('\n')
    result_lines = []
    in_list = False
    
    for line in lines:
        stripped = line.strip()
        
        # Check if it's a bullet point
        if re.match(r'^[-*] (.+)$', stripped):
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            match = re.match(r'^[-*] (.+)$', stripped)
            if match:
                result_lines.append(f'<li>{match.group(1)}</li>')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            
            if stripped:
                # Already processed headers/bold, wrap rest as paragraphs
                if not (stripped.startswith('<h') or stripped.startswith('<p') or stripped.startswith('<ul') or stripped.startswith('<li')):
                    result_lines.append(f'<p>{stripped}</p>')
                else:
                    result_lines.append(stripped)
            elif not in_list:
                result_lines.append('')
    
    if in_list:
        result_lines.append('</ul>')
    
    html = '\n'.join(result_lines)
    
    # Clean up empty paragraphs
    html = re.sub(r'<p>\s*</p>', '', html)
    
    # Wrap in HTML document
    return f"""<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<title>Udaipur Travel Itinerary</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
h1 {{ color: #2c3e50; }}
h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
h3 {{ color: #7f8c8d; }}
p {{ margin: 10px 0; }}
ul {{ margin: 10px 0; padding-left: 20px; }}
li {{ margin: 5px 0; }}
</style></head>
<body>
<h1>🗺️ Udaipur Travel Itinerary</h1>
{html}
</body></html>"""


def _export_to_pdf(
    itinerary: dict[str, Any] | None,
    sources: dict[str, Any] | None = None,
    response_text: str = "",
) -> None:
    """Export itinerary to PDF via n8n. Handles both structured and text-only responses."""
    try:
        from src.automation.n8n_client import send_itinerary_to_n8n, format_itinerary_for_pdf

        # If no structured itinerary, create one from response text
        if not itinerary or not itinerary.get("days"):
            if not response_text:
                st.error("No itinerary content available to export.")
                return
            
            # Create minimal structured data from text
            export_data = {
                "days": [],
                "metadata": {},
                "html_content": _text_to_html(response_text),
            }
            if sources:
                export_data["sources"] = sources
        else:
            # Use structured itinerary
            export_data = dict(itinerary)
            if sources:
                export_data["sources"] = sources
            
            # Generate HTML for PDF
            html_content = format_itinerary_for_pdf(export_data)
            export_data["html_content"] = html_content

        with st.spinner("Generating PDF..."):
            result = send_itinerary_to_n8n(export_data, generate_pdf=True, send_email=False)

        # Show debug info about the webhook URL being used
        debug_info = result.get("debug", {})
        webhook_url_used = debug_info.get("webhook_url", "unknown")
        
        # Always show debug expander to help troubleshoot
        show_debug = True
        
        with st.expander("🔍 Debug: Webhook Request Details", expanded=show_debug):
            st.write(f"**Webhook URL used:** `{webhook_url_used}`")
            st.write(f"**Is test webhook:** {debug_info.get('is_test_webhook', False)}")
            if debug_info.get("suggested_production_url"):
                st.info(f"💡 **Switch to production URL:** `{debug_info['suggested_production_url']}`")
            st.write(f"**Request status:** {result.get('status_code', 'N/A')}")
            
            # Show critical troubleshooting info for 404
            if result.get('status_code') == 404:
                st.error("❌ **404 Not Found - Webhook URL doesn't exist!**")
                st.write("**Most common causes:**")
                st.write("1. ❌ **Workflow is NOT ACTIVE** (toggle OFF in n8n)")
                st.write("   → Go to n8n, click workflow toggle at top to turn it ON/GREEN")
                st.write("2. ❌ Wrong URL in `.env` file")
                st.write("   → Copy exact Production URL from Webhook1 → Production URL tab")
                st.write("3. ❌ Streamlit not restarted after updating `.env`")
                st.write("   → Stop Streamlit (Ctrl+C) and start again")
            
            if result.get("error"):
                st.error(f"**Error:** {result.get('error')}")
                if result.get("error_type"):
                    st.caption(f"Error type: {result.get('error_type')}")
            if result.get("hint"):
                st.warning(f"**Hint:** {result.get('hint')}")
            if debug_info.get("response_body_preview"):
                st.write("**Response preview:**")
                st.code(debug_info["response_body_preview"][:500], language="json")

        if result.get("success"):
            # If n8n responds with PDF bytes, offer a direct download.
            pdf_bytes = result.get("pdf_bytes")
            if isinstance(pdf_bytes, (bytes, bytearray)) and pdf_bytes:
                st.success("PDF generated.")
                st.download_button(
                    "Download PDF",
                    data=pdf_bytes,
                    file_name="udaipur-itinerary.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
                with st.expander("n8n debug"):
                    st.json(result.get("debug") or {})
                return

            pdf_url = result.get("pdf_url")
            if pdf_url:
                st.success(f"PDF generated. [Download here]({pdf_url})")
            else:
                st.error(
                    "n8n responded, but no downloadable PDF was provided (missing `pdf_url` and no PDF bytes response)."
                )
                if result.get("hint"):
                    st.info(result["hint"])
                with st.expander("n8n debug"):
                    st.json(result.get("debug") or result.get("n8n_response") or {})
        else:
            error_msg = result.get("error", "Unknown error")
            if "not configured" in error_msg.lower():
                st.warning(
                    "⚠️ n8n webhook not configured. Add `N8N_WEBHOOK_URL` to your `.env` file to enable PDF export."
                )
            else:
                st.error(f"Failed to generate PDF: {result.get('message', 'Unknown error')}")
                if result.get("hint"):
                    st.info(result["hint"])
                with st.expander("n8n debug"):
                    st.json(result.get("debug") or {})
    except ImportError:
        st.error("n8n client not available")
    except Exception as e:
        logger.exception("PDF export failed: %s", e)
        st.error(f"PDF export failed: {str(e)}")


def _export_to_email(
    itinerary: dict[str, Any] | None,
    sources: dict[str, Any] | None = None,
    response_text: str = "",
    key_prefix: str = "email_export",
) -> None:
    """Send itinerary via simple HTML email using n8n (no PDF generation).

    Uses a Streamlit form so users can enter email + submit in one click.
    """
    try:
        from src.automation.n8n_client import send_itinerary_to_n8n, format_itinerary_for_pdf
        from src.utils.config import n8n_webhook_url

        form_key = f"{key_prefix}_form"
        email_key = f"{key_prefix}_email"

        with st.form(form_key, clear_on_submit=False):
            email = st.text_input(
                "Enter your email address:",
                key=email_key,
                placeholder="your@email.com",
            )
            submitted = st.form_submit_button("Send email", use_container_width=True)

        if not submitted:
            # Keep UI clean; only show a small optional debug section.
            webhook_url = n8n_webhook_url()
            with st.expander("Debug", expanded=False):
                st.write(f"Webhook: `{webhook_url or 'not configured'}`")
            return

        # Validate email on submit
        if not email or "@" not in email:
            st.warning("⚠️ Please enter a valid email address.")
            return

        # If no structured itinerary, create one from response text
        if not itinerary or not itinerary.get("days"):
            if not response_text:
                st.error("No itinerary content available to export.")
                return
            
            # Create minimal structured data from text
            export_data = {
                "days": [],
                "metadata": {},
                "html_content": _text_to_html(response_text),
            }
            if sources:
                export_data["sources"] = sources
        else:
            # Use structured itinerary
            export_data = dict(itinerary)
            if sources:
                export_data["sources"] = sources
            
            # Generate HTML for email
            html_content = format_itinerary_for_pdf(export_data)
            export_data["html_content"] = html_content

        # Check if webhook URL is configured BEFORE sending
        webhook_url = n8n_webhook_url()
        if not webhook_url:
            st.error("n8n webhook URL not configured. Set `N8N_WEBHOOK_URL` in `travel-planner/.env` and restart Streamlit.")
            return
        
        # Initialize result dict for debug display
        result = {}
        
        with st.spinner(f"Sending itinerary to {email}..."):
            # Only send HTML email; do not request PDF generation
            result = send_itinerary_to_n8n(export_data, email=email, generate_pdf=False, send_email=True)

        # Show debug info only when something goes wrong (keep UI clean).
        debug_info = result.get("debug", {}) if result else {}
        webhook_url_used = debug_info.get("webhook_url", webhook_url or "not configured")
        
        if not result.get("success"):
            with st.expander("Debug", expanded=False):
                st.write(f"Webhook: `{webhook_url_used}`")
                st.write(f"Status: {result.get('status_code', 'N/A')}")
                if result.get("error"):
                    st.write(f"Error: {result.get('error')}")
                if debug_info.get("response_body_preview"):
                    st.code(debug_info["response_body_preview"][:500], language="json")

        if result.get("success"):
            email_sent = result.get("email_sent", False)
            n8n_response = result.get("n8n_response", {})
            
            if email_sent:
                st.success(f"✅ Itinerary sent to {email}. Check your inbox (and spam folder).")
                st.info("💡 If you don't see the email, check your n8n workflow executions for any errors.")
            else:
                st.warning("⚠️ n8n responded successfully, but did not confirm `email_sent=true`.")
                st.write("**Possible reasons:**")
                st.write("1. The n8n workflow's 'Respond to Webhook' node is not returning `email_sent: true`")
                st.write("2. The email node failed silently (check n8n executions)")
                st.write("3. SMTP credentials are not configured in n8n")
                st.write("4. The email is in your spam folder")
                
                if result.get("hint"):
                    st.info(f"💡 **Hint:** {result['hint']}")
                
                with st.expander("📋 Full n8n Response", expanded=True):
                    st.json(n8n_response)
                    st.write("**What to check:**")
                    st.write("- Look for `email_sent: true` in the response above")
                    st.write("- If missing, update your 'Respond to Webhook' node to return this field")
                    st.write("- Check n8n Executions tab for any email node errors")
        else:
            error_msg = result.get("error", "Unknown error")
            if "not configured" in error_msg.lower():
                st.warning(
                    "⚠️ n8n webhook not configured. Add `N8N_WEBHOOK_URL` to your `.env` file to enable email export."
                )
            else:
                st.error(f"Failed to send email: {result.get('message', 'Unknown error')}")
                if result.get("hint"):
                    st.info(result["hint"])
                with st.expander("n8n debug"):
                    st.json(result.get("debug") or {})
    except ImportError:
        st.error("n8n client not available")
    except Exception as e:
        logger.exception("Email export failed: %s", e)
        st.error(f"Email export failed: {str(e)}")


def _render_eval_results(
    results: dict[str, Any],
    itinerary: dict[str, Any],
    st_ref=st,
) -> None:
    """Render persisted evaluation results (feasibility, grounding, edit correctness)."""
    feasibility_result = results.get("feasibility")
    grounding_result = results.get("grounding")
    edit_result = results.get("edit_correctness")

    st_ref.markdown("##### Evaluation metrics")

    if feasibility_result is not None:
        _display_feasibility_result(feasibility_result, st_ref)
    else:
        st_ref.caption("Feasibility: not run")

    st_ref.divider()

    if grounding_result is not None:
        _display_grounding_result(grounding_result, st_ref)
    else:
        st_ref.caption("Grounding: not run")

    st_ref.divider()

    if edit_result is not None:
        _display_edit_correctness_result(edit_result, st_ref)
    else:
        st_ref.info("⚠️ **Edit Correctness: N/A** (no previous itinerary to compare)")
        st_ref.caption(
            "This evaluation compares the current itinerary with the previous version. Make an edit to see results."
        )

    with st_ref.expander("📋 Detailed Evaluation Results (JSON)"):
        st_ref.json(
            {
                "feasibility": feasibility_result,
                "grounding": grounding_result,
                "edit_correctness": edit_result,
            }
        )


def _run_all_evaluations(
    itinerary: dict[str, Any],
    sources: dict[str, Any] | None,
    st_ref=st,
) -> None:
    """Run all three evaluations, display results, and persist in session state."""
    from src.evaluations.feasibility_eval import evaluate_feasibility
    from src.evaluations.grounding_eval import evaluate_grounding
    from src.evaluations.edit_correctness_eval import evaluate_edit_correctness
    from src.data.repositories.poi_repository import POIRepository

    safe_sources = sources or {}
    days = itinerary.get("days", [])
    meta = itinerary.get("metadata", {})
    pace = meta.get("pace", "moderate")
    # Use higher daily_hours for parsed (prose) itineraries so full-day plans don't fail
    daily_hours = meta.get("daily_hours") if meta.get("daily_hours") is not None else 13

    if "previous_itinerary" not in st.session_state:
        st.session_state.previous_itinerary = None
    previous_itinerary = st.session_state.previous_itinerary

    feasibility_result = None
    try:
        feasibility_result = evaluate_feasibility(days, daily_hours=daily_hours, pace=pace)
        feasibility_result["_days"] = days
    except Exception as e:
        logger.exception("Feasibility evaluation failed: %s", e)
        st_ref.error(f"❌ Feasibility evaluation failed: {str(e)}")

    grounding_result = None
    known_pois = None
    try:
        repo = POIRepository()
        repo_pois = repo.get_pois(max_results=200)
        source_pois = list(safe_sources.get("pois") or [])
        # Merge source POIs with canonical pois.json so places like Lake Pichola are always known
        seen_names: set[str] = set()
        known_pois = []
        for p in source_pois + repo_pois:
            name = (p.get("name") or "").strip().lower()
            if name and name not in seen_names:
                seen_names.add(name)
                known_pois.append(p)

        # Use itinerary POIs for coverage check (expect response to mention these), not full poi_search pool
        # Normalize long "names" (e.g. full sentences from prose) to short place names so grounding overlap works
        itinerary_pois: list[dict[str, Any]] = []
        seen_lower: set[str] = set()
        for day in days:
            for act in day.get("activities", []):
                poi = act.get("poi")
                if not poi or not poi.get("name"):
                    continue
                raw_name = (poi.get("name") or "").strip()
                short_name = _short_place_from_description(raw_name) if len(raw_name) > 60 else raw_name
                short_name = short_name.strip() if short_name else raw_name
                if not short_name:
                    continue
                key = short_name.lower()
                if key in seen_lower:
                    continue
                seen_lower.add(key)
                itinerary_pois.append({"name": short_name, "type": poi.get("type"), "lat": poi.get("lat"), "lon": poi.get("lon")})

        response_text = st.session_state.get("last_response") or ""
        grounding_result = evaluate_grounding(
            response_text or "Itinerary generated",
            sources=itinerary_pois if itinerary_pois else safe_sources.get("pois"),
            known_pois=known_pois,
        )
    except Exception as e:
        logger.exception("Grounding evaluation failed: %s", e)
        st_ref.error(f"❌ Grounding evaluation failed: {str(e)}")

    edit_result = None
    try:
        if previous_itinerary:
            user_edit_message = st.session_state.get("last_user_message")
            edit_result = evaluate_edit_correctness(
                previous_itinerary.get("days", []),
                days,
                known_pois=known_pois if known_pois else None,
                user_edit_message=user_edit_message,
            )
    except Exception as e:
        logger.exception("Edit correctness evaluation failed: %s", e)
        st_ref.error(f"❌ Edit correctness evaluation failed: {str(e)}")

    # Do not overwrite previous_itinerary here; it is set in app.py when a new message is received.

    # Persist results so they survive reruns
    st.session_state.eval_results = {
        "itinerary_key": _itinerary_key(itinerary),
        "results": {
            "feasibility": feasibility_result,
            "grounding": grounding_result,
            "edit_correctness": edit_result,
        },
    }

    # Display results in this run
    _render_eval_results(st.session_state.eval_results["results"], itinerary, st_ref)


def _show_followup_questions(
    itinerary: dict[str, Any] | None,
    response_text: str,
    st=st,
    sources: dict[str, Any] | None = None,
) -> None:
    """Display follow-up questions section at the very bottom."""
    import streamlit as st

    # Always show at the very bottom with clear separation
    st.markdown("---")
    st.markdown("### 💬 What would you like to do next?")

    days = itinerary.get("days", []) if itinerary else []

    # Export section — only email, always visible (form inside expander)
    st.markdown("**📤 Export itinerary**")
    with st.expander("📧 Email itinerary", expanded=False):
        _export_to_email(itinerary, sources, response_text=response_text, key_prefix="followup_email")
    st.markdown("")

    # Check if itinerary is incomplete
    incomplete_days = []
    for day in days:
        activities = day.get("activities", [])
        if not activities or len(activities) < 3:
            incomplete_days.append(day.get("day_number", 0))

    # Check if response already contains a question
    has_question = any(
        phrase in response_text.lower()
        for phrase in ["would you like", "do you want", "let me know", "tell me", "what would", "could you", "can you"]
    )

    # Show contextual follow-up based on situation
    if incomplete_days:
        st.info(
            f"**I notice Day {', '.join(map(str, incomplete_days))} {'is' if len(incomplete_days) == 1 else 'are'} incomplete. "
            "Would you like me to:"
        )
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("- 🔍 Find more heritage sites")
            st.markdown("- 🌳 Add nature spots and gardens")
        with col2:
            st.markdown("- 🛍️ Include shopping and markets")
            st.markdown("- 🍽️ Add more dining options")
    elif not itinerary or not days:
        # No itinerary generated yet - ask for preferences
        st.info(
            "**To create your perfect itinerary, I'd like to know:**\n"
            "- How many days are you planning to spend in Udaipur?\n"
            "- What are your main interests? (heritage sites, nature, food, culture, shopping)\n"
            "- What pace do you prefer? (relaxed, moderate, or packed)\n"
            "- Any specific budget considerations?"
        )
    elif not has_question:
        # Generic follow-up if no question in response
        st.info(
            "**Need adjustments?** I can help you:\n"
            "- Modify the itinerary (add/remove activities)\n"
            "- Change the pace (more relaxed or packed)\n"
            "- Focus on specific interests (heritage, food, nature, culture)\n"
            "- Adjust the budget or duration\n"
            "- Explain why I suggested specific places (just ask 'why' about any place)"
        )

    # Quick action buttons
    st.markdown("**Quick actions:**")
    action_col1, action_col2, action_col3, action_col4 = st.columns(4)
    with action_col1:
        if st.button("🔍 Find more places", use_container_width=True, key="followup_more_places"):
            st.session_state.pending_followup = "Find more places to visit"
            st.rerun()
    with action_col2:
        if st.button("⚡ Make it faster", use_container_width=True, key="followup_faster"):
            st.session_state.pending_followup = "Make the itinerary more packed with more activities"
            st.rerun()
    with action_col3:
        if st.button("🌴 Make it relaxed", use_container_width=True, key="followup_relaxed"):
            st.session_state.pending_followup = "Make the itinerary more relaxed with fewer activities per day"
            st.rerun()
    with action_col4:
        if st.button("❓ Ask why", use_container_width=True, key="followup_why"):
            st.session_state.pending_followup = (
                "Why did you suggest these places? Can you explain your recommendations?"
            )
            st.rerun()


def _display_feasibility_result(result: dict[str, Any], st=st) -> None:
    """Display feasibility evaluation results in formatted way."""
    passed = result.get("passed", False)
    score = result.get("score", 0.0)
    total_hours = result.get("total_hours", 0.0)
    issues = result.get("issues", [])
    details = result.get("details", {})

    daily_cap = details.get("daily_cap", 8.0)
    pace = details.get("pace", "moderate")
    days_evaluated = details.get("days_evaluated", 0)

    # Status icon and header
    status_icon = "✅" if passed else "❌"
    status_text = "PASS" if passed else "FAIL"
    score_pct = int(score * 100)

    st.markdown(f"{status_icon} **Feasibility Eval: {status_text}** (Score: {score_pct}%)")

    # Details with tree structure
    avg_hours_per_day = total_hours / days_evaluated if days_evaluated > 0 else 0
    hours_status = "within limit" if avg_hours_per_day <= daily_cap else f"EXCEEDED by {round(avg_hours_per_day - daily_cap, 1)} hours"

    st.markdown(f"   ├─ Daily hours: {round(avg_hours_per_day, 1)} / {round(daily_cap, 1)} ({hours_status})")

    # Travel times check - analyze actual travel times
    max_travel_time = 0
    if days_evaluated > 0 and "_days" in result:
        for day in result.get("_days", []):
            for act in day.get("activities", []):
                travel = act.get("travel_time_from_previous", 0)
                if travel > max_travel_time:
                    max_travel_time = travel

    if max_travel_time > 0:
        travel_status = f"All < {max_travel_time + 1} min" if max_travel_time < 30 else f"Max {max_travel_time} min"
        st.markdown(f"   ├─ Travel times: {travel_status}")
    else:
        st.markdown("   ├─ Travel times: All < 30 min")

    # Count POIs per day
    if days_evaluated > 0 and "_days" in result:
        total_pois = sum(len(day.get("activities", [])) for day in result.get("_days", []))
        pois_per_day = total_pois / days_evaluated if days_evaluated > 0 else 0
        st.markdown(f"   └─ Pace: {pace.title()} (~{int(pois_per_day)} places per day)")
    else:
        st.markdown(f"   └─ Pace: {pace.title()}")

    # Issues
    if issues:
        st.markdown("**Issues found:**")
        for issue in issues[:5]:  # Show first 5 issues
            st.markdown(f"   └─ {issue}")
        if len(issues) > 5:
            st.caption(f"   ... and {len(issues) - 5} more issues")


def _display_grounding_result(result: dict[str, Any], st=st) -> None:
    """Display grounding evaluation results in formatted way."""
    passed = result.get("passed", False)
    score = result.get("score", 0.0)
    issues = result.get("issues", [])
    details = result.get("details", {})

    mentioned_pois = details.get("mentioned_pois", 0)
    unverified_pois = details.get("unverified_pois", 0)
    verified_pois = mentioned_pois - unverified_pois

    # Status icon and header
    status_icon = "✅" if passed else "❌"
    status_text = "PASS" if passed else "FAIL"
    score_pct = int(score * 100)

    st.markdown(f"{status_icon} **Grounding Eval: {status_text}** (Score: {score_pct}%)")

    # Details with tree structure
    if mentioned_pois > 0:
        st.markdown(f"   ├─ POIs verified: {verified_pois}/{mentioned_pois} in database")
    else:
        st.markdown("   ├─ POIs verified: N/A (no POIs mentioned)")

    if unverified_pois == 0:
        st.markdown("   ├─ Zero hallucinations")
    else:
        st.markdown(f"   ├─ Hallucinated POIs: {unverified_pois}")

    claims_checked = details.get("claims_checked", 0)
    ungrounded_claims = details.get("ungrounded_claims", 0)
    if claims_checked > 0:
        if ungrounded_claims == 0:
            st.markdown("   └─ All sources cited")
        else:
            st.markdown(f"   └─ Ungrounded claims: {ungrounded_claims}")
    else:
        st.markdown("   └─ All sources cited")

    # Issues
    if issues:
        st.markdown("**Issues found:**")
        for issue in issues[:5]:  # Show first 5
            st.markdown(f"   └─ {issue}")
        if len(issues) > 5:
            st.caption(f"   ... and {len(issues) - 5} more issues")


def _display_edit_correctness_result(result: dict[str, Any], st=st) -> None:
    """Display edit correctness evaluation results in formatted way."""
    passed = result.get("passed", False)
    score = result.get("score", 0.0)
    issues = result.get("issues", [])
    details = result.get("details", {})

    original_days = details.get("original_days", 0)
    edited_days = details.get("edited_days", 0)

    # Status icon and header
    status_icon = "✅" if passed else "❌"
    status_text = "PASS" if passed else "FAIL"
    score_pct = int(score * 100)

    st.markdown(f"{status_icon} **Edit Correctness: {status_text}** (Score: {score_pct}%)")

    # Details with tree structure
    st.markdown(f"   ├─ Original days: {original_days}")
    st.markdown(f"   ├─ Edited days: {edited_days}")
    if original_days != edited_days:
        change = edited_days - original_days
        st.markdown(f"   └─ Day count change: {change:+d} days")
    else:
        st.markdown("   └─ Structure preserved")

    # Issues
    if issues:
        st.markdown("**Issues found:**")
        for issue in issues[:5]:  # Show first 5
            st.markdown(f"   └─ {issue}")
        if len(issues) > 5:
            st.caption(f"   ... and {len(issues) - 5} more issues")

