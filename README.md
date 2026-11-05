# AI Daily Post

## 功能

- 前一天自然日的 AI 新闻采集和中文日报生成；
- A/B/C 信源配置集中在 `config/sources.yaml`；
- RSS 优先，网页栏目作为候选，文章原文作为核验输入；
- 生成 Markdown 和 HTML；
- GitHub Pages：首页直接展示最新完整日报，左侧日期归档、全文搜索、目录、阅读进度和多种阅读主题；

- RSS 订阅：`site/feed.xml` 输出最近 50 期日报全文，并支持阅读器自动发现；
- Python 使用 `uv` 管理；
- GitHub Actions 手动运行时可以指定 `report_date`。

## 本地运行

本项目使用 uv 管理 Python 版本、虚拟环境和依赖，不直接使用 `pip install`。

```bash
uv lock    # 首次或依赖变更时执行；网络可用后提交生成的 uv.lock
uv sync
cp .env.example .env
set -a; source .env; set +a
uv run python -m app --report-date 2026-10-06
```

本地测试只验证纯函数，不需要网络或密钥：

```bash
uv run python -m unittest discover -s tests -v
```

本地生成站点后可以用静态服务器预览：

```bash
uv run python -m http.server 8000 --directory site
```

然后打开 `http://localhost:8000`。

## 日报收录范围与运行诊断

- 保持 A/B/C 信源。现有信源有可用 RSS 时优先获取带发布日期的条目。
- 收录重大消息，也收录可核验的功能更新、小型工具、开源实践与专业解读。证据充足时目标为 15–25 条，最多 30 条；不设置最低条数，不用旧闻凑数。
- A 类公告和 B 类可信报道可独立收录。C 类作者自己的实践/观点须明确归因，不能独立核验重大公司消息。
- 文章请求预算为 120 条，按信源轮询分配，避免前几个信源占满预算；单篇输入摘录限制为 3000 字符以控制 AI 输入规模。
- 日志显示各信源候选数、请求失败、目标日日期数量、正文可用数量和最终日报条数。

Actions 列表中的 `Deploy Pages · existing reports only` 只重新部署已有内容，不生成新日期的日报；`Generate AI daily report` 才会采集、生成并部署新日报。即使当天确实没有可靠新闻，完整生成流程也会发布该日期的空日报，而不是停留在旧日期。

## 运行时间和日期窗口

定时任务使用 `01:17 UTC`，即 `09:17 Asia/Shanghai`。默认报告日期是运行时区的前一天，例如 2026-10-07 早上运行时生成 `2026-10-06` 日报。手动运行可以用 `report_date` 覆盖。

## GitHub Pages 页面结构

```text
site/
├── index.html                 首页和最新日报
├── archive.html               全部日报归档
├── feed.xml                   RSS 订阅源
├── assets/style.css           页面样式
└── issues/YYYY-MM-DD/
    ├── index.html             单期日报详情页
    └── data.json              用于重新构建归档和导航的数据
```

RSS 地址：<https://dcyuan33.github.io/ai-daily-post/feed.xml>

GitHub Pages 使用 Actions 构建并部署 `site/`。每次日报生成后，Workflow 会：

1. 生成 Markdown、HTML 和 Pages 静态文件；
2. 将 `reports/` 和 `site/` 提交回仓库；
3. 上传 `site/` 为 Pages artifact；
4. 部署到 GitHub Pages。
