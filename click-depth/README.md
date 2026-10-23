# Buried Pages Finder

Crawls a website and shows how many clicks every page is from the homepage.
It reports:

- **Buried pages**: 4 or more clicks deep (you can change this), with the click path
  and suggested pages to link from
- **Orphan pages**: listed in `sitemap.xml` but not linked from any crawled page
- **Barely linked pages**: only one or two internal links point to them
- Target keywords (optional): buried pages that match a keyword are marked high priority

## Files

| File | Purpose |
|---|---|
| `click_depth.py` | Crawler and analysis. Works on its own from the command line, or imported |
| `app.py` | Flask web app: runs crawls in the background, serves the page |
| `templates/index.html` | The page (form, progress bar, results) |
| `Procfile`, `requirements.txt`, `.python-version` | Deployment settings |

## Run on your computer

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000. The app refuses localhost and private addresses as
targets (a safety measure for public hosting), so test it against a real public site.

Without the web page:

```bash
python click_depth.py https://example.com --max-pages 50 --keywords "wedding catering"
```

## Put it on GitHub

```bash
git init
git add .
git commit -m "Buried pages finder"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git push -u origin main
```

## Deploy on Railway

1. In Railway, choose **New Project > Deploy from GitHub repo** and pick this repository.
2. Railway reads `requirements.txt` and `Procfile`. No other setup is needed.
3. Under **Settings > Networking**, generate a domain.

Optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `MAX_PAGES_CAP` | 300 | Highest page limit a visitor can choose |
| `MAX_RUNNING_JOBS` | 3 | Crawls that can run at once |
| `CRAWL_DELAY` | 0.3 | Seconds between requests to the target site |

## Before you go live

- Open `click_depth.py` and change `USER_AGENT` to include your site or email, so
  site owners know who is crawling them.
- Keep `--workers 1` in the `Procfile`. Crawl progress is held in memory, so more
  than one worker would lose track of running crawls. Results are deleted after one hour.
- Sites that build their links with JavaScript show fewer pages than a browser would.
  To support them, replace `safe_fetch` in `app.py` with a Playwright-based version.
- This is a public tool that makes requests on behalf of visitors. Consider adding
  rate limiting per visitor (for example Flask-Limiter) before sharing it widely.

## Use it inside your existing tool

```python
from click_depth import crawl, analyze

site = crawl("https://example.com", max_pages=200)
report = analyze(site, keywords=["wedding catering"])
```

`report` is a plain dictionary with `depth_distribution`, `deep_pages`,
`orphan_pages` and `weakly_linked_pages`. If your tool already crawls pages, you
can skip `crawl` and build the same `pages` structure from your own data.
