"""
Website content monitor for Dominic.
Crawls https://aitoolsempire.co for new articles.
"""
import sys
import os
import time
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urljoin, urlparse

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

import requests
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from automation.dominic.config import get_config
from automation.dominic.db import get_crawled_urls, log_crawl
from automation.dominic.logger import log_action, log_error

HEADERS = {
    "User-Agent": "DominicBot/1.0 (AIToolsEmpire; +https://aitoolsempire.co)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_DELAY = 0.5  # seconds between requests


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

def fetch_page(url: str) -> Optional[Dict]:
    """
    Fetch and parse a single page.
    Returns dict with {url, html, soup} or None on error.
    """
    if BeautifulSoup is None:
        log_error("crawler", "beautifulsoup4 not installed", url)
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log_error("crawler", f"HTTP {resp.status_code}", url)
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        return {"url": url, "html": resp.text, "soup": soup}
    except Exception as e:
        log_error("crawler", str(e), url)
        return None


def extract_article_data(soup, url: str) -> Dict:
    """
    Extract article data from a BeautifulSoup object.
    Returns dict with {url, title, content, category, meta_desc}.
    """
    title = ""
    # Try og:title, then h1, then <title>
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)

    # Meta description
    meta_desc = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        meta_desc = og_desc["content"].strip()
    if not meta_desc:
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag and desc_tag.get("content"):
            meta_desc = desc_tag["content"].strip()

    # Category — from breadcrumbs, URL path, or meta
    category = _extract_category(soup, url)

    # Main content text
    content = _extract_main_content(soup)

    return {
        "url": url,
        "title": title,
        "content": content,
        "category": category,
        "meta_desc": meta_desc,
    }


def _extract_category(soup, url: str) -> str:
    """Best-effort category extraction."""
    # From URL path
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2:
        return parts[0].replace("-", " ").title()

    # From breadcrumb
    breadcrumb = soup.find(class_=re.compile(r"breadcrumb", re.I))
    if breadcrumb:
        items = breadcrumb.find_all("a")
        if items:
            return items[-1].get_text(strip=True)

    # From article:section meta
    section = soup.find("meta", property="article:section")
    if section and section.get("content"):
        return section["content"].strip()

    return "General"


def _extract_main_content(soup) -> str:
    """Extract main readable content, stripping nav/footer/ads."""
    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", ".sidebar", ".menu", ".ad"]):
        tag.decompose()

    # Try article tag, main, or .content
    for selector in ["article", "main", ".entry-content", ".post-content",
                     ".article-body", "#content", ".content"]:
        el = soup.select_one(selector)
        if el:
            return el.get_text(separator=" ", strip=True)[:5000]

    # Fallback: body
    body = soup.find("body")
    if body:
        return body.get_text(separator=" ", strip=True)[:5000]

    return ""


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------

def get_sitemap_urls() -> List[str]:
    """Parse sitemap.xml for page URLs."""
    cfg = get_config()
    sitemap_url = f"{cfg.site_url}/sitemap.xml"
    urls = []

    try:
        resp = requests.get(sitemap_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "xml") if BeautifulSoup else None
        if not soup:
            return []
        locs = soup.find_all("loc")
        for loc in locs:
            u = loc.get_text(strip=True)
            if u and _is_content_url(u, cfg.site_url):
                urls.append(u)
        log_action("sitemap_crawl", "crawler", "ok", f"found {len(urls)} URLs")
    except Exception as e:
        log_error("crawler", str(e), "get_sitemap_urls")

    return urls


def get_blog_urls() -> List[str]:
    """Scrape blog/articles listing pages for content URLs."""
    cfg = get_config()
    seed_paths = [
        "/articles", "/blog", "/reviews", "/tools",
        "/comparisons", "/tutorials",
    ]
    urls = []

    for path in seed_paths:
        page_url = f"{cfg.site_url}{path}"
        result = fetch_page(page_url)
        if not result:
            time.sleep(REQUEST_DELAY)
            continue
        soup = result["soup"]
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = a["href"]
            full = urljoin(cfg.site_url, href)
            if _is_content_url(full, cfg.site_url) and full not in urls:
                urls.append(full)
        time.sleep(REQUEST_DELAY)

    log_action("blog_url_scrape", "crawler", "ok", f"found {len(urls)} URLs")
    return urls


def _is_content_url(url: str, site_url: str) -> bool:
    """Return True if URL looks like a content page on our site."""
    if not url.startswith(site_url):
        return False
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    # Exclude admin, static, API paths
    exclude = ["/admin", "/static", "/api", "/wp-", "/feed", "?", "#", ".xml", ".json",
               "/login", "/signup", "/checkout", "/cart"]
    for ex in exclude:
        if ex in url:
            return False
    # Must have some path depth
    parts = [p for p in path.split("/") if p]
    return len(parts) >= 1


def filter_new_urls(urls: List[str]) -> List[str]:
    """Return only URLs not previously crawled."""
    crawled = get_crawled_urls()
    return [u for u in urls if u not in crawled]


# ---------------------------------------------------------------------------
# Main crawl
# ---------------------------------------------------------------------------

def crawl_site(max_pages: int = 50) -> List[Dict]:
    """
    Full site crawl.
    Returns list of page dicts: {url, title, content, category, meta_desc}
    """
    if BeautifulSoup is None:
        log_error("crawler", "beautifulsoup4 not installed — cannot crawl", "")
        return []

    cfg = get_config()
    log_action("crawl_start", "crawler", "running", cfg.site_url)

    # Discover URLs
    all_urls = []
    sitemap_urls = get_sitemap_urls()
    if sitemap_urls:
        all_urls.extend(sitemap_urls)
    else:
        blog_urls = get_blog_urls()
        all_urls.extend(blog_urls)

    # Deduplicate
    all_urls = list(dict.fromkeys(all_urls))[:max_pages]

    articles = []
    for url in all_urls:
        result = fetch_page(url)
        if not result:
            time.sleep(REQUEST_DELAY)
            continue
        article = extract_article_data(result["soup"], url)
        if article["title"] and len(article["content"]) > 100:
            articles.append(article)
        time.sleep(REQUEST_DELAY)

    log_action("crawl_complete", "crawler", "ok", f"fetched {len(articles)} articles")
    return articles


def run_crawl() -> List[Dict]:
    """
    Main entry point.
    Crawls site, filters to new URLs, logs results, returns new articles.
    """
    cfg = get_config()

    all_articles = crawl_site(max_pages=50)

    # Filter to new URLs
    all_urls = [a["url"] for a in all_articles]
    new_urls_set = set(filter_new_urls(all_urls))
    new_articles = [a for a in all_articles if a["url"] in new_urls_set]

    # Log crawl
    log_crawl(
        url=cfg.site_url,
        articles_found=len(all_articles),
        new_ideas=len(new_articles),
        status="ok",
    )

    log_action(
        "run_crawl",
        "crawler",
        "complete",
        f"total={len(all_articles)}, new={len(new_articles)}"
    )

    return new_articles
