"""Windows platform layer — all Win32 ``ctypes`` access lives here.

Chronicle needs exactly two things from the operating system:

    1. The title and executable of the *foreground* window.
    2. How long the user has been idle (no keyboard/mouse input).

Both are obtained through the Win32 API via :mod:`ctypes`, which is inherently
brittle: window handles go stale between calls, processes exit mid-query, and
protected/elevated processes refuse to open. Every call here is therefore
defensive — failures are logged at debug level and surfaced as ``None`` rather
than raised, so a single bad poll never takes the tracker down.

Isolating this module also keeps the rest of the codebase import-clean on
non-Windows machines (where ``ctypes.windll`` does not exist): nothing imports
``platform`` until the tracker actually starts.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from dataclasses import dataclass

logger = logging.getLogger("chronicle.platform")

# ── Win32 DLL handles ────────────────────────────────────────────────────────
# Loaded at import time; this module is only imported on Windows.
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_psapi = ctypes.windll.psapi

# OpenProcess access flags (winnt.h).
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_QUERY_INFORMATION = 0x0400
_PROCESS_VM_READ = 0x0010

# Declaring argtypes/restypes lets ctypes marshal arguments correctly across
# 32/64-bit and surfaces type errors early instead of corrupting the stack.
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.GetTickCount.restype = wintypes.DWORD


class _LASTINPUTINFO(ctypes.Structure):
    """Mirror of the Win32 ``LASTINPUTINFO`` struct used by ``GetLastInputInfo``."""

    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class WindowInfo:
    """A snapshot of the foreground window.

    Attributes:
        app_name: Executable name without extension (e.g. ``"Code"``).
        title: The window's title-bar text.
        executable: Executable filename (e.g. ``"Code.exe"``).
    """

    app_name: str
    title: str
    executable: str


def get_idle_seconds() -> float:
    """Return seconds since the last keyboard or mouse input.

    Uses ``GetLastInputInfo`` together with ``GetTickCount``. Both report
    milliseconds since boot; their difference is the idle interval. ``GetTickCount``
    wraps roughly every 49 days, which would briefly yield a negative value — we
    clamp to ``0`` to stay well-behaved across the wrap.

    Returns:
        Idle time in seconds, or ``0.0`` if the query fails.
    """
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    try:
        if not _user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        elapsed_ms = _kernel32.GetTickCount() - info.dwTime
        return max(0.0, elapsed_ms / 1000.0)
    except OSError as exc:  # pragma: no cover - defensive
        logger.debug("GetLastInputInfo failed: %s", exc)
        return 0.0


def _resolve_executable(pid: int) -> str:
    """Resolve a PID to its executable basename, or ``""`` on failure.

    Opens the process with the least privilege that works
    (``QUERY_LIMITED_INFORMATION`` first, then the legacy combination) and reads
    the image path. Elevated or protected processes will refuse to open; that is
    expected and simply yields an empty executable name.
    """
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        handle = _kernel32.OpenProcess(
            _PROCESS_QUERY_INFORMATION | _PROCESS_VM_READ, False, pid
        )
    if not handle:
        return ""

    try:
        buffer = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        # QueryFullProcessImageNameW is available on Vista+ and avoids the
        # 32-vs-64-bit pitfalls of GetModuleFileNameExW.
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            path = buffer.value
        elif _psapi.GetModuleFileNameExW(handle, None, buffer, 512):
            path = buffer.value
        else:
            return ""
        return os.path.basename(path) if path else ""
    except OSError as exc:  # pragma: no cover - defensive
        logger.debug("Could not resolve executable for pid %s: %s", pid, exc)
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def get_foreground_window() -> WindowInfo | None:
    """Return information about the currently focused window.

    Returns ``None`` when there is no usable foreground window — for example on
    the lock screen, during a desktop transition, or for a window with no title.
    Callers should treat ``None`` as "skip this poll", not as an error.
    """
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None

        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None

        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if not title:
            return None

        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        executable = _resolve_executable(pid.value) if pid.value else ""
        app_name = os.path.splitext(executable)[0] if executable else ""

        return WindowInfo(app_name=app_name, title=title, executable=executable)
    except OSError as exc:  # pragma: no cover - defensive
        logger.debug("Foreground window query failed: %s", exc)
        return None
