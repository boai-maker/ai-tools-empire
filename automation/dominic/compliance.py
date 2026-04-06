"""
Compliance, duplicate detection, and confidence scoring for Dominic.
"""
import sys
import difflib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.logger import log_action, log_error

# ---------------------------------------------------------------------------
# Platform rules
# ---------------------------------------------------------------------------

PLATFORM_RULES = {
    "twitter": {
        "max_chars": 280,
        "min_chars": 20,
        "max_hashtags": 2,
        "max_urls": 2,
        "min_posting_gap_hours": 3,
    },
    "youtube": {
        "max_title_chars": 100,
        "min_title_chars": 20,
        "max_description_chars": 5000,
        "min_posting_gap_hours": 12,
    },
}

# Good posting windows (hour ranges, Eastern Time)
POSTING_WINDOWS = {
    "twitter": [(8, 10), (12, 13), (17, 19), (20, 22)],
    "youtube": [(9, 12), (14, 17)],
}


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def is_duplicate_content(text: str, threshold: float = 0.85) -> bool:
    """
    Fuzzy match `text` against dom_history and dom_content.
    Returns True if a match above threshold is found.
    """
    if not text or len(text) < 10:
        return False

    text_clean = text.lower().strip()

    try:
        from automation.dominic.db import get_dom_conn
        conn = get_dom_conn()

        # Check dom_content
        rows_content = conn.execute(
            "SELECT headline, body FROM dom_content ORDER BY created_at DESC LIMIT 500"
        ).fetchall()

        # Check dom_history
        rows_history = conn.execute(
            "SELECT content_summary, full_content FROM dom_history ORDER BY published_at DESC LIMIT 500"
        ).fetchall()

        conn.close()

        all_texts = []
        for r in rows_content:
            if r[0]:
                all_texts.append(r[0].lower().strip())
            if r[1]:
                all_texts.append(r[1].lower().strip()[:300])
        for r in rows_history:
            if r[0]:
                all_texts.append(r[0].lower().strip())
            if r[1]:
                all_texts.append(r[1].lower().strip()[:300])

        for existing in all_texts:
            ratio = difflib.SequenceMatcher(None, text_clean[:300], existing[:300]).ratio()
            if ratio >= threshold:
                return True

    except Exception as e:
        log_error("compliance", str(e), "is_duplicate_content")

    return False


# ---------------------------------------------------------------------------
# Content scoring
# ---------------------------------------------------------------------------

def score_content(content_dict: Dict) -> float:
    """
    Score content 0.0 - 1.0 based on freshness, uniqueness, relevance, quality, length.
    """
    score = 0.50

    headline = content_dict.get("headline") or ""
    body = content_dict.get("body") or ""
    platform = content_dict.get("platform") or "twitter"
    content_type = content_dict.get("content_type") or ""
    created_at = content_dict.get("created_at") or ""

    # --- Freshness: prefer newer content ---
    if created_at:
        try:
            created = datetime.fromisoformat(created_at.replace("Z", ""))
            age_hours = (datetime.utcnow() - created).total_seconds() / 3600
            if age_hours < 6:
                score += 0.10
            elif age_hours < 24:
                score += 0.05
            elif age_hours > 168:  # > 7 days
                score -= 0.05
        except Exception:
            pass

    # --- Uniqueness ---
    combined = f"{headline} {body[:200]}"
    if is_duplicate_content(combined, threshold=0.80):
        score -= 0.35
    elif is_duplicate_content(combined, threshold=0.90):
        score -= 0.20

    # --- Relevance: AI tools keywords ---
    relevance_words = [
        "ai", "tool", "automation", "chatgpt", "claude", "gpt", "generate",
        "content", "creator", "workflow", "productivity", "review", "comparison",
        "free", "best", "top", "how to", "tutorial"
    ]
    text_lower = (headline + " " + body).lower()
    rel_count = sum(1 for w in relevance_words if w in text_lower)
    score += min(rel_count * 0.02, 0.15)

    # --- Quality: engagement signals ---
    engagement_words = [
        "save time", "earn money", "tested", "honest", "results",
        "step by step", "vs", "alternative", "free", "secret", "hack",
        "actually works", "tried", "compared"
    ]
    eng_count = sum(1 for w in engagement_words if w in text_lower)
    score += min(eng_count * 0.03, 0.12)

    # --- Length (platform-appropriate) ---
    if platform == "twitter":
        body_len = len(body)
        if 80 <= body_len <= 260:
            score += 0.08
        elif body_len > 280:
            score -= 0.20
        elif body_len < 20:
            score -= 0.15
    elif platform == "youtube":
        if len(headline) >= 20:
            score += 0.05

    # --- Content type bonus ---
    high_value = {"tool_spotlight", "listicle", "tutorial"}
    if content_type in high_value:
        score += 0.08

    return round(max(0.0, min(1.0, score)), 3)


def filter_content(content_list: List[Dict], min_score: float = 0.7) -> List[Dict]:
    """Filter content list, keeping only items at or above min_score."""
    result = []
    for item in content_list:
        s = item.get("confidence") or score_content(item)
        if s >= min_score:
            item["confidence"] = s
            result.append(item)
    log_action("filter_content", "compliance", "ok",
               f"before={len(content_list)}, after={len(result)}, threshold={min_score}")
    return result


# ---------------------------------------------------------------------------
# Rate limits
# ---------------------------------------------------------------------------

def check_rate_limits(platform: str) -> Tuple[bool, str]:
    """
    Check if it's safe to post on platform now.
    Returns (ok: bool, reason: str).
    """
    rules = PLATFORM_RULES.get(platform, {})
    min_gap = rules.get("min_posting_gap_hours", 3)

    try:
        from automation.dominic.db import get_dom_conn
        conn = get_dom_conn()
        row = conn.execute(
            """SELECT published_at FROM dom_history
               WHERE platform = ?
               ORDER BY published_at DESC LIMIT 1""",
            (platform,)
        ).fetchone()
        conn.close()

        if row and row[0]:
            last_post = datetime.fromisoformat(row[0].replace("Z", ""))
            elapsed = (datetime.utcnow() - last_post).total_seconds() / 3600
            if elapsed < min_gap:
                wait = round(min_gap - elapsed, 1)
                return False, f"Too soon — last {platform} post {elapsed:.1f}h ago, need {min_gap}h gap. Wait {wait}h."

    except Exception as e:
        log_error("compliance", str(e), "check_rate_limits")

    return True, "ok"


def validate_for_platform(content: Dict, platform: str) -> Tuple[bool, List[str]]:
    """
    Validate content against platform-specific rules.
    Returns (valid: bool, issues: list).
    """
    issues = []
    rules = PLATFORM_RULES.get(platform, {})

    if platform == "twitter":
        body = content.get("body") or ""
        # Length
        if len(body) > rules.get("max_chars", 280):
            issues.append(f"Tweet too long: {len(body)} chars (max 280)")
        if len(body) < rules.get("min_chars", 20):
            issues.append(f"Tweet too short: {len(body)} chars (min 20)")
        # Hashtags
        ht_count = body.count("#")
        if ht_count > rules.get("max_hashtags", 2):
            issues.append(f"Too many hashtags: {ht_count} (max 2)")

    elif platform == "youtube":
        headline = content.get("headline") or ""
        if len(headline) > rules.get("max_title_chars", 100):
            issues.append(f"Title too long: {len(headline)} chars")
        if len(headline) < rules.get("min_title_chars", 20):
            issues.append(f"Title too short: {len(headline)} chars")

    valid = len(issues) == 0
    return valid, issues


def get_posting_window(platform: str) -> bool:
    """
    Return True if current hour (Eastern) is a good time to post.
    """
    try:
        import pytz
        cfg = get_config()
        tz = pytz.timezone(cfg.timezone)
        now_local = datetime.now(tz)
        current_hour = now_local.hour
    except Exception:
        current_hour = datetime.utcnow().hour  # Fallback: UTC

    windows = POSTING_WINDOWS.get(platform, [(8, 22)])
    for start, end in windows:
        if start <= current_hour < end:
            return True
    return False


def audit_content(content_dict: Dict) -> Dict:
    """
    Full content audit: duplicate check + score + platform validation.
    Returns audit report dict.
    """
    platform = content_dict.get("platform") or "twitter"
    headline = content_dict.get("headline") or ""
    body = content_dict.get("body") or ""
    combined = f"{headline} {body[:200]}"

    # Duplicate check
    is_dup = is_duplicate_content(combined)

    # Score
    content_score = score_content(content_dict)

    # Platform validation
    valid_platform, platform_issues = validate_for_platform(content_dict, platform)

    # Rate limit check
    rate_ok, rate_reason = check_rate_limits(platform)

    # Posting window
    in_window = get_posting_window(platform)

    # Overall pass/fail
    cfg = get_config()
    passes = (
        not is_dup
        and content_score >= cfg.confidence_threshold
        and valid_platform
        and rate_ok
    )

    report = {
        "passes": passes,
        "is_duplicate": is_dup,
        "score": content_score,
        "platform_valid": valid_platform,
        "platform_issues": platform_issues,
        "rate_limit_ok": rate_ok,
        "rate_limit_reason": rate_reason,
        "in_posting_window": in_window,
        "confidence_threshold": cfg.confidence_threshold,
    }

    log_action("audit_content", "compliance", "pass" if passes else "fail",
               f"score={content_score}, dup={is_dup}, platform_ok={valid_platform}")

    return report
