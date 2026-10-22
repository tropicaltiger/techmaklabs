# Tech Mak Labs — Keyword Intelligence (Prototype v0.5)

A lightweight SEO research app that combines Google Search Console CSV evidence with a public website content scan.

## Run locally
- Python 3.9+ recommended
- `python server.py`
- Open `http://localhost:8080`

No third-party Python packages, paid SEO API, or database are required for this prototype.

## Deploy to Railway
1. Upload the contents of this folder to the root of a GitHub repository.
2. In Railway, create a project from that GitHub repository.
3. Railway should detect the `Procfile`; the start command is `python server.py`.
4. Deploy and open the generated public domain.

## Current capabilities
- 50 preloaded DivineCare Physio target keywords
- Import Search Console Queries and Pages CSV exports
- Import multiple query-filtered Pages CSV exports to map query → URL
- Website content scan: up to 30 same-domain HTML pages per run
- Compare target phrases against page titles, H1/H2/H3 headings and visible text
- Flag potential content gaps and title/H1 placement gaps
- Potential URL overlap review and CSV exports
- CSV processing remains in the browser; the crawler fetches only public pages on the server

## Important limitations
- This is a prototype, not a multi-user product; no accounts, database, or persistent project storage.
- Website scan is a lightweight HTML crawler, not a full browser. JavaScript-rendered content may be missed. Pages blocked by site access controls, robots restrictions, timeouts, or server responses may not be scanned.
- Maximum 30 pages per scan. It does not fetch live rankings, search volumes, competitor data, or Google Business Profile data.
- Exact phrase absence is not proof of a topic gap; synonyms and semantic relevance need human review.
- Multiple URLs for one query are a review signal, not definitive cannibalization.
- This server-side crawler is intended for a controlled prototype. Before public multi-user launch, add rate limiting, stronger DNS-rebinding protections, crawl policy/robots handling, request logging, and abuse controls.

Never paste Google passwords or API keys into the app.
