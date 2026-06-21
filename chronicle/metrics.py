"""Focus metrics — turning the event stream into a Focus Score.

The central idea is to treat attention as a signal and measure its *disorder*
with Shannon entropy. Within each hour we build a distribution over activity
categories; an hour spent entirely in one category has zero entropy (deep focus)
while an hour split evenly across many categories approaches maximum entropy
(fragmented attention). Normalising by ``log2(n_categories)`` keeps the result on
a 0–1 scale regardless of how many categories appear.

The **Focus Score** is the event-weighted average of ``1 - entropy`` across the
day, so busy fragmented hours pull it down more than a quiet scattered minute.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from datetime import date, datetime
from typing import Any

from .classifier import is_productive
from .config import get_config

logger = logging.getLogger("chronicle.metrics")

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def shannon_entropy(distribution: dict[str, float]) -> float:
    """Return the Shannon entropy (in bits) of a count/probability distribution."""
    total = sum(distribution.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in distribution.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def normalized_entropy(distribution: dict[str, float]) -> float:
    """Return entropy scaled to ``0`` (single focus) … ``1`` (max fragmentation)."""
    active = {k: v for k, v in distribution.items() if v > 0}
    if len(active) <= 1:
        return 0.0
    max_entropy = math.log2(len(active))
    if max_entropy == 0:
        return 0.0
    return min(1.0, shannon_entropy(active) / max_entropy)


def _event_hour(event: dict[str, Any]) -> int | None:
    """Extract the hour-of-day from an event, or ``None`` if unparseable."""
    ts = event.get("timestamp")
    if isinstance(ts, datetime):
        return ts.hour
    try:
        return datetime.strptime(ts, _TS_FORMAT).hour
    except (ValueError, TypeError):
        return None


def compute_hourly_entropy(events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Compute per-hour entropy and category mix.

    Idle events are excluded from the entropy calculation (idleness is not
    fragmentation) but retained in the reported distribution for display.

    Returns:
        Mapping of ``hour -> {entropy, total_events, dominant_category,
        category_distribution}``.
    """
    buckets: dict[int, list[dict[str, Any]]] = {}
    for event in events:
        hour = _event_hour(event)
        if hour is not None:
            buckets.setdefault(hour, []).append(event)

    result: dict[int, dict[str, Any]] = {}
    for hour, hour_events in buckets.items():
        active = Counter(
            e.get("category", "Other") for e in hour_events if e.get("category") != "Idle"
        )
        idle_count = sum(1 for e in hour_events if e.get("category") == "Idle")

        if not active:
            result[hour] = {
                "entropy": 0.0,
                "total_events": len(hour_events),
                "dominant_category": "Idle",
                "category_distribution": {"Idle": idle_count},
            }
            continue

        distribution = dict(active)
        if idle_count:
            distribution["Idle"] = idle_count

        result[hour] = {
            "entropy": round(normalized_entropy(dict(active)), 4),
            "total_events": len(hour_events),
            "dominant_category": active.most_common(1)[0][0],
            "category_distribution": distribution,
        }
    return result


def compute_daily_focus_score(hourly: dict[int, dict[str, Any]]) -> float:
    """Return the event-weighted daily Focus Score (``0`` … ``1``)."""
    weighted_sum = 0.0
    total_weight = 0
    for metrics in hourly.values():
        weight = metrics.get("total_events", 0)
        if weight > 0:
            weighted_sum += (1.0 - metrics.get("entropy", 0.0)) * weight
            total_weight += weight
    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 4)


def compute_productivity_stats(
    events: list[dict[str, Any]],
    sessions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute headline daily statistics from events (and optional sessions).

    Returns a dict with tracked/active/productive/idle seconds, a per-category
    breakdown, the longest focus session, context-switch count and active hours.
    """
    poll_interval = get_config().poll_interval
    if not events:
        return _empty_stats()

    total_events = len(events)
    counts = Counter(e.get("category", "Other") for e in events)
    idle_count = sum(1 for e in events if e.get("is_idle"))

    active_seconds = (total_events - idle_count) * poll_interval
    productive_events = sum(c for cat, c in counts.items() if is_productive(cat))
    productive_seconds = productive_events * poll_interval

    top_categories = [
        {
            "category": cat,
            "seconds": count * poll_interval,
            "percentage": round(100 * count / total_events, 1),
        }
        for cat, count in counts.most_common()
    ]

    context_switches = 0
    previous = None
    active_hours: set[int] = set()
    for event in events:
        cat = event.get("category", "Other")
        if previous is not None and cat != previous:
            context_switches += 1
        previous = cat
        if not event.get("is_idle"):
            hour = _event_hour(event)
            if hour is not None:
                active_hours.add(hour)

    longest_focus = 0.0
    if sessions:
        longest_focus = max(
            (s.get("duration_seconds", 0) for s in sessions if is_productive(s.get("category", ""))),
            default=0.0,
        )

    return {
        "total_tracked_seconds": total_events * poll_interval,
        "active_seconds": active_seconds,
        "productive_seconds": productive_seconds,
        "productive_pct": round(100 * productive_seconds / active_seconds, 1) if active_seconds else 0,
        "idle_seconds": idle_count * poll_interval,
        "top_categories": top_categories,
        "longest_focus_minutes": round(longest_focus / 60, 1),
        "context_switches": context_switches,
        "active_hours": len(active_hours),
    }


def _empty_stats() -> dict[str, Any]:
    return {
        "total_tracked_seconds": 0,
        "active_seconds": 0,
        "productive_seconds": 0,
        "productive_pct": 0,
        "idle_seconds": 0,
        "top_categories": [],
        "longest_focus_minutes": 0,
        "context_switches": 0,
        "active_hours": 0,
    }


def daily_summaries_from_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build per-day Focus Score summaries from aggregated hourly counts.

    Args:
        rows: ``(day, hour, category, count, idle_count)`` rows as returned by
            :func:`chronicle.database.get_hourly_category_counts`.

    Returns:
        Mapping of ISO date string to ``{date, focus_score, active_seconds,
        total_events}``. This is the data behind the multi-week heatmap and is
        computed without ever loading raw events into memory.
    """
    poll_interval = get_config().poll_interval

    # day -> hour -> {category: count}; plus per-day totals.
    per_day: dict[str, dict[int, dict[str, int]]] = {}
    totals: dict[str, int] = {}
    active: dict[str, int] = {}
    for row in rows:
        day, hour, category = row["day"], row["hour"], row["category"]
        count, idle = row["count"], row["idle_count"] or 0
        per_day.setdefault(day, {}).setdefault(hour, {})[category] = count
        totals[day] = totals.get(day, 0) + count
        active[day] = active.get(day, 0) + (count - idle)

    summaries: dict[str, dict[str, Any]] = {}
    for day, hours in per_day.items():
        weighted_sum = 0.0
        weight_total = 0
        for distribution in hours.values():
            non_idle = {c: n for c, n in distribution.items() if c != "Idle"}
            hour_events = sum(distribution.values())
            if hour_events == 0:
                continue
            entropy = normalized_entropy(non_idle) if non_idle else 0.0
            weighted_sum += (1.0 - entropy) * hour_events
            weight_total += hour_events
        summaries[day] = {
            "date": day,
            "focus_score": round(weighted_sum / weight_total, 4) if weight_total else 0.0,
            "active_seconds": active.get(day, 0) * poll_interval,
            "total_events": totals.get(day, 0),
        }
    return summaries
