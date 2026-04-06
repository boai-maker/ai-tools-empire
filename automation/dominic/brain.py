"""
Dominic Brain — Main orchestrator.
Coordinates all subsystems: crawl → ideas → generate → score → schedule → publish → report.
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.db import (
    init_dominic_db, save_content, get_draft_content,
    get_pending_content, get_dom_config, set_dom_config
)
from automation.dominic.admin import is_paused, get_current_mode, get_status
from automation.dominic.logger import log_action, log_error, get_logger

_log = get_logger()


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

def _check_active() -> bool:
    """Return True if Dominic is not paused."""
    if is_paused():
        log_action("cycle_check", "brain", "skipped", "Dominic is paused")
        return False
    return True


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_dominic_cycle() -> Dict:
    """
    Full Dominic cycle:
    crawl → ideas → plan → publish → report
    Returns summary dict.
    """
    if not _check_active():
        return {"status": "paused"}

    summary = {
        "started_at": datetime.utcnow().isoformat(),
        "articles_found": 0,
        "ideas_generated": 0,
        "content_saved": 0,
        "posts_published": 0,
        "errors": [],
    }

    try:
        log_action("cycle_start", "brain", "running", "")

        # 1. Crawl site
        try:
            from automation.dominic.crawler import run_crawl
            new_articles = run_crawl()
            summary["articles_found"] = len(new_articles)
            log_action("crawl", "brain", "ok", f"found {len(new_articles)} new articles")
        except Exception as e:
            summary["errors"].append(f"crawl: {e}")
            log_error("brain", str(e), "crawl phase")
            new_articles = []

        # 2. Extract ideas from new articles + evergreen
        ideas = []
        try:
            from automation.dominic.idea_engine import (
                batch_extract_ideas, generate_evergreen_ideas, deduplicate_ideas
            )
            if new_articles:
                article_ideas = batch_extract_ideas(new_articles, max_ideas=3)
                ideas.extend(article_ideas)

            # Always top up with evergreen ideas
            evergreen = generate_evergreen_ideas(n=5)
            ideas.extend(evergreen)

            # Deduplicate
            ideas = deduplicate_ideas(ideas)
            summary["ideas_generated"] = len(ideas)
            log_action("ideas", "brain", "ok", f"total ideas: {len(ideas)}")
        except Exception as e:
            summary["errors"].append(f"ideas: {e}")
            log_error("brain", str(e), "idea phase")

        # 3. Generate content (tweets + YouTube)
        cfg = get_config()
        saved_ids = []
        try:
            from automation.dominic.tweet_gen import generate_tweet, validate_tweet
            from automation.dominic.compliance import audit_content

            for idea in ideas:
                platform = idea.get("platform") or "twitter"

                if platform in ("twitter", "both"):
                    try:
                        tweet_text = generate_tweet(idea)
                        tweet_idea = {
                            **idea,
                            "body": tweet_text,
                            "platform": "twitter",
                        }
                        audit = audit_content(tweet_idea)
                        if audit.get("score", 0) >= cfg.confidence_threshold:
                            cid = save_content(
                                headline=idea.get("headline", ""),
                                body=tweet_text,
                                content_type=idea.get("content_type", "educational"),
                                platform="twitter",
                                confidence=audit["score"],
                                url=idea.get("url", ""),
                                source_title=idea.get("source_title", ""),
                                status="queued",
                            )
                            if cid:
                                saved_ids.append(cid)
                    except Exception as e:
                        log_error("brain", str(e), "tweet gen")

                if platform in ("youtube", "both"):
                    try:
                        from automation.dominic.youtube_gen import generate_video_concept, save_video_draft
                        concept = generate_video_concept(idea)
                        idea_with_concept = {
                            **idea,
                            "headline": concept.get("title", idea.get("headline", "")),
                            "platform": "youtube",
                        }
                        cid = save_video_draft(concept)
                        if cid:
                            saved_ids.append(cid)
                    except Exception as e:
                        log_error("brain", str(e), "youtube gen")

            summary["content_saved"] = len(saved_ids)
            log_action("generate_content", "brain", "ok", f"saved {len(saved_ids)} items")
        except Exception as e:
            summary["errors"].append(f"generate: {e}")
            log_error("brain", str(e), "generate phase")

        # 4. Schedule new content
        try:
            from automation.dominic.planner import plan_week
            plan = plan_week()
            log_action("plan_week", "brain", "ok",
                       f"twitter={len(plan.get('twitter',[]))}, youtube={len(plan.get('youtube',[]))}")
        except Exception as e:
            summary["errors"].append(f"plan: {e}")
            log_error("brain", str(e), "plan phase")

        # 5. Publish due posts
        try:
            from automation.dominic.publisher import run_due_posts
            pub_results = run_due_posts()
            summary["posts_published"] = pub_results.get("posted", 0)
            log_action("publish", "brain", "ok",
                       f"posted={pub_results.get('posted',0)}, failed={pub_results.get('failed',0)}")
        except Exception as e:
            summary["errors"].append(f"publish: {e}")
            log_error("brain", str(e), "publish phase")

        summary["completed_at"] = datetime.utcnow().isoformat()
        log_action("cycle_complete", "brain", "ok", str(summary))

    except Exception as e:
        summary["errors"].append(f"cycle: {e}")
        log_error("brain", str(e), "run_dominic_cycle top-level")

    return summary


# ---------------------------------------------------------------------------
# Routine functions
# ---------------------------------------------------------------------------

def morning_routine() -> None:
    """
    8 AM routine:
    - Crawl site for new articles
    - Extract ideas
    - Plan the day
    - Send daily briefing to Telegram
    """
    if not _check_active():
        return

    log_action("morning_routine", "brain", "start", "")

    # Crawl
    try:
        from automation.dominic.crawler import run_crawl
        new_articles = run_crawl()
    except Exception as e:
        log_error("brain", str(e), "morning_routine crawl")
        new_articles = []

    # Ideas
    try:
        from automation.dominic.idea_engine import (
            batch_extract_ideas, generate_evergreen_ideas, deduplicate_ideas
        )
        ideas = batch_extract_ideas(new_articles, max_ideas=3)
        ideas += generate_evergreen_ideas(n=5)
        ideas = deduplicate_ideas(ideas)
    except Exception as e:
        log_error("brain", str(e), "morning_routine ideas")
        ideas = []

    # Generate tweets
    cfg = get_config()
    try:
        from automation.dominic.tweet_gen import generate_tweet
        from automation.dominic.compliance import audit_content
        for idea in ideas[:10]:
            if idea.get("platform") in ("twitter", "both"):
                try:
                    tweet = generate_tweet(idea)
                    tweet_idea = {**idea, "body": tweet, "platform": "twitter"}
                    audit = audit_content(tweet_idea)
                    if audit.get("score", 0) >= cfg.confidence_threshold:
                        save_content(
                            headline=idea.get("headline", ""),
                            body=tweet,
                            content_type=idea.get("content_type", "educational"),
                            platform="twitter",
                            confidence=audit["score"],
                            url=idea.get("url", ""),
                            source_title=idea.get("source_title", ""),
                            status="queued",
                        )
                except Exception as e:
                    log_error("brain", str(e), "morning tweet gen")
    except Exception as e:
        log_error("brain", str(e), "morning_routine content gen")

    # Plan
    try:
        from automation.dominic.planner import plan_week
        plan_week()
    except Exception as e:
        log_error("brain", str(e), "morning_routine plan")

    # Briefing
    try:
        from automation.dominic.planner import get_today_schedule
        from automation.dominic.telegram_notifier import send_daily_briefing
        today_posts = get_today_schedule()
        send_daily_briefing(today_posts)
    except Exception as e:
        log_error("brain", str(e), "morning_routine briefing")

    log_action("morning_routine", "brain", "complete", "")


def posting_routine() -> Dict:
    """
    Called at posting times (9 AM, 6 PM ET for Twitter; noon for YouTube).
    Checks schedule and publishes due content.
    """
    if not _check_active():
        return {"status": "paused"}

    log_action("posting_routine", "brain", "start", "")
    try:
        from automation.dominic.publisher import run_due_posts
        results = run_due_posts()
        log_action("posting_routine", "brain", "complete",
                   f"posted={results.get('posted',0)}")
        return results
    except Exception as e:
        log_error("brain", str(e), "posting_routine")
        return {"error": str(e)}


def evening_routine() -> None:
    """
    8 PM routine:
    - Update analytics
    - Send daily summary
    """
    if not _check_active():
        return

    log_action("evening_routine", "brain", "start", "")

    # Analytics update
    try:
        from automation.dominic.analytics import run_analytics_update
        run_analytics_update()
    except Exception as e:
        log_error("brain", str(e), "evening_routine analytics")

    # Daily summary
    try:
        from automation.dominic.analytics import get_weekly_stats
        from automation.dominic.telegram_notifier import send_message
        stats = get_weekly_stats()
        today_posts = stats.get("total_posts", 0)
        send_message(
            f"🌙 <b>Dominic Evening Summary</b>\n"
            f"Posts this week: {today_posts}\n"
            f"Avg engagement: {stats.get('avg_engagement', 0)}\n"
            f"Failures: {stats.get('failures', 0)}\n"
            f"<i>All systems nominal.</i>"
        )
    except Exception as e:
        log_error("brain", str(e), "evening_routine summary")

    log_action("evening_routine", "brain", "complete", "")


def weekly_routine() -> None:
    """
    Monday 9 AM routine:
    - Generate full weekly content plan
    - Send weekly performance report
    """
    if not _check_active():
        return

    log_action("weekly_routine", "brain", "start", "")

    # Generate weekly plan
    try:
        from automation.dominic.planner import plan_week
        plan = plan_week()
        log_action("weekly_plan", "brain", "ok",
                   f"twitter={len(plan.get('twitter',[]))}, youtube={len(plan.get('youtube',[]))}")
    except Exception as e:
        log_error("brain", str(e), "weekly_routine plan")

    # Weekly report
    try:
        from automation.dominic.analytics import generate_weekly_report
        from automation.dominic.telegram_notifier import send_message
        report = generate_weekly_report()
        send_message(report)
    except Exception as e:
        log_error("brain", str(e), "weekly_routine report")

    log_action("weekly_routine", "brain", "complete", "")


def handle_new_article(article: Dict) -> None:
    """
    Immediately generate and queue ideas from a freshly discovered article.
    """
    if not _check_active():
        return

    try:
        from automation.dominic.idea_engine import extract_ideas_from_article, deduplicate_ideas
        from automation.dominic.tweet_gen import generate_tweet
        from automation.dominic.compliance import audit_content

        ideas = extract_ideas_from_article(article)
        ideas = deduplicate_ideas(ideas)
        cfg = get_config()

        for idea in ideas[:3]:
            if idea.get("platform") in ("twitter", "both"):
                tweet = generate_tweet(idea)
                tweet_idea = {**idea, "body": tweet, "platform": "twitter"}
                audit = audit_content(tweet_idea)
                if audit.get("score", 0) >= cfg.confidence_threshold:
                    save_content(
                        headline=idea.get("headline", ""),
                        body=tweet,
                        content_type=idea.get("content_type", "educational"),
                        platform="twitter",
                        confidence=audit["score"],
                        url=article.get("url", ""),
                        source_title=article.get("title", ""),
                        status="queued",
                    )
        log_action("handle_new_article", "brain", "ok", article.get("title", "")[:60])
    except Exception as e:
        log_error("brain", str(e), f"handle_new_article: {article.get('title','?')}")


def run_approval_cycle() -> None:
    """
    In approval mode: send all pending drafts to Telegram for review.
    """
    if not _check_active():
        return

    mode = get_current_mode()
    if mode != "approval":
        log_action("approval_cycle", "brain", "skipped", "Not in approval mode")
        return

    try:
        from automation.dominic.telegram_notifier import notify_awaiting_approval
        drafts = get_draft_content(limit=10)
        sent = 0
        for draft in drafts:
            if draft.get("telegram_notified") == 0:
                notify_awaiting_approval(
                    draft.get("platform", "twitter"),
                    draft,
                    draft["id"]
                )
                # Mark notified
                from automation.dominic.db import get_dom_conn
                conn = get_dom_conn()
                conn.execute(
                    "UPDATE dom_content SET telegram_notified=1, status='awaiting_approval' WHERE id=?",
                    (draft["id"],)
                )
                conn.commit()
                conn.close()
                sent += 1
        log_action("approval_cycle", "brain", "ok", f"sent {sent} drafts for approval")
    except Exception as e:
        log_error("brain", str(e), "run_approval_cycle")
