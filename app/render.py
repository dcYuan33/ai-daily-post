from __future__ import annotations

import html
from pathlib import Path

try:
    import markdown
except ImportError:  # Keeps date/config unit tests runnable before dependencies are installed.
    markdown = None

from .labels import category_label
from .models import DailyReport


def render_markdown(report: DailyReport) -> str:
    lines = [
        f"# {report.report_date}",
        "",
        f"- Generated: {report.generated_at}",
        f"- Report date: {report.report_date} (Asia/Shanghai)",
        "",
        "## Highlights",
        "",
    ]
    if not report.items:
        lines.append("No sufficiently reliable AI developments were found for this date.")
    for index, item in enumerate(report.items, 1):
        lines.extend([
            f"### {index}. {item.title}",
            f"- Time: {item.time}",
            f"- Category: {category_label(item.category)}",
            f"- Summary: {item.summary}",
        ])
        if item.comment:
            lines.append(f"- Comment: {item.comment}")
        source_text = "; ".join(
            f"[{source['name']} ({source['tier']})]({source['url']})" for source in item.sources
        )
        lines.extend([f"- Sources: {source_text}", ""])
    return "\n".join(lines).rstrip() + "\n"


def render_html(report: DailyReport) -> str:
    md = render_markdown(report)
    if markdown is not None:
        body = markdown.markdown(md, extensions=["extra", "sane_lists"])
    else:
        body = "<pre>" + html.escape(md) + "</pre>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(report.report_date)}</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.7;max-width:860px;margin:32px auto;padding:0 20px;color:#222}}h1{{border-bottom:1px solid #ddd;padding-bottom:12px}}h2{{margin-top:32px}}h3{{margin-top:26px}}a{{color:#1769aa}}li{{margin:8px 0}}</style>
</head><body>{body}</body></html>"""


def save_report(report: DailyReport, root: Path) -> tuple[Path, Path]:
    folder = root / "reports" / report.report_date[:4] / report.report_date[5:7]
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f"ai-daily-{report.report_date}"
    md_path, html_path = stem.with_suffix(".md"), stem.with_suffix(".html")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return md_path, html_path
