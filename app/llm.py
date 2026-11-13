from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime

from .models import Candidate, DailyReport, ReportItem

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
RETRY_BASE_SECONDS = 5.0
MAX_RETRY_DELAY_SECONDS = 60.0


def _retry_delay(error: Exception, attempt: int) -> float:
    if isinstance(error, urllib.error.HTTPError) and error.code == 429:
        value = (error.headers.get("Retry-After") or "").strip()
        if value.isdigit():
            return min(MAX_RETRY_DELAY_SECONDS, float(value))
    return min(MAX_RETRY_DELAY_SECONDS, RETRY_BASE_SECONDS * 2 ** (attempt - 1))


def _post_completion(url: str, headers: dict, data: bytes) -> dict:
    """POST to the chat completions endpoint, retrying transient upstream errors."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = error.read().decode("utf-8", "replace").strip()[:500]
            finally:
                error.close()
            if error.code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f"AI API request failed (HTTP {error.code}): {detail}"
                ) from error
            delay = _retry_delay(error, attempt)
            logger.warning(
                "AI API returned HTTP %s (attempt %d/%d); retrying in %.0fs: %s",
                error.code, attempt, MAX_ATTEMPTS, delay, detail,
            )
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f"AI API request failed after {MAX_ATTEMPTS} attempts: {error}"
                ) from error
            delay = _retry_delay(error, attempt)
            logger.warning(
                "AI API request error (attempt %d/%d); retrying in %.0fs: %s",
                attempt, MAX_ATTEMPTS, delay, error,
            )
        time.sleep(delay)
    raise AssertionError("unreachable")


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(text[start : end + 1])


def _section_for(section_kinds: set[str]) -> str:
    if "paper" in section_kinds:
        return "paper"
    return "news"


def generate_report(settings, target_date: date, candidates: list[Candidate]) -> DailyReport:
    if not settings.ai_api_key or not settings.ai_model:
        raise RuntimeError("AI_API_KEY and AI_MODEL are required")
    prompt = settings.prompt_file.read_text(encoding="utf-8")
    payload = {
        "target_date": target_date.isoformat(),
        "candidates": [candidate.as_prompt_dict() for candidate in candidates],
    }
    body = {
        "model": settings.ai_model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    request_headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
    }
    result = _post_completion(
        f"{settings.ai_base_url}/chat/completions",
        request_headers,
        json.dumps(body).encode("utf-8"),
    )
    content = result["choices"][0]["message"]["content"]
    parsed = _extract_json(content)
    allowed_sources = {}
    for candidate in candidates:
        meta = {
            "name": candidate.source_name,
            "url": candidate.url,
            "kind": candidate.kind,
            "code_url": candidate.code_url,
        }
        if candidate.url:
            allowed_sources[candidate.url] = meta
        if candidate.source_url:
            # The source homepage is a fallback citation; do not let papers from the
            # same source overwrite each other's code_url.
            allowed_sources.setdefault(
                candidate.source_url,
                {**meta, "url": candidate.source_url, "code_url": ""},
            )
    items = []
    for raw in parsed.get("items", []):
        # Never trust an LLM-invented URL or source metadata. Only retain URLs
        # present in the fetched candidate set, and use the collector's metadata.
        matched = [
            allowed_sources[source["url"]]
            for source in raw.get("sources", [])
            if source.get("url") in allowed_sources
        ]
        if not raw.get("title") or not raw.get("summary") or not matched:
            continue
        section = _section_for({source["kind"] for source in matched})
        # A section may cite only sources of its own kind. Papers may cite only
        # Papers With Code.
        matched = [source for source in matched if source["kind"] == section]
        if not matched:
            continue
        sources = [
            {"name": source["name"], "url": source["url"]}
            for source in matched
        ]
        code_url = next((source["code_url"] for source in matched if source["code_url"]), "")
        items.append(
            ReportItem(
                title=str(raw["title"]),
                time=str(raw.get("time") or target_date.isoformat()),
                category=str(raw.get("category") or "Other"),
                summary=str(raw["summary"]),
                comment=str(raw.get("comment") or ""),
                sources=sources,
                section=section,
                code_url=code_url if section == "paper" else "",
            )
        )
    return DailyReport(
        title=str(parsed.get("title") or f"AI Daily | {target_date.isoformat()}"),
        report_date=target_date.isoformat(),
        generated_at=datetime.now(settings.timezone).isoformat(),
        items=items,
    )
