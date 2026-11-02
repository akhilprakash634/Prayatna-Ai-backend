import ipaddress
import re
import socket
import time
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup

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

def is_safe_url(url: str) -> bool:
    """Validate that the URL uses HTTP/HTTPS and resolves only to public, non-private IP addresses."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        
        hostname = parsed.hostname
        if not hostname:
            return False
        
        # Block localhost strings explicitly
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            return False

        # Resolve IP addresses for the hostname
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            for network in BLOCKED_IP_NETWORKS:
                if ip_obj in network:
                    return False
        return True
    except Exception:
        return False

def clean_html_content(soup: BeautifulSoup) -> str:
    """Extract readable text and eliminate nav, scripts, styles, forms, and footers."""
    # Remove unwanted tags
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "iframe"]):
        tag.decompose()
        
    text = soup.get_text(separator=" ", strip=True)
    # Collapse consecutive whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> List[str]:
    """Split text into manageable overlapping chunks based on words."""
    words = text.split()
    if not words:
        return []
    
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
        i += (chunk_size - overlap)
    return chunks

class WebsiteScraper:
    def __init__(self, max_pages: int = 50, timeout: int = 10, delay: float = 0.5):
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay
        self.headers = {
            "User-Agent": "PrayatnaAIBot/1.0 (+https://prayatna.co.in/)",
            "Accept": "text/html,application/xhtml+xml"
        }

    def scrape(self, start_url: str) -> List[Dict[str, any]]:
        """Scrape the given website up to max_pages, staying strictly within the same domain."""
        if not is_safe_url(start_url):
            raise ValueError(f"URL is invalid, untrusted, or resolves to a restricted private network: {start_url}")

        parsed_start = urlparse(start_url)
        target_domain = parsed_start.netloc.lower()

        visited: Set[str] = set()
        queue: List[str] = [start_url]
        scraped_pages: List[Dict[str, any]] = []

        while queue and len(visited) < self.max_pages:
            current_url = queue.pop(0)
            
            # Normalize URL (strip fragment and trailing slash)
            norm_url = current_url.split("#")[0].rstrip("/")
            if norm_url in visited:
                continue
            
            if not is_safe_url(current_url):
                continue

            parsed_current = urlparse(current_url)
            # Restrict crawler strictly to the same domain
            if parsed_current.netloc.lower() != target_domain:
                continue

            visited.add(norm_url)

            try:
                time.sleep(self.delay)
                resp = requests.get(current_url, headers=self.headers, timeout=self.timeout)
                if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Extract page title
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else parsed_current.path or "Home"
                
                # Extract clean text
                body_text = clean_html_content(soup)
                if len(body_text) > 100:
                    chunks = chunk_text(body_text, chunk_size=400, overlap=60)
                    scraped_pages.append({
                        "url": current_url,
                        "title": title,
                        "text": body_text,
                        "chunks": chunks
                    })

                # Discover internal links
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    joined_url = urljoin(current_url, href)
                    parsed_joined = urlparse(joined_url)
                    
                    # Only queue HTTP/HTTPS on the same domain, skipping file downloads or mailto
                    if (parsed_joined.scheme in ("http", "https") and 
                        parsed_joined.netloc.lower() == target_domain):
                        clean_link = joined_url.split("#")[0].rstrip("/")
                        if clean_link not in visited and clean_link not in queue:
                            # Skip common binary/asset links
                            if not re.search(r"\.(pdf|jpg|jpeg|png|gif|zip|docx|svg|css|js)$", parsed_joined.path.lower()):
                                queue.append(clean_link)

            except Exception as e:
                # Log or ignore individual page failure
                continue

        return scraped_pages
