import unittest
from datetime import date, datetime
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

from app.collect import (
    _github_trending_candidates,
    _local_date,
    _page_date,
    _paper_candidates,
    _rss_candidates,
    collect_candidates,
    enrich_candidates,
    fetch_page,
)
from app.models import Candidate


class CollectionTests(unittest.TestCase):
    def test_rss_dates_use_report_timezone(self):
        self.assertEqual(_local_date(datetime.fromisoformat("2026-10-06T20:00:00+00:00")), date(2026, 10, 7))
        self.assertEqual(_local_date(datetime.fromisoformat("2026-10-07T20:00:00+00:00")), date(2026, 10, 8))
        self.assertEqual(_local_date(datetime(2026, 10, 7)), date(2026, 10, 7))

    def test_jsonld_publication_date_precedes_unrelated_time(self):
        soup = BeautifulSoup('''<time datetime="2026-10-08"></time>
            <script type="application/ld+json">{"@graph":[
              {"@type":"NewsArticle","datePublished":"2026-10-07T12:00:00Z"}
            ]}</script>''', "html.parser")
        self.assertEqual(_page_date(soup), datetime.fromisoformat("2026-10-07T12:00:00+00:00"))

    @patch("app.collect.requests.get")
    def test_fetch_preserves_date_before_text_cleanup(self, get):
        get.return_value = Mock(url="https://example.com/news", text='''<html><body>
            <script type="application/ld+json">{"@type":"BlogPosting","datePublished":"2026-10-07"}</script>
            <article><header><time datetime="2026-10-07"></time></header>
            <p>A new developer tool with a verifiable announcement and detailed documentation.</p></article>
            </body></html>''')
        _, content, published = fetch_page("https://example.com/news")
        self.assertIn("developer tool", content)
        self.assertEqual(published, datetime(2026, 10, 7))

    @patch("app.collect.fetch_page", return_value=("https://example.com/article", "body", None))
    def test_article_budget_covers_late_sources_and_is_stable(self, fetch):
        candidates = [Candidate(source, "https://example.com/", str(i), f"https://example.com/{source}/{i}")
                      for source in ("first", "second", "last")
                      for i in range(20)]
        enriched = enrich_candidates(candidates, max_articles=6)
        self.assertEqual([item.source_name for item in enriched], ["first", "second", "last"] * 2)
        self.assertEqual(fetch.call_count, 6)

    @patch("app.collect.enrich_candidates")
    @patch("app.collect.load_sources", return_value=[])
    def test_collection_does_not_send_known_old_news_to_ai(self, load, enrich):
        items = [Candidate("Test", "https://example.com/", title, f"https://example.com/{title}", published_at=stamp)
                 for title, stamp in [("today", datetime(2026, 10, 7)),
                                      ("old", datetime(2026, 10, 6)), ("unknown", None)]]
        enrich.return_value = items
        self.assertEqual([item.title for item in collect_candidates(None, date(2026, 10, 7))], ["today", "unknown"])

    @patch("app.collect.fetch_page", return_value=("https://example.com/article", "body", None))
    def test_paper_source_weight_selects_more_papers(self, fetch):
        candidates = (
            [Candidate("paper", "https://example.com/", f"p{i}", f"https://example.com/p/{i}", kind="paper", weight=4) for i in range(8)]
            + [Candidate("news", "https://example.com/", f"n{i}", f"https://example.com/n/{i}") for i in range(8)]
        )
        enriched = enrich_candidates(candidates, max_articles=10)
        self.assertEqual(sum(item.source_name == "paper" for item in enriched), 8)
        self.assertEqual(sum(item.source_name == "news" for item in enriched), 2)

    @patch("app.collect.requests.get")
    def test_paper_candidates_keep_only_code_backed_papers(self, get):
        get.return_value = Mock()
        get.return_value.json.return_value = [
            {"paper": {
                "id": "2611.00001", "title": "Paper with code",
                "summary": "Paper abstract.", "submittedOnDailyAt": "2026-11-05T00:00:00.000Z",
                "githubRepo": "https://github.com/example/paper",
            }},
            {"paper": {
                "id": "2611.00002", "title": "Paper without code",
                "summary": "Paper abstract.", "submittedOnDailyAt": "2026-11-05T00:00:00.000Z",
                "githubRepo": None,
            }},
        ]
        source = {
            "name": "Papers With Code", "url": "https://huggingface.co/papers",
            "api": "https://huggingface.co/api/daily_papers", "kind": "paper", "weight": 4,
        }
        entries = _paper_candidates(source, date(2026, 11, 5))
        self.assertEqual([entry.title for entry in entries], ["Paper with code"])
        self.assertEqual(entries[0].code_url, "https://github.com/example/paper")
        self.assertEqual(entries[0].kind, "paper")
        self.assertEqual(entries[0].weight, 4)
        self.assertEqual(entries[0].published_at.date(), date(2026, 11, 5))

    @patch("app.collect.requests.get")
    def test_github_trending_keeps_only_new_repositories(self, get):
        trending_page = Mock(text='''
            <article class="Box-row">
              <h2><a href="/new/project">new / project</a></h2>
              <p>New agent project.</p>
              <div class="f6">Python 1,234 stars today</div>
            </article>
            <article class="Box-row">
              <h2><a href="/old/project">old / project</a></h2>
              <p>Old established project.</p>
              <div class="f6">Python 99,999 stars today</div>
            </article>''')
        new_repo = Mock()
        new_repo.json.return_value = {
            "html_url": "https://github.com/new/project",
            "description": "New agent project.",
            "created_at": "2026-09-01T00:00:00Z",
            "stargazers_count": 1234,
            "topics": ["agents"],
            "archived": False,
            "fork": False,
        }
        old_repo = Mock()
        old_repo.json.return_value = {
            "html_url": "https://github.com/old/project",
            "description": "Old established project.",
            "created_at": "2023-01-01T00:00:00Z",
            "stargazers_count": 99999,
            "archived": False,
            "fork": False,
        }
        get.side_effect = [trending_page, new_repo, old_repo]
        source = {
            "name": "GitHub Trending", "url": "https://github.com/trending",
            "collection": "trending", "kind": "project", "since": "daily",
            "max_age_days": 90, "limit": 8,
        }
        entries = _github_trending_candidates(source, date(2026, 11, 5))
        self.assertEqual([entry.title for entry in entries], ["new/project"])
        self.assertEqual(entries[0].kind, "project")
        self.assertEqual(entries[0].url, "https://github.com/new/project")
        self.assertEqual(entries[0].published_at.date(), date(2026, 11, 5))
        self.assertIn("1,234 stars today", entries[0].summary)

    def test_candidate_prompt_dict_has_no_tier(self):
        candidate = Candidate("Test", "https://example.com/", "Title", "https://example.com/a")
        self.assertNotIn("tier", candidate.as_prompt_dict())

    @patch("app.collect.requests.get")
    def test_rss_excludes_next_local_day_not_previous_utc_day(self, get):
        get.return_value = Mock(content=b'''<rss version="2.0"><channel><title>AI</title>
            <item><title>Included</title><link>https://example.com/yes</link>
              <pubDate>Tue, 06 Oct 2026 20:00:00 GMT</pubDate></item>
            <item><title>Next day</title><link>https://example.com/no</link>
              <pubDate>Wed, 07 Oct 2026 20:00:00 GMT</pubDate></item>
            </channel></rss>''')
        source = {"rss": "https://example.com/rss", "url": "https://example.com/", "name": "Test"}
        entries = _rss_candidates(source, date(2026, 10, 7))
        self.assertEqual([entry.title for entry in entries], ["Included"])


if __name__ == "__main__":
    unittest.main()
