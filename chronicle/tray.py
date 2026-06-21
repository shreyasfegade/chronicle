"""System-tray icon and controls.

The icon is drawn at runtime with Pillow so the project ships no binary assets,
and the menu lets the user open the dashboard, pause/resume tracking, or quit.
``pystray`` and ``Pillow`` are optional: if either is missing the app logs a
warning and runs headless rather than failing to start.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from typing import Any

from .config import get_config

logger = logging.getLogger("chronicle.tray")


def _create_icon_image() -> Any:
    """Draw the Chronicle tray icon (a stylised clock) with Pillow."""
    from PIL import Image, ImageDraw

    size = 64
    center = size // 2
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.ellipse([2, 2, size - 2, size - 2], fill=(99, 102, 241, 255))
    draw.ellipse([8, 8, size - 8, size - 8], fill=(79, 70, 229, 255))
    draw.arc([12, 12, size - 12, size - 12], start=30, end=330, fill=(255, 255, 255, 255), width=4)
    draw.line([center, center, center, 16], fill=(255, 255, 255, 255), width=3)
    draw.line([center, center, center + 10, center - 6], fill=(167, 139, 250, 255), width=2)
    draw.ellipse([center - 3, center - 3, center + 3, center + 3], fill=(255, 255, 255, 255))
    return image


def start_tray(tracker: Any) -> Any | None:
    """Start the tray icon on a daemon thread.

    Args:
        tracker: The :class:`~chronicle.tracker.Tracker` whose pause/resume/stop
            the menu drives.

    Returns:
        The running ``pystray.Icon``, or ``None`` if tray support is unavailable.
    """
    try:
        import pystray
        from pystray import MenuItem as Item
    except ImportError:
        logger.warning("pystray/Pillow not installed — running without a tray icon.")
        return None

    url = get_config().dashboard_url

    def open_dashboard(icon: Any, item: Any) -> None:
        webbrowser.open(url)

    def toggle_pause(icon: Any, item: Any) -> None:
        tracker.resume() if tracker.is_paused else tracker.pause()
        icon.update_menu()

    def pause_label(item: Any) -> str:
        return "Resume tracking" if tracker.is_paused else "Pause tracking"

    def quit_app(icon: Any, item: Any) -> None:
        tracker.stop()
        icon.stop()

    menu = pystray.Menu(
        Item("Open dashboard", open_dashboard, default=True),
        Item(pause_label, toggle_pause),
        pystray.Menu.SEPARATOR,
        Item("Quit", quit_app),
    )
    icon = pystray.Icon(
        "Chronicle", icon=_create_icon_image(), title="Chronicle — Focus Intelligence", menu=menu
    )
    threading.Thread(target=icon.run, name="chronicle-tray", daemon=True).start()
    logger.info("System tray icon started")
    return icon
