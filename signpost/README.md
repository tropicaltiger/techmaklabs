# Signpost on Railway

Local question research plus Business Profile posts and articles, for local business clients.

## Files
- `server.js`: small Express server. Keeps your Anthropic key on the server and forwards requests, with an hourly limit per visitor.
- `public/index.html`: the Signpost app.
- `package.json`, `railway.json`: Railway build and start settings.

## Deploy
1. Create an API key at console.anthropic.com (billing must be set up first). Debit cards work only if international online payments are on.
2. Push this folder to a GitHub repo (private is fine).
3. On railway.app choose New Project, then Deploy from GitHub repo, and pick it.
4. In the service, open Variables and add `ANTHROPIC_API_KEY` with your key.
5. In Settings, under Networking, click Generate Domain. Open the link.

## Optional variables
| Name | Default | Purpose |
|---|---|---|
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model used for every call |
| `MAX_OUTPUT_TOKENS` | `2000` | Longer articles need more |
| `RATE_LIMIT_PER_HOUR` | `40` | Calls per visitor per hour. Protects your bill |
| `WEB_SEARCH_TOOL` | `web_search_20250305` | Change only if Anthropic retires it |
| `ANTHROPIC_API_URL` | Anthropic's URL | For testing with a mock |

## Change the name
Open `public/index.html`, find the block between `CONFIG_START` and `CONFIG_END`, and edit `brand`. The page title and logo sign update on their own.

## Cost
Roughly 3 to 4 cents for one full cycle (find questions, one post, one article). Set a budget alert in the Anthropic Console.

## Keep it private
Anyone with the link can spend your credits, up to the hourly limit. Share the link only with clients you trust, or add a password in front of it.
