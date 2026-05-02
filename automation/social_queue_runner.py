"""
Social Queue Runner — Posts from social_queue table to Twitter.
Reads platform='twitter', posted=0 rows and sends them via Tweepy.
Rate-limit safe: posts up to MAX_POSTS_PER_RUN per execution.
Skips Reddit (no credentials) — marks Reddit posts posted=2 (skipped).

Usage:
  python3 -m automation.social_queue_runner          # run once
  python3 -m automation.social_queue_runner --dry    # dry run, no actual posting
"""

import sys
import os
import sqlite3
import time
import logging
import argparse
from datetime import datetime

# Path setup
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("social_queue_runner")

# Twitter free tier: ~17 tweets per 24h, 1 per 15min is safe
MAX_POSTS_PER_RUN = 5
SLEEP_BETWEEN_POSTS = 3  # seconds between API calls within one run


def get_conn():
    conn = sqlite3.connect(os.path.join(_ROOT, "data.db"))
    conn.row_factory = sqlite3.Row
    return conn


def get_twitter_client():
    """Return authenticated Tweepy v2 client or None."""
    try:
        import tweepy
        api_key    = getattr(config, "TWITTER_API_KEY", "") or os.getenv("TWITTER_API_KEY", "")
        api_secret = getattr(config, "TWITTER_API_SECRET", "") or os.getenv("TWITTER_API_SECRET", "")
        access_tok = getattr(config, "TWITTER_ACCESS_TOKEN", "") or os.getenv("TWITTER_ACCESS_TOKEN", "")
        access_sec = getattr(config, "TWITTER_ACCESS_SECRET", "") or os.getenv("TWITTER_ACCESS_SECRET", "")

        if not all([api_key, api_secret, access_tok, access_sec]):
            log.error("Twitter credentials incomplete — check config")
            return None

        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_tok,
            access_token_secret=access_sec,
        )
        return client
    except ImportError:
        log.error("tweepy not installed: pip install tweepy")
        return None
    except Exception as e:
        log.error(f"Twitter client init failed: {e}")
        return None


def send_telegram(msg: str):
    """Send a Telegram notification using the Rider bot."""
    try:
        import urllib.request, urllib.parse
        token = "8744852303:AAFC5tipgyFunXt2BWjQLQ1VaSt24foZhEI"
        chat_id = "6194068092"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, timeout=10
        )
    except Exception as e:
        log.warning(f"Telegram notification failed: {e}")


def skip_reddit_posts(conn: sqlite3.Connection) -> int:
    """Mark Reddit posts as skipped (posted=2) — no credentials available."""
    c = conn.cursor()
    c.execute(
        "UPDATE social_queue SET posted=2, posted_at=? WHERE platform='reddit' AND posted=0",
        (datetime.utcnow().isoformat(),)
    )
    count = c.rowcount
    conn.commit()
    if count > 0:
        log.info(f"Marked {count} Reddit posts as skipped (no credentials)")
    return count


def run(dry_run: bool = False) -> dict:
    """
    Main runner. Returns stats dict.
    """
    log.info(f"=== Social Queue Runner {'(DRY RUN) ' if dry_run else ''}===")
    results = {"posted": 0, "failed": 0, "skipped": 0, "dry_run": dry_run}

    conn = get_conn()

    # Skip Reddit
    results["skipped"] = skip_reddit_posts(conn)

    # Get pending Twitter posts
    c = conn.cursor()
    c.execute(
        """SELECT id, content, scheduled_for
           FROM social_queue
           WHERE platform='twitter' AND posted=0
           ORDER BY scheduled_for ASC
           LIMIT ?""",
        (MAX_POSTS_PER_RUN,)
    )
    rows = c.fetchall()

    if not rows:
        log.info("No pending Twitter posts in queue")
        conn.close()
        return results

    log.info(f"Found {len(rows)} Twitter posts to send")

    if dry_run:
        for row in rows:
            log.info(f"[DRY RUN] Would post ID={row['id']}: {row['content'][:100]}...")
            results["posted"] += 1
        conn.close()
        return results

    # Get Twitter client
    client = get_twitter_client()
    if not client:
        log.error("Twitter client unavailable — aborting")
        conn.close()
        return results

    for row in rows:
        post_id = row["id"]
        content = row["content"].strip()

        # Enforce Twitter character limit
        if len(content) > 280:
            content = content[:277] + "..."

        try:
            response = client.create_tweet(text=content)
            tweet_id = str(response.data["id"])
            tweet_url = f"https://x.com/i/web/status/{tweet_id}"

            # Mark as posted
            c.execute(
                "UPDATE social_queue SET posted=1, posted_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), post_id)
            )
            conn.commit()

            results["posted"] += 1
            log.info(f"✅ Posted ID={post_id} → {tweet_url}")

            time.sleep(SLEEP_BETWEEN_POSTS)

        except Exception as e:
            err = str(e)
            results["failed"] += 1
            log.error(f"❌ Failed ID={post_id}: {err}")

            # If rate limited, stop this run
            if "429" in err or "Too Many Requests" in err or "rate limit" in err.lower():
                log.warning("Rate limit hit — stopping this run")
                break

    conn.close()

    # Telegram summary
    if results["posted"] > 0 or results["failed"] > 0:
        remaining_q = _get_remaining_count()
        msg = (
            f"📣 Social Queue Runner\n"
            f"✅ Posted: {results['posted']}\n"
            f"❌ Failed: {results['failed']}\n"
            f"⏭️ Reddit skipped: {results['skipped']}\n"
            f"📥 Remaining in queue: {remaining_q}"
        )
        send_telegram(msg)

    log.info(f"Run complete: {results}")
    return results


def _get_remaining_count() -> int:
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM social_queue WHERE platform='twitter' AND posted=0")
        n = c.fetchone()[0]
        conn.close()
        return n
    except Exception:
        return -1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Social Queue Runner")
    parser.add_argument("--dry", action="store_true", help="Dry run — don't actually post")
    args = parser.parse_args()
    run(dry_run=args.dry)
