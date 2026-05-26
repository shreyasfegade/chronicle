"""
Chronicle — SQLite Database Layer
Manages all persistent storage: raw events, stitched sessions, and hourly metrics.
Uses WAL mode for safe concurrent access from tracker + server threads.
"""

import sqlite3
import threading
import os
from datetime import datetime, date, timedelta
from contextlib import contextmanager

DB_NAME = "chronicle.db"

_local = threading.local()
_write_lock = threading.Lock()


def _get_db_path():
    """Get the database path in the same directory as this script."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)


def _get_connection():
    """Get a thread-local SQLite connection."""
    if not hasattr(_local, "connection") or _local.connection is None:
        _local.connection = sqlite3.connect(
            _get_db_path(),
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        _local.connection.row_factory = sqlite3.Row
        _local.connection.execute("PRAGMA journal_mode=WAL")
        _local.connection.execute("PRAGMA synchronous=NORMAL")
        _local.connection.execute("PRAGMA cache_size=-8000")  # 8MB cache
    return _local.connection


@contextmanager
def get_db():
    """Context manager for database access."""
    conn = _get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise


def init_db():
    """Initialize database schema. Safe to call multiple times."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                app_name TEXT NOT NULL,
                window_title TEXT NOT NULL,
                executable TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Other',
                is_idle INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                category TEXT NOT NULL,
                app_name TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                event_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);
            CREATE INDEX IF NOT EXISTS idx_sessions_category ON sessions(category);

            CREATE TABLE IF NOT EXISTS hourly_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                hour INTEGER NOT NULL,
                entropy REAL NOT NULL DEFAULT 0.0,
                total_events INTEGER NOT NULL DEFAULT 0,
                dominant_category TEXT NOT NULL DEFAULT 'Other',
                category_distribution TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                UNIQUE(date, hour)
            );

            CREATE INDEX IF NOT EXISTS idx_hourly_date ON hourly_metrics(date);
        """)
        conn.commit()


# ── Event Operations ──────────────────────────────────────────────────────────

def insert_event(timestamp, app_name, window_title, executable, category, is_idle):
    """Insert a raw tracking event. Thread-safe."""
    with _write_lock:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO events (timestamp, app_name, window_title, executable, category, is_idle)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (timestamp, app_name, window_title, executable, category, int(is_idle)),
            )
            conn.commit()


def get_events_for_date(target_date=None):
    """Get all events for a given date (default: today)."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM events
               WHERE timestamp >= ? AND timestamp < ?
               ORDER BY timestamp ASC""",
            (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
        ).fetchall()
    return [dict(r) for r in rows]


def get_events_for_hour(target_date, hour):
    """Get events for a specific hour on a date."""
    date_str = target_date.isoformat()
    start = f"{date_str} {hour:02d}:00:00"
    end = f"{date_str} {hour:02d}:59:59"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC",
            (start, end),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_events(limit=50):
    """Get the most recent events."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Session Operations ────────────────────────────────────────────────────────

def clear_sessions_for_date(target_date=None):
    """Clear sessions for recomputation."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    with _write_lock:
        with get_db() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE start_time >= ? AND start_time < ?",
                (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
            )
            conn.commit()


def insert_session(start_time, end_time, category, app_name, duration_seconds, event_count):
    """Insert a stitched session."""
    with _write_lock:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO sessions (start_time, end_time, category, app_name, duration_seconds, event_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (start_time, end_time, category, app_name, duration_seconds, event_count),
            )
            conn.commit()


def insert_sessions_batch(sessions_list):
    """Insert multiple sessions in a single transaction."""
    with _write_lock:
        with get_db() as conn:
            conn.executemany(
                """INSERT INTO sessions (start_time, end_time, category, app_name, duration_seconds, event_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (s["start_time"], s["end_time"], s["category"], s["app_name"],
                     s["duration_seconds"], s["event_count"])
                    for s in sessions_list
                ],
            )
            conn.commit()


def get_sessions_for_date(target_date=None):
    """Get all sessions for a given date."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM sessions
               WHERE start_time >= ? AND start_time < ?
               ORDER BY start_time ASC""",
            (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Hourly Metrics Operations ─────────────────────────────────────────────────

def upsert_hourly_metric(target_date, hour, entropy, total_events, dominant_category, category_distribution):
    """Insert or update hourly metrics."""
    date_str = target_date.isoformat() if isinstance(target_date, date) else target_date
    with _write_lock:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO hourly_metrics (date, hour, entropy, total_events, dominant_category, category_distribution)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(date, hour) DO UPDATE SET
                       entropy=excluded.entropy,
                       total_events=excluded.total_events,
                       dominant_category=excluded.dominant_category,
                       category_distribution=excluded.category_distribution""",
                (date_str, hour, entropy, total_events, dominant_category, category_distribution),
            )
            conn.commit()


def get_hourly_metrics_for_date(target_date=None):
    """Get all hourly metrics for a date."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM hourly_metrics WHERE date = ? ORDER BY hour ASC",
            (date_str,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Aggregate Queries ─────────────────────────────────────────────────────────

def get_category_summary_for_date(target_date=None):
    """Get total time per category for a date."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT category, COUNT(*) as event_count,
                      SUM(CASE WHEN is_idle = 0 THEN 1 ELSE 0 END) as active_count
               FROM events
               WHERE timestamp >= ? AND timestamp < ?
               GROUP BY category
               ORDER BY event_count DESC""",
            (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_summary(target_date=None):
    """Get a complete daily summary."""
    if target_date is None:
        target_date = date.today()
    date_str = target_date.isoformat()
    with get_db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as total FROM events WHERE timestamp >= ? AND timestamp < ?",
            (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
        ).fetchone()
        active = conn.execute(
            "SELECT COUNT(*) as active FROM events WHERE timestamp >= ? AND timestamp < ? AND is_idle = 0",
            (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
        ).fetchone()
        first = conn.execute(
            "SELECT MIN(timestamp) as first_event FROM events WHERE timestamp >= ? AND timestamp < ?",
            (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
        ).fetchone()
        last = conn.execute(
            "SELECT MAX(timestamp) as last_event FROM events WHERE timestamp >= ? AND timestamp < ?",
            (f"{date_str} 00:00:00", f"{date_str} 23:59:59"),
        ).fetchone()
    return {
        "date": date_str,
        "total_events": total["total"] if total else 0,
        "active_events": active["active"] if active else 0,
        "first_event": first["first_event"] if first else None,
        "last_event": last["last_event"] if last else None,
    }


def get_available_dates():
    """Get list of dates that have tracking data."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT DATE(timestamp) as track_date
               FROM events ORDER BY track_date DESC LIMIT 30"""
        ).fetchall()
    return [r["track_date"] for r in rows]
