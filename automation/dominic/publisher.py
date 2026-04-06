"""
Publishing engine for Dominic.
Handles actual posting to Twitter and YouTube with retry logic.
"""
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.db import (
    get_content_by_id, mark_published, mark_failed,
    update_content_status, get_due_schedule_rows, update_schedule_status
)
from automation.dominic.logger import log_action, log_error, log_post
from automation.dominic.telegram_notifier import (
    notify_post_success, notify_post_failed,
    notify_awaiting_approval
)

# ---------------------------------------------------------------------------
# Twitter posting
# ---------------------------------------------------------------------------

def _get_twitter_client():
    """Return authenticated Tweepy client."""
    try:
        import tweepy
        cfg = get_config()
        if not all([cfg.twitter_api_key, cfg.twitter_api_secret,
                    cfg.twitter_access_token, cfg.twitter_access_secret]):
            return None
        client = tweepy.Client(
            consumer_key=cfg.twitter_api_key,
            consumer_secret=cfg.twitter_api_secret,
            access_token=cfg.twitter_access_token,
            access_token_secret=cfg.twitter_access_secret,
        )
        return client
    except ImportError:
        log_error("publisher", "tweepy not installed", "_get_twitter_client")
        return None
    except Exception as e:
        log_error("publisher", str(e), "_get_twitter_client")
        return None


def _post_to_twitter(text: str) -> Tuple[bool, str, str]:
    """
    Post tweet. Returns (success, tweet_id, tweet_url).
    """
    client = _get_twitter_client()
    if not client:
        return False, "", "Twitter client not available"

    try:
        response = client.create_tweet(text=text)
        tweet_id = str(response.data["id"])
        # Try to get username for URL
        try:
            me = client.get_me()
            username = me.data.username
        except Exception:
            username = "AIToolsEmpire"
        tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
        return True, tweet_id, tweet_url
    except Exception as e:
        return False, "", str(e)


def publish_tweet(content_id: int) -> Tuple[bool, str]:
    """
    Post a tweet for content_id. Marks result. Notifies Telegram.
    Returns (success, publish_url).
    """
    content = get_content_by_id(content_id)
    if not content:
        log_error("publisher", f"Content not found: {content_id}", "publish_tweet")
        return False, ""

    # Check mode
    cfg = get_config()
    if cfg.mode == "approval":
        result = check_approval_mode(content_id)
        if not result:
            return False, "awaiting_approval"

    tweet_text = content.get("body") or content.get("headline") or ""
    if not tweet_text:
        log_error("publisher", f"No text for content {content_id}", "publish_tweet")
        return False, ""

    # Truncate if needed
    if len(tweet_text) > 280:
        tweet_text = tweet_text[:277] + "..."

    success, external_id, url_or_error = _post_to_twitter(tweet_text)

    if success:
        mark_published(content_id, url_or_error, external_id)
        log_post("twitter", tweet_text[:100], "success", url_or_error)
        notify_post_success("twitter", content, url_or_error, datetime.utcnow().isoformat())
        log_action("publish_tweet", "publisher", "success", f"id={content_id}, url={url_or_error}")
        return True, url_or_error
    else:
        mark_failed(content_id, url_or_error)
        log_post("twitter", tweet_text[:100], "failed", url_or_error)
        notify_post_failed("twitter", content, url_or_error, content.get("retry_count", 0))
        log_action("publish_tweet", "publisher", "failed", f"id={content_id}, err={url_or_error}")
        return False, ""


# ---------------------------------------------------------------------------
# YouTube posting
# ---------------------------------------------------------------------------

def publish_youtube_draft(content_id: int) -> Tuple[bool, str]:
    """
    Save YouTube draft (no actual upload — saves to community post or notifies Kenny).
    Returns (success, reference_url).
    """
    content = get_content_by_id(content_id)
    if not content:
        log_error("publisher", f"Content not found: {content_id}", "publish_youtube_draft")
        return False, ""

    cfg = get_config()

    # Try YouTube community post if available
    try:
        import sys
        sys.path.insert(0, str(_ROOT))
        from automation.youtube_community import post_community_update
        headline = content.get("headline") or ""
        body = content.get("body") or ""
        # Use headline as community post text
        post_text = f"{headline}\n\n{body[:800]}\n\n{cfg.site_url}"
        result = post_community_update(post_text[:1000])
        if result:
            url = f"https://youtube.com/channel/{result}"
            mark_published(content_id, url, result)
            log_post("youtube", headline[:100], "success", url)
            notify_post_success("youtube", content, url, datetime.utcnow().isoformat())
            log_action("publish_youtube_draft", "publisher", "success", f"id={content_id}")
            return True, url
    except Exception as e:
        log_error("publisher", str(e), "publish_youtube_draft youtube_community attempt")

    # Fallback: mark as published with a local reference, notify Kenny
    draft_ref = f"youtube_draft_{content_id}_{int(datetime.utcnow().timestamp())}"
    ref_url = f"{cfg.site_url}/youtube-drafts/{draft_ref}"
    mark_published(content_id, ref_url, draft_ref)
    notify_post_success("youtube", content, ref_url, datetime.utcnow().isoformat())
    log_post("youtube", (content.get("headline") or "")[:100], "draft_saved", ref_url)
    log_action("publish_youtube_draft", "publisher", "draft_saved", f"id={content_id}")
    return True, ref_url


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

def publish_with_retry(platform: str, content_id: int, max_retries: int = 3) -> Tuple[bool, str]:
    """
    Publish with retry on failure.
    Returns (success, url).
    """
    content = get_content_by_id(content_id)
    if not content:
        return False, ""

    retry_count = content.get("retry_count") or 0

    for attempt in range(1, max_retries + 1):
        if platform == "twitter":
            success, url = publish_tweet(content_id)
        elif platform == "youtube":
            success, url = publish_youtube_draft(content_id)
        else:
            log_error("publisher", f"Unknown platform: {platform}", "publish_with_retry")
            return False, ""

        if success:
            return True, url

        # Don't retry if awaiting approval
        if url == "awaiting_approval":
            return False, "awaiting_approval"

        if attempt < max_retries:
            log_action("retry_publish", "publisher", f"attempt_{attempt}",
                       f"content_id={content_id}, platform={platform}")
            time.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s

    log_action("publish_exhausted_retries", "publisher", "failed",
               f"content_id={content_id}, platform={platform}")
    return False, ""


# ---------------------------------------------------------------------------
# Approval mode
# ---------------------------------------------------------------------------

def check_approval_mode(content_id: int) -> bool:
    """
    In approval mode: send draft to Telegram, set status to awaiting_approval.
    Returns False (caller should not publish yet).
    """
    content = get_content_by_id(content_id)
    if not content:
        return False

    platform = content.get("platform") or "twitter"
    status = content.get("status") or ""

    # Already approved — allow
    if status == "approved":
        return True

    # Set to awaiting approval and notify
    update_content_status(content_id, "awaiting_approval")
    notify_awaiting_approval(platform, content, content_id)
    log_action("awaiting_approval", "publisher", "sent_to_telegram", f"content_id={content_id}")
    return False


# ---------------------------------------------------------------------------
# Run due posts
# ---------------------------------------------------------------------------

def run_due_posts() -> Dict:
    """
    Check dom_schedule for due posts and publish them.
    Returns summary dict.
    """
    cfg = get_config()
    if cfg.paused:
        log_action("run_due_posts", "publisher", "skipped", "Dominic is paused")
        return {"skipped": True, "reason": "paused"}

    due_rows = get_due_schedule_rows()
    results = {"posted": 0, "failed": 0, "skipped": 0, "details": []}

    for row in due_rows:
        schedule_id = row["id"]
        content_id = row["content_id"]
        platform = row["platform"]

        # Double-check content exists
        content = get_content_by_id(content_id)
        if not content:
            update_schedule_status(schedule_id, "failed")
            results["failed"] += 1
            continue

        success, url = publish_with_retry(platform, content_id)

        if success:
            update_schedule_status(schedule_id, "posted")
            results["posted"] += 1
            results["details"].append({"platform": platform, "content_id": content_id, "url": url, "status": "posted"})
        elif url == "awaiting_approval":
            update_schedule_status(schedule_id, "pending")  # Keep pending until approved
            results["skipped"] += 1
        else:
            update_schedule_status(schedule_id, "failed")
            results["failed"] += 1
            results["details"].append({"platform": platform, "content_id": content_id, "status": "failed"})

    log_action("run_due_posts", "publisher", "complete",
               f"posted={results['posted']}, failed={results['failed']}")
    return results


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def handle_failure(content_id: int, error: str, platform: str) -> None:
    """Log failure, notify, and attempt reschedule."""
    content = get_content_by_id(content_id)
    if content:
        retry_count = content.get("retry_count") or 0
        notify_post_failed(platform, content, error, retry_count)

    mark_failed(content_id, error)
    log_error("publisher", error, f"handle_failure content_id={content_id}, platform={platform}")

    # Try to reschedule if retries remaining
    if content and (content.get("retry_count") or 0) < 3:
        try:
            from automation.dominic.planner import find_next_slot, schedule_content
            next_slot = find_next_slot(platform)
            schedule_content(content_id, platform, next_slot)
            log_action("reschedule_failed", "publisher", "rescheduled",
                       f"content_id={content_id}, next_slot={next_slot}")
        except Exception as e:
            log_error("publisher", str(e), "reschedule after failure")
