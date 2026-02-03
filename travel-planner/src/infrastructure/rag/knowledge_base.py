"""
File-based knowledge base. Loads text files from data/knowledge/ and retrieves by keyword.

Moved from `src.rag.knowledge_base` to keep file IO and knowledge loading in the
infrastructure layer.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.utils.config import project_root
from src.utils.logger import get_logger

logger = get_logger()

DEFAULT_KNOWLEDGE_DIR = "data/knowledge"
TEXT_EXTENSIONS = (".txt",)


def _knowledge_dir() -> Path:
    return project_root() / "data" / "knowledge"


class UdaipurKnowledgeBase:
    """
    Load text files from data/knowledge/ and provide keyword-based context retrieval.
    No vector DB; simple keyword matching.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or _knowledge_dir()
        self._files: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._base.is_dir():
            logger.warning("Knowledge dir not found: %s", self._base)
            return
        for p in self._base.iterdir():
            if p.suffix.lower() in TEXT_EXTENSIONS and p.is_file():
                try:
                    text = p.read_text(encoding="utf-8")
                    self._files[p.stem] = text
                except Exception as e:
                    logger.warning("Failed to load %s: %s", p, e)
        logger.info("Loaded %d knowledge files", len(self._files))

    def get_context(self, query_type: str) -> str:
        """
        Return relevant text sections for a query type.

        Uses simple keyword matching. query_type can be e.g.:
        - "overview", "getting_around", "attractions", "neighborhoods"
        - "tips", "weather", "food", "etiquette", "transport", "budget"

        Returns:
            Concatenated relevant sections from loaded files.
        """
        q = (query_type or "").strip().lower()
        snippets: list[str] = []
        for _, text in self._files.items():
            # Split by ## Header or ##Header
            sections = re.split(r"\n##?\s+", text)
            for sec in sections:
                sec_lower = sec.lower()
                if not sec.strip():
                    continue
                if _matches_query(sec_lower, q):
                    snippets.append(sec.strip())
        if not snippets:
            # Fallback: return first 2000 chars from first file
            for _, text in self._files.items():
                if len(text) > 2000:
                    snippets.append(text[:2000] + "\n[...]")
                else:
                    snippets.append(text)
                break
        return "\n\n---\n\n".join(snippets) if snippets else ""


def _matches_query(text: str, query: str) -> bool:
    """True if text appears relevant to query via keyword overlap."""
    if not query:
        return True
    keywords = set(re.findall(r"\w+", query))
    text_words = set(re.findall(r"\w+", text))
    overlap = keywords & text_words
    return len(overlap) >= 1 or query in text

