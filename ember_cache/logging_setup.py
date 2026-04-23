"""Logging configuration for the Ember Cache server."""

from __future__ import annotations

import logging
import os
import sys


def configure(level: str | None = None) -> None:
    """Configure root logging once, using LOG_LEVEL env var by default."""
    resolved = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=resolved,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
