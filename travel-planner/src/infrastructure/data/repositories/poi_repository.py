"""
POI repository: load static POIs from data/knowledge/pois.json and apply filters.

Moved from `src.data.repositories.poi_repository` to keep persistence and IO in
the infrastructure layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.config import project_root
from src.utils.logger import get_logger

logger = get_logger()


def _pois_path() -> Path:
    return project_root() / "data" / "knowledge" / "pois.json"


class POIRepository:
    """
    Load and filter static POIs from pois.json.
    Supports max_results, type, indoor_only, and similar constraints.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _pois_path()
        self._pois: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._pois is not None:
            return self._pois
        p = self._path
        if not p.is_file():
            logger.warning("POI file not found: %s", p)
            self._pois = []
            return self._pois
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._pois = data if isinstance(data, list) else []
            return self._pois
        except Exception as e:
            logger.exception("Failed to load POIs from %s: %s", p, e)
            self._pois = []
            return self._pois

    def get_pois(
        self,
        *,
        types: list[str] | None = None,
        indoor_only: bool = False,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Return POIs from static data, filtered by type, indoor, and limit.

        Args:
            types: Filter by POI type (e.g. heritage, food). None = all.
            indoor_only: If True, only return POIs with indoor=True.
            max_results: Maximum number of POIs to return.

        Returns:
            List of POI dicts (name, type, lat, lon, duration_hours, etc.).
        """
        raw = self._load()
        out: list[dict[str, Any]] = []
        type_filters = [(t or "").lower() for t in (types or [])]
        for poi in raw:
            if type_filters and (poi.get("type") or "").lower() not in type_filters:
                continue
            if indoor_only and not poi.get("indoor", False):
                continue
            out.append(poi)
            if len(out) >= max_results:
                break
        return out

