import ipaddress
import logging
import os
import re
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Serialize headless browser scrapes so memory usage remains bounded on small hosts
_playwright_lock = threading.Lock()

# SSRF Protection: Block internal, private, loopback, and cloud metadata addresses
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

ASSET_EXT_REGEX = re.compile(
    r"\.(pdf|jpg|jpeg|png|gif|webp|ico|zip|rar|tar|gz|docx|xlsx|pptx|svg|css|js|mp4|mp3|woff2?)$",
    re.IGNORECASE,
)


class SpaScrapeError(Exception):
    """Raised when a JavaScript SPA cannot be rendered into readable text."""


def is_safe_url(url: str) -> bool:
    """Validate that the URL uses HTTP/HTTPS and resolves only to public, non-private IP addresses."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Block localhost and cloud metadata hostnames explicitly
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            return False

        # Resolve IP addresses for the hostname
        addr_info = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            for network in BLOCKED_IP_NETWORKS:
                if ip_obj in network:
                    return False
        return True
    except Exception:
        return False


def _apex_host(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parsed.port
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        return f"{host}:{port}"
    return host


def _is_same_site(url_a: str, url_b: str) -> bool:
    pa = urlparse(url_a)
    pb = urlparse(url_b)
    return pb.scheme in ("http", "https") and _apex_host(url_a) == _apex_host(url_b)


def clean_html_content(soup: BeautifulSoup) -> str:
    """Extract readable text and eliminate nav, scripts, styles, forms, and footers."""
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "iframe"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_internal_links(soup: BeautifulSoup, current_url: str, anchor_url: str) -> List[str]:
    """Extract same-site HTTP/HTTPS links from soup BEFORE mutating/decomposing nav/footer tags."""
    discovered: List[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = (a_tag.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        joined_url = urljoin(current_url, href)
        parsed_joined = urlparse(joined_url)
        if not _is_same_site(anchor_url, joined_url):
            continue
        if ASSET_EXT_REGEX.search(parsed_joined.path or ""):
            continue
        clean_link = joined_url.split("#")[0].rstrip("/") or joined_url.split("#")[0]
        if clean_link not in discovered:
            discovered.append(clean_link)
    return discovered


def _looks_like_spa_shell(html_text: str, cleaned_len: int) -> bool:
    """Detect pages that serve an empty JS application shell instead of server-rendered HTML."""
    if cleaned_len > 150:
        return False
    lower = html_text.lower()
    if re.search(r'<div[^>]+id=["\'](?:root|app|__next|___gatsby)["\']', html_text, re.IGNORECASE):
        return True
    if "enable javascript" in lower or "without javascript enabled" in lower:
        return True
    if "<script" in lower and ("type=\"module\"" in lower or "/static/js/" in lower or "/assets/" in lower):
        return True
    return False


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> List[str]:
    """Split text into manageable overlapping chunks based on words."""
    words = text.split()
    if not words:
        return []

    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk:
            chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
        i += chunk_size - overlap
    return chunks


class WebsiteScraper:
    def __init__(self, max_pages: int = 50, timeout: int = 10, delay: float = 0.5):
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay
        self.headers = {
            "User-Agent": "PrayatnaAIBot/1.0 (+https://prayatna.co.in/)",
            "Accept": "text/html,application/xhtml+xml",
        }
        self.browser_user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )

    def _safe_get(self, url: str, anchor_url: str, max_redirects: int = 5) -> Optional[requests.Response]:
        """Fetch URL with explicit per-hop SSRF validation on redirects."""
        current = url
        for _ in range(max_redirects + 1):
            if not is_safe_url(current):
                return None
            resp = requests.get(
                current,
                headers=self.headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    return None
                next_url = urljoin(current, location)
                if not is_safe_url(next_url) or not _is_same_site(anchor_url, next_url):
                    return None
                current = next_url
                continue
            return resp
        return None

    def _discover_sitemap_links(self, start_url: str) -> List[str]:
        """Attempt lightweight discovery of same-site URLs from /sitemap.xml."""
        parsed = urlparse(start_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
        if not is_safe_url(sitemap_url):
            return []
        try:
            resp = self._safe_get(sitemap_url, start_url)
            if not resp or resp.status_code != 200 or "<loc>" not in resp.text:
                return []
            locs = re.findall(r"<loc>\s*(https?://[^<\s]+)\s*</loc>", resp.text, re.IGNORECASE)
            links: List[str] = []
            for loc in locs:
                if _is_same_site(start_url, loc) and is_safe_url(loc):
                    p = urlparse(loc)
                    if not ASSET_EXT_REGEX.search(p.path or ""):
                        clean = loc.split("#")[0].rstrip("/") or loc.split("#")[0]
                        if clean not in links:
                            links.append(clean)
                if len(links) >= self.max_pages:
                    break
            return links
        except Exception:
            return []

    def _scrape_with_playwright(self, start_url: str, seed_links: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Render JS-heavy SPA pages via headless Chromium with strict SSRF request filtering."""
        if os.getenv("PLAYWRIGHT_SCRAPE_ENABLED", "true").lower() == "false":
            raise SpaScrapeError(
                "This website requires JavaScript rendering (SPA) and headless rendering is disabled."
            )

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise SpaScrapeError(
                "This website loads content via client-side JavaScript (SPA) and Playwright is not installed."
            )

        spa_max_pages = min(self.max_pages, 15)
        visited: Set[str] = set()
        queue: List[str] = [start_url]
        for s in seed_links or []:
            if s not in queue:
                queue.append(s)

        scraped_pages: List[Dict[str, Any]] = []

        with _playwright_lock:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-extensions",
                            "--disable-background-networking",
                        ],
                    )
                    try:
                        context = browser.new_context(user_agent=self.browser_user_agent)

                        def _route_filter(route):
                            req = route.request
                            req_url = req.url
                            parsed_req = urlparse(req_url)
                            if parsed_req.scheme in ("data", "blob"):
                                return route.continue_()
                            if parsed_req.scheme not in ("http", "https") or not is_safe_url(req_url):
                                return route.abort()
                            if req.resource_type in ("image", "media", "font"):
                                return route.abort()
                            return route.continue_()

                        context.route("**/*", _route_filter)
                        page = context.new_page()

                        while queue and len(visited) < spa_max_pages:
                            current_url = queue.pop(0)
                            norm_url = current_url.split("#")[0].rstrip("/") or current_url.split("#")[0]
                            if norm_url in visited:
                                continue
                            if not is_safe_url(current_url) or not _is_same_site(start_url, current_url):
                                continue

                            visited.add(norm_url)
                            try:
                                if self.delay > 0 and len(visited) > 1:
                                    time.sleep(min(self.delay, 0.3))
                                resp = page.goto(current_url, wait_until="domcontentloaded", timeout=15000)
                                if not resp or resp.status >= 400:
                                    continue

                                final_url = page.url
                                if not is_safe_url(final_url) or not _is_same_site(start_url, final_url):
                                    continue

                                try:
                                    page.wait_for_load_state("networkidle", timeout=7000)
                                except Exception:
                                    pass

                                try:
                                    page.wait_for_function(
                                        "() => document.body && document.body.innerText.trim().length > 120",
                                        timeout=4000,
                                    )
                                except Exception:
                                    pass

                                html = page.content()
                                soup = BeautifulSoup(html, "html.parser")
                                title_tag = soup.find("title")
                                title = title_tag.get_text(strip=True) if title_tag else urlparse(final_url).path or "Home"

                                # Discover links before clean_html_content removes nav/header/footer
                                for link in _extract_internal_links(soup, final_url, start_url):
                                    link_norm = link.split("#")[0].rstrip("/") or link.split("#")[0]
                                    if link_norm not in visited and link not in queue:
                                        queue.append(link)

                                body_text = clean_html_content(soup)
                                if len(body_text) > 100:
                                    chunks = chunk_text(body_text, chunk_size=400, overlap=60)
                                    scraped_pages.append(
                                        {
                                            "url": final_url,
                                            "title": title,
                                            "text": body_text,
                                            "chunks": chunks,
                                        }
                                    )
                            except Exception as page_err:
                                logger.debug("Playwright page error for %s: %s", current_url, page_err)
                                continue
                    finally:
                        browser.close()
            except Exception as launch_err:
                logger.warning("Playwright headless launch/execution failed for %s: %s", start_url, launch_err)
                raise SpaScrapeError(
                    "This website uses client-side JavaScript rendering (SPA) and headless browser rendering failed."
                )

        if not scraped_pages:
            raise SpaScrapeError(
                "This website relies on client-side JavaScript rendering and yielded no readable text even after rendering."
            )
        return scraped_pages

    def scrape(self, start_url: str) -> List[Dict[str, Any]]:
        """Scrape the given website up to max_pages, staying strictly within the same site (with SPA fallback)."""
        if not is_safe_url(start_url):
            raise ValueError(f"URL is invalid, untrusted, or resolves to a restricted private network: {start_url}")

        visited: Set[str] = set()
        queue: List[str] = [start_url]
        sitemap_links = self._discover_sitemap_links(start_url)
        for s in sitemap_links:
            if s not in queue:
                queue.append(s)

        scraped_pages: List[Dict[str, Any]] = []
        saw_spa_shell = False

        while queue and len(visited) < self.max_pages:
            current_url = queue.pop(0)
            norm_url = current_url.split("#")[0].rstrip("/") or current_url.split("#")[0]
            if norm_url in visited:
                continue

            if not is_safe_url(current_url) or not _is_same_site(start_url, current_url):
                continue

            visited.add(norm_url)

            try:
                time.sleep(self.delay)
                resp = self._safe_get(current_url, start_url)
                if not resp or resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                    continue

                effective_url = resp.url or current_url
                soup = BeautifulSoup(resp.text, "html.parser")
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else urlparse(effective_url).path or "Home"

                # Extract internal links BEFORE clean_html_content removes nav/header/footer
                for link in _extract_internal_links(soup, effective_url, start_url):
                    link_norm = link.split("#")[0].rstrip("/") or link.split("#")[0]
                    if link_norm not in visited and link not in queue:
                        queue.append(link)

                body_text = clean_html_content(soup)
                if len(body_text) > 100:
                    chunks = chunk_text(body_text, chunk_size=400, overlap=60)
                    scraped_pages.append(
                        {
                            "url": effective_url,
                            "title": title,
                            "text": body_text,
                            "chunks": chunks,
                        }
                    )
                elif _looks_like_spa_shell(resp.text, len(body_text)):
                    saw_spa_shell = True

            except Exception:
                continue

        if not scraped_pages and saw_spa_shell:
            logger.info("Static scrape saw JS SPA shell for %s; falling back to headless Chromium.", start_url)
            return self._scrape_with_playwright(start_url, seed_links=sitemap_links)

        return scraped_pages
