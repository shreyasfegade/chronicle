"""Rule-based activity classifier.

Classification is deliberately simple and transparent — no ML, no network. Each
event is mapped to a category in two passes:

    1. **Executable match.** The process name (e.g. ``code``, ``chrome``) is
       looked up in :data:`EXE_RULES`.
    2. **Title refinement.** For browsers — and for anything still unmatched —
       the window title is tested against :data:`TITLE_RULES`, so a Chrome tab on
       GitHub becomes *Coding* while a Chrome tab on YouTube becomes
       *Entertainment*.

Users can extend both passes without touching code by adding a ``custom_rules``
block to ``config.json`` (see :func:`apply_custom_rules`).
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("chronicle.classifier")

# ── Category metadata ────────────────────────────────────────────────────────
# ``color`` is mirrored in the dashboard; ``productive`` drives the productive-%
# stat. Order here is also the canonical display order.

CATEGORIES: dict[str, dict[str, Any]] = {
    "Coding":          {"color": "#6366f1", "icon": "⌨", "productive": True},
    "DevOps":          {"color": "#10b981", "icon": "🔧", "productive": True},
    "Writing":         {"color": "#14b8a6", "icon": "✍", "productive": True},
    "Design":          {"color": "#ec4899", "icon": "🎨", "productive": True},
    "Studying":        {"color": "#f59e0b", "icon": "📚", "productive": True},
    "Communication":   {"color": "#8b5cf6", "icon": "💬", "productive": True},
    "Browsing":        {"color": "#3b82f6", "icon": "🌐", "productive": False},
    "Entertainment":   {"color": "#f43f5e", "icon": "🎮", "productive": False},
    "File Management": {"color": "#64748b", "icon": "📁", "productive": False},
    "System":          {"color": "#475569", "icon": "⚙", "productive": False},
    "Idle":            {"color": "#334155", "icon": "💤", "productive": False},
    "Other":           {"color": "#6b7280", "icon": "•", "productive": False},
}

# ── Executable → category ────────────────────────────────────────────────────
# Keys are lowercase executable names without the ``.exe`` suffix.

EXE_RULES: dict[str, str] = {
    # Coding
    "code": "Coding", "devenv": "Coding", "idea64": "Coding", "idea": "Coding",
    "pycharm64": "Coding", "pycharm": "Coding", "webstorm64": "Coding",
    "webstorm": "Coding", "clion64": "Coding", "goland64": "Coding",
    "rider64": "Coding", "sublime_text": "Coding", "atom": "Coding",
    "notepad++": "Coding", "vim": "Coding", "nvim": "Coding", "emacs": "Coding",
    "cursor": "Coding", "windsurf": "Coding", "zed": "Coding",
    # DevOps / terminals
    "windowsterminal": "DevOps", "cmd": "DevOps", "powershell": "DevOps",
    "pwsh": "DevOps", "wt": "DevOps", "conhost": "DevOps", "mintty": "DevOps",
    "hyper": "DevOps", "alacritty": "DevOps", "wezterm-gui": "DevOps",
    "putty": "DevOps", "mremoteng": "DevOps", "filezilla": "DevOps",
    "winscp": "DevOps", "postman": "DevOps", "insomnia": "DevOps",
    "docker desktop": "DevOps", "lazydocker": "DevOps",
    # Communication
    "slack": "Communication", "teams": "Communication", "ms-teams": "Communication",
    "discord": "Communication", "telegram": "Communication",
    "whatsapp": "Communication", "signal": "Communication", "zoom": "Communication",
    "skype": "Communication", "thunderbird": "Communication", "outlook": "Communication",
    # Browsers (refined by title below)
    "chrome": "Browsing", "firefox": "Browsing", "msedge": "Browsing",
    "brave": "Browsing", "opera": "Browsing", "vivaldi": "Browsing",
    "arc": "Browsing", "safari": "Browsing", "iexplore": "Browsing",
    # Entertainment
    "spotify": "Entertainment", "vlc": "Entertainment", "wmplayer": "Entertainment",
    "steam": "Entertainment", "epicgameslauncher": "Entertainment",
    "battle.net": "Entertainment", "origin": "Entertainment", "obs64": "Entertainment",
    "obs": "Entertainment",
    # Design
    "photoshop": "Design", "illustrator": "Design", "figma": "Design",
    "sketch": "Design", "xd": "Design", "afterfx": "Design", "premiere": "Design",
    "davinci resolve": "Design", "blender": "Design", "gimp-2.10": "Design",
    "gimp": "Design", "inkscape": "Design", "canva": "Design", "mspaint": "Design",
    # Writing
    "winword": "Writing", "excel": "Writing", "powerpnt": "Writing",
    "onenote": "Writing", "notion": "Writing", "obsidian": "Writing",
    "typora": "Writing", "marktext": "Writing", "libreoffice": "Writing",
    "swriter": "Writing",
    # Studying
    "anki": "Studying", "kindle": "Studying", "acrord32": "Studying",
    "acrobat": "Studying", "sumatrapdf": "Studying", "foxitreader": "Studying",
    "zotero": "Studying", "mendeley": "Studying", "calibre": "Studying",
    # File management
    "explorer": "File Management", "totalcmd64": "File Management",
    "totalcmd": "File Management", "7zfm": "File Management", "winrar": "File Management",
    # System
    "taskmgr": "System", "regedit": "System", "mmc": "System", "control": "System",
    "systemsettings": "System", "msconfig": "System",
}

# ── Window title → category ──────────────────────────────────────────────────
# Applied after the executable pass; the first matching pattern wins.

TITLE_RULES: list[tuple[str, str]] = [
    (r"github|gitlab|bitbucket|stack ?overflow|codepen|codesandbox|replit|leetcode|hackerrank|codeforces", "Coding"),
    (r"docs\.|documentation|tutorial|udemy|coursera|khan academy|edx|pluralsight|dev\.to|arxiv|google scholar", "Studying"),
    (r"gmail|outlook\.live|mail\.|inbox|slack\.com|discord\.com|teams\.microsoft|web\.whatsapp|web\.telegram|messenger\.com", "Communication"),
    (r"youtube|netflix|twitch|reddit|twitter|x\.com|instagram|facebook|tiktok|hulu|disney\+|prime video|9gag|imgur", "Entertainment"),
    (r"figma\.com|canva\.com|dribbble|behance|pinterest", "Design"),
    (r"docs\.google\.com|notion\.so|overleaf|grammarly|hemingway", "Writing"),
    (r"aws\.amazon|console\.cloud\.google|portal\.azure|vercel\.com|netlify\.com|heroku|kubernetes|jenkins|circleci|grafana|datadog", "DevOps"),
    (r"amazon\.|ebay\.|walmart|bestbuy", "Browsing"),
]

# Compiled lazily so custom rules added at startup are picked up.
_compiled_title_rules: list[tuple[re.Pattern[str], str]] | None = None


def apply_custom_rules(custom: dict[str, Any]) -> None:
    """Merge user-supplied rules from configuration on top of the built-ins.

    The expected shape (all keys optional)::

        {
          "exe":   {"myeditor": "Coding"},
          "title": [["jira|confluence", "DevOps"]],
          "categories": {"Coding": {"color": "#ff0000"}}
        }

    Executable keys are lowercased; title rules are prepended so they take
    precedence over the defaults.
    """
    global _compiled_title_rules
    if not custom:
        return

    for exe, category in (custom.get("exe") or {}).items():
        EXE_RULES[exe.lower()] = category

    title_rules = custom.get("title") or []
    for entry in reversed(title_rules):
        try:
            pattern, category = entry
            TITLE_RULES.insert(0, (pattern, category))
        except (ValueError, TypeError):
            logger.warning("Skipping malformed custom title rule: %r", entry)

    for name, info in (custom.get("categories") or {}).items():
        CATEGORIES.setdefault(name, dict(CATEGORIES["Other"])).update(info)

    _compiled_title_rules = None  # force recompile
    logger.info("Applied %d custom classification rule group(s)", len(custom))


def _title_rules() -> list[tuple[re.Pattern[str], str]]:
    """Return the compiled title rules, compiling on first use."""
    global _compiled_title_rules
    if _compiled_title_rules is None:
        _compiled_title_rules = [
            (re.compile(pattern, re.IGNORECASE), category)
            for pattern, category in TITLE_RULES
        ]
    return _compiled_title_rules


def classify(app_name: str, window_title: str, executable: str = "") -> str:
    """Classify an activity into a category name.

    Args:
        app_name: Executable name without extension.
        window_title: The window's title-bar text.
        executable: Full executable filename (optional, improves matching).

    Returns:
        A category from :data:`CATEGORIES` (``"Other"`` if nothing matches).
    """
    if not app_name and not window_title:
        return "Idle"

    exe_key = executable.lower().removesuffix(".exe").strip()
    app_key = app_name.lower().strip()
    title = window_title.lower().strip()

    category = EXE_RULES.get(exe_key) or EXE_RULES.get(app_key)

    # Partial executable/app match (e.g. "Code - Insiders").
    if category is None:
        for key, cat in EXE_RULES.items():
            if key and (key in app_key or key in exe_key):
                category = cat
                break

    # Refine browsers, or rescue anything still unmatched, using the title.
    if category in ("Browsing", None) and title:
        for pattern, cat in _title_rules():
            if pattern.search(title):
                category = cat
                break

    return category or "Other"


def get_category_info(category: str) -> dict[str, Any]:
    """Return display metadata (color/icon/productive) for a category."""
    return CATEGORIES.get(category, CATEGORIES["Other"])


def get_all_categories() -> dict[str, dict[str, Any]]:
    """Return a copy of all category definitions."""
    return {name: dict(info) for name, info in CATEGORIES.items()}


def is_productive(category: str) -> bool:
    """Return whether a category counts toward productive time."""
    return bool(get_category_info(category).get("productive", False))
