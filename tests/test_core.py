import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from app.main import resolve_report_date
from app.models import DailyReport, ReportItem
from app.render import render_markdown, save_report
from app.site import build_site, rebuild_site


class FakeSettings:
    timezone = ZoneInfo("Asia/Shanghai")


class CoreTests(unittest.TestCase):
    def test_default_report_date_is_previous_local_day(self):
        # Explicit dates are stable and do not depend on the machine clock.
        self.assertEqual(resolve_report_date(FakeSettings(), "2026-10-05"), date(2026, 10, 5))

    def test_markdown_contains_sources(self):
        report = DailyReport(
            title="AI 日报｜2026-10-05",
            report_date="2026-10-05",
            generated_at="2026-10-06T09:17:00+08:00",
            items=[ReportItem(
                title="测试新闻",
                time="2026-10-05",
                category="模型与研究",
                summary="这是测试摘要。",
                sources=[{"name": "OpenAI News", "tier": "A", "url": "https://example.com/news"}],
            )],
        )
        output = render_markdown(report)
        self.assertIn("测试新闻", output)
        self.assertIn("OpenAI News（A）", output)
        self.assertIn("https://example.com/news", output)


    def test_build_site(self):
        report = DailyReport(
            "AI 日报｜2026-10-06",
            "2026-10-06",
            "2026-10-07T09:17:00+08:00",
            [ReportItem(
                title="测试新闻",
                time="2026-10-06",
                category="模型与研究",
                summary="这是测试摘要。",
                sources=[{"name": "OpenAI News", "tier": "A", "url": "https://example.com/news"}],
            )],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_site(report, root)
            self.assertTrue((root / "site/index.html").exists())
            self.assertTrue((root / "site/archive.html").exists())
            issue = root / "site/issues/2026-10-06/index.html"
            self.assertTrue(issue.exists())
            self.assertIn("../../assets/style.css", issue.read_text(encoding="utf-8"))

    def test_reader_escapes_content_and_rejects_unsafe_sources(self):
        report = DailyReport(
            "AI 日报｜2026-10-06", "2026-10-06", "now",
            [ReportItem(
                title="<script>alert(1)</script>", time="2026-10-06", category="测试",
                summary="摘要 <b>不应被当作 HTML</b>",
                sources=[
                    {"name": "恶意", "tier": "A", "url": "javascript:alert(1)"},
                    {"name": "安全来源", "tier": "B", "url": "https://example.com"},
                ],
            )],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_site(report, root)
            page = (root / "site/index.html").read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
            self.assertNotIn("javascript:alert(1)", page)
            self.assertIn("https://example.com", page)

    def test_build_site_writes_rss_feed(self):
        report = DailyReport(
            "AI 日报｜2026-10-06", "2026-10-06", "2026-10-07T09:17:00+08:00",
            [ReportItem(
                title="测试新闻", time="2026-10-06", category="模型与研究",
                summary="这是测试摘要。", comment="这是简评。",
                sources=[
                    {"name": "安全来源", "tier": "A", "url": "https://example.com/news"},
                    {"name": "恶意", "tier": "B", "url": "javascript:alert(1)"},
                ],
            )],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_site(report, root)
            feed = (root / "site/feed.xml").read_text(encoding="utf-8")
            channel = ET.fromstring(feed).find("channel")
            self.assertEqual(channel.findtext("title"), "AI 日报 · AI Daily Post")
            self.assertEqual(channel.find("{http://www.w3.org/2005/Atom}link").get("rel"), "self")
            item = channel.find("item")
            self.assertEqual(item.findtext("title"), "AI 日报｜2026-10-06")
            self.assertEqual(item.findtext("link"), "https://dcyuan33.github.io/ai-daily-post/issues/2026-10-06/")
            self.assertEqual(item.findtext("pubDate"), "Wed, 07 Oct 2026 09:17:00 +0800")
            content = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            self.assertIn("测试新闻", content)
            self.assertIn("https://dcyuan33.github.io/ai-daily-post/issues/2026-10-06/#item-1", content)
            self.assertIn("https://example.com/news", content)
            self.assertNotIn("javascript:alert(1)", feed)
            self.assertIn('rel="alternate" type="application/rss+xml"', (root / "site/index.html").read_text(encoding="utf-8"))

    def test_rebuild_site_preserves_multiple_issue_archive(self):
        first = DailyReport("AI 日报｜2026-10-06", "2026-10-06", "now", [])
        second = DailyReport("AI 日报｜2026-10-07", "2026-10-07", "now", [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_site(first, root)
            issue_dir = root / "site/issues/2026-10-07"
            issue_dir.mkdir(parents=True)
            (issue_dir / "data.json").write_text(
                json.dumps({
                    "title": second.title, "report_date": second.report_date,
                    "generated_at": second.generated_at, "items": [],
                }), encoding="utf-8"
            )
            original = (root / "site/issues/2026-10-06/data.json").read_text(encoding="utf-8")
            rebuild_site(root)
            self.assertIn("2026-10-07", (root / "site/index.html").read_text(encoding="utf-8"))
            self.assertIn("issues/2026-10-06/", (root / "site/issues/2026-10-07/index.html").read_text(encoding="utf-8"))
            self.assertEqual(original, (root / "site/issues/2026-10-06/data.json").read_text(encoding="utf-8"))

    def test_save_report(self):
        report = DailyReport("AI 日报｜2026-10-05", "2026-10-05", "now", [])
        with tempfile.TemporaryDirectory() as directory:
            md, html = save_report(report, Path(directory))
            self.assertTrue(md.exists())
            self.assertTrue(html.exists())
            self.assertIn("暂未发现", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
