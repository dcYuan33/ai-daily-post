from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Candidate:
    source_name: str
    tier: str
    source_url: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    content: str = ""
    topics: list[str] = field(default_factory=list)
    kind: str = "news"
    code_url: str = ""
    weight: int = 1

    def as_prompt_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "tier": self.tier,
            "source_url": self.source_url,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "summary": self.summary[:2000],
            "content_excerpt": self.content[:3000],
            "topics": self.topics,
            "kind": self.kind,
            "code_url": self.code_url,
        }


@dataclass
class ReportItem:
    title: str
    time: str
    category: str
    summary: str
    comment: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    section: str = "news"
    code_url: str = ""


@dataclass
class DailyReport:
    title: str
    report_date: str
    generated_at: str
    items: list[ReportItem] = field(default_factory=list)
