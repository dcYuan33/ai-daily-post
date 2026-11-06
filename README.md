# AI Daily Post

## Features

- Collects AI news for the previous calendar day and generates an English daily report;
- A/B/C sources are configured in `config/sources.yaml`;
- Reports are split into **News / Articles / Papers**: official blogs and in-depth articles go in Articles, and code-backed papers go in Papers;
- RSS/API first, with webpage sections as candidates and article pages as verification input;
- Generates Markdown and HTML;
- GitHub Pages: the homepage shows the latest full issue, with date archives, full-text search, table of contents, reading progress, and multiple reading themes;
- RSS feed: `site/feed.xml` publishes the latest 50 issues with full text and reader auto-discovery;
- Python is managed with `uv`;
- GitHub Actions can accept a `report_date` when run manually.

## Local development

This project uses `uv` to manage the Python version, virtual environment, and dependencies. Do not use `pip install` directly.

```bash
uv lock    # first run or after dependency changes; commit the generated uv.lock when network is available
uv sync
cp .env.example .env
set -a; source .env; set +a
uv run python -m app --report-date 2026-10-06
```

Local tests only cover pure functions and need no network or API key:

```bash
uv run python -m unittest discover -s tests -v
```

Preview the generated site with a static server:

```bash
uv run python -m http.server 8000 --directory site
```

Then open `http://localhost:8000`.

## Coverage and diagnostics

- The project keeps A/B/C sources. RSS/API feeds are preferred when available.
- Reports have three sections:
  - **News**: items from `kind: news` sources;
  - **Articles**: official blogs from OpenAI, Anthropic, Google DeepMind, Google Research, Meta AI, Microsoft Research, AWS ML, Apple ML, BAIR, Hugging Face, plus high-quality publications such as The Gradient and Lil'Log. These article sources are tier A and appear in the Articles section;
  - **Papers**: paper sources only keep papers with a public code repository, and every paper appears in the Papers section. The paper source has a higher weight (`weight: 4`) and collects up to 12 papers per day. `paperswithcode.com` now redirects to Hugging Face Papers, so collection uses its daily-papers API and keeps only entries with a non-empty `githubRepo`.
- Include major news as well as verifiable feature updates, small tools, open-source work, and expert analysis. When evidence supports it, target 10–18 news items, 4–8 articles, and 6–12 papers, with a maximum of 30 items. There is no minimum: never pad with old news.
- Tier-A official announcements, lab/research blogs, and code-backed papers may be included on their own; tier-B credible reporting may also be included on its own. Tier-C author practice and opinion must be clearly attributed and cannot independently verify major company news.
- The article request budget is 120. Sources are polled in round-robin order, and the paper source receives extra slots by weight. Each article excerpt is capped at 3000 characters to control AI input size.
- Logs show per-source candidate counts, request failures, dated candidates for the target day, available article text, and the final item count.
- Ten sources were removed after zero appearances across 29 issues and zero candidates in live collection, or because they were blocked/paywalled: FTC, CISA, Reuters, AP, NYT, WSJ, FT, The Information, CNN, and Stanford HAI. The decision used historical report usage and a live candidate probe.

In the Actions list, `Deploy Pages · existing reports only` only redeploys existing content; `Generate AI daily report` collects, generates, and deploys a new issue. Even when there is no reliable news that day, the full generation flow publishes an empty issue for that date instead of leaving the old date on the homepage.

## Schedule and date window

The scheduled run uses `01:17 UTC`, or `09:17 Asia/Shanghai`. The default report date is the previous day in the runtime timezone; for example, a run on the morning of 2026-10-07 generates the 2026-10-06 issue. A manual run can override it with `report_date`.

## GitHub Pages structure

```text
site/
├── index.html                 homepage and latest issue
├── archive.html               full issue archive
├── feed.xml                   RSS feed
├── assets/style.css           site styles
└── issues/YYYY-MM-DD/
    ├── index.html             issue detail page
    └── data.json              data used to rebuild the archive and navigation
```

RSS: <https://dcyuan33.github.io/ai-daily-post/feed.xml>

GitHub Pages builds and deploys `site/` with Actions. After each report, the workflow:

1. Generates Markdown, HTML, and static Pages files;
2. Commits `reports/` and `site/` back to the repository;
3. Uploads `site/` as the Pages artifact;
4. Deploys to GitHub Pages.
