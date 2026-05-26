"""
Chronicle — FastAPI REST API Server
Serves the dashboard and provides API endpoints for timeline, sessions, metrics data.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from database import (
    get_events_for_date,
    get_sessions_for_date,
    get_hourly_metrics_for_date,
    get_category_summary_for_date,
    get_daily_summary,
    get_available_dates,
    get_recent_events,
)
from classifier import get_all_categories, get_category_info
from sessions import stitch_sessions, compute_and_store_sessions, format_duration
from metrics import (
    compute_hourly_entropy,
    compute_daily_focus_score,
    compute_productivity_stats,
    compute_and_store_metrics,
)

logger = logging.getLogger("chronicle.server")

app = FastAPI(title="Chronicle", version="1.0.0")

# Mount static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard."""
    index_path = static_dir / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/today")
async def api_today():
    """Get comprehensive data for today."""
    today = date.today()

    # Get raw events and compute everything
    events = get_events_for_date(today)

    # Stitch sessions
    sessions = stitch_sessions(events)

    # Compute entropy
    hourly_entropy = compute_hourly_entropy(events)
    focus_score = compute_daily_focus_score(hourly_entropy)

    # Compute productivity stats
    stats = compute_productivity_stats(events, sessions)

    # Category info
    categories = get_all_categories()

    return {
        "date": today.isoformat(),
        "focus_score": focus_score,
        "stats": stats,
        "hourly_entropy": {
            str(h): m for h, m in hourly_entropy.items()
        },
        "sessions": sessions[-20:],  # Last 20 sessions
        "categories": categories,
        "total_events": len(events),
    }


@app.get("/api/timeline/{target_date}")
async def api_timeline(target_date: str):
    """
    Get timeline data for a specific date.
    Returns events bucketed by minute for the horizontal timeline.
    """
    try:
        dt = date.fromisoformat(target_date)
    except ValueError:
        return JSONResponse({"error": "Invalid date format. Use YYYY-MM-DD."}, status_code=400)

    events = get_events_for_date(dt)

    if not events:
        return {"date": target_date, "timeline": [], "total_events": 0}

    # Build minute-by-minute timeline (1440 minutes in a day)
    timeline = []
    minute_buckets = {}

    for event in events:
        try:
            ts = datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S")
            minute_key = ts.hour * 60 + ts.minute
            if minute_key not in minute_buckets:
                minute_buckets[minute_key] = {
                    "minute": minute_key,
                    "hour": ts.hour,
                    "minute_of_hour": ts.minute,
                    "categories": {},
                    "apps": {},
                }
            bucket = minute_buckets[minute_key]
            cat = event["category"]
            bucket["categories"][cat] = bucket["categories"].get(cat, 0) + 1
            app = event["app_name"]
            if app:
                bucket["apps"][app] = bucket["apps"].get(app, 0) + 1
        except (ValueError, KeyError):
            continue

    # Determine dominant category for each minute
    for minute_key, bucket in sorted(minute_buckets.items()):
        dominant_cat = max(bucket["categories"], key=bucket["categories"].get)
        dominant_app = max(bucket["apps"], key=bucket["apps"].get) if bucket["apps"] else ""
        cat_info = get_category_info(dominant_cat)
        timeline.append({
            "minute": minute_key,
            "hour": bucket["hour"],
            "minute_of_hour": bucket["minute_of_hour"],
            "category": dominant_cat,
            "app": dominant_app,
            "color": cat_info["color"],
            "event_count": sum(bucket["categories"].values()),
        })

    return {
        "date": target_date,
        "timeline": timeline,
        "total_events": len(events),
    }


@app.get("/api/sessions/{target_date}")
async def api_sessions(target_date: str):
    """Get stitched sessions for a date."""
    try:
        dt = date.fromisoformat(target_date)
    except ValueError:
        return JSONResponse({"error": "Invalid date format."}, status_code=400)

    events = get_events_for_date(dt)
    sessions = stitch_sessions(events)

    # Enrich sessions with category info and formatted duration
    for session in sessions:
        cat_info = get_category_info(session["category"])
        session["color"] = cat_info["color"]
        session["icon"] = cat_info["icon"]
        session["productive"] = cat_info["productive"]
        session["duration_formatted"] = format_duration(session["duration_seconds"])

    return {
        "date": target_date,
        "sessions": sessions,
        "total_sessions": len(sessions),
    }


@app.get("/api/metrics/{target_date}")
async def api_metrics(target_date: str):
    """Get focus entropy and productivity metrics for a date."""
    try:
        dt = date.fromisoformat(target_date)
    except ValueError:
        return JSONResponse({"error": "Invalid date format."}, status_code=400)

    events = get_events_for_date(dt)
    sessions = stitch_sessions(events)
    hourly_entropy = compute_hourly_entropy(events)
    focus_score = compute_daily_focus_score(hourly_entropy)
    stats = compute_productivity_stats(events, sessions)

    return {
        "date": target_date,
        "focus_score": focus_score,
        "hourly_entropy": {str(h): m for h, m in hourly_entropy.items()},
        "stats": stats,
    }


@app.get("/api/categories")
async def api_categories():
    """Get all category definitions."""
    return get_all_categories()


@app.get("/api/live")
async def api_live():
    """Get live tracking status and recent events."""
    recent = get_recent_events(limit=5)
    today_summary = get_daily_summary()

    return {
        "recent_events": recent,
        "today_summary": today_summary,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/dates")
async def api_dates():
    """Get list of dates with tracking data."""
    dates = get_available_dates()
    return {"dates": dates}
