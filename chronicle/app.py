"""Application bootstrap — wire the tracker, server, and tray together.

This is the one place that knows about every component. It initialises the
database, starts the background tracker and tray, opens the dashboard, and then
runs the (blocking) web server until interrupted, shutting everything down
cleanly on the way out.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
import webbrowser
from types import FrameType

from .config import get_config
from .logging_setup import configure_logging

logger = logging.getLogger("chronicle")

_BANNER = r"""
  ┌─────────────────────────────────────────────┐
  │                                             │
  │   ◆  C H R O N I C L E                       │
  │      Passive focus intelligence              │
  │                                             │
  │   Dashboard : {url:<30}│
  │   Storage   : local SQLite (WAL)             │
  │                                             │
  │   Ctrl+C to quit                             │
  │                                             │
  └─────────────────────────────────────────────┘
"""


def main() -> None:
    """Start Chronicle and block until interrupted."""
    configure_logging()
    config = get_config()
    print(_BANNER.format(url=config.dashboard_url))

    from .database import init_db

    logger.info("Initialising database…")
    init_db()

    from .classifier import apply_custom_rules

    apply_custom_rules(config.custom_rules)

    from .tracker import Tracker

    tracker = Tracker(config)
    tracker.start()

    from .tray import start_tray

    tray_icon = start_tray(tracker)

    def open_browser() -> None:
        time.sleep(1.5)  # let uvicorn bind first
        if config.open_browser:
            webbrowser.open(config.dashboard_url)
            logger.info("Dashboard opened at %s", config.dashboard_url)

    threading.Thread(target=open_browser, name="chronicle-browser", daemon=True).start()

    def shutdown(signum: int, frame: FrameType | None) -> None:
        logger.info("Shutting down…")
        tracker.stop()
        if tray_icon is not None:
            try:
                tray_icon.stop()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    import uvicorn

    from .server import app

    logger.info("Starting dashboard server on %s", config.dashboard_url)
    try:
        uvicorn.run(app, host=config.host, port=config.port, log_level="warning")
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        tracker.stop()
        logger.info("Chronicle stopped. Goodbye.")


if __name__ == "__main__":
    main()
