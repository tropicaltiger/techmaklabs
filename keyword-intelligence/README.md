# Tech Mak Labs — Keyword Intelligence v0.6

A lightweight, GitHub/Railway-ready prototype that combines Google Search Console CSV analysis with a cautious public-site content scan.

## What's new in v0.6
- Sitemap-assisted URL discovery using same-domain sitemap entries and sitemap declarations in robots.txt.
- Internal-link crawling remains enabled, with a maximum of 30 visited pages per scan.
- Compares target keywords with page titles, H1/H2/H3 headings and extracted page text.
- Reports evidence and suggested next steps without treating exact-phrase absence as proof a page is irrelevant.
- GSC CSVs are parsed in the browser; no Google or Anthropic API key is required.

## Deploy on Railway
1. Upload these files to a GitHub repository (root directory).
2. Create a Railway project from that repository.
3. Railway detects `requirements.txt` and `Procfile`; the app listens on the `PORT` environment variable.
4. Open the public URL and test the website scan.

## Files
- `index.html` — browser UI and CSV analysis.
- `server.py` — HTTP server and bounded same-domain public HTML crawler.
- `requirements.txt` — no third-party dependencies required.
- `Procfile` — Railway start command.

## Current limits
- Up to 30 pages per scan; sitemap discovery is capped to avoid unbounded crawling.
- Static HTML extraction only. JavaScript-rendered content may be missing.
- The crawler is not a full technical SEO audit and does not fetch live Google rankings, search volume, competitor metrics, or map-pack results.
- General Queries and Pages exports do not reveal a definitive query-to-URL relationship; use query-filtered Pages exports for that evidence.
- No ranking guarantees. Review intent and page quality before changing URLs or creating pages.

## Security and cost
- No secret keys are required for this version.
- The crawler accepts public HTTP/HTTPS URLs only, rejects private/local IP addresses, limits response sizes and stays on the same hostname.
