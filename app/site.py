from __future__ import annotations

import html
import json
import logging
import math
from collections import OrderedDict
from dataclasses import asdict
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .models import DailyReport, ReportItem

ASSETS = Path(__file__).parent / "assets"
SITE_URL = "https://dcyuan33.github.io/ai-daily-post/"
SITE_TITLE = "AI 日报 · AI Daily Post"
SITE_DESCRIPTION = "每日 AI 资讯精选，基于 A/B/C 信源整理，保留原始来源。"
REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")
FEED_LIMIT = 50
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
THEMES = (("editorial", "经典", "#faf8f5", "#c44b2b"), ("mono", "极简", "#ffffff", "#111111"), ("dune", "沙丘", "#faf6f0", "#b57b31"), ("blueprint", "蓝图", "#f8faff", "#2563eb"), ("ink", "墨夜", "#191714", "#ee8866"))
ICONS = {
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    "link": '<path d="m10 13 4-4m-6 7-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 1 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
    "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18m-12 5h.01M12 16h.01M15 16h.01"/>',
    "up": '<path d="m6 14 6-6 6 6"/>',
    "external": '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
    "book": '<path d="M12 6c-3-3-7-3-10-2v15c3-1 7-1 10 2 3-3 7-3 10-2V4c-3-1-7-1-10 2Zm0 0v15"/>',
    "rss": '<path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/>',
}


def _icon(name: str) -> str:
    return f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'


def _e(value: str) -> str:
    return html.escape(str(value), quote=True)


def report_to_dict(report: DailyReport) -> dict:
    return asdict(report)


def report_from_dict(data: dict) -> DailyReport:
    date.fromisoformat(data["report_date"])
    return DailyReport(
        title=data["title"], report_date=data["report_date"],
        generated_at=data.get("generated_at", ""),
        items=[ReportItem(**item) for item in data.get("items", [])],
    )


def _load_reports(site_root: Path) -> list[DailyReport]:
    reports = {}
    for path in sorted((site_root / "issues").glob("*/data.json")):
        try:
            report = report_from_dict(json.loads(path.read_text(encoding="utf-8")))
            if report.report_date != path.parent.name:
                raise ValueError("Report date does not match its directory")
            reports[report.report_date] = report
        except (OSError, KeyError, TypeError, ValueError) as exc:
            logging.warning("Skipping invalid report %s: %s", path, exc)
    return sorted(reports.values(), key=lambda r: r.report_date, reverse=True)


def _reading_minutes(report: DailyReport) -> int:
    return max(1, math.ceil(sum(len(item.summary) + len(item.comment) for item in report.items) / 400))


def _sidebar(reports: list[DailyReport], prefix: str, current: str, archive: bool) -> str:
    months: OrderedDict[str, list[DailyReport]] = OrderedDict()
    for report in reports:
        months.setdefault(report.report_date[:7], []).append(report)
    groups = []
    for month, issues in months.items():
        links = []
        for report in issues:
            day = date.fromisoformat(report.report_date)
            weekday = "一二三四五六日"[day.weekday()]
            active = report.report_date == current and not archive
            latest = report is reports[0]
            searchable = " ".join([report.report_date, report.title] + [item.title + " " + item.summary for item in report.items])
            links.append(f'''<a class="date-entry{' active' if active else ''}" href="{prefix}issues/{report.report_date}/" data-date-entry data-search-text="{_e(searchable)}"{' aria-current="page"' if active else ''}>
                <div class="date-entry-top"><time datetime="{report.report_date}">{day:%m.%d}</time><span>周{weekday}</span>{'<i class="latest-dot" title="最新一期"></i>' if latest else ''}</div>
                <div class="date-entry-bottom"><span>{len(report.items)} 条资讯</span><span class="entry-arrow">↗</span></div></a>''')
        groups.append(f'<section class="date-group"><h3>{month[:4]} 年 {int(month[5:])} 月</h3>{"".join(links)}</section>')
    return f'''<aside class="sidebar" id="archive-sidebar" aria-label="日报归档">
        <div class="sidebar-heading"><span>{_icon('calendar')} 日报归档</span><button class="icon-button mobile-only" data-close-archive aria-label="关闭归档">{_icon('close')}</button></div>
        <label class="sidebar-search">{_icon('search')}<input type="search" data-archive-search placeholder="搜索日期或关键词" aria-label="搜索日期或关键词" autocomplete="off"></label>
        <div class="date-list">{"".join(groups) or '<p class="sidebar-empty">等待第一期日报</p>'}<p class="sidebar-empty" data-search-empty hidden>没有找到匹配的日报</p></div>
        <a class="all-issues{' active' if archive else ''}" href="{prefix}archive.html">全部归档 <span>{len(reports)}</span></a>
        <div class="sidebar-footer"><span class="live-dot"></span> 每日更新 · UTC+8<br><small>A / B / C 信源 · AI 辅助整理</small></div>
    </aside>'''


def _page(title: str, content: str, reports: list[DailyReport], prefix: str = "./", current: str = "", archive: bool = False) -> str:
    theme_options = "".join(f'<button type="button" data-set-theme="{key}" aria-pressed="false"><span class="theme-swatch" style="--swatch-bg:{bg};--swatch-accent:{accent}"></span>{name}<span class="theme-check">✓</span></button>' for key, name, bg, accent in THEMES)
    return f'''<!doctype html>
<html lang="zh-CN" data-theme="editorial"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="每日 AI 资讯精选，基于 A/B/C 信源整理，保留原始来源。">
<meta name="color-scheme" content="light dark"><title>{_e(title)}</title>
<script>try{{const t=localStorage.getItem('ai-daily-theme');if(['editorial','mono','dune','blueprint','ink'].includes(t))document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
<link rel="stylesheet" href="{prefix}assets/style.css"><script defer src="{prefix}assets/site.js"></script>
<link rel="alternate" type="application/rss+xml" title="AI 日报 RSS" href="{SITE_URL}feed.xml">
</head><body data-site-root="{prefix}">
<a class="skip-link" href="#main">跳到正文</a>
<header class="site-header"><div class="header-inner">
<button class="icon-button mobile-only" data-open-archive aria-controls="archive-sidebar" aria-expanded="false" aria-label="打开日报归档">{_icon('menu')}</button>
<a class="brand" href="{prefix}index.html"><span class="brand-symbol" aria-hidden="true">a<span>i</span></span><span>AI 日报 <small>DAILY POST</small></span></a>
<span class="header-note">世界变化很快，读点重要的。</span>
<div class="header-actions"><button class="icon-button copy-button" data-copy-link aria-label="复制本期链接">{_icon('link')}</button>
<details class="theme-picker"><summary class="icon-button" aria-label="切换阅读主题">{_icon('sun')}</summary><div class="theme-menu"><p>阅读主题</p>{theme_options}</div></details>
<a class="icon-button repo-link" href="{prefix}feed.xml" aria-label="RSS 订阅" title="RSS 订阅">{_icon('rss')}</a>
<a class="icon-button repo-link" href="https://github.com/dcYuan33/AI_Daily_Post" target="_blank" rel="noopener noreferrer" aria-label="GitHub 仓库">{_icon('external')}</a></div>
</div><div class="reading-progress" data-reading-progress></div></header>
<div class="sidebar-backdrop" data-close-archive hidden></div>
<div class="reader-layout">{_sidebar(reports, prefix, current, archive)}<main id="main" class="main-pane" tabindex="-1">{content}</main></div>
<div class="status-toast" role="status" aria-live="polite" data-status hidden></div>
</body></html>'''


def _overview(report: DailyReport) -> str:
    categories: OrderedDict[str, list[tuple[int, ReportItem]]] = OrderedDict()
    for index, item in enumerate(report.items, 1):
        categories.setdefault(item.category or "其他", []).append((index, item))
    groups = []
    for category, items in categories.items():
        links = "".join(f'<li><a href="#item-{index}"><span class="overview-bullet"></span><span>{_e(item.title)}</span><span class="item-tag">#{index:02d}</span></a></li>' for index, item in items)
        groups.append(f'<section class="overview-group"><h3>{_e(category)} <span>{len(items)}</span></h3><ul>{links}</ul></section>')
    if not groups:
        groups.append('<p class="empty-note">本期暂未发现足够可靠的重要 AI 新进展。宁缺毋滥，明天再见。</p>')
    return f'<section class="overview" aria-labelledby="overview-title"><div class="section-kicker"><h2 id="overview-title">今日概览</h2><span>THE DAILY BRIEF</span></div>{"".join(groups)}</section>'


def _safe_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def _paragraphs(text: str) -> str:
    return "".join(f'<p>{_e(line)}</p>' for line in text.splitlines() if line.strip())


def _article_item(index: int, item: ReportItem) -> str:
    sources = "".join(f'<a class="source-link" href="{_e(source["url"])}" target="_blank" rel="noopener noreferrer"><span class="source-tier">{_e(source["tier"])}</span>{_e(source["name"])}{_icon("external")}</a>' for source in item.sources if _safe_url(source["url"]))
    comment = f'<aside class="comment"><span class="comment-label">简评 / OUR TAKE</span>{_paragraphs(item.comment)}</aside>' if item.comment else ""
    return f'''<article class="article-item" id="item-{index}" data-article>
        <div class="article-meta"><span class="item-tag">#{index:02d}</span><span>{_e(item.category)}</span><span class="meta-dot">·</span><span>{_e(item.time)}</span></div>
        <h2><a href="#item-{index}">{_e(item.title)}</a></h2>
        <div class="article-body">{_paragraphs(item.summary)}</div>{comment}
        <div class="sources"><span class="sources-label">来源</span>{sources}</div>
    </article>'''


def _reader(report: DailyReport, reports: list[DailyReport], prefix: str) -> str:
    day = date.fromisoformat(report.report_date)
    index = next(i for i, issue in enumerate(reports) if issue.report_date == report.report_date)
    newer = reports[index - 1] if index else None
    older = reports[index + 1] if index + 1 < len(reports) else None
    weekday = "一二三四五六日"[day.weekday()]
    prev_link = f'<a href="{prefix}issues/{older.report_date}/"><span>← 上一期</span><strong>{older.report_date}</strong></a>' if older else '<div class="pager-disabled"><span>← 上一期</span><strong>已是最早一期</strong></div>'
    next_link = f'<a href="{prefix}issues/{newer.report_date}/"><span>下一期 →</span><strong>{newer.report_date}</strong></a>' if newer else f'<a href="{prefix}archive.html"><span>继续探索 →</span><strong>浏览全部归档</strong></a>'
    toc_links = "".join(f'<a href="#item-{i}"><span class="item-tag">#{i:02d}</span><span>{_e(item.title)}</span></a>' for i, item in enumerate(report.items, 1))
    toc = f'<details class="floating-toc"><summary aria-label="打开本期目录">{_icon("menu")}<span>目录</span></summary><nav class="toc-panel" aria-label="本期目录"><h2>本期目录 · {len(report.items)} 条</h2>{toc_links}</nav></details>' if report.items else ""
    articles = "".join(_article_item(i, item) for i, item in enumerate(report.items, 1))
    try:
        generated = datetime.fromisoformat(report.generated_at).strftime("%Y.%m.%d %H:%M %z")
    except ValueError:
        generated = report.generated_at
    return f'''<div class="reading-shell" data-report-date="{report.report_date}">
        <header class="issue-header"><div class="issue-dateline"><span>{MONTHS[day.month - 1].upper()} {day.year}</span><span class="dateline-rule"></span><span>NO. {len(reports) - index:03d}</span></div>
        <div class="issue-title-row"><h1><time datetime="{report.report_date}">{day:%m.%d}</time><span class="title-period"> / </span><span class="title-cn">AI 日报</span></h1><span class="weekday">星期{weekday}</span></div>
        <p class="issue-subtitle">从纷繁的信息中，找到值得关注的 AI 进展。</p>
        <div class="issue-metadata"><span>{_icon('book')}{len(report.items)} 条精选</span><span>约 {_reading_minutes(report)} 分钟阅读</span><span>Asia/Shanghai</span></div></header>
        {_overview(report)}
        <div class="article-section-label"><span>深入阅读</span><span class="dateline-rule"></span><span>IN DETAIL</span></div>
        <div class="articles">{articles or '<p class="empty-note">本期暂无详细条目，可以通过左侧归档浏览往期内容。</p>'}</div>
        <nav class="issue-pager" aria-label="相邻日报">{prev_link}{next_link}</nav>
        <footer class="reading-footer"><a class="footer-brand" href="{prefix}index.html">AI DAILY POST<span>保持好奇，保持判断。</span></a><p>AI 辅助整理 · 原始来源可追溯<br>生成于 {_e(generated)}{'' if not generated else ' · 报告日期采用 UTC+8'}</p></footer>
        {toc}<button class="back-to-top icon-button" data-back-top aria-label="回到顶部" hidden>{_icon('up')}</button>
    </div>'''


def _archive_content(reports: list[DailyReport], prefix: str) -> str:
    entries = []
    for report in reports:
        day = date.fromisoformat(report.report_date)
        excerpt = report.items[0].title if report.items else "本期暂无足够可靠的重要 AI 新进展"
        searchable = " ".join([report.report_date, report.title] + [item.title + " " + item.summary for item in report.items])
        entries.append(f'''<a class="archive-entry" href="{prefix}issues/{report.report_date}/" data-archive-entry data-search-text="{_e(searchable)}"><time datetime="{report.report_date}"><small>{day.year}</small>{day:%m.%d}</time><div><h2>{_e(report.title)}</h2><p>{_e(excerpt)}</p><span>{len(report.items)} 条精选 · 约 {_reading_minutes(report)} 分钟阅读</span></div><span class="archive-arrow">↗</span></a>''')
    return f'''<div class="reading-shell archive-shell"><header class="issue-header"><div class="issue-dateline"><span>THE COLLECTION</span><span class="dateline-rule"></span><span>{len(reports):03d} ISSUES</span></div><h1 class="archive-title">每一天，都值得回看。</h1><p class="issue-subtitle">在这里，找到你错过的 AI 进展。</p></header>
        <label class="archive-search">{_icon('search')}<input type="search" data-list-search placeholder="搜索日报日期、标题或关键词…" aria-label="搜索全部日报"></label>
        <div class="archive-list">{"".join(entries) or '<p class="empty-note">第一期日报尚未生成。</p>'}<p class="empty-note" data-list-empty hidden>没有找到匹配的日报，试试其他关键词。</p></div></div>'''


def _xml(value: str) -> str:
    text = "".join(ch for ch in str(value) if ch in "\t\n\r" or "\x20" <= ch <= "\ud7ff" or "\ue000" <= ch <= "\ufffd" or ch >= "\U00010000")
    return html.escape(text, quote=True)


def _cdata(value: str) -> str:
    return "<![CDATA[" + value.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _feed_datetime(report: DailyReport) -> datetime:
    try:
        generated = datetime.fromisoformat(report.generated_at)
    except (TypeError, ValueError):
        generated = datetime.combine(date.fromisoformat(report.report_date), time(9, 17))
    return generated.replace(tzinfo=REPORT_TIMEZONE) if generated.tzinfo is None else generated


def _feed_issue_html(report: DailyReport) -> str:
    issue_url = f"{SITE_URL}issues/{report.report_date}/"
    blocks = [f'<p>{_e(report.title)} · {len(report.items)} 条精选</p>']
    for index, item in enumerate(report.items, 1):
        sources = " ".join(
            f'<a href="{_e(source["url"])}">{_e(source["tier"])} · {_e(source["name"])}</a>'
            for source in item.sources if _safe_url(source["url"])
        )
        summary = "".join(f"<p>{_e(line)}</p>" for line in item.summary.splitlines() if line.strip())
        comment = "".join(f"<p>{_e(line)}</p>" for line in item.comment.splitlines() if line.strip())
        comment = f"<blockquote><strong>简评</strong>{comment}</blockquote>" if comment else ""
        source_line = f'<p class="sources">来源：{sources}</p>' if sources else ""
        blocks.append(f'''<h2><a href="{_e(issue_url)}#item-{index}">{_e(item.title)}</a></h2>
<p><em>{_e(item.category)} · {_e(item.time)}</em></p>{summary}{comment}{source_line}''')
    return "".join(blocks)


def _feed_description(report: DailyReport) -> str:
    titles = [item.title for item in report.items[:3]]
    if not titles:
        return "本期暂未发现足够可靠的重要 AI 新进展。"
    suffix = " 等。" if len(report.items) > 3 else "。"
    return f"本期收录 {len(report.items)} 条：" + "；".join(titles) + suffix


def _feed_xml(reports: list[DailyReport]) -> str:
    entries = []
    for report in reports[:FEED_LIMIT]:
        issue_url = f"{SITE_URL}issues/{report.report_date}/"
        entries.append(f'''<item>
<title>{_xml(report.title)}</title>
<link>{_xml(issue_url)}</link>
<guid isPermaLink="true">{_xml(issue_url)}</guid>
<pubDate>{format_datetime(_feed_datetime(report))}</pubDate>
<description>{_xml(_feed_description(report))}</description>
<content:encoded>{_cdata(_feed_issue_html(report))}</content:encoded>
</item>''')
    last_build = format_datetime(_feed_datetime(reports[0])) if reports else format_datetime(datetime.now(timezone.utc))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>{_xml(SITE_TITLE)}</title>
<link>{SITE_URL}</link>
<description>{_xml(SITE_DESCRIPTION)}</description>
<language>zh-CN</language>
<lastBuildDate>{last_build}</lastBuildDate>
<generator>ai-daily-post</generator>
<atom:link href="{SITE_URL}feed.xml" rel="self" type="application/rss+xml"/>
{"".join(entries)}
</channel>
</rss>
'''


def rebuild_site(root: Path) -> Path:
    """Rebuild existing issues without collecting news or calling AI."""
    site_root = root / "site"
    (site_root / "assets").mkdir(parents=True, exist_ok=True)
    for name, destination in (("site.css", "style.css"), ("site.js", "site.js")):
        (site_root / "assets" / destination).write_text((ASSETS / name).read_text(encoding="utf-8"), encoding="utf-8")
    reports = _load_reports(site_root)
    home = _reader(reports[0], reports, "./") if reports else '<div class="reading-shell"><header class="issue-header"><div class="issue-dateline">AI DAILY POST</div><h1 class="archive-title">下一份灵感，<br>即将抵达。</h1><p class="issue-subtitle">第一期 AI 日报将在生成后出现在这里。</p></header></div>'
    (site_root / "index.html").write_text(_page("AI 日报 · AI Daily Post", home, reports, current=reports[0].report_date if reports else ""), encoding="utf-8")
    (site_root / "archive.html").write_text(_page("日报归档 · AI Daily Post", _archive_content(reports, "./"), reports, archive=True), encoding="utf-8")
    (site_root / "feed.xml").write_text(_feed_xml(reports), encoding="utf-8")
    for report in reports:
        content = _reader(report, reports, "../../")
        (site_root / "issues" / report.report_date / "index.html").write_text(_page(report.title, content, reports, "../../", report.report_date), encoding="utf-8")
    # A project Pages 404 can appear at any depth. Resolve its homepage from the
    # known project root rather than the missing path's directory.
    error = '<div class="reading-shell"><header class="issue-header"><div class="issue-dateline">404 / PAGE NOT FOUND</div><h1 class="archive-title">这一页，暂时缺席。</h1><p class="issue-subtitle">回到首页，继续探索 AI 世界。</p><a class="return-home" href="./index.html" data-home-link>返回首页 →</a></header></div>'
    not_found = _page("页面不存在 · AI Daily Post", error, reports)
    # 404 pages may be served from a nested URL. Load assets from the Pages
    # project root before the browser resolves relative URLs against that path.
    asset_loader = """<script>(function(){const parts=location.pathname.split('/');const root=location.hostname.endsWith('.github.io')&&parts[1]?'/'+parts[1]+'/':'/';document.write('<link rel=\"stylesheet\" href=\"'+root+'assets/style.css\"><script defer src=\"'+root+'assets/site.js\"><\\/script>');})();</script>"""
    not_found = not_found.replace('<link rel="stylesheet" href="./assets/style.css"><script defer src="./assets/site.js"></script>', asset_loader)
    root_script = """<script>(function(){const parts=location.pathname.split('/');const root=location.hostname.endsWith('.github.io')&&parts[1]?'/'+parts[1]+'/':'/';document.body.dataset.siteRoot=root;document.querySelectorAll('a[href^=\"./\"]').forEach(a=>a.href=root+a.getAttribute('href').slice(2));})();</script>"""
    (site_root / "404.html").write_text(not_found.replace("</body>", root_script + "</body>"), encoding="utf-8")
    (site_root / ".nojekyll").touch()
    return site_root


def build_site(report: DailyReport, root: Path) -> Path:
    date.fromisoformat(report.report_date)
    issue_dir = root / "site" / "issues" / report.report_date
    issue_dir.mkdir(parents=True, exist_ok=True)
    (issue_dir / "data.json").write_text(json.dumps(report_to_dict(report), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return rebuild_site(root)


if __name__ == "__main__":
    from .config import ROOT
    print(f"Rebuilt site at {rebuild_site(ROOT)}")
