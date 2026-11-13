import io
import json
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.collect import load_sources
from app.llm import MAX_ATTEMPTS, _post_completion, _section_for
from app.main import resolve_report_date
from app.models import DailyReport, ReportItem
from app.render import render_markdown, save_report
from app.site import build_site, rebuild_site


class FakeSettings:
    timezone = ZoneInfo("Asia/Shanghai")


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


def http_error(code: int, body: bytes = b'{"error":"upstream"}') -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.com/v1/chat/completions", code, "error", {}, io.BytesIO(body)
    )


class CoreTests(unittest.TestCase):
    def test_default_report_date_is_previous_local_day(self):
        # Explicit dates are stable and do not depend on the machine clock.
        self.assertEqual(resolve_report_date(FakeSettings(), "2026-10-05"), date(2026, 10, 5))

    def test_completion_retries_transient_http_errors(self):
        responses = [
            http_error(500),
            http_error(503),
            FakeResponse({"choices": [{"message": {"content": "{}"}}]}),
        ]
        with patch("app.llm.urllib.request.urlopen", side_effect=responses), \
                patch("app.llm.time.sleep") as sleep:
            result = _post_completion("https://example.com/v1/chat/completions", {}, b"{}")
        self.assertEqual(result["choices"][0]["message"]["content"], "{}")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [5.0, 10.0])

    def test_completion_does_not_retry_client_errors(self):
        with patch("app.llm.urllib.request.urlopen", side_effect=http_error(401)), \
                patch("app.llm.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
                _post_completion("https://example.com/v1/chat/completions", {}, b"{}")
        sleep.assert_not_called()

    def test_completion_gives_up_after_max_attempts(self):
        with patch(
            "app.llm.urllib.request.urlopen",
            side_effect=[http_error(500) for _ in range(MAX_ATTEMPTS)],
        ), patch("app.llm.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                _post_completion("https://example.com/v1/chat/completions", {}, b"{}")

    def test_markdown_contains_sources(self):
        report = DailyReport(
            title="AI Daily | 2026-10-05",
            report_date="2026-10-05",
            generated_at="2026-10-06T09:17:00+08:00",
            items=[ReportItem(
                title="Test story",
                time="2026-10-05",
                category="Models & Research",
                summary="This is a test summary.",
                sources=[{"name": "OpenAI News", "url": "https://example.com/news"}],
            )],
        )
        output = render_markdown(report)
        self.assertIn("# AI Daily | 2026-10-05", output)
        self.assertIn("## News", output)
        self.assertIn("Models & Research", output)
        self.assertIn("Test story", output)
        self.assertIn("[OpenAI News](https://example.com/news)", output)
        self.assertNotIn("OpenAI News (A)", output)

    def test_section_is_derived_from_source_kind(self):
        self.assertEqual(_section_for({"news"}), "news")
        self.assertEqual(_section_for({"article"}), "news")
        self.assertEqual(_section_for({"paper", "news"}), "paper")
        self.assertEqual(_section_for(set()), "news")

    def test_sources_config_has_two_kinds_and_no_tier(self):
        sources = load_sources(Path(__file__).resolve().parent.parent / "config/sources.yaml")
        self.assertEqual({source["kind"] for source in sources}, {"news", "paper"})
        self.assertFalse(any("tier" in source for source in sources))
        self.assertEqual([source["name"] for source in sources if source["kind"] == "paper"], ["Papers With Code"])
        self.assertNotIn("GitHub Trending", [source["name"] for source in sources])
        news_names = [source["name"] for source in sources if source["kind"] == "news"]
        for name in ("OpenAI News", "Anthropic News", "Hugging Face Blog", "Simon Willison's Weblog"):
            self.assertIn(name, news_names)

    def test_build_site(self):
        report = DailyReport(
            "AI Daily | 2026-10-06",
            "2026-10-06",
            "2026-10-07T09:17:00+08:00",
            [ReportItem(
                title="Test story",
                time="2026-10-06",
                category="Models & Research",
                summary="This is a test summary.",
                sources=[{"name": "OpenAI News", "url": "https://example.com/news"}],
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
            "AI Daily | 2026-10-06", "2026-10-06", "now",
            [ReportItem(
                title="<script>alert(1)</script>", time="2026-10-06", category="Test",
                summary="Summary <b>must not be treated as HTML</b>",
                sources=[
                    {"name": "Malicious", "url": "javascript:alert(1)"},
                    {"name": "Safe source", "url": "https://example.com"},
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
            "AI Daily | 2026-10-06", "2026-10-06", "2026-10-07T09:17:00+08:00",
            [ReportItem(
                title="Test story", time="2026-10-06", category="Models & Research",
                summary="This is a test summary.", comment="This is a test comment.",
                sources=[
                    {"name": "Safe source", "url": "https://example.com/news"},
                    {"name": "Malicious", "url": "javascript:alert(1)"},
                ],
            )],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_site(report, root)
            feed = (root / "site/feed.xml").read_text(encoding="utf-8")
            channel = ET.fromstring(feed).find("channel")
            self.assertEqual(channel.findtext("title"), "AI Daily Post")
            self.assertEqual(channel.findtext("language"), "en")
            self.assertEqual(channel.find("{http://www.w3.org/2005/Atom}link").get("rel"), "self")
            image = channel.find("image")
            self.assertEqual(image.findtext("url"), "https://dcyuan33.github.io/ai-daily-post/assets/feed-logo-144.png")
            self.assertEqual(image.findtext("width"), "144")
            self.assertEqual(image.findtext("height"), "144")
            self.assertEqual(channel.findtext("{http://www.w3.org/2005/Atom}logo"), "https://dcyuan33.github.io/ai-daily-post/assets/logo.png")
            item = channel.find("item")
            self.assertEqual(item.findtext("title"), "2026-10-06")
            self.assertEqual(item.findtext("link"), "https://dcyuan33.github.io/ai-daily-post/issues/2026-10-06/")
            self.assertEqual(item.findtext("pubDate"), "Wed, 07 Oct 2026 09:17:00 +0800")
            content = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            self.assertIn("Test story", content)
            self.assertIn("This is a test summary.", content)
            self.assertIn("This is a test comment.", content)
            self.assertIn("Models &amp; Research", content)
            self.assertNotIn("AI Daily | ", content)
            self.assertNotIn("https://dcyuan33.github.io/ai-daily-post/issues/2026-10-06/#item-1", content)
            self.assertIn("https://example.com/news", content)
            self.assertNotIn("javascript:alert(1)", feed)
            self.assertIn('rel="alternate" type="application/rss+xml"', (root / "site/index.html").read_text(encoding="utf-8"))

    def test_rebuild_site_preserves_multiple_issue_archive(self):
        first = DailyReport("AI Daily | 2026-10-06", "2026-10-06", "now", [])
        second = DailyReport("AI Daily | 2026-10-07", "2026-10-07", "now", [])
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

    def test_sections_group_news_and_papers(self):
        report = DailyReport(
            "AI Daily | 2026-10-06", "2026-10-06", "2026-10-07T09:17:00+08:00",
            [
                ReportItem(
                    title="News item", time="2026-10-06", category="Models & Research",
                    summary="News summary.", section="news",
                    sources=[{"name": "OpenAI News", "url": "https://example.com/news"}],
                ),
                ReportItem(
                    title="Legacy article item", time="2026-10-06", category="Models & Research",
                    summary="Legacy article summary.", section="article",
                    sources=[{"name": "Anthropic News", "url": "https://example.com/article"}],
                ),
                ReportItem(
                    title="Paper item", time="2026-10-06", category="Models & Research",
                    summary="Paper summary.", section="paper", code_url="https://github.com/example/code",
                    sources=[{"name": "Papers With Code", "url": "https://example.com/paper"}],
                ),
            ],
        )
        output = render_markdown(report)
        positions = [output.index("## News"), output.index("## Papers")]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("## Articles", output)
        self.assertNotIn("## Projects", output)
        self.assertLess(output.index("Legacy article item"), output.index("## Papers"))
        self.assertIn("- Code: https://github.com/example/code", output)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_site(report, root)
            page = (root / "site/index.html").read_text(encoding="utf-8")
            for section in ("news", "paper"):
                self.assertIn(f'id="section-{section}"', page)
            self.assertNotIn('id="section-article"', page)
            self.assertNotIn('id="section-project"', page)
            self.assertIn("Legacy article item", page)
            self.assertIn('href="https://github.com/example/code"', page)

    def test_save_report(self):
        report = DailyReport("AI Daily | 2026-10-05", "2026-10-05", "now", [])
        with tempfile.TemporaryDirectory() as directory:
            md, html = save_report(report, Path(directory))
            self.assertTrue(md.exists())
            self.assertTrue(html.exists())
            self.assertIn("No sufficiently reliable AI developments were found for this date.", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
