"""Logging configuration.

Logs go to the console for interactive runs and to a rotating ``chronicle.log``
file beside the database so a tray-only session still leaves a trail. The noisy
uvicorn access log is quietened to keep the console readable.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import PROJECT_ROOT, get_config

_CONSOLE_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s"
_FILE_FORMAT = "%(asctime)s | %(name)-22s | %(levelname)-7s | %(message)s"


def configure_logging() -> None:
    """Install console and rotating-file handlers on the root logger."""
    level = getattr(logging, get_config().log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers if called more than once.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt="%H:%M:%S"))
    root.addHandler(console)

    try:
        file_handler = RotatingFileHandler(
            PROJECT_ROOT / "chronicle.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
        root.addHandler(file_handler)
    except OSError as exc:  # pragma: no cover - non-fatal
        root.warning("File logging disabled: %s", exc)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
