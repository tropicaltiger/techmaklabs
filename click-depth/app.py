"""
Web app around click_depth.py.

Routes
  GET  /                  the page
  POST /api/start         {url, keywords, max_pages, deep} -> {job_id}
  GET  /api/status/<id>   progress, and the report once finished
  GET  /health            for the host's health check

Crawls take minutes, so each one runs in a background thread and the page polls
for progress. Jobs live in memory, so run a SINGLE worker process (see Procfile).
"""
import ipaddress
import os
import socket
import threading
import time
import uuid
from urllib.parse import urljoin, urlparse

import requests
from flask import Flask, jsonify, render_template, request

import click_depth as cd

app = Flask(__name__)

MAX_PAGES_CAP = int(os.environ.get("MAX_PAGES_CAP", 300))
MAX_RUNNING_JOBS = int(os.environ.get("MAX_RUNNING_JOBS", 3))
CRAWL_DELAY = float(os.environ.get("CRAWL_DELAY", 0.3))
JOB_TTL_SECONDS = 3600
MAX_BODY_BYTES = 2_000_000

JOBS = {}
LOCK = threading.Lock()


# ------------------------------------------------------------ safe fetching
# This app is public, so people could point it at internal addresses
# (localhost, cloud metadata, private networks). Every request, including each
# redirect hop, is checked to make sure it resolves to a public IP.
def is_public_url(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        return False
    for info in infos:
        try:
            if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
                return False
        except ValueError:
            return False
    return True


def safe_get(url, timeout=15):
    """GET with manual redirects (max 5 hops), each hop checked. Returns (response, final_url)."""
    for _ in range(6):
        if not is_public_url(url):
            return None, url
        try:
            r = requests.get(
                url, headers={"User-Agent": cd.USER_AGENT}, timeout=timeout,
                allow_redirects=False, stream=True,
            )
        except requests.RequestException:
            return None, url
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location")
            r.close()
            if not loc:
                return None, url
            url = urljoin(url, loc)
            continue
        return r, url
    return None, url


def read_body(r):
    chunks, size = [], 0
    for chunk in r.iter_content(65536):
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            break
        chunks.append(chunk)
    r.close()
    return b"".join(chunks).decode(r.encoding or "utf-8", errors="replace")


def safe_fetch(url):
    r, final = safe_get(url)
    if r is None or r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
        if r is not None:
            r.close()
        return final, None
    return final, read_body(r)


def safe_text(url):
    r, _ = safe_get(url)
    if r is None or r.status_code != 200:
        if r is not None:
            r.close()
        return None
    return read_body(r)


# ------------------------------------------------------------ jobs
def cleanup_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    with LOCK:
        for jid in [j for j, v in JOBS.items() if v["created"] < cutoff]:
            del JOBS[jid]


def run_job(job_id, url, max_pages, keywords, deep):
    job = JOBS[job_id]
    try:
        site = cd.crawl(
            url, max_pages=max_pages, delay=CRAWL_DELAY,
            fetch=safe_fetch, sitemap_fetch=safe_text,
            progress=lambda done, queued, cur: job.update(crawled=done, queued=queued, current=cur),
        )
        if not site["pages"]:
            job.update(status="error", error="Could not read any pages. Check the address, "
                       "or the site may block crawlers (robots.txt).")
            return
        job["report"] = cd.analyze(site, deep_threshold=deep, keywords=keywords)
        job["status"] = "done"
    except Exception as exc:  # keep the thread from dying silently
        job.update(status="error", error=f"Crawl failed: {exc}")


def clamp(value, low, high, default):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------ routes
@app.get("/")
def index():
    return render_template("index.html", max_pages_cap=MAX_PAGES_CAP)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/start")
def start():
    cleanup_jobs()
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="Enter a website address."), 400
    if "://" not in url:
        url = "https://" + url
    if not is_public_url(url):
        return jsonify(error="That address can't be reached. Use a public website, "
                             "for example https://example.com"), 400

    raw = data.get("keywords") or ""
    keywords = [k.strip() for k in raw.replace(",", "\n").splitlines() if k.strip()][:10]
    max_pages = clamp(data.get("max_pages"), 10, MAX_PAGES_CAP, 100)
    deep = clamp(data.get("deep"), 2, 8, 4)

    with LOCK:
        running = sum(1 for j in JOBS.values() if j["status"] == "running")
        if running >= MAX_RUNNING_JOBS:
            return jsonify(error="The tool is busy with other crawls. Try again in a minute."), 429
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = {"status": "running", "created": time.time(), "crawled": 0,
                        "queued": 0, "current": "", "max_pages": max_pages}
    threading.Thread(target=run_job, args=(job_id, url, max_pages, keywords, deep), daemon=True).start()
    return jsonify(job_id=job_id)


@app.get("/api/status/<job_id>")
def status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="This crawl has expired. Start a new one."), 404
    out = {k: job[k] for k in ("status", "crawled", "queued", "current", "max_pages")}
    if job["status"] == "done":
        out["report"] = job["report"]
    if job["status"] == "error":
        out["error"] = job["error"]
    return jsonify(out)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)

