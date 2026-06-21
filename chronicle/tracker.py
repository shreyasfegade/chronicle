"""Background tracker — the polling loop.

A single daemon thread wakes every ``poll_interval`` seconds, asks the platform
layer for the foreground window and idle time, classifies the activity, and
writes one event. The loop is wrapped so that any per-poll failure is logged and
swallowed: the tracker is meant to run untouched for days, so it must survive the
occasional transient Win32 error rather than crash the process.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from . import platform
from .classifier import classify
from .config import Config, get_config
from .database import init_db, insert_event

logger = logging.getLogger("chronicle.tracker")

_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_TITLE_LENGTH = 500


class Tracker:
    """Polls the active window on a background thread and records events."""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or get_config()
        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None
        self._event_count = 0
        self._consecutive_errors = 0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start polling on a daemon thread (no-op if already running)."""
        if self._running:
            return
        init_db()
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="chronicle-tracker", daemon=True
        )
        self._thread.start()
        logger.info(
            "Tracker started (interval=%.1fs, idle_threshold=%.0fs)",
            self._config.poll_interval,
            self._config.idle_threshold,
        )

    def stop(self) -> None:
        """Signal the loop to stop and wait briefly for the thread to exit."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self._config.poll_interval + 2)
        logger.info("Tracker stopped after recording %d events", self._event_count)

    def pause(self) -> None:
        """Stop recording events without stopping the thread."""
        self._paused = True
        logger.info("Tracker paused")

    def resume(self) -> None:
        """Resume recording events."""
        self._paused = False
        logger.info("Tracker resumed")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def event_count(self) -> int:
        return self._event_count

    # ── Loop ─────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        """Poll until stopped, isolating each iteration from the loop's health."""
        while self._running:
            start = time.monotonic()
            if not self._paused:
                try:
                    self._poll_once()
                    self._consecutive_errors = 0
                except Exception:  # noqa: BLE001 - loop must never die
                    self._consecutive_errors += 1
                    logger.exception(
                        "Poll failed (%d in a row)", self._consecutive_errors
                    )
            # Account for the work just done so cadence stays close to interval.
            time.sleep(max(0.0, self._config.poll_interval - (time.monotonic() - start)))

    def _poll_once(self) -> None:
        """Capture and store a single tracking event."""
        idle_seconds = platform.get_idle_seconds()
        is_idle = idle_seconds >= self._config.idle_threshold

        window = platform.get_foreground_window()
        if window is None:
            return  # No usable foreground window (locked screen, transition, …).

        category = "Idle" if is_idle else classify(
            window.app_name, window.title, window.executable
        )

        insert_event(
            timestamp=datetime.now().strftime(_TS_FORMAT),
            app_name=window.app_name,
            window_title=window.title[:_MAX_TITLE_LENGTH],
            executable=window.executable,
            category=category,
            is_idle=is_idle,
        )
        self._event_count += 1
