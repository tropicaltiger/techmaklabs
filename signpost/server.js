// Signpost server for Railway. Holds the Anthropic key and forwards requests.
// Variables: ANTHROPIC_API_KEY (required), ANTHROPIC_MODEL, WEB_SEARCH_TOOL,
// MAX_OUTPUT_TOKENS, RATE_LIMIT_PER_HOUR, ANTHROPIC_API_URL
const express = require('express');
const path = require('path');

const app = express();
app.set('trust proxy', 1);
const PORT = process.env.PORT || 3000;
const MODEL = process.env.ANTHROPIC_MODEL || 'claude-sonnet-5-5';
const SEARCH_TOOL = process.env.WEB_SEARCH_TOOL || 'web_search_20250305';
const MAX_TOKENS = parseInt(process.env.MAX_OUTPUT_TOKENS, 10) || 2000;
const LIMIT = parseInt(process.env.RATE_LIMIT_PER_HOUR, 10) || 40;
const API_URL = process.env.ANTHROPIC_API_URL || 'https://api.anthropic.com/v1/messages';
const MAX_PROMPT = 8000;

app.use(express.json({ limit: '64kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// simple in-memory per-IP limiter
const hits = new Map();
setInterval(() => { const now = Date.now(); for (const [k, v] of hits) if (v.reset < now) hits.delete(k); }, 600000).unref();
function limiter(req, res, next) {
  const now = Date.now();
  let h = hits.get(req.ip);
  if (!h || h.reset < now) { h = { n: 0, reset: now + 3600000 }; hits.set(req.ip, h); }
  if (++h.n > LIMIT) {
    return res.status(429).json({ error: { message: 'Hourly limit reached. Try again in ' + Math.ceil((h.reset - now) / 60000) + ' minutes.' } });
  }
  next();
}

app.post('/api/generate', limiter, async (req, res) => {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return res.status(500).json({ error: { message: 'ANTHROPIC_API_KEY is not set in Railway variables.' } });
  const { prompt, useSearch } = req.body || {};
  if (!prompt || typeof prompt !== 'string') return res.status(400).json({ error: { message: "Missing 'prompt'." } });
  if (prompt.length > MAX_PROMPT) return res.status(413).json({ error: { message: 'Prompt is too long.' } });

  const body = { model: MODEL, max_tokens: MAX_TOKENS, messages: [{ role: 'user', content: prompt }] };
  if (useSearch) body.tools = [{ type: SEARCH_TOOL, name: 'web_search', max_uses: 2 }];

  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 90000);
  try {
    const r = await fetch(API_URL, {
      method: 'POST', signal: ctl.signal,
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify(body)
    });
    const data = await r.json();
    res.status(r.status).json(data);
  } catch (err) {
    console.error('Upstream error:', err.name);
    const timeout = err.name === 'AbortError';
    res.status(timeout ? 504 : 502).json({ error: { message: timeout ? 'The AI service took too long. Try again.' : 'Could not reach the AI service.' } });
  } finally { clearTimeout(timer); }
});

app.get('/health', (req, res) => res.json({ ok: true }));
app.use((err, req, res, next) => {
  const status = err.status || 500;
  res.status(status).json({ error: { message: status === 413 ? 'Request too large.' : 'Bad request.' } });
});
if (require.main === module) app.listen(PORT, () => console.log('Signpost running on port ' + PORT));
module.exports = app;
