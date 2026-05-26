"""
Chronicle — Rule-Based Activity Classifier
Maps application names and window titles to human-readable categories.
Two-pass classification: executable match first, then window title keyword refinement.
"""

import re

# ── Category Definitions ──────────────────────────────────────────────────────

CATEGORIES = {
    "Coding":         {"color": "#6366f1", "icon": "⌨️", "productive": True},
    "Browsing":       {"color": "#3b82f6", "icon": "🌐", "productive": False},
    "Communication":  {"color": "#8b5cf6", "icon": "💬", "productive": True},
    "Entertainment":  {"color": "#f43f5e", "icon": "🎮", "productive": False},
    "Design":         {"color": "#ec4899", "icon": "🎨", "productive": True},
    "Writing":        {"color": "#14b8a6", "icon": "✍️", "productive": True},
    "Studying":       {"color": "#f59e0b", "icon": "📚", "productive": True},
    "DevOps":         {"color": "#10b981", "icon": "🔧", "productive": True},
    "File Management":{"color": "#64748b", "icon": "📁", "productive": False},
    "System":         {"color": "#475569", "icon": "⚙️", "productive": False},
    "Idle":           {"color": "#1e293b", "icon": "💤", "productive": False},
    "Other":          {"color": "#6b7280", "icon": "❓", "productive": False},
}

# ── Executable → Category Rules ───────────────────────────────────────────────
# Keys are lowercase executable names (without .exe)

EXE_RULES = {
    # Coding
    "code":            "Coding",
    "devenv":          "Coding",  # Visual Studio
    "idea64":          "Coding",  # IntelliJ IDEA
    "idea":            "Coding",
    "pycharm64":       "Coding",
    "pycharm":         "Coding",
    "webstorm64":      "Coding",
    "webstorm":        "Coding",
    "clion64":         "Coding",
    "goland64":        "Coding",
    "rider64":         "Coding",
    "sublime_text":    "Coding",
    "atom":            "Coding",
    "notepad++":       "Coding",
    "vim":             "Coding",
    "nvim":            "Coding",
    "emacs":           "Coding",
    "cursor":          "Coding",
    "windsurf":        "Coding",
    "zed":             "Coding",

    # DevOps / Terminal
    "windowsterminal": "DevOps",
    "cmd":             "DevOps",
    "powershell":      "DevOps",
    "pwsh":            "DevOps",
    "wt":              "DevOps",
    "conhost":         "DevOps",
    "mintty":          "DevOps",
    "hyper":           "DevOps",
    "alacritty":       "DevOps",
    "wezterm-gui":     "DevOps",
    "putty":           "DevOps",
    "mremoteng":       "DevOps",
    "filezilla":       "DevOps",
    "winscp":          "DevOps",
    "postman":         "DevOps",
    "insomnia":        "DevOps",
    "docker desktop":  "DevOps",
    "lazydocker":      "DevOps",

    # Communication
    "slack":           "Communication",
    "teams":           "Communication",
    "ms-teams":        "Communication",
    "discord":         "Communication",
    "telegram":        "Communication",
    "whatsapp":        "Communication",
    "signal":          "Communication",
    "zoom":            "Communication",
    "skype":           "Communication",
    "thunderbird":     "Communication",
    "outlook":         "Communication",

    # Browsers (classified by title later)
    "chrome":          "Browsing",
    "firefox":         "Browsing",
    "msedge":          "Browsing",
    "brave":           "Browsing",
    "opera":           "Browsing",
    "vivaldi":         "Browsing",
    "arc":             "Browsing",
    "safari":          "Browsing",
    "iexplore":        "Browsing",

    # Entertainment
    "spotify":         "Entertainment",
    "vlc":             "Entertainment",
    "wmplayer":        "Entertainment",
    "steam":           "Entertainment",
    "epicgameslauncher": "Entertainment",
    "battle.net":      "Entertainment",
    "origin":          "Entertainment",
    "obs64":           "Entertainment",
    "obs":             "Entertainment",

    # Design
    "photoshop":       "Design",
    "illustrator":     "Design",
    "figma":           "Design",
    "sketch":          "Design",
    "xd":              "Design",
    "afterfx":         "Design",
    "premiere":        "Design",
    "davinci resolve": "Design",
    "blender":         "Design",
    "gimp-2.10":       "Design",
    "gimp":            "Design",
    "inkscape":        "Design",
    "canva":           "Design",
    "paint":           "Design",
    "mspaint":         "Design",

    # Writing
    "winword":         "Writing",
    "excel":           "Writing",
    "powerpnt":        "Writing",
    "onenote":         "Writing",
    "notion":          "Writing",
    "obsidian":        "Writing",
    "typora":          "Writing",
    "marktext":        "Writing",
    "libreoffice":     "Writing",
    "swriter":         "Writing",

    # Studying
    "anki":            "Studying",
    "kindle":          "Studying",
    "acrord32":        "Studying",  # Adobe Reader
    "acrobat":         "Studying",
    "sumatrapdf":      "Studying",
    "foxitreader":     "Studying",
    "zotero":          "Studying",
    "mendeley":        "Studying",
    "calibre":         "Studying",

    # File Management
    "explorer":        "File Management",
    "totalcmd64":      "File Management",
    "totalcmd":        "File Management",
    "7zfm":            "File Management",
    "winrar":          "File Management",

    # System
    "taskmgr":         "System",
    "regedit":         "System",
    "mmc":             "System",
    "control":         "System",
    "systemsettings":  "System",
    "msconfig":        "System",
}

# ── Window Title → Category Refinement Rules ──────────────────────────────────
# Applied after exe classification, can override browser classification

TITLE_RULES = [
    # Coding-related browser tabs
    (r"github|gitlab|bitbucket|stackoverflow|stack overflow|codepen|codesandbox|replit|leetcode|hackerrank|codeforces",
     "Coding"),
    # Documentation / Studying in browser
    (r"docs\.|documentation|tutorial|course|udemy|coursera|khan academy|edx|pluralsight|medium\.com.*programming|dev\.to|arxiv|research paper|google scholar",
     "Studying"),
    # Communication in browser
    (r"gmail|outlook\.live|mail\.|inbox|slack\.com|discord\.com|teams\.microsoft|web\.whatsapp|web\.telegram|messenger\.com",
     "Communication"),
    # Entertainment in browser
    (r"youtube|netflix|twitch|reddit|twitter|x\.com|instagram|facebook|tiktok|hulu|disney\+|prime video|spotify\.com|9gag|imgur",
     "Entertainment"),
    # Design in browser
    (r"figma\.com|canva\.com|dribbble|behance|pinterest",
     "Design"),
    # Writing in browser
    (r"docs\.google\.com|notion\.so|overleaf|grammarly|hemingway",
     "Writing"),
    # DevOps in browser
    (r"aws\.amazon|console\.cloud\.google|portal\.azure|vercel\.com|netlify\.com|heroku\.com|docker\.com|kubernetes|jenkins|circleci|travis-ci|grafana|datadog",
     "DevOps"),
    # Shopping / Other browsing (keep as Browsing)
    (r"amazon\.|ebay\.|shopping|walmart|bestbuy",
     "Browsing"),
]


def classify(app_name, window_title, executable=""):
    """
    Classify an activity based on the app name, window title, and executable.
    Returns a category string.

    Strategy:
    1. Check executable name against EXE_RULES
    2. For browsers, refine using window title against TITLE_RULES
    3. Fall back to app_name matching against EXE_RULES
    4. Default to "Other"
    """
    if not app_name and not window_title:
        return "Idle"

    # Normalize inputs
    exe_lower = executable.lower().replace(".exe", "").strip() if executable else ""
    app_lower = app_name.lower().strip() if app_name else ""
    title_lower = window_title.lower().strip() if window_title else ""

    # Step 1: Match by executable
    category = EXE_RULES.get(exe_lower)

    # Step 2: If no exe match, try app name
    if category is None:
        category = EXE_RULES.get(app_lower)

    # Step 3: Partial match on app name
    if category is None:
        for exe_key, cat in EXE_RULES.items():
            if exe_key in app_lower or exe_key in exe_lower:
                category = cat
                break

    # Step 4: For browsers (or if still no match), refine by title
    if category in ("Browsing", None) and title_lower:
        for pattern, title_cat in TITLE_RULES:
            if re.search(pattern, title_lower, re.IGNORECASE):
                category = title_cat
                break

    # Step 5: Default
    if category is None:
        category = "Other"

    return category


def get_category_info(category):
    """Get the display info (color, icon, productive) for a category."""
    return CATEGORIES.get(category, CATEGORIES["Other"])


def get_all_categories():
    """Return all category definitions."""
    return CATEGORIES.copy()


def is_productive(category):
    """Check if a category is considered productive."""
    info = CATEGORIES.get(category, CATEGORIES["Other"])
    return info.get("productive", False)
