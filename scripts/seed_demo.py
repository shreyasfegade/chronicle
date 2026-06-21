"""Populate the database with a realistic sample of activity.

This is a developer/demo convenience — it lets you see the dashboard fully alive
without waiting days for real data to accumulate (and it produces the screenshots
in the README). It synthesises a few weeks of plausible workdays: deep-focus
coding blocks, meetings, lunch breaks, study sessions, and deliberately
fragmented afternoons so the Focus Score and entropy turbulence have something
to show.

Usage::

    python scripts/seed_demo.py            # seed the last 21 days
    python scripts/seed_demo.py --days 30
    python scripts/seed_demo.py --reset    # wipe existing events first

The data is written to the same local ``chronicle.db`` the app uses; nothing
leaves your machine.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chronicle.classifier import classify  # noqa: E402
from chronicle.config import get_config  # noqa: E402
from chronicle.database import get_db, init_db, insert_events_batch  # noqa: E402

# Representative (app, executable, title) samples per category.
SAMPLES: dict[str, list[tuple[str, str, str]]] = {
    "Coding": [
        ("Code", "Code.exe", "tracker.py — chronicle — Visual Studio Code"),
        ("Code", "Code.exe", "server.py — chronicle — Visual Studio Code"),
        ("Code", "Code.exe", "style.css — chronicle — Visual Studio Code"),
        ("pycharm64", "pycharm64.exe", "metrics.py — Chronicle"),
    ],
    "DevOps": [
        ("WindowsTerminal", "WindowsTerminal.exe", "pwsh — chronicle"),
        ("WindowsTerminal", "WindowsTerminal.exe", "git log — chronicle"),
        ("chrome", "chrome.exe", "chronicle · GitHub Actions"),
    ],
    "Writing": [
        ("Code", "Code.exe", "README.md — chronicle — Visual Studio Code"),
        ("obsidian", "obsidian.exe", "Design notes — Obsidian"),
        ("chrome", "chrome.exe", "Architecture draft — Google Docs"),
    ],
    "Studying": [
        ("chrome", "chrome.exe", "Shannon entropy — Wikipedia"),
        ("sumatrapdf", "SumatraPDF.exe", "Information Theory (Cover & Thomas).pdf"),
        ("chrome", "chrome.exe", "D3 in Depth — documentation"),
    ],
    "Design": [
        ("figma", "figma.exe", "Chronicle Dashboard — Figma"),
        ("chrome", "chrome.exe", "Dashboard concepts — Dribbble"),
    ],
    "Communication": [
        ("slack", "slack.exe", "#engineering — Slack"),
        ("chrome", "chrome.exe", "Inbox (3) — Gmail"),
        ("zoom", "Zoom.exe", "Zoom Meeting"),
    ],
    "Browsing": [
        ("chrome", "chrome.exe", "Hacker News"),
        ("chrome", "chrome.exe", "Amazon.com — Shopping Cart"),
    ],
    "Entertainment": [
        ("chrome", "chrome.exe", "lofi hip hop radio — YouTube"),
        ("Spotify", "Spotify.exe", "Deep Focus — Spotify"),
    ],
}

# A weekday template: (start_hour, end_hour, [(category, weight), ...]).
# A single dominant category ⇒ deep focus (low entropy); a balanced mix ⇒
# fragmented attention (high entropy).
WEEKDAY_BLOCKS = [
    (9.0, 9.4, [("Communication", 3), ("Browsing", 2)]),          # easing in
    (9.4, 11.5, [("Coding", 1)]),                                 # deep work (pure)
    (11.5, 12.0, [("Communication", 4), ("Coding", 1)]),          # standup
    (12.0, 12.8, [("__idle__", 1)]),                              # lunch
    (12.8, 13.6, [("Coding", 3), ("Browsing", 2), ("Communication", 1)]),  # scattered
    (13.6, 15.6, [("Coding", 8), ("Writing", 1)]),               # deep work
    (15.6, 16.1, [("Design", 1)]),                               # focused design
    (16.1, 17.0, [("Studying", 6), ("Browsing", 1)]),            # study
    (17.0, 17.6, [("Communication", 2), ("Browsing", 2), ("Entertainment", 1)]),  # wind-down
]

# Lighter, more leisure-leaning weekend.
WEEKEND_BLOCKS = [
    (10.5, 11.5, [("Browsing", 3), ("Communication", 1)]),
    (11.5, 13.0, [("Coding", 4), ("Studying", 3), ("Entertainment", 2)]),
    (15.0, 16.5, [("Studying", 5), ("Writing", 2), ("Browsing", 2)]),
    (20.0, 21.5, [("Entertainment", 5), ("Browsing", 2)]),
]


def _weighted_choice(weighted: list[tuple[str, int]], rng: random.Random) -> str:
    choices, weights = zip(*weighted)
    return rng.choices(choices, weights=weights, k=1)[0]


def _build_day(
    day: date,
    rng: random.Random,
    can_skip: bool = True,
    focus_bias: float | None = None,
) -> list[tuple]:
    """Generate event rows for one day at the configured poll interval."""
    interval = get_config().poll_interval
    blocks = WEEKEND_BLOCKS if day.weekday() >= 5 else WEEKDAY_BLOCKS
    # Occasionally skip a day entirely to make the heatmap realistic, but never
    # the most recent day — the dashboard opens on "today" and should look alive.
    if can_skip and rng.random() < 0.12:
        return []

    rows: list[tuple] = []
    midnight = datetime.combine(day, time())
    # Each day has its own "focus mood": high-focus days sharpen every block
    # toward its dominant category (low entropy), scattered days flatten them.
    # This gives the multi-week heatmap a realistic spread of scores.
    if focus_bias is None:
        focus_bias = rng.uniform(0.0, 1.0)
    # A single monotonic cursor across all blocks guarantees ordered,
    # non-overlapping timestamps (so contiguous runs stay contiguous).
    cursor = 0.0
    for start_h, end_h, base_mix in blocks:
        # Sharpen the dominant category on focused days.
        mix = [
            (cat, w * (1 + focus_bias * 5) if w == max(x[1] for x in base_mix) else w)
            for cat, w in base_mix
        ]
        block_start = start_h * 3600 + rng.uniform(0, 45)  # start a little late
        end = end_h * 3600
        t = max(cursor, block_start)
        # How concentrated this block is on its top category, 0..1. Deep-work
        # blocks dwell on one app for minutes; scattered blocks churn quickly.
        weights = [w for _, w in mix]
        concentration = max(weights) / sum(weights)

        while t < end:
            category = _weighted_choice(mix, rng)
            is_idle = category == "__idle__"
            if is_idle:
                app, exe, title, cat = "", "", "", "Idle"
                dwell = end - t  # one unbroken idle run (e.g. lunch)
            else:
                app, exe, title = rng.choice(SAMPLES[category])
                cat = classify(app, title, exe)
                # Focused blocks → longer runs; fragmented blocks → short runs.
                dwell = rng.uniform(45, 90 + concentration * 540)
            run_end = min(end, t + dwell)
            while t < run_end:
                ts = midnight + timedelta(seconds=t)
                rows.append((ts.strftime("%Y-%m-%d %H:%M:%S"), app, title, exe, cat, int(is_idle)))
                t += interval
        cursor = t
    return rows


def seed(days: int, reset: bool, seed_value: int = 7) -> None:
    rng = random.Random(seed_value)
    init_db()

    if reset:
        with get_db() as conn:
            conn.execute("DELETE FROM events")
            conn.commit()
        print("Cleared existing events.")

    today = date.today()
    total = 0
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        # Make "today" a strong-focus day so the dashboard opens looking sharp.
        rows = _build_day(day, rng, can_skip=offset != 0, focus_bias=0.85 if offset == 0 else None)
        if rows:
            insert_events_batch(rows)
        total += len(rows)
        print(f"  {day}  {len(rows):>5} events")
    print(f"Seeded {total} events across {days} days into {get_config().db_path.name}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Chronicle with demo data.")
    parser.add_argument("--days", type=int, default=21, help="Number of days to generate.")
    parser.add_argument("--reset", action="store_true", help="Delete existing events first.")
    args = parser.parse_args()
    seed(days=args.days, reset=args.reset)


if __name__ == "__main__":
    main()
