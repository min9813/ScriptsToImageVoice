from __future__ import annotations

import logging
import os
from typing import Optional


_CONFIGURED = False


def setup_logging(level: Optional[str] = None) -> None:
    """Configure root logging once with a consistent, readable format.

    Args:
        level: Optional log level name (e.g., "INFO", "DEBUG"). If omitted,
               reads LOG_LEVEL env or defaults to INFO.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level_name = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger with global config ensured."""
    setup_logging()
    return logging.getLogger(name)

