# AI Daily Post

## Features

- Collects AI news for the previous calendar day and generates an English daily report;
- Sources are configured in `config/sources.yaml` and grouped into three kinds: news, paper, and project;
- Reports are split into **News / Papers / Projects**: news, official blogs, and in-depth analysis go in News, Papers With Code goes in Papers, and new GitHub trending repositories go in Projects;
- Projects only include repositories created within the last 90 days, so old projects are not clustered into the section;
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

- Sources are grouped into three kinds in `config/sources.yaml`: news, paper, and project. RSS/API feeds are preferred when available.
- Reports have three sections:
  - **News**: items from `kind: news` sources, including OpenAI News, Anthropic News, Hugging Face Blog, and Simon Willison's Weblog;
  - **Papers**: items from Papers With Code only. Every paper has a public code repository. The paper source has a higher weight (`weight: 4`) and collects up to 12 papers per day. `paperswithcode.com` now redirects to Hugging Face Papers, so collection uses its daily-papers API and keeps only entries with a non-empty `githubRepo`;
  - **Projects**: items from GitHub Trending only. Collection keeps repositories created within the last 90 days (`max_age_days: 90`) and drops established projects that briefly trend. Each project is a separate item; projects are never clustered.
- The former Articles section was removed: its sources now publish as news, and archived issues that used that section render those items under News.
- Include major news as well as verifiable feature updates, small tools, open-source work, and expert analysis. When evidence supports it, target 10–18 news items, 6–12 papers, and 3–8 projects, with a maximum of 34 items. There is no minimum: never pad with old news.
- Sources are no longer ranked by tier. The report section comes from the source kind, and every source URL is retained from the collected candidate set.
- The page-fetch budget is 120. Sources are polled in round-robin order, and the paper source receives extra slots by weight. Each fetched excerpt is capped at 3000 characters to control AI input size. GitHub Trending candidates already carry their description and star counts, so they do not consume page requests.
- Logs show per-source candidate counts, request failures, dated candidates for the target day, available article text, and the final item count.
- Sources used fewer than 10 times across the existing 29 issues were removed, except for Papers With Code, GitHub Trending, and Anthropic News. Papers With Code and GitHub Trending are the only sources for their sections; Anthropic News is retained because the official Anthropic and OpenAI blogs are required in News.
- Set `GITHUB_TOKEN` to raise the GitHub API rate limit used to check repository creation dates. The token needs no scopes for public repositories.

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
