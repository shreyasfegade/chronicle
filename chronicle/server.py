"""FastAPI application — serves the dashboard and a small JSON API.

Everything is derived from the raw ``events`` table at request time. A single
day is cheap to recompute (a day of polling is only a few thousand rows), so the
server keeps no caches and there are no stale aggregates to invalidate.

Endpoints:
    GET /                       The dashboard (static HTML).
    GET /api/day/{date}         Consolidated day payload (the dashboard's main call).
    GET /api/heatmap            Per-day Focus Score summary over a window of days.
    GET /api/live               Current tracking status and recent events.
    GET /api/categories         Category metadata.
    GET /api/dates              Dates that have data.
    GET /api/export/{date}      Download a day as JSON or CSV.
    GET /api/health             Liveness probe.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .classifier import get_all_categories, get_category_info
from .config import get_config
from .database import (
    get_available_dates,
    get_daily_summary,
    get_events_for_date,
    get_hourly_category_counts,
    get_recent_events,
)
from .metrics import (
    compute_daily_focus_score,
    compute_hourly_entropy,
    compute_productivity_stats,
    daily_summaries_from_counts,
)
from .sessions import format_duration, stitch_sessions

logger = logging.getLogger("chronicle.server")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_TS_FORMAT = "%Y-%m-%d %H:%M:%S"

app = FastAPI(title="Chronicle", version=__version__, docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _parse_date(value: str) -> date | None:
    """Parse ``YYYY-MM-DD`` into a ``date``, or ``None`` if invalid."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _build_timeline(events: list[dict[str, Any]], hourly: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Bucket events by minute for the Focus Stream ribbon.

    Each bucket carries its dominant category (and colour), the share of the
    minute that was active (drives the ribbon's thickness) and the entropy of the
    surrounding hour (drives its turbulence).
    """
    buckets: dict[int, dict[str, Any]] = {}
    for event in events:
        try:
            ts = datetime.strptime(event["timestamp"], _TS_FORMAT)
        except (ValueError, KeyError):
            continue
        minute = ts.hour * 60 + ts.minute
        bucket = buckets.setdefault(
            minute, {"hour": ts.hour, "categories": {}, "apps": {}, "total": 0, "idle": 0}
        )
        category = event.get("category", "Other")
        bucket["categories"][category] = bucket["categories"].get(category, 0) + 1
        bucket["total"] += 1
        if event.get("is_idle"):
            bucket["idle"] += 1
        app_name = event.get("app_name")
        if app_name:
            bucket["apps"][app_name] = bucket["apps"].get(app_name, 0) + 1

    timeline: list[dict[str, Any]] = []
    for minute, bucket in sorted(buckets.items()):
        dominant = max(bucket["categories"], key=bucket["categories"].get)
        dominant_app = max(bucket["apps"], key=bucket["apps"].get) if bucket["apps"] else ""
        active_ratio = 1.0 - (bucket["idle"] / bucket["total"]) if bucket["total"] else 0.0
        timeline.append(
            {
                "minute": minute,
                "hour": bucket["hour"],
                "category": dominant,
                "app": dominant_app,
                "color": get_category_info(dominant)["color"],
                "active_ratio": round(active_ratio, 3),
                "entropy": hourly.get(bucket["hour"], {}).get("entropy", 0.0),
                "event_count": bucket["total"],
            }
        )
    return timeline


def _enrich_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach display metadata to stitched sessions."""
    for session in sessions:
        info = get_category_info(session["category"])
        session["color"] = info["color"]
        session["icon"] = info["icon"]
        session["productive"] = info["productive"]
        session["duration_formatted"] = format_duration(session["duration_seconds"])
    return sessions


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the dashboard HTML."""
    return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# ── API ──────────────────────────────────────────────────────────────────────

@app.get("/api/day/{target_date}")
async def api_day(target_date: str) -> Any:
    """Return the full computed payload for one day."""
    day = _parse_date(target_date)
    if day is None:
        return JSONResponse({"error": "Invalid date. Use YYYY-MM-DD."}, status_code=400)

    events = get_events_for_date(day)
    sessions = _enrich_sessions(stitch_sessions(events))
    hourly = compute_hourly_entropy(events)

    return {
        "date": day.isoformat(),
        "focus_score": compute_daily_focus_score(hourly),
        "stats": compute_productivity_stats(events, sessions),
        "hourly_entropy": {str(hour): metrics for hour, metrics in hourly.items()},
        "timeline": _build_timeline(events, hourly),
        "sessions": sessions,
        "total_events": len(events),
    }


@app.get("/api/heatmap")
async def api_heatmap(days: int = 28) -> Any:
    """Return per-day Focus Score / activity for the last ``days`` days."""
    days = max(1, min(days, 370))
    today = date.today()
    start = today - timedelta(days=days - 1)

    summaries = daily_summaries_from_counts(get_hourly_category_counts(start, today))

    empty = {"focus_score": 0.0, "active_seconds": 0, "total_events": 0}
    series = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        series.append({"date": day, **{**empty, **summaries.get(day, {})}})

    return {"days": days, "start": start.isoformat(), "end": today.isoformat(), "series": series}


@app.get("/api/live")
async def api_live() -> Any:
    """Return current tracking status and the most recent events."""
    return {
        "recent_events": get_recent_events(limit=8),
        "today_summary": get_daily_summary(),
        "server_time": datetime.now().strftime(_TS_FORMAT),
    }


@app.get("/api/categories")
async def api_categories() -> Any:
    """Return category metadata (colours, icons, productive flags)."""
    return get_all_categories()


@app.get("/api/dates")
async def api_dates() -> Any:
    """Return the list of dates that have tracking data."""
    return {"dates": get_available_dates()}


@app.get("/api/export/{target_date}")
async def api_export(target_date: str, format: str = "json") -> Any:
    """Export a day's raw events as JSON or CSV."""
    day = _parse_date(target_date)
    if day is None:
        return JSONResponse({"error": "Invalid date. Use YYYY-MM-DD."}, status_code=400)

    events = get_events_for_date(day)
    if format.lower() == "csv":
        buffer = io.StringIO()
        columns = ["timestamp", "app_name", "window_title", "executable", "category", "is_idle"]
        writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events)
        return PlainTextResponse(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="chronicle-{day}.csv"'},
        )
    return Response(
        content=JSONResponse({"date": day.isoformat(), "events": events}).body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="chronicle-{day}.json"'},
    )


@app.get("/api/health")
async def api_health() -> Any:
    """Liveness probe with version and configured poll interval."""
    config = get_config()
    return {"status": "ok", "version": __version__, "poll_interval": config.poll_interval}
