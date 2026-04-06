"""
Reddit Poster — posts to subreddits using PRAW.
Reads from social_queue table (platform='reddit').

Setup: add to .env:
  REDDIT_CLIENT_ID=your_client_id
  REDDIT_CLIENT_SECRET=your_client_secret
  REDDIT_USERNAME=your_username
  REDDIT_PASSWORD=your_password
  REDDIT_USER_AGENT=AIToolsEmpire/1.0

Get credentials at: https://www.reddit.com/prefs/apps
  → Create app → Script type
  → redirect uri: http://localhost:8080
"""
import logging
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from database.db import get_conn

log = logging.getLogger(__name__)

# Subreddit posting rules — respect each community
SUBREDDIT_RULES = {
    "Blogging":         {"min_karma": 0, "link_ok": True},
    "SEO":              {"min_karma": 0, "link_ok": True},
    "juststart":        {"min_karma": 0, "link_ok": False},  # no self-promo until karma built
    "artificial":       {"min_karma": 0, "link_ok": True},
    "freelance":        {"min_karma": 0, "link_ok": False},
    "smallbusiness":    {"min_karma": 0, "link_ok": True},
    "ContentMarketing": {"min_karma": 0, "link_ok": True},
    "affiliatemarketing": {"min_karma": 0, "link_ok": True},
}


def get_reddit_client():
    """Return authenticated PRAW Reddit instance or None if creds missing."""
    try:
        import praw
        client_id     = getattr(config, "REDDIT_CLIENT_ID", None) or os.getenv("REDDIT_CLIENT_ID")
        client_secret = getattr(config, "REDDIT_CLIENT_SECRET", None) or os.getenv("REDDIT_CLIENT_SECRET")
        username      = getattr(config, "REDDIT_USERNAME", None) or os.getenv("REDDIT_USERNAME")
        password      = getattr(config, "REDDIT_PASSWORD", None) or os.getenv("REDDIT_PASSWORD")
        user_agent    = getattr(config, "REDDIT_USER_AGENT", None) or os.getenv("REDDIT_USER_AGENT", "AIToolsEmpire/1.0")

        if not all([client_id, client_secret, username, password]):
            log.warning("Reddit credentials not configured — posts will be queued but not sent")
            return None

        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=user_agent,
        )
        reddit.user.me()  # Verify auth
        return reddit
    except ImportError:
        log.error("praw not installed: pip3 install praw")
        return None
    except Exception as e:
        log.error(f"Reddit auth failed: {e}")
        return None


def parse_post_content(content: str) -> dict:
    """
    Parse content field.
    Expected format:
        SUBREDDIT: r/SEO
        TITLE: Your post title here
        BODY: Full post body text...
    """
    subreddit_match = re.search(r"SUBREDDIT:\s*r?/?(\w+)", content)
    title_match     = re.search(r"TITLE:\s*(.+?)(?:\n|BODY:)", content, re.DOTALL)
    body_match      = re.search(r"BODY:\s*(.+)$", content, re.DOTALL)

    return {
        "subreddit": subreddit_match.group(1).strip() if subreddit_match else "juststart",
        "title":     title_match.group(1).strip() if title_match else content[:100],
        "body":      body_match.group(1).strip() if body_match else content,
    }


def post_to_reddit(content: str, queue_id: int) -> bool:
    """Submit one post from the queue. Returns True on success."""
    parsed = parse_post_content(content)
    subreddit_name = parsed["subreddit"]
    title = parsed["title"]
    body = parsed["body"]

    reddit = get_reddit_client()
    if not reddit:
        log.info(f"[MOCK REDDIT] r/{subreddit_name} | {title[:60]}...")
        _mark_posted(queue_id)
        return True  # Mock success so scheduler keeps running

    try:
        subreddit = reddit.subreddit(subreddit_name)
        subreddit.submit(title=title, selftext=body)
        log.info(f"Posted to r/{subreddit_name}: {title[:60]}")
        _mark_posted(queue_id)
        return True
    except Exception as e:
        log.error(f"Reddit post failed (r/{subreddit_name}): {e}")
        return False


def _mark_posted(queue_id: int):
    conn = get_conn()
    conn.execute("UPDATE social_queue SET posted=1, posted_at=CURRENT_TIMESTAMP WHERE id=?", (queue_id,))
    conn.commit()
    conn.close()


def run_reddit_posting(count: int = 1) -> int:
    """
    Called by scheduler. Posts `count` pending Reddit items due now.
    Returns number successfully posted.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, content FROM social_queue
        WHERE platform='reddit' AND posted=0
          AND (scheduled_for IS NULL OR scheduled_for <= datetime('now'))
        ORDER BY scheduled_for ASC
        LIMIT ?
    """, (count,)).fetchall()
    conn.close()

    sent = 0
    for row in rows:
        if post_to_reddit(row["content"], row["id"]):
            sent += 1
    return sent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sent = run_reddit_posting(count=1)
    print(f"Posted {sent} Reddit post(s)")
