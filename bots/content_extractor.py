"""
Bot 3: Content Extractor
Extracts trending AI/tech content ideas from the web.
"""
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from database.db import get_conn

logger = logging.getLogger(__name__)

BOT_NAME = "content_extractor"

AI_KEYWORDS = {
    "ai", "gpt", "llm", "tool", "automation", "claude", "openai",
    "chatgpt", "agent", "artificial intelligence", "machine learning",
    "copilot", "gemini", "mistral", "model", "neural", "workflow",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_hacker_news_ai() -> list:
    """
    Scrapes HN front page and returns AI/tool related items.
    Returns list of {title, url, score}.
    """
    results = []
    try:
        resp = requests.get("https://news.ycombinator.com/", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"HN returned {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("tr.athing")

        for item in items[:30]:
            title_cell = item.select_one("span.titleline a")
            if not title_cell:
                continue

            title = title_cell.get_text(strip=True)
            url = title_cell.get("href", "")

            # Skip HN-internal links
            if url.startswith("item?"):
                url = f"https://news.ycombinator.com/{url}"

            # Filter by AI keywords
            title_lower = title.lower()
            if not any(kw in title_lower for kw in AI_KEYWORDS):
                continue

            # Score is in the next sibling row
            score = 0
            subtext_row = item.find_next_sibling("tr")
            if subtext_row:
                score_span = subtext_row.select_one("span.score")
                if score_span:
                    try:
                        score = int(score_span.get_text().replace(" points", "").strip())
                    except ValueError:
                        score = 0

            results.append({"title": title, "url": url, "score": score})

        logger.info(f"HN: found {len(results)} AI-related items")
    except Exception as e:
        logger.error(f"fetch_hacker_news_ai error: {e}")

    return results


def fetch_product_hunt_ai() -> list:
    """
    Scrapes Product Hunt AI topics page.
    Returns list of {name, tagline, url}.
    """
    results = []
    try:
        url = "https://www.producthunt.com/topics/artificial-intelligence"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Product Hunt returned {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, "html.parser")

        # Product Hunt items are in data-test="post-item" sections or h3 elements
        items = soup.select("h3")
        seen = set()

        for item in items[:20]:
            name = item.get_text(strip=True)
            if not name or name in seen:
                continue
            seen.add(name)

            # Try to find tagline from parent context
            parent = item.parent
            tagline = ""
            if parent:
                p_tags = parent.select("p")
                for p in p_tags:
                    text = p.get_text(strip=True)
                    if text and text != name:
                        tagline = text[:200]
                        break

            # Build URL from name slug
            slug = name.lower().replace(" ", "-").replace("/", "")
            product_url = f"https://www.producthunt.com/products/{slug}"

            results.append({"name": name, "tagline": tagline, "url": product_url})

        logger.info(f"Product Hunt: found {len(results)} AI products")
    except Exception as e:
        logger.error(f"fetch_product_hunt_ai error: {e}")

    return results


def extract_content_ideas(sources: list) -> list:
    """
    Uses Claude to analyze source items and generate article ideas.
    Returns list of {topic, keywords, tool_focus, priority}.
    """
    if not sources:
        return []

    # Build a summary of sources for Claude
    source_text = ""
    for i, item in enumerate(sources[:20], 1):
        if "title" in item:
            source_text += f"{i}. {item.get('title', '')} — {item.get('url', '')}\n"
        elif "name" in item:
            source_text += f"{i}. {item.get('name', '')} — {item.get('tagline', '')}\n"

    prompt = f"""Based on these trending AI/tech items from Hacker News and Product Hunt:

{source_text}

Generate exactly 5 article ideas for AI Tools Empire (aitoolsempire.co), a site reviewing AI tools.
Each idea should be practical, SEO-friendly, and drive affiliate conversions.

Respond in this exact format (one idea per block):
TOPIC: [topic title]
KEYWORDS: [comma-separated keywords]
TOOL_FOCUS: [primary AI tool to feature, or "general"]
PRIORITY: [1-10, 10=highest]
---

Write all 5 ideas in this format."""

    response = ask_claude(prompt, max_tokens=1500)

    ideas = []
    if not response:
        return ideas

    blocks = response.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        idea = {"topic": "", "keywords": "", "tool_focus": "general", "priority": 5}
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("TOPIC:"):
                idea["topic"] = line[6:].strip()
            elif line.startswith("KEYWORDS:"):
                idea["keywords"] = line[9:].strip()
            elif line.startswith("TOOL_FOCUS:"):
                idea["tool_focus"] = line[11:].strip()
            elif line.startswith("PRIORITY:"):
                try:
                    idea["priority"] = int(line[9:].strip())
                except ValueError:
                    idea["priority"] = 5

        if idea["topic"]:
            ideas.append(idea)

    logger.info(f"extract_content_ideas: generated {len(ideas)} ideas")
    return ideas[:5]


def run_content_extractor() -> int:
    """
    Fetches from all sources, generates ideas, adds to content_queue.
    Returns count of ideas added.
    """
    logger.info("Content Extractor: starting run")
    added = 0

    try:
        hn_items = fetch_hacker_news_ai()
        ph_items = fetch_product_hunt_ai()

        all_sources = hn_items + ph_items

        if not all_sources:
            logger.warning("Content Extractor: no sources fetched")
            log_bot_event(BOT_NAME, "warning", "No sources fetched this run")
            upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
            return 0

        ideas = extract_content_ideas(all_sources)

        if not ideas:
            logger.warning("Content Extractor: no ideas generated")
            log_bot_event(BOT_NAME, "warning", "No ideas generated from sources")
            upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
            return 0

        conn = get_conn()
        for idea in ideas:
            try:
                conn.execute("""
                    INSERT INTO content_queue (topic, keywords, tool_focus, priority)
                    VALUES (?, ?, ?, ?)
                """, (
                    idea["topic"],
                    idea["keywords"],
                    idea.get("tool_focus", "general"),
                    idea.get("priority", 5),
                ))
                added += 1
            except Exception as e:
                logger.warning(f"Failed to insert idea '{idea.get('topic', '')}': {e}")

        conn.commit()
        conn.close()

        log_bot_event(
            BOT_NAME,
            "ideas_added",
            f"Added {added} ideas from {len(hn_items)} HN + {len(ph_items)} PH items"
        )
        logger.info(f"Content Extractor: added {added} ideas to queue")

    except Exception as e:
        logger.error(f"Content Extractor error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return added
