# Tech Mak Labs — Keyword Intelligence (Prototype v0.4)

A lightweight web app for validating target keywords against Google Search Console CSV exports.

## Run locally
- Python 3.9+ recommended
- `python server.py`
- Open `http://localhost:8080`

No API keys, paid services, database, or third-party JavaScript libraries are required for this prototype.

## Deploy to Railway
1. Create a new GitHub repository and upload these files.
2. In Railway, create a project from that GitHub repository.
3. Railway should detect the `Procfile`; the start command is `python server.py`.
4. Deploy and open the generated public domain.
5. Add a custom domain later if desired.

## Current capabilities
- Preloaded 50 DivineCare Physio target keywords
- Import Queries and Pages CSV exports
- Import multiple query-filtered Pages CSV exports; filename is used to identify the query (e.g. `physiotherapy-langley.csv`)
- Keyword-to-page evidence table and possible overlap review
- CSV exports

## Limitations
- This is a prototype, not a multi-user product; it has no accounts, database, or persistent project storage.
- CSV data is processed locally in the browser and is not uploaded.
- It does not fetch live rankings, search volumes, competitor data, or Google Business Profile data.
- A query missing from an export is not proof of zero search demand.
- Multiple URLs appearing for a query is a review signal, not definitive cannibalization.

## Important
Do not paste Google passwords or API keys into the app. Before adding Search Console OAuth, define consent, data storage, and access controls.
