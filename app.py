"""
Chronicle — One-Command Entry Point
Starts the background tracker, FastAPI server, system tray icon,
and opens the dashboard in the browser. All from a single `python app.py`.
"""

import sys
import os
import time
import logging
import threading
import webbrowser
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Logging Setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("chronicle")

# Suppress noisy loggers
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)

# ── Configuration ─────────────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 7745
DASHBOARD_URL = f"http://{HOST}:{PORT}"
POLL_INTERVAL = 3        # seconds between polls
IDLE_THRESHOLD = 120     # seconds before marking idle


def main():
    """Main entry point — starts everything."""
    print()
    print("  +----------------------------------------------------+")
    print("  |                                                    |")
    print("  |     *  C H R O N I C L E                           |")
    print("  |        Passive Time Intelligence Engine            |")
    print("  |                                                    |")
    print("  |     Dashboard:  http://localhost:7745               |")
    print("  |     Storage:    Local SQLite (chronicle.db)        |")
    print("  |     Tracking:   Every 3 seconds                   |")
    print("  |                                                    |")
    print("  |     Press Ctrl+C to quit                           |")
    print("  |                                                    |")
    print("  +----------------------------------------------------+")
    print()

    # Step 1: Initialize database
    logger.info("Initializing database...")
    from database import init_db
    init_db()

    # Step 2: Start the background tracker
    logger.info("Starting background tracker...")
    from tracker import Tracker
    tracker = Tracker(interval=POLL_INTERVAL, idle_threshold=IDLE_THRESHOLD)
    tracker.start()

    # Step 3: Start system tray icon
    logger.info("Starting system tray icon...")
    try:
        from tray import start_tray
        tray_icon = start_tray(tracker)
    except Exception as e:
        logger.warning(f"System tray icon failed to start: {e}")
        tray_icon = None

    # Step 4: Open browser after a short delay
    def open_browser():
        time.sleep(1.5)  # Wait for server to start
        webbrowser.open(DASHBOARD_URL)
        logger.info(f"Dashboard opened at {DASHBOARD_URL}")

    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Step 5: Start FastAPI server (blocks until shutdown)
    logger.info(f"Starting server on {DASHBOARD_URL}...")
    import uvicorn
    from server import app

    # Handle Ctrl+C gracefully
    def signal_handler(signum, frame):
        logger.info("Shutting down Chronicle...")
        tracker.stop()
        if tray_icon:
            try:
                tray_icon.stop()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        tracker.stop()
        logger.info("Chronicle stopped. Goodbye!")


if __name__ == "__main__":
    main()
