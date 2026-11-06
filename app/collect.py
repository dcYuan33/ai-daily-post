from __future__ import annotations

import html
import json
import logging
import os
import re
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from .models import Candidate

USER_AGENT = "ai-daily/0.1 (+https://github.com/)"
TIMEOUT = 10
GITHUB_API_URL = "https://api.github.com/repos"
REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger(__name__)


def load_sources(path):
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle).get("sources", [])


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, time):
        return datetime.combine(date.today(), value)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None


def _clean_text(value: str) -> str:
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


def _article_text(soup: BeautifulSoup) -> str:
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        node.decompose()
    article = soup.find("article") or soup.find("main") or soup.body
    if not article:
        return ""
    paragraphs = [_clean_text(p.get_text(" ", strip=True)) for p in article.find_all(["p", "li"])]
    return "\n".join(p for p in paragraphs if len(p) >= 30)[:12000]


def _page_date(soup: BeautifulSoup) -> datetime | None:
    for selector in (
        "meta[property='article:published_time']",
        "meta[property='og:published_time']",
        "meta[name='date']",
        "meta[name='pubdate']",
    ):
        node = soup.select_one(selector)
        if node:
            value = node.get("content") or node.get("datetime") or node.get_text(" ", strip=True)
            parsed = _parse_datetime(value)
            if parsed:
                return parsed

    def structured_date(node):
        if isinstance(node, list):
            return next((value for child in node if (value := structured_date(child))), None)
        if isinstance(node, dict):
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if any(kind in {"Article", "NewsArticle", "BlogPosting", "TechArticle", "Report"} for kind in types):
                parsed = _parse_datetime(node.get("datePublished"))
                if parsed:
                    return parsed
            return structured_date(node.get("@graph", []))
        return None

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            parsed = structured_date(json.loads(script.get_text()))
        except (TypeError, ValueError):
            continue
        if parsed:
            return parsed
    node = soup.select_one("time[datetime]")
    return _parse_datetime(node.get("datetime")) if node else None


def _local_date(value: datetime) -> date:
    # Date-only / naive publication stamps use the date shown by the source.
    return value.astimezone(REPORT_TIMEZONE).date() if value.tzinfo else value.date()


def fetch_page(url: str) -> tuple[str, str, datetime | None]:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        published_at = _page_date(soup)
        return response.url, _article_text(soup), published_at
    except requests.RequestException as exc:
        logger.warning("Article fetch failed %s: %s", url, exc)
        return url, "", None


def _rss_candidates(source: dict, target_date: date, limit: int = 40) -> list[Candidate]:
    try:
        response = requests.get(source["rss"], headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except requests.RequestException as exc:
        logger.warning("Source fetch failed %s: %s", source["name"], exc)
        return []
    result: list[Candidate] = []
    for entry in parsed.entries[:limit]:
        published = _parse_datetime(entry.get("published") or entry.get("updated"))
        if published and _local_date(published) != target_date:
            continue
        url = entry.get("link") or source["url"]
        result.append(
            Candidate(
                source_name=source["name"],
                source_url=source["url"],
                title=_clean_text(entry.get("title", "")),
                url=url,
                published_at=published,
                summary=_clean_text(entry.get("summary", "") or entry.get("description", "")),
                topics=source.get("topics", []),
                kind=source.get("kind", "news"),
                weight=source.get("weight", 1),
            )
        )
    return result


def _webpage_candidates(source: dict, target_date: date, limit: int = 20) -> list[Candidate]:
    try:
        response = requests.get(source["url"], headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Source fetch failed %s: %s", source["name"], exc)
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["nav", "header", "footer"]):
        node.decompose()
    container = soup.find("main") or soup
    source_host = urlsplit(response.url).hostname
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for link in container.find_all("a", href=True):
        title = _clean_text(link.get_text(" ", strip=True))
        url = urljoin(response.url, link["href"]).split("#", 1)[0]
        parsed_url = urlsplit(url)
        if (not title or len(title) < 12 or url in seen
                or parsed_url.scheme not in {"http", "https"}
                or parsed_url.hostname != source_host
                or parsed_url.path.rstrip("/") == urlsplit(response.url).path.rstrip("/")):
            continue
        # Section landing pages rarely expose reliable dates. Keep candidates and let article verification/LLM decide.
        seen.add(url)
        candidates.append(
            Candidate(
                source_name=source["name"],
                source_url=source["url"],
                title=title,
                url=url,
                summary="",
                topics=source.get("topics", []),
                kind=source.get("kind", "news"),
                weight=source.get("weight", 1),
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _paper_candidates(source: dict, target_date: date, limit: int = 12) -> list[Candidate]:
    """Fetch papers that ship a public code repository for the target day.

    paperswithcode.com now redirects to Hugging Face Papers. The daily-papers API
    keeps the original submission date, so papers can be filtered by report day
    without relying on fragile article-page date markup.
    """
    api = source.get("api")
    if not api:
        return []
    try:
        response = requests.get(
            api,
            params={"date": target_date.isoformat()},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Paper source fetch failed %s: %s", source["name"], exc)
        return []
    if not isinstance(payload, list):
        logger.warning("Paper source returned an invalid payload %s", source["name"])
        return []
    result: list[Candidate] = []
    for entry in payload:
        paper = entry.get("paper", entry) if isinstance(entry, dict) else {}
        code_url = _clean_text(paper.get("githubRepo") or "")
        if not code_url:
            continue
        paper_id = str(paper.get("id") or "").strip()
        title = _clean_text(paper.get("title", ""))
        if not paper_id or not title:
            continue
        published = _parse_datetime(paper.get("submittedOnDailyAt") or paper.get("publishedAt"))
        summary = _clean_text(paper.get("summary", ""))
        result.append(
            Candidate(
                source_name=source["name"],
                source_url=source["url"],
                title=title,
                url=f"https://huggingface.co/papers/{paper_id}",
                published_at=published,
                summary=summary,
                content=summary,
                topics=source.get("topics", []),
                kind=source.get("kind", "paper"),
                code_url=code_url,
                weight=source.get("weight", 1),
            )
        )
        if len(result) >= limit:
            break
    logger.info("Paper source %s: %d papers with code", source["name"], len(result))
    return result


def _github_headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_trending_candidates(source: dict, target_date: date, limit: int = 8) -> list[Candidate]:
    """Keep only recently created repositories from the GitHub Trending page.

    GitHub Trending has no creation-date filter, so each trending repository is
    checked through the public API. Established projects that occasionally trend
    are excluded instead of being clustered into the Projects section.
    """
    try:
        response = requests.get(
            source["url"],
            params={"since": source.get("since", "daily")},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Trending source fetch failed %s: %s", source["name"], exc)
        return []
    soup = BeautifulSoup(response.text, "html.parser")
    cutoff = target_date - timedelta(days=int(source.get("max_age_days", 90)))
    headers = _github_headers()
    result: list[Candidate] = []
    for card in soup.select("article.Box-row"):
        link = card.select_one("h2 a[href]")
        if not link:
            continue
        repo_path = link.get("href", "").strip("/")
        if not re.fullmatch(r"[^/]+/[^/]+", repo_path):
            continue
        card_text = _clean_text(card.get_text(" ", strip=True))
        stars_today = ""
        match = re.search(r"([\d,]+)\s+stars?\s+today", card_text)
        if match:
            stars_today = match.group(1)
        try:
            details = requests.get(
                f"{GITHUB_API_URL}/{repo_path}",
                headers=headers,
                timeout=TIMEOUT,
            )
            details.raise_for_status()
            repo = details.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("GitHub repository lookup failed %s: %s", repo_path, exc)
            continue
        if not isinstance(repo, dict):
            continue
        created = _parse_datetime(repo.get("created_at"))
        if not created or created.date() < cutoff or created.date() > target_date:
            continue
        if repo.get("archived") or repo.get("fork"):
            continue
        description_node = card.select_one("p")
        description = _clean_text(
            (description_node.get_text(" ", strip=True) if description_node else "")
            or repo.get("description", "")
        )
        stars = int(repo.get("stargazers_count") or 0)
        summary_parts = [f"New GitHub repository trending on {target_date.isoformat()}."]
        if description:
            summary_parts.append(description)
        stars_text = f"Created {created.date().isoformat()}; {stars:,} stars in total"
        if stars_today:
            stars_text += f", {stars_today} stars today"
        summary_parts.append(stars_text + ".")
        summary = " ".join(summary_parts)
        topics = list(source.get("topics", []))
        topics.extend(str(topic) for topic in (repo.get("topics") or [])[:6] if topic)
        result.append(
            Candidate(
                source_name=source["name"],
                source_url=source["url"],
                title=repo_path,
                url=repo.get("html_url") or f"https://github.com/{repo_path}",
                published_at=datetime.combine(target_date, time.min),
                summary=summary,
                content=summary,
                topics=topics,
                kind=source.get("kind", "project"),
                weight=source.get("weight", 1),
            )
        )
        if len(result) >= limit:
            break
    logger.info("Trending source %s: %d new repositories", source["name"], len(result))
    return result


def enrich_candidates(candidates: list[Candidate], max_articles: int = 120) -> list[Candidate]:
    # Landing pages can expose many links. Bound and parallelize article requests so a
    # single slow source cannot consume the whole GitHub Actions job.
    # Round-robin sources so the first few configured sites cannot exhaust the
    # budget. Within each source, dated RSS entries come before undated links.
    # Sources with a higher weight (such as papers) receive more slots per round.
    groups: dict[str, deque] = {}
    weights: dict[str, int] = {}
    for candidate in sorted(candidates, key=lambda item: item.published_at is None):
        groups.setdefault(candidate.source_name, deque()).append(candidate)
        weights[candidate.source_name] = max(weights.get(candidate.source_name, 1), candidate.weight)
    selected = []
    while len(selected) < max_articles and any(groups.values()):
        for name, group in groups.items():
            for _ in range(max(1, weights.get(name, 1))):
                if not group:
                    break
                selected.append(group.popleft())
                if len(selected) == max_articles:
                    break
            if len(selected) == max_articles:
                break
    logger.info("Selected %d/%d candidates across %d sources: %s",
                len(groups), len(selected), len(candidates),
                dict(Counter(candidate.source_name for candidate in selected)))
    pending = [candidate for candidate in selected if not candidate.content]
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(fetch_page, candidate.url): candidate for candidate in pending}
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                final_url, content, published_at = future.result()
            except Exception:
                final_url, content, published_at = candidate.url, "", None
            candidate.url = final_url
            candidate.content = content
            candidate.published_at = candidate.published_at or published_at
    return selected


def collect_candidates(sources_path, target_date: date) -> list[Candidate]:
    candidates: list[Candidate] = []
    for source in load_sources(sources_path):
        if source.get("collection") == "papers":
            entries = _paper_candidates(source, target_date, limit=int(source.get("limit", 12)))
        elif source.get("collection") == "trending":
            entries = _github_trending_candidates(source, target_date, limit=int(source.get("limit", 8)))
        else:
            entries = _rss_candidates(source, target_date) if source.get("rss") else []
            if not entries:
                entries = _webpage_candidates(source, target_date)
        logger.info("Source %s: %d candidates", source["name"], len(entries))
        candidates.extend(entries)
    # URL/title de-duplication before expensive article fetches.
    unique: dict[str, Candidate] = {}
    for item in candidates:
        key = re.sub(r"\W+", " ", item.url.lower()).strip() or re.sub(r"\W+", " ", item.title.lower()).strip()
        unique.setdefault(key, item)
    enriched = enrich_candidates(list(unique.values()))
    dated_today = sum(bool(item.published_at and _local_date(item.published_at) == target_date) for item in enriched)
    logger.info("Enriched %d candidates: %d dated %s; %d with article text",
                len(enriched), dated_today, target_date, sum(bool(item.content) for item in enriched))
    eligible = [item for item in enriched if not item.published_at or _local_date(item.published_at) == target_date]
    logger.info("Excluded %d articles dated outside the report day; %d sent to AI",
                len(enriched) - len(eligible), len(eligible))
    return eligible
