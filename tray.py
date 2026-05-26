"""
Chronicle — System Tray Icon
Provides a system tray icon with menu options using pystray.
Generates a dynamic icon using Pillow (no external icon file needed).
"""

import threading
import logging
import webbrowser

logger = logging.getLogger("chronicle.tray")

DASHBOARD_URL = "http://localhost:7745"


def _create_icon_image():
    """Create a Chronicle icon image using Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle with gradient effect
    # Dark indigo base
    draw.ellipse([2, 2, size - 2, size - 2], fill=(99, 102, 241, 255))
    # Inner circle for depth
    draw.ellipse([8, 8, size - 8, size - 8], fill=(79, 70, 229, 255))

    # Draw a clock-inspired "C" shape
    center = size // 2
    # Outer ring
    draw.arc([12, 12, size - 12, size - 12], start=30, end=330, fill=(255, 255, 255, 255), width=4)
    # Clock hand
    draw.line([center, center, center, 16], fill=(255, 255, 255, 255), width=3)
    draw.line([center, center, center + 10, center - 6], fill=(167, 139, 250, 255), width=2)
    # Center dot
    draw.ellipse([center - 3, center - 3, center + 3, center + 3], fill=(255, 255, 255, 255))

    return img


def start_tray(tracker_instance):
    """
    Start the system tray icon in a background thread.

    Args:
        tracker_instance: The Tracker instance to control pause/resume.
    """
    try:
        import pystray
        from pystray import MenuItem as Item
    except ImportError:
        logger.warning("pystray not installed. System tray icon disabled.")
        return None

    icon_image = _create_icon_image()

    def on_open_dashboard(icon, item):
        webbrowser.open(DASHBOARD_URL)

    def on_pause_resume(icon, item):
        if tracker_instance.is_paused:
            tracker_instance.resume()
        else:
            tracker_instance.pause()
        # Update the menu
        icon.update_menu()

    def get_pause_text(item):
        return "▶ Resume Tracking" if tracker_instance.is_paused else "⏸ Pause Tracking"

    def on_quit(icon, item):
        tracker_instance.stop()
        icon.stop()

    menu = pystray.Menu(
        Item("Chronicle", on_open_dashboard, default=True, enabled=True),
        pystray.Menu.SEPARATOR,
        Item("🌐 Open Dashboard", on_open_dashboard),
        Item(get_pause_text, on_pause_resume),
        pystray.Menu.SEPARATOR,
        Item("❌ Quit", on_quit),
    )

    icon = pystray.Icon(
        name="Chronicle",
        icon=icon_image,
        title="Chronicle — Time Intelligence",
        menu=menu,
    )

    # Run in background thread
    tray_thread = threading.Thread(target=icon.run, daemon=True, name="chronicle-tray")
    tray_thread.start()
    logger.info("System tray icon started")

    return icon
