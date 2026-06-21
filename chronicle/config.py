"""Central configuration for Chronicle.

All tunable behaviour lives here rather than being scattered as magic numbers
across modules. Defaults are sensible for a single-user desktop; they can be
overridden, in increasing order of precedence, by:

    1. The dataclass defaults below.
    2. A ``config.json`` file in the project root (see ``config.example.json``).
    3. ``CHRONICLE_*`` environment variables (e.g. ``CHRONICLE_PORT=8000``).

The loaded configuration is process-wide and resolved once via :func:`get_config`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger("chronicle.config")

# Project root: the directory that contains this package.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
CONFIG_FILENAME = "config.json"


@dataclass
class Config:
    """Runtime configuration for the tracker, server, and analytics.

    Attributes:
        host: Address the dashboard server binds to. Keep it loopback-only
            unless you explicitly want the dashboard reachable from the network.
        port: TCP port for the dashboard server.
        open_browser: Whether to open the dashboard automatically on startup.
        poll_interval: Seconds between foreground-window polls. Each stored event
            represents roughly this much wall-clock time, so it is also the unit
            used to convert event counts into durations.
        idle_threshold: Seconds without keyboard/mouse input before the current
            time is classified as ``Idle``.
        session_gap_threshold: Maximum gap (seconds) between consecutive events
            of the same category that will still be merged into one session.
        session_min_duration: Sessions shorter than this (seconds) are discarded
            as noise rather than shown as focus blocks.
        database_path: Absolute path to the SQLite database. Empty means
            ``<project_root>/chronicle.db``.
        log_level: Root logging level name (e.g. ``"INFO"``, ``"DEBUG"``).
        custom_rules: Optional user classification overrides, merged on top of
            the built-in rules. See :mod:`chronicle.classifier`.
    """

    host: str = "127.0.0.1"
    port: int = 7745
    open_browser: bool = True

    poll_interval: float = 3.0
    idle_threshold: float = 120.0

    session_gap_threshold: float = 60.0
    session_min_duration: float = 30.0

    database_path: str = ""
    log_level: str = "INFO"

    custom_rules: dict[str, Any] = field(default_factory=dict)

    # ── Derived helpers ──────────────────────────────────────────────────────

    @property
    def db_path(self) -> Path:
        """Resolved database path, defaulting to ``<project_root>/chronicle.db``."""
        if self.database_path:
            return Path(self.database_path).expanduser().resolve()
        return PROJECT_ROOT / "chronicle.db"

    @property
    def dashboard_url(self) -> str:
        """Convenience URL for the local dashboard."""
        host = "localhost" if self.host in ("127.0.0.1", "0.0.0.0") else self.host
        return f"http://{host}:{self.port}"


def _coerce(name: str, raw: Any, default: Any) -> Any:
    """Coerce a raw (env/file) value to the type of the matching default."""
    if isinstance(default, bool):
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(raw)
    if isinstance(default, int) and not isinstance(default, bool):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


def _load_file(path: Path) -> dict[str, Any]:
    """Load a JSON config file, tolerating absence and malformed content."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("Ignoring %s: expected a JSON object.", path.name)
            return {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read %s (%s); using defaults.", path.name, exc)
        return {}


def load_config(config_path: Path | None = None) -> Config:
    """Build a :class:`Config` from defaults, an optional JSON file, and env vars.

    Args:
        config_path: Explicit path to a config file. Defaults to
            ``<project_root>/config.json`` when omitted.

    Returns:
        A fully resolved configuration object.
    """
    path = config_path or (PROJECT_ROOT / CONFIG_FILENAME)
    file_values = _load_file(path)

    valid = {f.name for f in fields(Config)}
    kwargs: dict[str, Any] = {}
    defaults = {f.name: getattr(Config, f.name, None) for f in fields(Config)}

    for key, value in file_values.items():
        if key.startswith("_"):
            continue  # underscore keys are comments (e.g. "_comment")
        if key not in valid:
            logger.warning("Unknown config key %r ignored.", key)
            continue
        if key == "custom_rules":
            kwargs[key] = value
        else:
            kwargs[key] = _coerce(key, value, defaults[key])

    # Environment overrides take final precedence.
    for f in fields(Config):
        if f.name == "custom_rules":
            continue
        env_key = f"CHRONICLE_{f.name.upper()}"
        if env_key in os.environ:
            kwargs[f.name] = _coerce(f.name, os.environ[env_key], defaults[f.name])

    config = Config(**kwargs)
    if file_values:
        logger.info("Loaded configuration overrides from %s", path.name)
    return config


_config: Config | None = None


def get_config() -> Config:
    """Return the process-wide configuration, loading it on first use."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Replace the process-wide configuration (primarily for tests/tools)."""
    global _config
    _config = config
