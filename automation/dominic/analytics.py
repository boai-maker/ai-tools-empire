"""
Analytics tracker and reporting for Dominic.
Tracks engagement and generates performance reports.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.db import get_dom_conn, get_history_stats
from automation.dominic.logger import log_action, log_error

# ---------------------------------------------------------------------------
# Twitter engagement tracking
# ---------------------------------------------------------------------------

def track_tweet_performance(history_id: int, tweet_id: str) -> Dict:
    """
    Fetch engagement metrics from Twitter API and update dom_history.
    Returns dict with likes, retweets, impressions.
    """
    if not tweet_id:
        return {}

    try:
        import tweepy
        cfg = get_config()
        client = tweepy.Client(
            consumer_key=cfg.twitter_api_key,
            consumer_secret=cfg.twitter_api_secret,
            access_token=cfg.twitter_access_token,
            access_token_secret=cfg.twitter_access_secret,
        )
        response = client.get_tweet(
            tweet_id,
            tweet_fields=["public_metrics"],
        )
        if not response.data:
            return {}

        metrics = response.data.public_metrics or {}
        likes = metrics.get("like_count", 0)
        retweets = metrics.get("retweet_count", 0)
        impressions = metrics.get("impression_count", 0)

        # Update dom_history
        conn = get_dom_conn()
        conn.execute(
            "UPDATE dom_history SET likes=?, retweets=?, views=? WHERE id=?",
            (likes, retweets, impressions, history_id)
        )
        conn.commit()
        conn.close()

        log_action("track_tweet", "analytics", "ok",
                   f"history_id={history_id}, likes={likes}, rt={retweets}")
        return {"likes": likes, "retweets": retweets, "impressions": impressions}

    except Exception as e:
        log_error("analytics", str(e), f"track_tweet history_id={history_id}")
        return {}


# ---------------------------------------------------------------------------
# Stats aggregation
# ---------------------------------------------------------------------------

def get_weekly_stats() -> Dict:
    """
    Return dict with posts_count, avg_engagement, top_post, failures for the past 7 days.
    """
    conn = get_dom_conn()

    # Posts count by platform
    rows = conn.execute(
        """SELECT platform, COUNT(*) as cnt,
           AVG(likes) as avg_likes, AVG(retweets) as avg_rt, AVG(views) as avg_views,
           SUM(likes) as total_likes
           FROM dom_history
           WHERE published_at >= datetime('now', '-7 days')
           GROUP BY platform"""
    ).fetchall()

    stats = {}
    total_posts = 0
    for r in rows:
        stats[r["platform"]] = dict(r)
        total_posts += r["cnt"]

    # Top post
    top_row = conn.execute(
        """SELECT content_summary, publish_url, likes, retweets, platform
           FROM dom_history
           WHERE published_at >= datetime('now', '-7 days')
           ORDER BY (likes + retweets * 2) DESC
           LIMIT 1"""
    ).fetchone()
    top_post = dict(top_row) if top_row else {}

    # Failures
    failures = conn.execute(
        """SELECT COUNT(*) FROM dom_content
           WHERE status='failed'
           AND created_at >= datetime('now', '-7 days')"""
    ).fetchone()[0]

    # Total engagement
    total_eng = conn.execute(
        """SELECT SUM(likes + retweets) FROM dom_history
           WHERE published_at >= datetime('now', '-7 days')"""
    ).fetchone()[0] or 0

    conn.close()

    avg_engagement = round(total_eng / total_posts, 2) if total_posts > 0 else 0.0

    return {
        "total_posts": total_posts,
        "avg_engagement": avg_engagement,
        "top_post": top_post.get("content_summary", "N/A")[:100],
        "top_post_url": top_post.get("publish_url", ""),
        "failures": failures,
        "by_platform": stats,
        "week_start": (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d"),
        "week_end": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def get_platform_breakdown() -> Dict:
    """Return stats broken down by platform."""
    conn = get_dom_conn()
    rows = conn.execute(
        """SELECT platform,
           COUNT(*) as total_posts,
           SUM(likes) as total_likes,
           SUM(retweets) as total_rt,
           SUM(views) as total_views,
           AVG(likes) as avg_likes,
           MAX(likes) as max_likes
           FROM dom_history
           GROUP BY platform"""
    ).fetchall()
    conn.close()
    return {r["platform"]: dict(r) for r in rows}


def get_top_content(n: int = 5) -> List[Dict]:
    """Return top N performing content by engagement."""
    conn = get_dom_conn()
    rows = conn.execute(
        """SELECT content_summary, publish_url, platform,
           likes, retweets, views, published_at,
           (likes + retweets * 2 + views * 0.01) as engagement_score
           FROM dom_history
           WHERE likes > 0 OR retweets > 0
           ORDER BY engagement_score DESC
           LIMIT ?""",
        (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recommendations() -> str:
    """
    Generate AI recommendations based on performance data.
    Returns a text recommendation string.
    """
    try:
        stats = get_weekly_stats()
        breakdown = get_platform_breakdown()
        top = get_top_content(3)

        import anthropic
        cfg = get_config()
        client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

        top_content_str = "\n".join(
            f"- {t.get('content_summary','?')[:80]} (likes={t.get('likes',0)}, rt={t.get('retweets',0)})"
            for t in top
        )

        prompt = f"""You are a social media analyst for AI Tools Empire (aitoolsempire.co).
Analyze this week's performance and give 3-4 specific, actionable recommendations.

Weekly stats:
- Total posts: {stats.get('total_posts', 0)}
- Avg engagement: {stats.get('avg_engagement', 0)}
- Failures: {stats.get('failures', 0)}
- Top post: {stats.get('top_post', 'N/A')}

Top performing content:
{top_content_str}

Platform breakdown: {breakdown}

Give specific recommendations about:
1. What content types to create more of
2. Best posting times/frequency
3. Topics that resonate with the AI tools audience
4. Any issues to address

Keep it brief and actionable (4-6 bullet points). Use plain text."""

        response = client.messages.create(
            model=cfg.claude_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else "No recommendations available."

    except Exception as e:
        log_error("analytics", str(e), "get_recommendations")
        return (
            "Recommendations unavailable.\n"
            "Tip: Keep posting consistently — 2x/day on Twitter and 3x/week on YouTube "
            "is the sweet spot for the AI tools audience."
        )


def generate_weekly_report() -> str:
    """Generate a full weekly performance report as a text string for Telegram."""
    stats = get_weekly_stats()
    breakdown = get_platform_breakdown()
    top = get_top_content(3)
    recommendations = get_recommendations()

    twitter = breakdown.get("twitter", {})
    youtube = breakdown.get("youtube", {})

    top_content_lines = "\n".join(
        f"  {i+1}. {t.get('content_summary','?')[:60]} (likes={t.get('likes',0)})"
        for i, t in enumerate(top)
    ) or "  No data yet."

    report = f"""<b>📊 Dominic Weekly Performance Report</b>
<i>{stats.get('week_start')} → {stats.get('week_end')}</i>

<b>Overview</b>
Total posts: {stats.get('total_posts', 0)}
Avg engagement: {stats.get('avg_engagement', 0)}
Failures: {stats.get('failures', 0)}

<b>Twitter</b>
Posts: {twitter.get('total_posts', 0)}
Total likes: {twitter.get('total_likes', 0)}
Total retweets: {twitter.get('total_rt', 0)}
Avg likes/post: {round(twitter.get('avg_likes', 0) or 0, 1)}

<b>YouTube</b>
Drafts published: {youtube.get('total_posts', 0)}

<b>Top Content</b>
{top_content_lines}

<b>Recommendations</b>
{recommendations[:600]}

<i>AI Tools Empire | aitoolsempire.co</i>"""

    return report


def run_analytics_update() -> Dict:
    """
    Update engagement metrics for all recent tracked posts.
    Returns summary of updates.
    """
    conn = get_dom_conn()
    # Get recent Twitter history with external_id
    rows = conn.execute(
        """SELECT id, external_id FROM dom_history
           WHERE platform='twitter'
           AND external_id != ''
           AND published_at >= datetime('now', '-7 days')
           ORDER BY published_at DESC
           LIMIT 50"""
    ).fetchall()
    conn.close()

    updated = 0
    errors = 0
    for row in rows:
        history_id = row["id"]
        tweet_id = row["external_id"]
        result = track_tweet_performance(history_id, tweet_id)
        if result:
            updated += 1
        else:
            errors += 1

    log_action("run_analytics_update", "analytics", "ok", f"updated={updated}, errors={errors}")
    return {"updated": updated, "errors": errors}
