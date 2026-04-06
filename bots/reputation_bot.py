"""
Bot 13: Reputation / Brand Monitoring Bot
Monitors brand mentions and analyzes sentiment.
"""
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from bots.shared.notifier import notify

logger = logging.getLogger(__name__)

BOT_NAME = "reputation_bot"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def search_brand_mentions(query: str = "aitoolsempire") -> list:
    """
    Searches for brand mentions via DuckDuckGo Lite.
    Returns list of {title, url, snippet}.
    """
    mentions = []

    try:
        url = f"https://lite.duckduckgo.com/lite/?q={query}"
        resp = requests.get(url, headers=HEADERS, timeout=15)

        if resp.status_code != 200:
            logger.warning(f"DuckDuckGo returned {resp.status_code}")
            return mentions

        soup = BeautifulSoup(resp.text, "html.parser")

        # DDG Lite result structure: results are in table rows
        # Links are in <a class="result-link"> and snippets in <td class="result-snippet">
        result_links = soup.select("a.result-link")
        result_snippets = soup.select("td.result-snippet")

        for i, link in enumerate(result_links[:10]):
            title = link.get_text(strip=True)
            href = link.get("href", "")

            snippet = ""
            if i < len(result_snippets):
                snippet = result_snippets[i].get_text(strip=True)

            if title and href:
                mentions.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet[:300],
                })

        # Also try the span-based layout DDG sometimes uses
        if not mentions:
            spans = soup.select("span.result__title")
            for span in spans[:10]:
                title = span.get_text(strip=True)
                parent_link = span.find_parent("a")
                href = parent_link.get("href", "") if parent_link else ""
                mentions.append({
                    "title": title,
                    "url": href,
                    "snippet": "",
                })

        logger.info(f"Reputation Bot: found {len(mentions)} mentions for '{query}'")

    except Exception as e:
        logger.error(f"search_brand_mentions error: {e}")

    return mentions


def analyze_sentiment(mentions: list) -> dict:
    """
    Uses Claude to analyze sentiment of brand mentions.
    Returns {positive: n, neutral: n, negative: n, summary: str}.
    """
    if not mentions:
        return {"positive": 0, "neutral": 0, "negative": 0, "summary": "No mentions found to analyze."}

    mentions_text = "\n".join([
        f"- Title: {m.get('title', '')}\n  Snippet: {m.get('snippet', 'No snippet')}\n  URL: {m.get('url', '')}"
        for m in mentions[:10]
    ])

    prompt = f"""Analyze the sentiment of these brand mentions for AI Tools Empire (aitoolsempire.co):

{mentions_text}

Classify each mention as positive, neutral, or negative.
Then provide:

POSITIVE: [count]
NEUTRAL: [count]
NEGATIVE: [count]
SUMMARY: [2-3 sentence summary of overall brand perception and any notable issues]"""

    response = ask_claude(prompt, max_tokens=600)

    result = {"positive": 0, "neutral": 0, "negative": 0, "summary": "Analysis unavailable."}

    if not response:
        return result

    for line in response.split("\n"):
        stripped = line.strip()
        if stripped.startswith("POSITIVE:"):
            try:
                result["positive"] = int(stripped[9:].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif stripped.startswith("NEUTRAL:"):
            try:
                result["neutral"] = int(stripped[8:].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif stripped.startswith("NEGATIVE:"):
            try:
                result["negative"] = int(stripped[9:].strip().split()[0])
            except (ValueError, IndexError):
                pass
        elif stripped.startswith("SUMMARY:"):
            result["summary"] = stripped[8:].strip()

    return result


def run_reputation_bot() -> dict:
    """
    Searches brand mentions, analyzes sentiment.
    Sends alert if negative sentiment > 20%.
    Returns summary.
    """
    logger.info("Reputation Bot: starting run")

    result = {
        "mentions_found": 0,
        "positive": 0,
        "neutral": 0,
        "negative": 0,
        "alert_sent": False,
    }

    try:
        # Search multiple variants
        all_mentions = []

        for query in ["aitoolsempire", "ai tools empire", "aitoolsempire.co"]:
            mentions = search_brand_mentions(query)
            all_mentions.extend(mentions)

        # Deduplicate by URL
        seen_urls = set()
        unique_mentions = []
        for m in all_mentions:
            url = m.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_mentions.append(m)

        result["mentions_found"] = len(unique_mentions)

        if unique_mentions:
            sentiment = analyze_sentiment(unique_mentions)
            result["positive"] = sentiment["positive"]
            result["neutral"] = sentiment["neutral"]
            result["negative"] = sentiment["negative"]

            total = result["positive"] + result["neutral"] + result["negative"]
            negative_pct = (result["negative"] / total * 100) if total > 0 else 0

            # Alert if negative sentiment > 20%
            if negative_pct > 20:
                alert_msg = (
                    f"Brand monitoring alert: {negative_pct:.0f}% negative sentiment "
                    f"detected across {result['mentions_found']} mentions.\n\n"
                    f"Summary: {sentiment['summary']}"
                )
                notify(alert_msg, level="warning", use_telegram=True, use_email=True)
                result["alert_sent"] = True
                logger.warning(f"Reputation Bot: negative sentiment alert sent ({negative_pct:.0f}%)")

            upsert_bot_state(BOT_NAME, "latest_sentiment_summary", sentiment["summary"][:400])

            log_bot_event(
                BOT_NAME,
                "monitoring_complete",
                f"Mentions: {len(unique_mentions)}, Positive: {result['positive']}, "
                f"Neutral: {result['neutral']}, Negative: {result['negative']}. "
                f"Summary: {sentiment['summary'][:200]}"
            )
        else:
            log_bot_event(BOT_NAME, "monitoring_complete", "No brand mentions found")
            logger.info("Reputation Bot: no brand mentions found")

    except Exception as e:
        logger.error(f"Reputation Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
