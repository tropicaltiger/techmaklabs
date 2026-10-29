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
    """Canonicalize URL syntax while preserving the site's actual host and scheme."""
    url, _ = urldefrag((url or "").strip())
    p = urlparse(url)
    scheme = p.scheme.lower()
    host = (p.hostname or "").lower()
    if not scheme or not host:
        return url
    try:
        port = p.port
    except ValueError:
        port = None
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                   if not any(k.lower().startswith(t) for t in TRACKING))
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return p._replace(scheme=scheme, netloc=netloc, path=path,
                      params="", query=urlencode(query, doseq=True), fragment="").geturl()


def is_low_value_url(url):
    """Exclude common technical/archive URLs from orphan-content recommendations."""
    p = urlparse(url)
    path = p.path.lower().rstrip("/") or "/"
    if path.endswith(("/feed", "/rss", "/rss.xml", "/comments/feed")):
        return True
    if re.search(r"/(author|tag|category)/[^/]+(?:/page/\d+)?$", path):
        return True
    if re.search(r"/page/\d+$", path):
        return True
    if any(k.lower() in {"feed", "output"} for k, _ in parse_qsl(p.query)):
        return True
    return False


def tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def same_site(url, host):
    h = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return h == host.lower().removeprefix("www.")


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
    aliases = {}  # requested URL -> final URL after redirects
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
        if final_url != url:
            aliases[url] = final_url
        if final_url in pages:
            # A second route redirected to a page already crawled. Keep its alias
            # so links and sitemap entries resolve to the same graph node.
            aliases[url] = final_url
            continue

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

    def resolve_alias(url):
        seen = set()
        while url in aliases and url not in seen:
            seen.add(url)
            url = aliases[url]
        return url

    # Resolve redirect aliases before building the graph. This prevents false
    # zero-inbound counts and self-link recommendations caused by URL variants.
    for src, info in pages.items():
        resolved = set()
        for target in info["outlinks"]:
            target = resolve_alias(target)
            if target in pages and target != src:
                resolved.add(target)
        info["outlinks"] = resolved
        info["inlinks"] = set()
    for src, info in pages.items():
        for target in info["outlinks"]:
            pages[target]["inlinks"].add(src)

    sitemap_urls = [resolve_alias(u) for u in read_sitemap(start, sitemap_fetch)]
    return {"start": resolve_alias(start), "pages": pages,
            "sitemap_urls": sorted(set(sitemap_urls)), "truncated": truncated,
            "aliases": aliases}


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
    # Canonical URL identity matters: never recommend a self-link or an edge
    # that already exists in the graph.
    if target not in pages:
        return []
    t_tokens = pages[target]["tokens"]
    scored = []
    for url, info in pages.items():
        if url == target or info["depth"] > max_depth or target in info["outlinks"]:
            continue
        overlap = len(t_tokens & info["tokens"])
        if overlap:
            scored.append((overlap, -info["depth"], url))
    scored.sort(reverse=True)
    results = []
    for overlap, neg_depth, url in scored[:n]:
        shared = sorted(t_tokens & pages[url]["tokens"])
        results.append({
            "link_from": url,
            "shared_topic_words": shared,
            "target_url": target,
            "rationale": "Shares topic terms with the target and does not currently link to it.",
            "confidence": "medium" if overlap >= 3 else "low",
        })
    return results


def analyze(site, deep_threshold=4, weak_threshold=2, keywords=None):
    pages = site["pages"]
    keywords = [k.lower() for k in (keywords or [])]
    kw_tokens = [tokens(k) for k in keywords]

    def matched_keywords(info):
        return [keywords[i] for i, kt in enumerate(kw_tokens)
                if kt and kt <= info["tokens"]]

    def is_money_page(info):
        return bool(matched_keywords(info))

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
                "matched_keywords": matched_keywords(info),
                "click_path": path_to(pages, url),
                "suggestions": suggest_linkers(pages, url),
            })
    deep.sort(key=lambda d: (d["priority"] != "HIGH", -d["depth"]))

    # Sitemap candidates are split into genuinely observed orphans and URLs that
    # were not crawled (whose inbound-link status cannot be inferred reliably).
    crawled = set(pages)
    sitemap_candidates = [u for u in site["sitemap_urls"] if not is_low_value_url(u)]
    linked_from_crawl = {target for info in pages.values() for target in info["outlinks"]}
    # These URLs were not linked from any crawled page. With a complete crawl this
    # is strong evidence of an orphan; after a page-limit stop it remains uncertain
    # because an uncrawled page could contain the missing link.
    unlinked_sitemap_urls = [u for u in sitemap_candidates
                             if u != site["start"] and u not in linked_from_crawl]
    not_crawled = [u for u in sitemap_candidates
                   if u not in crawled and u in linked_from_crawl]
    orphans = {
        "status": "uncertain - crawl reached its page limit" if site["truncated"]
                  else "not linked from any crawled page",
        "urls": sorted(set(unlinked_sitemap_urls)),
        "not_crawled_urls": sorted(set(not_crawled)),
        "not_crawled_count": len(set(not_crawled)),
        "excluded_low_value_count": len(site["sitemap_urls"]) - len(sitemap_candidates),
    }

    # Weakly linked (shallow but only 1-2 inbound links, excluding homepage)
    weak = [
        {"url": u, "depth": i["depth"], "inbound_links": len(i["inlinks"]),
         "priority": "HIGH" if is_money_page(i) else "normal",
         "matched_keywords": matched_keywords(i),
         "suggestions": suggest_linkers(pages, u)}
        for u, i in pages.items()
        if u != site["start"] and len(i["inlinks"]) <= weak_threshold and i["depth"] < deep_threshold
    ]
    weak.sort(key=lambda d: (d["priority"] != "HIGH", d["inbound_links"]))

    notes = []
    if site["truncated"]:
        notes.append(f"Crawled {len(pages)} pages and reached the selected limit; "
                     "depth and link findings cover only the pages discovered within this crawl.")
    if orphans["not_crawled_count"]:
        notes.append(f"{orphans['not_crawled_count']} sitemap URL(s) were linked from crawled pages but not crawled before the limit; their depth and inbound-link counts are incomplete.")
    if orphans["excluded_low_value_count"]:
        notes.append(f"Excluded {orphans['excluded_low_value_count']} feed, archive, or pagination URL(s) from content-orphan recommendations.")
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
