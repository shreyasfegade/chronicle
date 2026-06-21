"""SQLite storage layer.

Chronicle stores a single source of truth: the raw ``events`` table, one row per
poll. Sessions and focus metrics are derived from it on demand (see
:mod:`chronicle.sessions` and :mod:`chronicle.metrics`) rather than cached, which
keeps the schema small and removes any risk of stale aggregates.

The database runs in WAL mode so the background writer (the tracker thread) and
the dashboard readers (FastAPI request threads) never block each other. Each
thread gets its own connection via thread-local storage; writes are additionally
serialised through a process-wide lock because SQLite permits only one writer.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterable, Iterator

from .config import get_config

logger = logging.getLogger("chronicle.database")

_local = threading.local()
_write_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    """Open a tuned SQLite connection to the configured database file."""
    conn = sqlite3.connect(str(get_config().db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")  # ~8 MB page cache
    conn.execute("PRAGMA busy_timeout=5000")  # wait, don't fail, on contention
    return conn


def _get_connection() -> sqlite3.Connection:
    """Return this thread's connection, creating it on first use."""
    conn = getattr(_local, "connection", None)
    if conn is None:
        conn = _connect()
        _local.connection = conn
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """Yield this thread's connection, rolling back on error."""
    conn = _get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    """Create the schema if needed. Safe to call repeatedly."""
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                app_name      TEXT    NOT NULL,
                window_title  TEXT    NOT NULL,
                executable    TEXT    NOT NULL DEFAULT '',
                category      TEXT    NOT NULL DEFAULT 'Other',
                is_idle       INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_category  ON events(category);
            """
        )
        conn.commit()
    logger.debug("Database ready at %s", get_config().db_path)


def _day_bounds(target_date: date) -> tuple[str, str]:
    """Return half-open ``[start, end)`` timestamp strings for a calendar day."""
    return f"{target_date.isoformat()} 00:00:00", f"{target_date.isoformat()} 23:59:59"


# ── Writes ───────────────────────────────────────────────────────────────────

def insert_event(
    timestamp: str,
    app_name: str,
    window_title: str,
    executable: str,
    category: str,
    is_idle: bool,
) -> None:
    """Insert one raw tracking event. Thread-safe."""
    with _write_lock, get_db() as conn:
        conn.execute(
            """INSERT INTO events
                   (timestamp, app_name, window_title, executable, category, is_idle)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (timestamp, app_name, window_title, executable, category, int(is_idle)),
        )
        conn.commit()


def insert_events_batch(rows: Iterable[tuple[str, str, str, str, str, int]]) -> None:
    """Insert many events in a single transaction (used by the demo seeder)."""
    with _write_lock, get_db() as conn:
        conn.executemany(
            """INSERT INTO events
                   (timestamp, app_name, window_title, executable, category, is_idle)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()


# ── Reads ────────────────────────────────────────────────────────────────────

def get_events_for_date(target_date: date | None = None) -> list[dict[str, Any]]:
    """Return all events for a day (default: today), oldest first."""
    target_date = target_date or date.today()
    start, end = _day_bounds(target_date)
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM events
               WHERE timestamp >= ? AND timestamp < ?
               ORDER BY timestamp ASC""",
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]


def get_events_in_range(start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Return events for the inclusive date range ``[start_date, end_date]``."""
    start = f"{start_date.isoformat()} 00:00:00"
    end = f"{end_date.isoformat()} 23:59:59"
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM events
               WHERE timestamp >= ? AND timestamp <= ?
               ORDER BY timestamp ASC""",
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent events, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_summary(target_date: date | None = None) -> dict[str, Any]:
    """Return event counts and first/last activity timestamps for a day."""
    target_date = target_date or date.today()
    start, end = _day_bounds(target_date)
    with get_db() as conn:
        row = conn.execute(
            """SELECT
                   COUNT(*)                                   AS total_events,
                   SUM(CASE WHEN is_idle = 0 THEN 1 ELSE 0 END) AS active_events,
                   MIN(timestamp)                             AS first_event,
                   MAX(timestamp)                             AS last_event
               FROM events
               WHERE timestamp >= ? AND timestamp < ?""",
            (start, end),
        ).fetchone()
    return {
        "date": target_date.isoformat(),
        "total_events": row["total_events"] or 0,
        "active_events": row["active_events"] or 0,
        "first_event": row["first_event"],
        "last_event": row["last_event"],
    }


def get_available_dates(limit: int = 60) -> list[str]:
    """Return distinct dates that have tracking data, most recent first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT DATE(timestamp) AS day
               FROM events ORDER BY day DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [r["day"] for r in rows]
