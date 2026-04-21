"""
Dominic entry point.
Sets up APScheduler and runs all routines on schedule.

Usage:
  python -m automation.dominic.run              # Start scheduler
  python -m automation.dominic.run --once       # Run one full cycle now
  python -m automation.dominic.run --crawl      # Crawl site now
  python -m automation.dominic.run --status     # Print status and exit
  python -m automation.dominic.run --morning    # Run morning routine now
"""
import sys
import os
import signal
import argparse
import logging
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Startup: initialize DB, logging
# ---------------------------------------------------------------------------

def _init():
    """Initialize Dominic systems."""
    try:
        from automation.dominic.db import init_dominic_db
        init_dominic_db()
    except Exception as e:
        print(f"[Dominic] DB init error: {e}")


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def _get_scheduler():
    """Build and return configured APScheduler BlockingScheduler."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print("[Dominic] ERROR: apscheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    from automation.dominic.config import get_config
    cfg = get_config()
    tz = cfg.timezone

    scheduler = BlockingScheduler(
        timezone=tz,
        job_defaults={
            "misfire_grace_time": 3600,
            "coalesce": True,
            "max_instances": 1,
        },
    )

    # --- Daily 8:00 AM: Morning routine ---
    scheduler.add_job(
        _safe_morning_routine,
        trigger=CronTrigger(hour=8, minute=0, timezone=tz),
        id="morning_routine",
        name="Morning Routine",
        replace_existing=True,
        max_instances=1,
    )

    # --- Daily 9:00 AM: Posting routine (Twitter) ---
    scheduler.add_job(
        _safe_posting_routine,
        trigger=CronTrigger(hour=9, minute=0, timezone=tz),
        id="posting_9am",
        name="Posting 9 AM",
        replace_existing=True,
        max_instances=1,
    )

    # --- Daily 12:00 PM: Posting routine (YouTube) ---
    scheduler.add_job(
        _safe_posting_routine,
        trigger=CronTrigger(hour=12, minute=0, timezone=tz),
        id="posting_noon",
        name="Posting Noon",
        replace_existing=True,
        max_instances=1,
    )

    # --- Daily 6:00 PM: Posting routine (Twitter) ---
    scheduler.add_job(
        _safe_posting_routine,
        trigger=CronTrigger(hour=18, minute=0, timezone=tz),
        id="posting_6pm",
        name="Posting 6 PM",
        replace_existing=True,
        max_instances=1,
    )

    # --- Daily 8:00 PM: Evening routine ---
    scheduler.add_job(
        _safe_evening_routine,
        trigger=CronTrigger(hour=20, minute=0, timezone=tz),
        id="evening_routine",
        name="Evening Routine",
        replace_existing=True,
        max_instances=1,
    )

    # --- Monday 9:00 AM: Weekly routine ---
    scheduler.add_job(
        _safe_weekly_routine,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=tz),
        id="weekly_routine",
        name="Weekly Routine",
        replace_existing=True,
        max_instances=1,
    )

    # --- Every 4 hours: Content crawl check ---
    scheduler.add_job(
        _safe_crawl_check,
        trigger=CronTrigger(hour="*/4", minute=30, timezone=tz),
        id="crawl_check",
        name="Crawl Check (4h)",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler


# ---------------------------------------------------------------------------
# Safe wrappers (catch all exceptions so scheduler never crashes)
# ---------------------------------------------------------------------------

def _safe_morning_routine():
    try:
        from automation.dominic.brain import morning_routine
        morning_routine()
    except Exception as e:
        _log_runtime_error("morning_routine", e)


def _safe_posting_routine():
    try:
        from automation.dominic.brain import posting_routine
        posting_routine()
    except Exception as e:
        _log_runtime_error("posting_routine", e)


def _safe_evening_routine():
    try:
        from automation.dominic.brain import evening_routine
        evening_routine()
    except Exception as e:
        _log_runtime_error("evening_routine", e)


def _safe_weekly_routine():
    try:
        from automation.dominic.brain import weekly_routine
        weekly_routine()
    except Exception as e:
        _log_runtime_error("weekly_routine", e)


def _safe_crawl_check():
    """Crawl for new content and generate ideas if paused=False."""
    try:
        from automation.dominic.admin import is_paused
        if is_paused():
            return
        from automation.dominic.crawler import run_crawl
        from automation.dominic.idea_engine import batch_extract_ideas, deduplicate_ideas
        from automation.dominic.tweet_gen import generate_tweet
        from automation.dominic.compliance import audit_content
        from automation.dominic.db import save_content
        from automation.dominic.config import get_config

        new_articles = run_crawl()
        if not new_articles:
            return

        cfg = get_config()
        ideas = batch_extract_ideas(new_articles, max_ideas=2)
        ideas = deduplicate_ideas(ideas)

        for idea in ideas[:5]:
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
                        url=idea.get("url", ""),
                        source_title=idea.get("source_title", ""),
                        status="queued",
                    )
    except Exception as e:
        _log_runtime_error("crawl_check", e)


def _log_runtime_error(routine: str, error: Exception):
    """Log a runtime error from a scheduled routine."""
    try:
        from automation.dominic.logger import log_error
        log_error("run", str(error), f"scheduled job: {routine}")
    except Exception:
        print(f"[Dominic] ERROR in {routine}: {error}")


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

_scheduler_ref = None


def _shutdown_handler(signum, frame):
    """Graceful shutdown on SIGINT/SIGTERM."""
    print("\n[Dominic] Shutting down gracefully...")
    try:
        from automation.dominic.telegram_notifier import send_message
        send_message("🛑 <b>Dominic is going offline.</b> Graceful shutdown.")
    except Exception:
        pass
    if _scheduler_ref:
        try:
            _scheduler_ref.shutdown(wait=False)
        except Exception:
            pass
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global _scheduler_ref

    parser = argparse.ArgumentParser(
        description="Dominic — Autonomous Social Media Bot for AI Tools Empire"
    )
    parser.add_argument("--once", action="store_true",
                        help="Run one full Dominic cycle and exit")
    parser.add_argument("--crawl", action="store_true",
                        help="Crawl site for new content and exit")
    parser.add_argument("--status", action="store_true",
                        help="Print Dominic status and exit")
    parser.add_argument("--morning", action="store_true",
                        help="Run morning routine now and exit")
    parser.add_argument("--posting", action="store_true",
                        help="Run posting routine now and exit")
    parser.add_argument("--evening", action="store_true",
                        help="Run evening routine now and exit")

    args = parser.parse_args()

    # Always initialize DB first
    _init()

    if args.status:
        from automation.dominic.admin import get_status, get_queue_summary
        s = get_status()
        counts = s.get("content_counts", {})
        print(f"\nDominic Status Report — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  State:  {'PAUSED' if s['paused'] else 'RUNNING'}")
        print(f"  Mode:   {s['mode']}")
        print(f"  Draft:  {counts.get('draft', 0)}")
        print(f"  Queued: {counts.get('queued', 0)}")
        print(f"  Published: {counts.get('published', 0)}")
        print(f"  Failed: {counts.get('failed', 0)}")
        next_p = s.get("next_scheduled")
        if next_p:
            print(f"  Next post: {next_p.get('scheduled_for','?')[:16]} | {next_p.get('platform','?')}")
        print(f"  Last action: {s.get('last_action','N/A')[:80]}")
        sys.exit(0)

    if args.once:
        print("[Dominic] Running one full cycle...")
        from automation.dominic.brain import run_dominic_cycle
        result = run_dominic_cycle()
        print(f"[Dominic] Cycle complete: {result}")
        sys.exit(0)

    if args.crawl:
        print("[Dominic] Running site crawl...")
        from automation.dominic.crawler import run_crawl
        articles = run_crawl()
        print(f"[Dominic] Crawl complete. New articles: {len(articles)}")
        for a in articles[:10]:
            print(f"  - {a.get('title','?')[:70]}")
        sys.exit(0)

    if args.morning:
        print("[Dominic] Running morning routine...")
        from automation.dominic.brain import morning_routine
        morning_routine()
        print("[Dominic] Morning routine complete.")
        sys.exit(0)

    if args.posting:
        print("[Dominic] Running posting routine...")
        from automation.dominic.brain import posting_routine
        result = posting_routine()
        print(f"[Dominic] Posting routine complete: {result}")
        sys.exit(0)

    if args.evening:
        print("[Dominic] Running evening routine...")
        from automation.dominic.brain import evening_routine
        evening_routine()
        print("[Dominic] Evening routine complete.")
        sys.exit(0)

    # --- Start the scheduler ---
    print(f"[Dominic] Starting scheduler at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("[Dominic] Press Ctrl+C to stop gracefully.")

    # Register signal handlers
    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    # Startup Telegram notification
    try:
        from automation.dominic.telegram_notifier import send_message
        send_message(
            "🤖 <b>Dominic is online and ready.</b>\n"
            f"Mode: {__import__('automation.dominic.admin', fromlist=['get_current_mode']).get_current_mode().upper()}\n"
            f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            "aitoolsempire.co"
        )
    except Exception as e:
        print(f"[Dominic] Telegram startup notification failed: {e}")

    scheduler = _get_scheduler()
    _scheduler_ref = scheduler

    # Log scheduled jobs
    print(f"[Dominic] Scheduled jobs:")
    for job in scheduler.get_jobs():
        next_run = getattr(job, "next_run_time", None)
        print(f"  - {job.id}: next run {next_run}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[Dominic] Scheduler stopped.")


if __name__ == "__main__":
    main()
