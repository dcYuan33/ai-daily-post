from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    root: Path
    timezone: ZoneInfo
    ai_api_key: str
    ai_base_url: str
    ai_model: str
    sources_config: Path
    prompt_file: Path


def _path(value: str, default: str) -> Path:
    return (ROOT / (value or default)).resolve()


def load_settings() -> Settings:
    timezone_name = os.getenv("REPORT_TIMEZONE", "Asia/Shanghai")
    return Settings(
        root=ROOT,
        timezone=ZoneInfo(timezone_name),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        ai_model=os.getenv("AI_MODEL", ""),
        sources_config=_path(os.getenv("SOURCES_CONFIG", "config/sources.yaml"), "config/sources.yaml"),
        prompt_file=_path(os.getenv("PROMPT_FILE", "prompts/ai-daily.md"), "prompts/ai-daily.md"),
    )
