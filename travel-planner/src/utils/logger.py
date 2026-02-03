"""Logging setup for the travel planner."""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "travel_planner",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """
    Configure and return a logger.

    Args:
        name: Logger name.
        level: Logging level.
        log_file: Optional path to log file. If None, logs to stderr only.

    Returns:
        Configured logger.
    """
    log = logging.getLogger(name)
    if log.handlers:
        return log

    log.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(fmt)
    log.addHandler(h)

    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)

    return log


def get_logger(name: str = "travel_planner") -> logging.Logger:
    """Return the application logger. Use after setup_logger has been called."""
    return logging.getLogger(name)
