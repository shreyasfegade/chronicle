"""
Chronicle — Session Stitcher
Merges raw tracking events into coherent focus sessions.
Adjacent events with the same category within a gap threshold form a single session.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger("chronicle.sessions")

DEFAULT_GAP_THRESHOLD = 60  # seconds — max gap between events in same session
DEFAULT_MIN_DURATION = 10   # seconds — minimum session duration to keep
POLL_INTERVAL = 3           # seconds — tracker polling interval


def stitch_sessions(events, gap_threshold=DEFAULT_GAP_THRESHOLD, min_duration=DEFAULT_MIN_DURATION):
    """
    Turn a list of raw events into coherent focus sessions.

    A session is a contiguous period where the user stayed in the same category.
    Events are merged if:
      - They share the same category
      - The gap between consecutive events is <= gap_threshold

    Args:
        events: List of event dicts with 'timestamp', 'category', 'app_name', 'is_idle'
        gap_threshold: Max seconds between events to merge into same session
        min_duration: Minimum session duration in seconds

    Returns:
        List of session dicts with start_time, end_time, category, app_name, duration_seconds, event_count
    """
    if not events:
        return []

    sessions = []
    current_session = None

    for event in events:
        try:
            ts = _parse_timestamp(event["timestamp"])
        except (ValueError, KeyError):
            continue

        category = event.get("category", "Other")
        app_name = event.get("app_name", "")
        is_idle = event.get("is_idle", False)

        if current_session is None:
            # Start first session
            current_session = _new_session(ts, category, app_name)
            continue

        time_gap = (ts - current_session["_last_ts"]).total_seconds()

        if category == current_session["category"] and time_gap <= gap_threshold:
            # Extend current session
            current_session["_last_ts"] = ts
            current_session["end_time"] = ts
            current_session["event_count"] += 1
            # Track the most frequent app in the session
            current_session["_app_counts"][app_name] = \
                current_session["_app_counts"].get(app_name, 0) + 1
        else:
            # Finalize current session and start a new one
            _finalize_session(current_session, sessions, min_duration)
            current_session = _new_session(ts, category, app_name)

    # Don't forget the last session
    if current_session:
        _finalize_session(current_session, sessions, min_duration)

    return sessions


def _new_session(timestamp, category, app_name):
    """Create a new session dict."""
    return {
        "start_time": timestamp,
        "end_time": timestamp,
        "category": category,
        "event_count": 1,
        "_last_ts": timestamp,
        "_app_counts": {app_name: 1},
    }


def _finalize_session(session, sessions_list, min_duration):
    """Finalize a session: compute duration, pick dominant app, add to list."""
    duration = (session["end_time"] - session["start_time"]).total_seconds()
    # Add poll interval to account for the last event's duration
    duration += POLL_INTERVAL

    if duration < min_duration:
        return  # Too short, discard

    # Pick the most used app in the session
    dominant_app = max(session["_app_counts"], key=session["_app_counts"].get)

    sessions_list.append({
        "start_time": session["start_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": session["end_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "category": session["category"],
        "app_name": dominant_app,
        "duration_seconds": round(duration, 1),
        "event_count": session["event_count"],
    })


def _parse_timestamp(ts):
    """Parse a timestamp string to datetime."""
    if isinstance(ts, datetime):
        return ts
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


def format_duration(seconds):
    """Format seconds into a human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def compute_and_store_sessions(target_date=None):
    """
    Recompute all sessions for a date and store them in the database.
    Called periodically by the server or tracker.
    """
    from database import get_events_for_date, clear_sessions_for_date, insert_sessions_batch

    events = get_events_for_date(target_date)
    if not events:
        return []

    sessions = stitch_sessions(events)

    # Clear existing sessions for the date and insert new ones
    clear_sessions_for_date(target_date)
    if sessions:
        insert_sessions_batch(sessions)

    logger.info(f"Stitched {len(events)} events into {len(sessions)} sessions")
    return sessions
