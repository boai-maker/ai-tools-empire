"""
Social Queue Runner — Posts from social_queue table to Twitter, Instagram, TikTok.

Platforms:
  twitter  → Tweepy v2 direct API
  instagram → Make.com webhook → Buffer → Instagram
  tiktok   → Make.com webhook → Buffer → TikTok
  reddit   → Skipped (no credentials), marked posted=2

Usage:
  python3 -m automation.social_queue_runner          # run once
  python3 -m automation.social_queue_runner --dry    # dry run, no posting
"""

import sys
import os
import sqlite3
import time
import json
import logging
import argparse
import urllib.request
import urllib.parse
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

MAX_POSTS_PER_RUN   = 5   # per platform per run
SLEEP_BETWEEN_POSTS = 3   # seconds between API calls


# ── helpers ──────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(os.path.join(_ROOT, "data.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _cfg(key: str) -> str:
    return getattr(config, key, "") or os.getenv(key, "")


def send_telegram(msg: str):
    try:
        token   = "8744852303:AAFC5tipgyFunXt2BWjQLQ1VaSt24foZhEI"
        chat_id = "6194068092"
        data    = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, timeout=10
        )
    except Exception as e:
        log.warning(f"Telegram notification failed: {e}")


# ── Twitter ───────────────────────────────────────────────────────────────────

def get_twitter_client():
    try:
        import tweepy
        keys = [_cfg(k) for k in (
            "TWITTER_API_KEY", "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"
        )]
        if not all(keys):
            log.error("Twitter credentials incomplete — check config")
            return None
        return tweepy.Client(
            consumer_key=keys[0], consumer_secret=keys[1],
            access_token=keys[2], access_token_secret=keys[3],
        )
    except ImportError:
        log.error("tweepy not installed: pip install tweepy")
        return None
    except Exception as e:
        log.error(f"Twitter client init failed: {e}")
        return None


def post_twitter(rows, dry_run: bool, conn) -> dict:
    results = {"posted": 0, "failed": 0}
    if not rows:
        return results

    log.info(f"Twitter: {len(rows)} posts to send")
    if dry_run:
        for r in rows:
            log.info(f"[DRY RUN] Twitter ID={r['id']}: {r['content'][:80]}...")
        results["posted"] = len(rows)
        return results

    client = get_twitter_client()
    if not client:
        results["failed"] = len(rows)
        return results

    c = conn.cursor()
    for row in rows:
        content = row["content"].strip()
        if len(content) > 280:
            content = content[:277] + "..."
        try:
            resp     = client.create_tweet(text=content)
            tweet_id = str(resp.data["id"])
            c.execute(
                "UPDATE social_queue SET posted=1, posted_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), row["id"])
            )
            conn.commit()
            results["posted"] += 1
            log.info(f"✅ Twitter ID={row['id']} → https://x.com/i/web/status/{tweet_id}")
            time.sleep(SLEEP_BETWEEN_POSTS)
        except Exception as e:
            err = str(e)
            results["failed"] += 1
            log.error(f"❌ Twitter ID={row['id']} failed: {err}")
            if "429" in err or "rate limit" in err.lower():
                log.warning("Rate limit hit — stopping Twitter run")
                break
    return results


# ── Make.com → Buffer → Instagram / TikTok ───────────────────────────────────

def post_via_make(rows, platform: str, dry_run: bool, conn) -> dict:
    """Push posts to Make.com webhook, which routes to Buffer → IG or TikTok."""
    results = {"posted": 0, "failed": 0}
    if not rows:
        return results

    webhook_url = _cfg("MAKE_BUFFER_WEBHOOK")
    if not webhook_url or "PASTE_YOUR" in webhook_url:
        log.warning(f"{platform}: MAKE_BUFFER_WEBHOOK not set — skipping")
        results["failed"] = len(rows)
        return results

    log.info(f"{platform}: {len(rows)} posts to send via Make webhook")
    if dry_run:
        for r in rows:
            log.info(f"[DRY RUN] {platform} ID={r['id']}: {r['content'][:80]}...")
        results["posted"] = len(rows)
        return results

    c = conn.cursor()
    for row in rows:
        content = row["content"].strip()
        # Instagram/TikTok: 2200 char limit, but keep it punchy for reach
        if len(content) > 2200:
            content = content[:2197] + "..."

        payload = json.dumps({
            "platform": platform,
            "text":     content,
            "source":   "aitoolsempire",
            "queued_at": datetime.utcnow().isoformat(),
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=15)
            status = resp.getcode()

            if status in (200, 201, 202, 204):
                c.execute(
                    "UPDATE social_queue SET posted=1, posted_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), row["id"])
                )
                conn.commit()
                results["posted"] += 1
                log.info(f"✅ {platform} ID={row['id']} → Make webhook OK (HTTP {status})")
            else:
                results["failed"] += 1
                log.error(f"❌ {platform} ID={row['id']} → webhook returned HTTP {status}")

            time.sleep(SLEEP_BETWEEN_POSTS)

        except Exception as e:
            results["failed"] += 1
            log.error(f"❌ {platform} ID={row['id']} failed: {e}")

    return results


# ── Reddit ────────────────────────────────────────────────────────────────────

def skip_reddit(conn) -> int:
    c = conn.cursor()
    c.execute(
        "UPDATE social_queue SET posted=2, posted_at=? WHERE platform='reddit' AND posted=0",
        (datetime.utcnow().isoformat(),)
    )
    count = c.rowcount
    conn.commit()
    if count > 0:
        log.info(f"Marked {count} Reddit posts as skipped")
    return count


# ── Main ──────────────────────────────────────────────────────────────────────

def _fetch_pending(conn, platform: str, limit: int):
    c = conn.cursor()
    c.execute(
        """SELECT id, content, scheduled_for
           FROM social_queue
           WHERE platform=? AND posted=0
           ORDER BY scheduled_for ASC
           LIMIT ?""",
        (platform, limit)
    )
    return c.fetchall()


def _remaining(platform: str = None) -> int:
    try:
        conn = get_conn()
        c    = conn.cursor()
        if platform:
            c.execute(
                "SELECT COUNT(*) FROM social_queue WHERE platform=? AND posted=0",
                (platform,)
            )
        else:
            c.execute("SELECT COUNT(*) FROM social_queue WHERE posted=0")
        n = c.fetchone()[0]
        conn.close()
        return n
    except Exception:
        return -1


def run(dry_run: bool = False) -> dict:
    log.info(f"=== Social Queue Runner {'(DRY RUN) ' if dry_run else ''}===")
    totals = {"twitter": {}, "instagram": {}, "tiktok": {}, "reddit_skipped": 0}

    conn = get_conn()

    # Reddit — skip always
    totals["reddit_skipped"] = skip_reddit(conn)

    # Twitter
    tw_rows = _fetch_pending(conn, "twitter", MAX_POSTS_PER_RUN)
    totals["twitter"] = post_twitter(tw_rows, dry_run, conn)

    # Instagram
    ig_rows = _fetch_pending(conn, "instagram", MAX_POSTS_PER_RUN)
    totals["instagram"] = post_via_make(ig_rows, "instagram", dry_run, conn)

    # TikTok
    tt_rows = _fetch_pending(conn, "tiktok", MAX_POSTS_PER_RUN)
    totals["tiktok"] = post_via_make(tt_rows, "tiktok", dry_run, conn)

    conn.close()

    # Telegram summary
    tw = totals["twitter"]
    ig = totals["instagram"]
    tt = totals["tiktok"]
    total_posted = tw.get("posted", 0) + ig.get("posted", 0) + tt.get("posted", 0)
    total_failed = tw.get("failed", 0) + ig.get("failed", 0) + tt.get("failed", 0)

    if total_posted > 0 or total_failed > 0:
        remaining = _remaining()
        msg = (
            f"📣 Social Queue Runner {'[DRY RUN]' if dry_run else ''}\n"
            f"🐦 Twitter:   ✅{tw.get('posted',0)} ❌{tw.get('failed',0)}\n"
            f"📸 Instagram: ✅{ig.get('posted',0)} ❌{ig.get('failed',0)}\n"
            f"🎵 TikTok:    ✅{tt.get('posted',0)} ❌{tt.get('failed',0)}\n"
            f"⏭️  Reddit skipped: {totals['reddit_skipped']}\n"
            f"📥 Remaining: {remaining}"
        )
        send_telegram(msg)

    log.info(f"Run complete: {totals}")
    return totals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Social Queue Runner")
    parser.add_argument("--dry", action="store_true", help="Dry run — don't actually post")
    args = parser.parse_args()
    run(dry_run=args.dry)
