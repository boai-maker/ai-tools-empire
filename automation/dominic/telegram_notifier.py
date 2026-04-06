"""
Telegram notification module for Dominic.
Uses direct HTTP requests — no python-telegram-bot required.
"""
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

import requests

from automation.dominic.config import get_config
from automation.dominic.logger import log_telegram, log_error

# ---------------------------------------------------------------------------
# Message templates
# ---------------------------------------------------------------------------

POST_SUCCESS_TEMPLATE = """
<b>✅ Dominic Posted Successfully</b>

<b>Platform:</b> {platform}
<b>Content:</b> {content_preview}
<b>URL:</b> {url}
<b>Posted at:</b> {posted_at}

<i>AI Tools Empire | dominic@auto</i>
""".strip()

POST_FAILED_TEMPLATE = """
<b>❌ Dominic Post Failed</b>

<b>Platform:</b> {platform}
<b>Content:</b> {content_preview}
<b>Error:</b> {error}
<b>Retry count:</b> {retry_count}
<b>Time:</b> {timestamp}

<i>Action required if retries exhausted.</i>
""".strip()

APPROVAL_NEEDED_TEMPLATE = """
<b>🔔 Approval Needed — Content #{content_id}</b>

<b>Platform:</b> {platform}
<b>Headline:</b> {headline}

<b>Body:</b>
{body_preview}

<b>Confidence:</b> {confidence:.0%}

Reply with:
/approve_{content_id} — publish it
/reject_{content_id} — skip it
""".strip()

WEEKLY_SUMMARY_TEMPLATE = """
<b>📊 Dominic Weekly Summary</b>
<i>Week ending {week_end}</i>

<b>Twitter</b>
  Posts: {twitter_posts}
  Avg Likes: {twitter_avg_likes}
  Avg Retweets: {twitter_avg_rt}

<b>YouTube</b>
  Drafts: {youtube_drafts}
  Published: {youtube_published}

<b>Overall</b>
  Total posts: {total_posts}
  Failures: {failures}
  Top content: {top_content}

Keep building the empire, Kenny! 🚀
""".strip()

DAILY_BRIEFING_TEMPLATE = """
<b>☀️ Dominic Daily Briefing</b>
<i>{date}</i>

<b>Today's schedule:</b>
{schedule_list}

<b>Queued drafts:</b> {queued_count}
<b>Pending approval:</b> {approval_count}

<i>aitoolsempire.co</i>
""".strip()

URGENT_ALERT_TEMPLATE = """
<b>🚨 URGENT — Dominic Alert</b>

{message}

<i>Time: {timestamp}</i>
""".strip()


# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------

def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """
    Send a message to DOMINIC_TELEGRAM_CHAT_ID.
    Returns True on success, False on failure.
    """
    cfg = get_config()
    token = cfg.telegram_token
    chat_id = cfg.telegram_chat_id

    if not token or not chat_id:
        log_error("telegram_notifier", "Telegram token or chat_id not configured", "")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        success = resp.status_code == 200
        if not success:
            log_error(
                "telegram_notifier",
                f"HTTP {resp.status_code}: {resp.text[:200]}",
                "send_message"
            )
        log_telegram(text[:80], success)
        return success
    except requests.exceptions.RequestException as e:
        log_error("telegram_notifier", str(e), "send_message network error")
        log_telegram(text[:80], False)
        return False


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def notify_post_success(
    platform: str,
    content: Dict,
    url: str,
    scheduled_time: str = None,
) -> bool:
    """Notify Kenny that a post was published successfully."""
    headline = content.get("headline") or content.get("body") or ""
    content_preview = headline[:200]
    posted_at = scheduled_time or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    text = POST_SUCCESS_TEMPLATE.format(
        platform=platform.upper(),
        content_preview=_esc(content_preview),
        url=url or "N/A",
        posted_at=posted_at,
    )
    return send_message(text)


def notify_post_failed(
    platform: str,
    content: Dict,
    error: str,
    retry_count: int = 0,
) -> bool:
    """Notify Kenny that a post failed."""
    headline = content.get("headline") or content.get("body") or ""
    content_preview = headline[:150]
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    text = POST_FAILED_TEMPLATE.format(
        platform=platform.upper(),
        content_preview=_esc(content_preview),
        error=_esc(str(error)[:300]),
        retry_count=retry_count,
        timestamp=timestamp,
    )
    return send_message(text)


def notify_awaiting_approval(
    platform: str,
    content: Dict,
    content_id: int,
) -> bool:
    """Send a draft to Telegram for approval (approval mode)."""
    headline = content.get("headline") or ""
    body = content.get("body") or ""
    confidence = content.get("confidence") or 0.0
    body_preview = body[:600]

    text = APPROVAL_NEEDED_TEMPLATE.format(
        content_id=content_id,
        platform=platform.upper(),
        headline=_esc(headline),
        body_preview=_esc(body_preview),
        confidence=confidence,
    )
    return send_message(text)


def notify_urgent(message: str) -> bool:
    """Send an urgent alert."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    text = URGENT_ALERT_TEMPLATE.format(
        message=_esc(message),
        timestamp=timestamp,
    )
    return send_message(text)


def send_weekly_summary(stats_dict: Dict) -> bool:
    """Send a formatted weekly summary."""
    week_end = datetime.utcnow().strftime("%b %d, %Y")
    twitter = stats_dict.get("twitter", {})
    youtube = stats_dict.get("youtube", {})

    text = WEEKLY_SUMMARY_TEMPLATE.format(
        week_end=week_end,
        twitter_posts=twitter.get("cnt", 0),
        twitter_avg_likes=round(twitter.get("avg_likes", 0), 1),
        twitter_avg_rt=round(twitter.get("avg_rt", 0), 1),
        youtube_drafts=youtube.get("drafts", 0),
        youtube_published=youtube.get("cnt", 0),
        total_posts=stats_dict.get("total_posts", 0),
        failures=stats_dict.get("failures", 0),
        top_content=_esc(stats_dict.get("top_content", "N/A")[:100]),
    )
    return send_message(text)


def send_daily_briefing(upcoming_posts: List[Dict]) -> bool:
    """Send the morning daily briefing."""
    date_str = datetime.utcnow().strftime("%A, %B %d, %Y")

    if upcoming_posts:
        lines = []
        for p in upcoming_posts[:8]:
            t = p.get("scheduled_for", "?")[:16]
            headline = (p.get("headline") or "")[:60]
            platform = p.get("platform", "?").upper()
            lines.append(f"  {t} — {platform} — {_esc(headline)}")
        schedule_list = "\n".join(lines)
    else:
        schedule_list = "  No posts scheduled for today."

    queued_count = stats_dict_quick().get("queued", 0)
    approval_count = stats_dict_quick().get("awaiting_approval", 0)

    text = DAILY_BRIEFING_TEMPLATE.format(
        date=date_str,
        schedule_list=schedule_list,
        queued_count=queued_count,
        approval_count=approval_count,
    )
    return send_message(text)


def format_post_update(
    platform: str,
    content: Dict,
    url: str,
    posted_at: str = None,
) -> str:
    """Return formatted HTML string for a post update."""
    headline = content.get("headline") or ""
    posted_at = posted_at or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return POST_SUCCESS_TEMPLATE.format(
        platform=platform.upper(),
        content_preview=_esc(headline[:200]),
        url=url or "N/A",
        posted_at=posted_at,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """Escape HTML special chars for Telegram HTML parse mode."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def stats_dict_quick() -> Dict:
    """Quick stats from DB for briefing."""
    try:
        from automation.dominic.db import get_dom_conn
        conn = get_dom_conn()
        queued = conn.execute(
            "SELECT COUNT(*) FROM dom_content WHERE status IN ('queued','approved')"
        ).fetchone()[0]
        awaiting = conn.execute(
            "SELECT COUNT(*) FROM dom_content WHERE status='awaiting_approval'"
        ).fetchone()[0]
        conn.close()
        return {"queued": queued, "awaiting_approval": awaiting}
    except Exception:
        return {"queued": 0, "awaiting_approval": 0}
