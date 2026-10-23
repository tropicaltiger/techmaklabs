"""Minimal app server plus a cautious, same-domain public HTML crawler."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin, urldefrag
from xml.etree import ElementTree
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import ipaddress, json, os, socket, re, time

PORT = int(os.environ.get("PORT", "8080"))
MAX_BYTES = 1_500_000
USER_AGENT = "TechMakLabsKeywordAudit/0.6 (+public-site SEO audit)"

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []; self.h1 = []; self.headings = []; self.text = []; self.links = []
        self._tag = None; self._skip = 0; self._in_title = False; self._heading = None
        self.canonical = None; self.meta_robots = ""
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip += 1
        if tag == "title": self._in_title = True
        if tag in ("h1", "h2", "h3"):
            self._heading = tag; self.headings.append([])
            if tag == "h1": self.h1.append([])
        if tag == "a" and a.get("href"): self.links.append(a["href"])
        if tag == "link" and a.get("rel", "").lower() == "canonical": self.canonical = a.get("href")
        if tag == "meta" and a.get("name", "").lower() == "robots": self.meta_robots = a.get("content", "").lower()
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template") and self._skip: self._skip -= 1
        if tag == "title": self._in_title = False
        if tag == self._heading: self._heading = None
    def handle_data(self, data):
        if self._skip: return
        val = re.sub(r"\s+", " ", data).strip()
        if not val: return
        if self._in_title: self.title.append(val)
        if self._heading and self.headings: self.headings[-1].append(val)
        if self._heading == "h1" and self.h1: self.h1[-1].append(val)
        self.text.append(val)
    def result(self, url):
        title = " ".join(self.title).strip()
        headings = [" ".join(x).strip() for x in self.headings if " ".join(x).strip()]
        h1 = [" ".join(x).strip() for x in self.h1 if " ".join(x).strip()]
        return {"url": url, "title": title, "h1": h1, "headings": headings, "text": " ".join(self.text)[:100000], "links": self.links, "noindex": "noindex" in self.meta_robots}

def validate_public_host(host):
    if not host or host.lower() in ("localhost", "localhost.localdomain"):
        raise ValueError("Please enter a public website domain")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError("The domain could not be resolved")
    if not infos: raise ValueError("The domain could not be resolved")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError("Private or local network addresses are not allowed")

def fetch_page(url, host):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname != host:
        return None
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=8) as response:
        final = urlparse(response.geturl())
        if final.hostname != host or final.scheme not in ("http", "https"):
            return None
        ctype = response.headers.get("Content-Type", "").lower()
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype: return None
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raw = raw[:MAX_BYTES]
        charset = response.headers.get_content_charset() or "utf-8"
        html = raw.decode(charset, errors="replace")
    parser = PageParser(); parser.feed(html)
    return parser.result(response.geturl())


def fetch_sitemap_urls(url, host, max_urls=150):
    """Read public sitemap XML cautiously; return same-host page URLs only."""
    found = []
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,*/*"})
        with urlopen(req, timeout=6) as response:
            if response.getcode() >= 400:
                return found
            raw = response.read(1_000_000)
        root = ElementTree.fromstring(raw)
        root_name = root.tag.rsplit("}", 1)[-1].lower()
        if root_name == "sitemapindex":
            child_maps = []
            for node in root:
                if node.tag.rsplit("}", 1)[-1].lower() == "sitemap":
                    loc = next((c.text for c in node if c.tag.rsplit("}", 1)[-1].lower() == "loc"), None)
                    if loc and urlparse(loc).hostname == host:
                        child_maps.append(loc.strip())
            for child in child_maps[:5]:
                found.extend(fetch_sitemap_urls(child, host, max(0, max_urls-len(found))))
                if len(found) >= max_urls:
                    break
        elif root_name == "urlset":
            for node in root:
                if node.tag.rsplit("}", 1)[-1].lower() != "url":
                    continue
                loc = next((c.text for c in node if c.tag.rsplit("}", 1)[-1].lower() == "loc"), None)
                if loc:
                    loc = urldefrag(loc.strip())[0]
                    parsed = urlparse(loc)
                    if parsed.scheme in ("http", "https") and parsed.hostname == host and not parsed.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip", ".xml", ".css", ".js")):
                        found.append(loc)
                        if len(found) >= max_urls:
                            break
    except Exception:
        return found
    return found


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()
    def do_POST(self):
        if self.path != "/api/crawl":
            self.send_error(404); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 10000: raise ValueError("Invalid request size")
            body = json.loads(self.rfile.read(length))
            raw_url = str(body.get("url", "")).strip()
            if not raw_url.startswith(("https://", "http://")): raw_url = "https://" + raw_url
            parsed = urlparse(raw_url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme not in ("https", "http") or not host or parsed.username or parsed.password:
                raise ValueError("Enter a valid public http(s) website URL")
            validate_public_host(host)
            try: max_pages = max(1, min(int(body.get("max_pages", 30)), 30))
            except (TypeError, ValueError): max_pages = 30
            start = f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"
            queue = [urldefrag(start)[0]]
            # Sitemap URLs help discover service/blog pages that are not linked from the homepage.
            robots_sitemaps = []
            try:
                req = Request(f"{parsed.scheme}://{parsed.netloc}/robots.txt", headers={"User-Agent": USER_AGENT})
                with urlopen(req, timeout=4) as response:
                    robots_text = response.read(200_000).decode("utf-8", errors="replace")
                for line in robots_text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sm = line.split(":", 1)[1].strip()
                        if urlparse(sm).hostname == host:
                            robots_sitemaps.append(sm)
            except Exception:
                pass
            sitemap_candidates = robots_sitemaps[:3] + [f"{parsed.scheme}://{parsed.netloc}/sitemap.xml",
                                                        f"{parsed.scheme}://{parsed.netloc}/sitemap_index.xml"]
            sitemap_urls = []
            for sm in dict.fromkeys(sitemap_candidates):
                sitemap_urls.extend(fetch_sitemap_urls(sm, host, 150))
                if len(sitemap_urls) >= 150:
                    break
            queue.extend(u for u in sitemap_urls if u not in queue)
            seen = set(); pages = []
            while queue and len(seen) < max_pages:
                url = queue.pop(0)
                pu = urlparse(url)
                if url in seen or pu.hostname != host or pu.scheme not in ("http", "https"): continue
                if pu.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".zip", ".xml", ".css", ".js")): continue
                seen.add(url)
                try:
                    page = fetch_page(url, host)
                    if not page: continue
                    pages.append({k:v for k,v in page.items() if k != "links"})
                    for href in page["links"]:
                        link = urldefrag(urljoin(url, href))[0]
                        lp = urlparse(link)
                        if lp.hostname == host and lp.scheme in ("http", "https") and link not in seen and len(queue) < 200:
                            queue.append(link)
                except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                    continue
                time.sleep(0.08)
            self._json(200, {"domain": host, "pages": pages, "visited": len(seen), "limit": max_pages, "discovery": "homepage links + same-domain sitemap URLs"})
        except Exception as exc:
            self._json(400, {"error": str(exc) or "Could not scan website"})
    def _json(self, code, data):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
