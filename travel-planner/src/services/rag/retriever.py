"""
Context retrieval for RAG. Wraps UdaipurKnowledgeBase and maps user intent to query_type.

Moved from `src.rag.retriever` to keep intent mapping and retrieval orchestration
in the services layer.
"""

from __future__ import annotations

from src.infrastructure.rag.knowledge_base import UdaipurKnowledgeBase


def retrieve_context(query: str, kb: UdaipurKnowledgeBase | None = None) -> str:
    """
    Retrieve knowledge-base context for a user query.

    Maps high-level intent (overview, tips, attractions, etc.) to
    query_type and returns relevant text.

    Args:
        query: Raw user query or intent description.
        kb: Optional knowledge base. If None, a new one is created.

    Returns:
        Retrieved context string.
    """
    kb = kb or UdaipurKnowledgeBase()
    q = (query or "").strip().lower()
    if any(k in q for k in ("overview", "introduce", "about", "city")):
        return kb.get_context("overview")
    if any(k in q for k in ("when", "best time", "weather", "season")):
        return kb.get_context("weather")
    if any(k in q for k in ("get around", "transport", "auto", "bus")):
        return kb.get_context("getting_around")
    if any(k in q for k in ("attraction", "see", "visit", "place")):
        return kb.get_context("attractions")
    if any(k in q for k in ("neighborhood", "area", "where to stay")):
        return kb.get_context("neighborhoods")
    if any(k in q for k in ("tip", "etiquette", "food safety", "budget")):
        return kb.get_context("tips")
    return kb.get_context("overview")

