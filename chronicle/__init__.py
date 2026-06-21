"""Chronicle — passive, local-first time and focus intelligence for Windows.

Chronicle polls the foreground window a few times a minute, classifies it,
stores the raw signal in a local SQLite database, and turns it into a
Shannon-entropy-based Focus Score rendered by a hand-built D3 dashboard.

The package is organised as a small set of single-responsibility modules:

    config      — central, file-backed configuration
    platform    — isolated Win32 ctypes calls (foreground window + idle time)
    tracker     — the background polling loop
    database    — SQLite storage layer (WAL mode)
    classifier  — rule-based activity categorisation
    sessions    — stitches raw events into focus sessions
    metrics     — Focus Score / entropy math
    server      — FastAPI app + JSON API
    tray        — system-tray icon and controls
"""

__version__ = "2.0.0"
__all__ = ["__version__"]
