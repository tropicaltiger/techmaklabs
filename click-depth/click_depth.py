"""
click_depth.py - find buried pages, orphan pages and weakly linked pages.

Dependencies: requests, beautifulsoup4
    pip install requests beautifulsoup4

Quick use:
    python click_depth.py https://example.com --max-pages 300 --keywords "wedding catering,corporate catering"

In your own app:
    from click_depth import crawl, analyze
    site = crawl("https://example.com", max_pages=300)
    report = analyze(site, keywords=["wedding catering"])
"""
import re
import sys
import time
import json
import argparse
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque, Counter
from urllib.parse import urljoin, urldefrag, urlparse, parse_qsl, urlencode

USER_AGENT = "OnPageAuditBot/1.0 (+contact: you@example.com)"  # change this
SKIP_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".pdf", ".zip",
    ".mp4", ".mp3", ".css", ".js", ".xml", ".json", ".woff", ".woff2", ".ttf",
)
TRACKING = ("utm_", "fbclid", "gclid", "mc_", "ref")
STOPWORDS = set(
    "the a an and or of in on for to with at by from is are be this that your our you we "
    "page home about contact us".split()
)


# ----------------------------------------------------------------- helpers
def normalize(url):
    """Drop fragments and tracking params, lowercase host, strip trailing slash."""
    url, _ = urldefrag(url.strip())
    p = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(TRACKING)]
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return p._replace(netloc=p.netloc.lower(), path=path, query=urlencode(query)).geturl()


def tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def same_site(url, host):
    h = urlparse(url).netloc.lower()
    return h == host or h == "www." + host or "www." + h == host


# ----------------------------------------------------------------- fetching
def default_fetch(url, timeout=15):
    """Return (final_url, html_or_None). Only HTML responses are returned."""
    import requests

    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.RequestException:
        return url, None
    if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
        return r.url, None
    return r.url, r.text


def read_sitemap(base, fetch_text, limit=2000):
    """Collect URLs from /sitemap.xml (follows one level of sitemap index)."""
    urls, queue, seen = [], [urljoin(base, "/sitemap.xml")], set()
    while queue and len(urls) < limit:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        body = fetch_text(sm)
        if not body:
            continue
        try:
            root = ET.fromstring(body.encode("utf-8") if isinstance(body, str) else body)
        except ET.ParseError:
            continue
        for loc in root.iter():
            if loc.tag.endswith("loc") and loc.text:
                u = loc.text.strip()
                (queue if u.endswith(".xml") else urls).append(u)
    return [normalize(u) for u in urls[:limit]]


def _text_fetch(url):
    import requests

    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        return r.text if r.status_code == 200 else None
    except requests.RequestException:
        return None


# ----------------------------------------------------------------- crawling
def crawl(start_url, max_pages=300, delay=0.5, fetch=None, sitemap_fetch=None,
          respect_robots=True, progress=None):
    """
    Breadth-first crawl. BFS guarantees each page gets its SHORTEST click depth.
    Returns a dict:
      pages: {url: {depth, parent, title, h1, tokens, outlinks:set, inlinks:set}}
      sitemap_urls, truncated (True if max_pages stopped the crawl)
    progress(pages_done, queue_size, current_url) is called after every page, if given.
    """
    fetch = fetch or default_fetch
    sitemap_fetch = sitemap_fetch or _text_fetch
    start = normalize(start_url)
    host = urlparse(start).netloc.lower().removeprefix("www.")

    robots = None
    if respect_robots:
        # Fetched through the same text fetcher as the sitemap, so a hosting app
        # can plug in its own safe fetcher. A missing robots.txt means "allow all".
        body = sitemap_fetch(urljoin(start, "/robots.txt"))
        if body:
            robots = urllib.robotparser.RobotFileParser()
            robots.parse(body.splitlines())

    from bs4 import BeautifulSoup

    pages, queue, queued = {}, deque([(start, 0, None)]), {start}
    truncated = False

    while queue:
        url, depth, parent = queue.popleft()
        if len(pages) >= max_pages:
            truncated = True
            break
        if robots and not robots.can_fetch(USER_AGENT, url):
            continue

        final_url, html = fetch(url)
        if html is None:
            continue
        final_url = normalize(final_url)
        if final_url != url and final_url in pages:
            continue  # redirected onto a page we already have

        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        h1 = soup.h1.get_text(strip=True) if soup.h1 else ""

        # Links inside nav/footer still count as real clicks, so we keep them.
        outlinks = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#", "whatsapp:")):
                continue
            target = normalize(urljoin(final_url, href))
            if urlparse(target).scheme not in ("http", "https"):
                continue
            if not same_site(target, host) or target.lower().endswith(SKIP_EXT):
                continue
            if target != final_url:
                outlinks.add(target)

        pages[final_url] = {
            "depth": depth,
            "parent": parent,
            "title": title,
            "h1": h1,
            "tokens": tokens(f"{title} {h1} {urlparse(final_url).path.replace('-', ' ')}"),
            "outlinks": outlinks,
            "inlinks": set(),
        }
        for t in sorted(outlinks):
            if t not in queued:
                queued.add(t)
                queue.append((t, depth + 1, final_url))
        if progress:
            progress(len(pages), len(queue), final_url)
        if delay:
            time.sleep(delay)

    # Build inlinks (only counting links from pages we actually crawled).
    for src, info in pages.items():
        for t in info["outlinks"]:
            if t in pages:
                pages[t]["inlinks"].add(src)

    sitemap_urls = read_sitemap(start, sitemap_fetch)
    return {"start": start, "pages": pages, "sitemap_urls": sitemap_urls, "truncated": truncated}


# ----------------------------------------------------------------- analysis
def path_to(pages, url):
    """Click path from the homepage to this page."""
    path = []
    while url:
        path.append(url)
        url = pages[url]["parent"] if url in pages else None
    return path[::-1]


def suggest_linkers(pages, target, max_depth=2, n=3):
    """Pick shallow pages whose topic overlaps the target and that don't link to it yet."""
    t_tokens = pages[target]["tokens"] if target in pages else set()
    scored = []
    for url, info in pages.items():
        if url == target or info["depth"] > max_depth or target in info["outlinks"]:
            continue
        overlap = len(t_tokens & info["tokens"])
        if overlap:
            scored.append((overlap, -info["depth"], url))
    scored.sort(reverse=True)
    return [
        {"link_from": u, "shared_topic_words": sorted(t_tokens & pages[u]["tokens"])}
        for _, _, u in scored[:n]
    ]


def analyze(site, deep_threshold=4, weak_threshold=2, keywords=None):
    pages = site["pages"]
    keywords = [k.lower() for k in (keywords or [])]
    kw_tokens = [tokens(k) for k in keywords]

    def is_money_page(info):
        return any(kt and kt <= info["tokens"] for kt in kw_tokens)

    # Distribution
    dist = Counter(info["depth"] for info in pages.values())

    # Deep pages
    deep = []
    for url, info in pages.items():
        if info["depth"] >= deep_threshold:
            deep.append({
                "url": url,
                "depth": info["depth"],
                "inbound_links": len(info["inlinks"]),
                "priority": "HIGH" if is_money_page(info) else "normal",
                "click_path": path_to(pages, url),
                "suggestions": suggest_linkers(pages, url),
            })
    deep.sort(key=lambda d: (d["priority"] != "HIGH", -d["depth"]))

    # Orphans: in sitemap but never linked from a crawled page
    crawled = set(pages)
    sitemap_only = [u for u in site["sitemap_urls"] if u not in crawled]
    orphans = {
        "status": "uncertain - crawl hit the page limit, these may just be undiscovered"
        if site["truncated"] else "confirmed - in sitemap but not linked from anywhere crawled",
        "urls": sitemap_only,
    }

    # Weakly linked (shallow but only 1-2 inbound links, excluding homepage)
    weak = [
        {"url": u, "depth": i["depth"], "inbound_links": len(i["inlinks"]),
         "priority": "HIGH" if is_money_page(i) else "normal",
         "suggestions": suggest_linkers(pages, u)}
        for u, i in pages.items()
        if u != site["start"] and len(i["inlinks"]) <= weak_threshold and i["depth"] < deep_threshold
    ]
    weak.sort(key=lambda d: (d["priority"] != "HIGH", d["inbound_links"]))

    notes = []
    if site["truncated"]:
        notes.append(f"Crawled {len(pages)} pages and stopped at the limit; "
                     "deeper pages may exist, so depth figures are incomplete.")
    return {
        "pages_crawled": len(pages),
        "max_depth": max(dist) if dist else 0,
        "depth_distribution": dict(sorted(dist.items())),
        "deep_pages": deep,
        "orphan_pages": orphans,
        "weakly_linked_pages": weak,
        "notes": notes,
    }


# ----------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="Find buried, orphan and weakly linked pages.")
    ap.add_argument("url")
    ap.add_argument("--max-pages", type=int, default=300)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--deep", type=int, default=4, help="depth treated as buried")
    ap.add_argument("--keywords", default="", help="comma-separated target keywords")
    ap.add_argument("--json", action="store_true", help="print raw JSON")
    a = ap.parse_args()

    site = crawl(a.url, max_pages=a.max_pages, delay=a.delay)
    rep = analyze(site, deep_threshold=a.deep, keywords=[k for k in a.keywords.split(",") if k.strip()])

    if a.json:
        print(json.dumps(rep, indent=2))
        return
    print(f"Pages crawled: {rep['pages_crawled']}   Deepest page: {rep['max_depth']} clicks")
    print("Depth distribution:", rep["depth_distribution"])
    for n in rep["notes"]:
        print("NOTE:", n)
    print(f"\nBuried pages (depth >= {a.deep}): {len(rep['deep_pages'])}")
    for d in rep["deep_pages"][:20]:
        print(f"  [{d['priority']}] depth {d['depth']}  {d['url']}")
        for s in d["suggestions"]:
            print(f"        -> link from {s['link_from']}")
    print(f"\nOrphan pages ({rep['orphan_pages']['status']}): {len(rep['orphan_pages']['urls'])}")
    for u in rep["orphan_pages"]["urls"][:20]:
        print("  ", u)
    print(f"\nWeakly linked pages: {len(rep['weakly_linked_pages'])}")
    for w in rep["weakly_linked_pages"][:20]:
        print(f"  [{w['priority']}] {w['inbound_links']} inbound  {w['url']}")


if __name__ == "__main__":
    sys.exit(main())
