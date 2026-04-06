"""
AI-powered content idea extraction using Anthropic Claude.
Generates tweet and YouTube content ideas from site articles.
"""
import sys
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.db import is_duplicate, get_dom_conn
from automation.dominic.logger import log_action, log_error

CONTENT_TYPES = [
    "tool_spotlight",
    "tutorial",
    "listicle",
    "trend",
    "promotional",
    "educational",
    "repurpose",
    "video_topic",
]

EVERGREEN_TOPICS = [
    "best AI writing tools for bloggers",
    "how to use ChatGPT to write faster",
    "AI tools that save 10 hours a week",
    "free AI tools every creator should know",
    "AI vs human writing — what's the difference?",
    "top AI tools for social media marketing",
    "how to make money with AI tools",
    "AI tools for small business owners",
    "best AI image generators compared",
    "AI tools for YouTube creators",
    "how to automate your content workflow with AI",
    "AI tools for SEO in 2025",
    "best AI tools for email marketing",
    "how to use AI for video creation",
    "AI tools for freelancers — complete guide",
]


def _get_client():
    """Return Anthropic client or None if unavailable."""
    try:
        import anthropic
        cfg = get_config()
        return anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    except ImportError:
        log_error("idea_engine", "anthropic package not installed", "")
        return None
    except Exception as e:
        log_error("idea_engine", str(e), "_get_client")
        return None


def _call_claude(prompt: str, max_tokens: int = 1200) -> str:
    """Call Claude and return response text."""
    client = _get_client()
    if not client:
        return ""
    try:
        cfg = get_config()
        response = client.messages.create(
            model=cfg.claude_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else ""
    except Exception as e:
        log_error("idea_engine", str(e), "_call_claude")
        return ""


def _parse_json_from_response(text: str) -> any:
    """Extract JSON from Claude response."""
    # Try to find a JSON array or object
    text = text.strip()
    for pattern in [r"\[.*\]", r"\{.*\}"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    # Last resort: try entire text
    try:
        return json.loads(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def classify_content_type(title: str, content: str) -> str:
    """
    Classify article into one of 8 content types.
    Returns a string from CONTENT_TYPES.
    """
    text = (title + " " + content[:500]).lower()

    if any(w in text for w in ["vs", "versus", "comparison", "compare", "vs."]):
        return "tool_spotlight"
    if any(w in text for w in ["how to", "tutorial", "guide", "step", "walkthrough"]):
        return "tutorial"
    if any(w in text for w in ["best", "top", "list", "picks", "tools you need"]):
        return "listicle"
    if any(w in text for w in ["trend", "2025", "2026", "future", "upcoming", "new"]):
        return "trend"
    if any(w in text for w in ["deal", "discount", "promo", "affiliate", "save money"]):
        return "promotional"
    if any(w in text for w in ["what is", "explained", "beginner", "basics", "101"]):
        return "educational"
    if any(w in text for w in ["video", "youtube", "watch", "script", "shorts"]):
        return "video_topic"

    return "repurpose"


def score_confidence(idea_dict: Dict) -> float:
    """
    Score confidence for an idea dict.
    Returns 0.0 - 1.0.
    """
    score = 0.5  # base

    headline = idea_dict.get("headline") or ""
    body = idea_dict.get("body") or ""
    content_type = idea_dict.get("content_type") or ""
    platform = idea_dict.get("platform") or ""

    # Length quality
    if len(headline) > 20:
        score += 0.05
    if len(body) > 60:
        score += 0.05

    # High-value content types
    if content_type in ("tool_spotlight", "listicle", "tutorial"):
        score += 0.10
    elif content_type in ("trend", "educational"):
        score += 0.05

    # Both platforms = higher value
    if platform == "both":
        score += 0.05

    # Engagement keywords
    engagement_words = [
        "save time", "earn money", "free", "best", "top", "how to",
        "vs", "results", "tested", "review", "secret", "hack"
    ]
    text = (headline + " " + body).lower()
    matches = sum(1 for w in engagement_words if w in text)
    score += min(matches * 0.02, 0.10)

    # Duplicate penalty
    if is_duplicate(headline):
        score -= 0.30

    return round(max(0.0, min(1.0, score)), 3)


def extract_ideas_from_article(article_dict: Dict) -> List[Dict]:
    """
    Use Claude to generate content ideas from an article.
    Returns list of idea dicts: {headline, body, content_type, platform, confidence}
    """
    title = article_dict.get("title") or ""
    content = (article_dict.get("content") or "")[:2000]
    url = article_dict.get("url") or ""
    category = article_dict.get("category") or ""

    prompt = f"""You are a social media content strategist for AI Tools Empire (aitoolsempire.co).
We help content creators, marketers, and small business owners discover and use AI tools.

Article title: {title}
Category: {category}
URL: {url}
Content snippet:
{content}

Generate 4 specific content ideas for Twitter and/or YouTube based on this article.
For each idea, output a JSON object with these fields:
- headline: short, punchy title or tweet hook (max 100 chars)
- body: the actual content (tweet text under 270 chars, or YouTube concept in 2-3 sentences)
- content_type: one of [tool_spotlight, tutorial, listicle, trend, promotional, educational, repurpose, video_topic]
- platform: one of [twitter, youtube, both]
- angle: brief note on the specific angle/hook being used

Return a valid JSON array of 4 objects. No explanation. Only the JSON array.
Make ideas specific, engaging, and useful for an AI tools audience.
Avoid generic or vague ideas."""

    raw = _call_claude(prompt, max_tokens=1500)
    parsed = _parse_json_from_response(raw)

    if not isinstance(parsed, list):
        log_error("idea_engine", "Failed to parse ideas from article", title)
        return []

    ideas = []
    for item in parsed[:6]:
        if not isinstance(item, dict):
            continue
        headline = item.get("headline") or ""
        body = item.get("body") or ""
        if not headline or not body:
            continue

        content_type = item.get("content_type") or classify_content_type(headline, body)
        if content_type not in CONTENT_TYPES:
            content_type = "repurpose"

        platform = item.get("platform") or "twitter"
        if platform not in ("twitter", "youtube", "both"):
            platform = "twitter"

        idea = {
            "headline": headline[:280],
            "body": body[:1000],
            "content_type": content_type,
            "platform": platform,
            "url": url,
            "source_title": title,
        }
        idea["confidence"] = score_confidence(idea)
        ideas.append(idea)

    log_action("extract_ideas", "idea_engine", "ok", f"article={title[:50]}, ideas={len(ideas)}")
    return ideas


def batch_extract_ideas(articles: List[Dict], max_ideas: int = 5) -> List[Dict]:
    """
    Process multiple articles and return a combined list of ideas.
    Limits to max_ideas per article.
    """
    all_ideas = []
    for article in articles:
        try:
            ideas = extract_ideas_from_article(article)
            all_ideas.extend(ideas[:max_ideas])
        except Exception as e:
            log_error("idea_engine", str(e), f"batch article={article.get('title','?')}")
    log_action("batch_extract_ideas", "idea_engine", "ok", f"total_ideas={len(all_ideas)}")
    return all_ideas


def generate_evergreen_ideas(n: int = 10) -> List[Dict]:
    """
    Generate ideas from AI tools topics without scraping.
    Uses Claude to brainstorm high-engagement content.
    """
    import random
    topics = random.sample(EVERGREEN_TOPICS, min(n, len(EVERGREEN_TOPICS)))
    topics_list = "\n".join(f"- {t}" for t in topics)

    prompt = f"""You are a social media content strategist for AI Tools Empire (aitoolsempire.co).
Target audience: content creators, marketers, small business owners, freelancers.

Generate {n} evergreen content ideas for Twitter and YouTube around these AI tools topics:
{topics_list}

For each idea return a JSON object:
- headline: punchy hook (max 100 chars)
- body: actual content text (tweet under 270 chars OR YouTube concept 2-3 sentences)
- content_type: one of [tool_spotlight, tutorial, listicle, trend, promotional, educational, repurpose, video_topic]
- platform: one of [twitter, youtube, both]

Return a valid JSON array of {n} objects. No explanation, only the JSON array.
Make every idea specific, useful, and engaging. Prioritize hooks that get clicks."""

    raw = _call_claude(prompt, max_tokens=2500)
    parsed = _parse_json_from_response(raw)

    if not isinstance(parsed, list):
        log_error("idea_engine", "Failed to parse evergreen ideas", "")
        return []

    ideas = []
    for item in parsed[:n]:
        if not isinstance(item, dict):
            continue
        headline = item.get("headline") or ""
        body = item.get("body") or ""
        if not headline or not body:
            continue
        content_type = item.get("content_type") or "educational"
        if content_type not in CONTENT_TYPES:
            content_type = "educational"
        platform = item.get("platform") or "twitter"
        if platform not in ("twitter", "youtube", "both"):
            platform = "twitter"
        idea = {
            "headline": headline[:280],
            "body": body[:1000],
            "content_type": content_type,
            "platform": platform,
            "url": "",
            "source_title": "evergreen",
        }
        idea["confidence"] = score_confidence(idea)
        ideas.append(idea)

    log_action("evergreen_ideas", "idea_engine", "ok", f"count={len(ideas)}")
    return ideas


def deduplicate_ideas(ideas: List[Dict]) -> List[Dict]:
    """
    Remove ideas that are too similar to each other or existing dom_content.
    Uses headline similarity check via is_duplicate.
    """
    seen_headlines = []
    result = []
    import difflib

    for idea in ideas:
        hl = (idea.get("headline") or "").lower().strip()
        if not hl:
            continue
        # Check against existing DB
        if is_duplicate(hl, threshold=0.80):
            continue
        # Check against batch
        dup_in_batch = False
        for seen in seen_headlines:
            ratio = difflib.SequenceMatcher(None, hl, seen).ratio()
            if ratio >= 0.80:
                dup_in_batch = True
                break
        if dup_in_batch:
            continue
        seen_headlines.append(hl)
        result.append(idea)

    log_action("deduplicate", "idea_engine", "ok",
               f"before={len(ideas)}, after={len(result)}")
    return result
