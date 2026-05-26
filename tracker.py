"""
Chronicle — Windows Active Window Tracker
Polls the foreground window every N seconds using Win32 APIs.
Detects idle time via GetLastInputInfo. Writes events to SQLite.
"""

import ctypes
import ctypes.wintypes
import threading
import time
import logging
import os
from datetime import datetime

logger = logging.getLogger("chronicle.tracker")

# Win32 structures and functions
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


def get_idle_seconds():
    """Get the number of seconds since the last user input (mouse/keyboard)."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        tick_count = kernel32.GetTickCount()
        elapsed = (tick_count - lii.dwTime) / 1000.0
        return max(0, elapsed)
    return 0


def get_foreground_window_info():
    """
    Get information about the currently focused window.
    Returns: (app_name, window_title, executable) or (None, None, None)
    """
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None, None

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return None, None, None

        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        window_title = buf.value

        # Get process ID
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        if pid.value == 0:
            return None, window_title, None

        # Get process handle and executable name
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        h_process = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid.value
        )

        if not h_process:
            return None, window_title, None

        try:
            # Get executable path
            exe_buf = ctypes.create_unicode_buffer(512)
            size = ctypes.wintypes.DWORD(512)

            # Try QueryFullProcessImageNameW first (works on modern Windows)
            if kernel32.QueryFullProcessImageNameW(h_process, 0, exe_buf, ctypes.byref(size)):
                exe_path = exe_buf.value
            else:
                # Fallback to GetModuleFileNameExW
                psapi.GetModuleFileNameExW(h_process, None, exe_buf, 512)
                exe_path = exe_buf.value

            if exe_path:
                executable = os.path.basename(exe_path)
                app_name = executable.replace(".exe", "").replace(".EXE", "")
            else:
                executable = ""
                app_name = ""

            return app_name, window_title, executable

        finally:
            kernel32.CloseHandle(h_process)

    except Exception as e:
        logger.debug(f"Error getting window info: {e}")
        return None, None, None


class Tracker:
    """
    Background tracker that polls the active window and records events.
    Runs in a dedicated daemon thread.
    """

    def __init__(self, interval=3, idle_threshold=120):
        """
        Args:
            interval: Seconds between polls (default 3).
            idle_threshold: Seconds of no input before marking as idle (default 120).
        """
        self.interval = interval
        self.idle_threshold = idle_threshold
        self._running = False
        self._paused = False
        self._thread = None
        self._last_app = None
        self._last_title = None
        self._event_count = 0

    def start(self):
        """Start the tracker in a background thread."""
        if self._running:
            return

        # Lazy imports to avoid circular dependency
        from database import init_db
        init_db()

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="chronicle-tracker")
        self._thread.start()
        logger.info(f"Tracker started (interval={self.interval}s, idle_threshold={self.idle_threshold}s)")

    def stop(self):
        """Stop the tracker."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info(f"Tracker stopped. Total events recorded: {self._event_count}")

    def pause(self):
        """Pause tracking without stopping the thread."""
        self._paused = True
        logger.info("Tracker paused")

    def resume(self):
        """Resume tracking."""
        self._paused = False
        logger.info("Tracker resumed")

    @property
    def is_running(self):
        return self._running

    @property
    def is_paused(self):
        return self._paused

    @property
    def event_count(self):
        return self._event_count

    def _poll_loop(self):
        """Main polling loop."""
        from database import insert_event
        from classifier import classify

        while self._running:
            try:
                if not self._paused:
                    self._record_event(insert_event, classify)
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Tracker error: {e}", exc_info=True)
                time.sleep(self.interval)

    def _record_event(self, insert_event, classify):
        """Record a single tracking event."""
        idle_seconds = get_idle_seconds()
        is_idle = idle_seconds >= self.idle_threshold

        app_name, window_title, executable = get_foreground_window_info()

        if app_name is None and window_title is None:
            return  # No foreground window (e.g., locked screen)

        app_name = app_name or ""
        window_title = window_title or ""
        executable = executable or ""

        # Classify the activity
        if is_idle:
            category = "Idle"
        else:
            category = classify(app_name, window_title, executable)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        insert_event(
            timestamp=timestamp,
            app_name=app_name,
            window_title=window_title[:500],  # Truncate very long titles
            executable=executable,
            category=category,
            is_idle=is_idle,
        )

        self._last_app = app_name
        self._last_title = window_title
        self._event_count += 1

        if self._event_count % 100 == 0:
            logger.debug(f"Events recorded: {self._event_count}")
