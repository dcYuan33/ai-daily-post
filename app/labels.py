from __future__ import annotations

CATEGORY_LABELS = {
    "Models & Research": "Models & Research",
    "Products & Developer Tools": "Products & Developer Tools",
    "Companies & Capital": "Companies & Capital",
    "Compute & Infrastructure": "Compute & Infrastructure",
    "Policy & Regulation": "Policy & Regulation",
    "Security & Society": "Security & Society",
    "Open Source Ecosystem": "Open Source Ecosystem",
    "Other": "Other",
}

SECTION_LABELS = {
    "news": "News",
    "paper": "Papers",
    "project": "Projects",
    "News": "News",
    "Paper": "Papers",
    "Project": "Projects",
    "Papers": "Papers",
    "Projects": "Projects",
    # Legacy issues: the Articles section was merged into News.
    "article": "News",
    "Article": "News",
    "Articles": "News",
}

SECTION_KEYS = {
    "news": "news",
    "paper": "paper",
    "project": "project",
    "News": "news",
    "Paper": "paper",
    "Project": "project",
    "Papers": "paper",
    "Projects": "project",
    # Legacy issues: the Articles section was merged into News.
    "article": "news",
    "Article": "news",
    "Articles": "news",
}

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_ABBR = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def category_label(value: str) -> str:
    return CATEGORY_LABELS.get(value, value)


def section_key(value: str) -> str:
    return SECTION_KEYS.get(value, value or "news")


def section_label(value: str) -> str:
    return SECTION_LABELS.get(value, value)
