"""
Chronicle — Focus Metrics Engine
Computes focus entropy scores and productivity metrics from tracking data.

Focus Entropy:
    Based on Shannon entropy, measures how fragmented attention is within an hour.
    Score 0.0 = perfect single-category focus (deep work)
    Score 1.0 = maximum fragmentation across many categories
    
    The raw entropy is normalized against the maximum possible entropy for the
    number of categories present, giving a 0-1 scale regardless of category count.
"""

import json
import math
import logging
from datetime import date, datetime
from collections import Counter

logger = logging.getLogger("chronicle.metrics")


def shannon_entropy(distribution):
    """
    Compute Shannon entropy for a probability distribution.
    
    Args:
        distribution: Dict of {category: count} or {category: proportion}
    
    Returns:
        Entropy value in bits
    """
    total = sum(distribution.values())
    if total == 0:
        return 0.0

    entropy = 0.0
    for count in distribution.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)

    return entropy


def normalized_entropy(distribution):
    """
    Compute normalized entropy (0-1 scale).
    0 = perfect focus (one category)
    1 = maximum fragmentation (equal split across all categories)
    """
    n_categories = len([v for v in distribution.values() if v > 0])
    if n_categories <= 1:
        return 0.0

    raw = shannon_entropy(distribution)
    max_entropy = math.log2(n_categories)

    if max_entropy == 0:
        return 0.0

    return min(1.0, raw / max_entropy)


def compute_hourly_entropy(events):
    """
    Compute focus entropy for each hour from raw events.
    
    Args:
        events: List of event dicts for a day
    
    Returns:
        Dict of {hour: {entropy, total_events, dominant_category, category_distribution}}
    """
    # Group events by hour
    hourly_buckets = {}
    for event in events:
        try:
            ts = event["timestamp"]
            if isinstance(ts, str):
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            else:
                dt = ts
            hour = dt.hour
        except (ValueError, KeyError):
            continue

        if hour not in hourly_buckets:
            hourly_buckets[hour] = []
        hourly_buckets[hour].append(event)

    # Compute entropy for each hour
    hourly_metrics = {}
    for hour, hour_events in hourly_buckets.items():
        # Count categories (excluding Idle from entropy calculation)
        cat_counts = Counter()
        for e in hour_events:
            cat = e.get("category", "Other")
            if cat != "Idle":
                cat_counts[cat] += 1

        if not cat_counts:
            # All idle
            hourly_metrics[hour] = {
                "entropy": 0.0,
                "total_events": len(hour_events),
                "dominant_category": "Idle",
                "category_distribution": {"Idle": len(hour_events)},
            }
            continue

        entropy = normalized_entropy(dict(cat_counts))
        dominant = cat_counts.most_common(1)[0][0]

        # Include idle in the distribution for display
        full_dist = dict(cat_counts)
        idle_count = sum(1 for e in hour_events if e.get("category") == "Idle")
        if idle_count > 0:
            full_dist["Idle"] = idle_count

        hourly_metrics[hour] = {
            "entropy": round(entropy, 4),
            "total_events": len(hour_events),
            "dominant_category": dominant,
            "category_distribution": full_dist,
        }

    return hourly_metrics


def compute_daily_focus_score(hourly_metrics):
    """
    Compute an overall daily focus score from hourly entropies.
    Weighted average where hours with more events count more.
    Inverted: 1.0 = perfect focus, 0.0 = completely fragmented.
    """
    if not hourly_metrics:
        return 0.0

    total_weight = 0
    weighted_sum = 0

    for hour, metrics in hourly_metrics.items():
        weight = metrics.get("total_events", 0)
        entropy = metrics.get("entropy", 0)
        if weight > 0:
            # Invert: low entropy = high focus
            focus = 1.0 - entropy
            weighted_sum += focus * weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    return round(weighted_sum / total_weight, 4)


def compute_productivity_stats(events, sessions=None):
    """
    Compute comprehensive productivity statistics for a day.
    
    Returns dict with:
        - total_tracked_seconds: Total time tracked
        - productive_seconds: Time in productive categories
        - productive_pct: Percentage of productive time
        - idle_seconds: Time marked as idle
        - top_categories: List of (category, seconds, pct)
        - longest_focus_minutes: Longest continuous focus session
        - context_switches: Number of category changes
        - active_hours: Number of hours with activity
    """
    from classifier import is_productive

    poll_interval = 3  # seconds per event

    if not events:
        return _empty_stats()

    total_events = len(events)
    total_seconds = total_events * poll_interval

    # Count by category
    cat_counts = Counter()
    idle_count = 0
    for e in events:
        cat = e.get("category", "Other")
        if e.get("is_idle"):
            idle_count += 1
        cat_counts[cat] += 1

    # Productive vs non-productive
    productive_events = sum(count for cat, count in cat_counts.items() if is_productive(cat))
    productive_seconds = productive_events * poll_interval
    active_seconds = (total_events - idle_count) * poll_interval

    # Category breakdown
    top_categories = []
    for cat, count in cat_counts.most_common():
        seconds = count * poll_interval
        pct = round(100 * count / total_events, 1) if total_events else 0
        top_categories.append({
            "category": cat,
            "seconds": seconds,
            "percentage": pct,
        })

    # Context switches
    context_switches = 0
    prev_cat = None
    for e in events:
        cat = e.get("category", "Other")
        if prev_cat is not None and cat != prev_cat:
            context_switches += 1
        prev_cat = cat

    # Active hours
    active_hours = set()
    for e in events:
        try:
            ts = e["timestamp"]
            if isinstance(ts, str):
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            else:
                dt = ts
            if not e.get("is_idle"):
                active_hours.add(dt.hour)
        except (ValueError, KeyError):
            pass

    # Longest focus session
    longest_focus = 0
    if sessions:
        for s in sessions:
            dur = s.get("duration_seconds", 0)
            if dur > longest_focus:
                longest_focus = dur

    productive_pct = round(100 * productive_seconds / active_seconds, 1) if active_seconds > 0 else 0

    return {
        "total_tracked_seconds": total_seconds,
        "active_seconds": active_seconds,
        "productive_seconds": productive_seconds,
        "productive_pct": productive_pct,
        "idle_seconds": idle_count * poll_interval,
        "top_categories": top_categories,
        "longest_focus_minutes": round(longest_focus / 60, 1),
        "context_switches": context_switches,
        "active_hours": len(active_hours),
    }


def _empty_stats():
    """Return empty stats dict."""
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


def compute_and_store_metrics(target_date=None):
    """
    Compute and store all hourly metrics for a date.
    Called periodically by the server.
    """
    from database import get_events_for_date, upsert_hourly_metric

    if target_date is None:
        target_date = date.today()

    events = get_events_for_date(target_date)
    if not events:
        return {}

    hourly = compute_hourly_entropy(events)

    for hour, metrics in hourly.items():
        upsert_hourly_metric(
            target_date=target_date,
            hour=hour,
            entropy=metrics["entropy"],
            total_events=metrics["total_events"],
            dominant_category=metrics["dominant_category"],
            category_distribution=json.dumps(metrics["category_distribution"]),
        )

    return hourly
