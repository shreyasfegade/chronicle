"""Session stitching — turn raw polls into coherent focus blocks.

A *session* is a contiguous stretch where the user stayed in one category.
Consecutive events are merged when they share a category and the gap between
them is within :attr:`Config.session_gap_threshold`; the resulting block is kept
only if it lasts at least :attr:`Config.session_min_duration`. This collapses the
thousands of three-second polls in a day into the handful of meaningful work
blocks a person would actually recognise.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .config import get_config

logger = logging.getLogger("chronicle.sessions")

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_ts(value: Any) -> datetime:
    """Parse a stored timestamp string (or pass through a ``datetime``)."""
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, _TS_FORMAT)


def stitch_sessions(
    events: list[dict[str, Any]],
    gap_threshold: float | None = None,
    min_duration: float | None = None,
) -> list[dict[str, Any]]:
    """Merge raw events into focus sessions.

    Args:
        events: Event dicts with ``timestamp``, ``category`` and ``app_name``,
            ordered oldest-first.
        gap_threshold: Override for the merge gap (seconds). Defaults to config.
        min_duration: Override for the minimum kept duration. Defaults to config.

    Returns:
        Session dicts with ``start_time``, ``end_time``, ``category``,
        ``app_name``, ``duration_seconds`` and ``event_count``.
    """
    config = get_config()
    gap_threshold = config.session_gap_threshold if gap_threshold is None else gap_threshold
    min_duration = config.session_min_duration if min_duration is None else min_duration
    poll_interval = config.poll_interval

    if not events:
        return []

    sessions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for event in events:
        try:
            ts = _parse_ts(event["timestamp"])
        except (ValueError, KeyError):
            continue

        category = event.get("category", "Other")
        app_name = event.get("app_name", "")

        if current is None:
            current = _new_session(ts, category, app_name)
            continue

        gap = (ts - current["_last_ts"]).total_seconds()
        if category == current["category"] and gap <= gap_threshold:
            current["_last_ts"] = ts
            current["end_time"] = ts
            current["event_count"] += 1
            current["_apps"][app_name] = current["_apps"].get(app_name, 0) + 1
        else:
            _finalize(current, sessions, min_duration, poll_interval)
            current = _new_session(ts, category, app_name)

    if current is not None:
        _finalize(current, sessions, min_duration, poll_interval)

    return sessions


def _new_session(ts: datetime, category: str, app_name: str) -> dict[str, Any]:
    return {
        "start_time": ts,
        "end_time": ts,
        "category": category,
        "event_count": 1,
        "_last_ts": ts,
        "_apps": {app_name: 1},
    }


def _finalize(
    session: dict[str, Any],
    out: list[dict[str, Any]],
    min_duration: float,
    poll_interval: float,
) -> None:
    """Compute duration, pick the dominant app, and keep the session if long enough."""
    # Add one poll interval so a session's duration reflects its final event.
    duration = (session["end_time"] - session["start_time"]).total_seconds() + poll_interval
    if duration < min_duration:
        return

    dominant_app = max(session["_apps"], key=session["_apps"].get)
    out.append(
        {
            "start_time": session["start_time"].strftime(_TS_FORMAT),
            "end_time": session["end_time"].strftime(_TS_FORMAT),
            "category": session["category"],
            "app_name": dominant_app,
            "duration_seconds": round(duration, 1),
            "event_count": session["event_count"],
        }
    )


def format_duration(seconds: float) -> str:
    """Format a duration as a compact human string (``"1h 5m"``, ``"40s"``)."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes, secs = divmod(seconds, 60)
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"
