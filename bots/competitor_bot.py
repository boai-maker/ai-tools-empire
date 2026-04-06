"""
Bot 11: Competitor / Trend Research Bot
Researches competitors and trending topics in the AI tools niche.
"""
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import (
    log_bot_event,
    upsert_bot_state,
    get_recent_articles,
)

logger = logging.getLogger(__name__)

BOT_NAME = "competitor_bot"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

AI_KEYWORDS = {
    "ai", "gpt", "llm", "tool", "automation", "claude", "openai",
    "chatgpt", "agent", "copilot", "gemini", "mistral", "artificial intelligence",
    "machine learning", "workflow", "productivity", "saas",
}


def search_trending_ai_topics() -> list:
    """
    Searches for trending AI topics using Google Trends RSS and HN as fallback.
    Returns list of {topic, source, relevance_score}.
    """
    results = []

    # Try Google Trends RSS for technology category
    try:
        trends_url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        resp = requests.get(trends_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "xml")
            items = soup.find_all("item")

            for item in items[:30]:
                title = item.find("title")
                if not title:
                    continue

                topic_text = title.get_text(strip=True).lower()
                if any(kw in topic_text for kw in AI_KEYWORDS):
                    traffic = item.find("ht:approx_traffic")
                    score = 5
                    if traffic:
                        traffic_text = traffic.get_text().replace("+", "").replace(",", "").strip()
                        try:
                            n = int(traffic_text)
                            score = min(10, max(1, int(n / 10000)))
                        except ValueError:
                            score = 5

                    results.append({
                        "topic": title.get_text(strip=True),
                        "source": "google_trends",
                        "relevance_score": score,
                    })

    except Exception as e:
        logger.warning(f"Google Trends fetch failed: {e}")

    # HN fallback — always run to supplement
    try:
        resp = requests.get("https://news.ycombinator.com/", headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("tr.athing")

            for item in items[:30]:
                title_cell = item.select_one("span.titleline a")
                if not title_cell:
                    continue

                title = title_cell.get_text(strip=True)
                if any(kw in title.lower() for kw in AI_KEYWORDS):
                    # Score from points
                    score = 5
                    subtext = item.find_next_sibling("tr")
                    if subtext:
                        score_el = subtext.select_one("span.score")
                        if score_el:
                            try:
                                pts = int(score_el.get_text().replace(" points", ""))
                                score = min(10, max(1, pts // 50))
                            except ValueError:
                                score = 5

                    results.append({
                        "topic": title,
                        "source": "hacker_news",
                        "relevance_score": score,
                    })

    except Exception as e:
        logger.warning(f"HN trending fetch failed: {e}")

    # Deduplicate and sort by relevance
    seen = set()
    unique = []
    for r in sorted(results, key=lambda x: x["relevance_score"], reverse=True):
        key = r["topic"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(r)

    logger.info(f"Competitor Bot: found {len(unique)} trending topics")
    return unique[:20]


def analyze_content_gaps(our_articles: list, trending: list) -> list:
    """
    Uses Claude to identify content gaps between what we cover and what's trending.
    Returns list of gap opportunities.
    """
    if not trending:
        return []

    our_titles = [a.get("title", "") for a in our_articles]
    trending_topics = [t.get("topic", "") for t in trending[:15]]

    prompt = f"""Analyze this content gap for AI Tools Empire (aitoolsempire.co):

OUR EXISTING ARTICLES:
{chr(10).join([f"- {t}" for t in our_titles]) if our_titles else "- (no articles yet)"}

TRENDING AI/TECH TOPICS:
{chr(10).join([f"- {t}" for t in trending_topics])}

Identify 5 specific content gap opportunities — topics trending right now that we haven't covered (or should cover better).
For each gap, explain why it's a good opportunity and what angle to take.

CONTENT GAP: [topic]
WHY IT MATTERS: [1-2 sentence explanation]
ARTICLE ANGLE: [specific article angle for aitoolsempire.co]
---

List 5 gaps in this format."""

    response = ask_claude(prompt, max_tokens=1500)

    gaps = []
    if not response:
        return gaps

    blocks = response.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        gap = {"topic": "", "why_it_matters": "", "article_angle": ""}
        for line in block.split("\n"):
            stripped = line.strip()
            if stripped.startswith("CONTENT GAP:"):
                gap["topic"] = stripped[12:].strip()
            elif stripped.startswith("WHY IT MATTERS:"):
                gap["why_it_matters"] = stripped[15:].strip()
            elif stripped.startswith("ARTICLE ANGLE:"):
                gap["article_angle"] = stripped[14:].strip()

        if gap["topic"]:
            gaps.append(gap)

    return gaps[:5]


def generate_competitor_insights() -> str:
    """
    Uses Claude to generate strategic insights about the AI tools niche.
    """
    prompt = """Generate strategic competitive insights for AI Tools Empire (aitoolsempire.co).

This is an AI tool review and comparison site competing with:
- Tool review sites (G2, Capterra)
- YouTube channels reviewing AI tools
- Individual bloggers in the AI niche
- AI tool directory sites

Provide insights on:
1. Our unique positioning opportunities
2. Content moats we can build
3. SEO opportunities competitors are missing
4. Audience segments underserved in the AI tools niche
5. Monetization opportunities beyond affiliate links

Be specific and actionable. Focus on 2024-2025 opportunities."""

    return ask_claude(prompt, max_tokens=1200)


def run_competitor_bot() -> dict:
    """
    Runs weekly research, logs findings, saves to bot_state.
    Returns summary.
    """
    logger.info("Competitor Bot: starting run")

    result = {
        "trending_topics_found": 0,
        "content_gaps_found": 0,
        "insights_generated": False,
    }

    try:
        trending = search_trending_ai_topics()
        result["trending_topics_found"] = len(trending)

        our_articles = get_recent_articles(n=20)
        gaps = analyze_content_gaps(our_articles, trending)
        result["content_gaps_found"] = len(gaps)

        insights = generate_competitor_insights()
        result["insights_generated"] = bool(insights)

        # Save findings to bot_state for other bots to reference
        if trending:
            trending_summary = "; ".join([t["topic"][:50] for t in trending[:5]])
            upsert_bot_state(BOT_NAME, "latest_trending", trending_summary)

        if gaps:
            gaps_summary = "; ".join([g["topic"][:50] for g in gaps])
            upsert_bot_state(BOT_NAME, "latest_gaps", gaps_summary)

            # Add gaps to content queue
            from database.db import get_conn
            conn = get_conn()
            for gap in gaps:
                try:
                    conn.execute("""
                        INSERT INTO content_queue (topic, keywords, tool_focus, priority)
                        VALUES (?, ?, ?, ?)
                    """, (
                        gap["article_angle"] or gap["topic"],
                        gap["topic"],
                        None,
                        7,  # High priority for gap content
                    ))
                except Exception:
                    pass  # May already exist
            conn.commit()
            conn.close()

        if insights:
            upsert_bot_state(BOT_NAME, "latest_insights", insights[:600])

        log_bot_event(
            BOT_NAME,
            "research_complete",
            f"Trending: {len(trending)}, Gaps: {len(gaps)}, Insights: {result['insights_generated']}"
        )

    except Exception as e:
        logger.error(f"Competitor Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
