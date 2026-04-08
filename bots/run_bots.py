"""
Main entry point for the AI Tools Empire autonomous bot system.
Uses APScheduler to run all bots on their configured schedules.
"""
import logging
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from database.db import init_db

# Import all bot run functions
from bots.website_monitor import run_website_monitor
from bots.content_extractor import run_content_extractor
from bots.youtube_bot import run_youtube_bot
from bots.blog_seo_bot import run_blog_seo_bot
from bots.lead_capture_bot import run_lead_capture_bot, send_welcome_if_needed
from bots.email_marketing_bot import run_email_marketing_bot
from bots.affiliate_revenue_bot import run_affiliate_revenue_bot
from bots.support_bot import run_support_bot
from bots.analytics_bot import run_analytics_bot
from bots.competitor_bot import run_competitor_bot
from bots.offer_optimizer_bot import run_offer_optimizer_bot
from bots.reputation_bot import run_reputation_bot
from bots.admin_notification_bot import run_admin_notification_bot
from bots.master_controller import run_health_check
from bots.affiliate_gmail_monitor import run_affiliate_gmail_monitor
from bots.youtube_shorts_bot import run_youtube_shorts_bot
from bots.fiverr_responder import run_fiverr_responder
from bots.linkedin_monitor import run_linkedin_monitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bots.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger("run_bots")


def _safe_run(fn, name: str):
    """Wraps a bot function in try/except so one failure doesn't crash the scheduler."""
    try:
        logger.info(f"Starting bot: {name}")
        result = fn()
        logger.info(f"Completed bot: {name} → {result}")
        return result
    except Exception as e:
        logger.error(f"Bot {name} FAILED: {e}", exc_info=True)
        return None


# Scheduler-compatible wrappers (no arguments allowed for APScheduler jobs)
def job_website_monitor():
    _safe_run(run_website_monitor, "website_monitor")

def job_lead_capture_welcome():
    _safe_run(send_welcome_if_needed, "lead_capture_welcome")

def job_content_extractor():
    _safe_run(run_content_extractor, "content_extractor")

def job_blog_seo_bot():
    _safe_run(run_blog_seo_bot, "blog_seo_bot")

def job_admin_morning_briefing():
    _safe_run(run_admin_notification_bot, "admin_notification_bot_morning")

def job_analytics_bot():
    _safe_run(run_analytics_bot, "analytics_bot")

def job_affiliate_revenue_bot():
    _safe_run(run_affiliate_revenue_bot, "affiliate_revenue_bot")

def job_youtube_bot():
    _safe_run(run_youtube_bot, "youtube_bot")

def job_email_sequence_only():
    """Runs only the sequence queue (not full newsletter)."""
    from bots.email_marketing_bot import process_sequence_queue
    _safe_run(process_sequence_queue, "email_sequence_queue")

def job_email_marketing_full():
    """Monday full newsletter run."""
    _safe_run(run_email_marketing_bot, "email_marketing_bot_full")

def job_competitor_bot():
    _safe_run(run_competitor_bot, "competitor_bot")

def job_offer_optimizer_bot():
    _safe_run(run_offer_optimizer_bot, "offer_optimizer_bot")

def job_reputation_bot():
    _safe_run(run_reputation_bot, "reputation_bot")

def job_affiliate_gmail_monitor():
    _safe_run(run_affiliate_gmail_monitor, "affiliate_gmail_monitor")

def job_youtube_shorts():
    _safe_run(run_youtube_shorts_bot, "youtube_shorts_bot")

def job_fiverr_responder():
    _safe_run(run_fiverr_responder, "fiverr_responder")

def job_linkedin_monitor():
    _safe_run(run_linkedin_monitor, "linkedin_monitor")


def on_job_error(event):
    """APScheduler error event listener."""
    logger.error(
        f"Job {event.job_id} raised an exception: {event.exception}",
        exc_info=(type(event.exception), event.exception, event.traceback),
    )


def on_job_executed(event):
    """APScheduler execution event listener."""
    logger.debug(f"Job {event.job_id} executed successfully")


def run_all_now():
    """
    Runs all bots once immediately, in logical order.
    Useful for initial setup and testing.
    """
    print("\n=== Running all bots NOW (test mode) ===\n")

    bots = [
        (run_website_monitor, "website_monitor"),
        (run_content_extractor, "content_extractor"),
        (run_blog_seo_bot, "blog_seo_bot"),
        (run_lead_capture_bot, "lead_capture_bot"),
        (run_affiliate_revenue_bot, "affiliate_revenue_bot"),
        (run_analytics_bot, "analytics_bot"),
        (run_youtube_bot, "youtube_bot"),
        (run_support_bot, "support_bot"),
        (run_competitor_bot, "competitor_bot"),
        (run_offer_optimizer_bot, "offer_optimizer_bot"),
        (run_reputation_bot, "reputation_bot"),
        (run_email_marketing_bot, "email_marketing_bot"),
        (run_admin_notification_bot, "admin_notification_bot"),
    ]

    results = {}
    for fn, name in bots:
        print(f"  Running {name}...")
        result = _safe_run(fn, name)
        results[name] = result
        print(f"  {name}: {result}\n")

    print("=== All bots complete ===\n")
    return results


if __name__ == "__main__":
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)

    print("=" * 60)
    print("  AI Tools Empire — Autonomous Bot System")
    print("  Starting up...")
    print("=" * 60)

    # Initialize database
    print("\n[1/3] Initializing database...")
    init_db()
    print("      Database ready.")

    # Run health check
    print("\n[2/3] Running health check...")
    try:
        health = run_health_check()
        for bot_name, status in health.items():
            last = status.get("last_run", "never")
            print(f"      {bot_name}: last run = {last}")
    except Exception as e:
        print(f"      Health check error: {e}")

    # Check for --run-all flag (runs everything immediately and exits)
    if "--run-all" in sys.argv:
        print("\n[--run-all] Running all bots immediately...")
        run_all_now()
        print("Done.")
        sys.exit(0)

    # Initialize APScheduler
    print("\n[3/3] Starting scheduler...")
    scheduler = BlockingScheduler(timezone="America/New_York")

    # Add event listeners
    scheduler.add_listener(on_job_error, EVENT_JOB_ERROR)
    scheduler.add_listener(on_job_executed, EVENT_JOB_EXECUTED)

    # --- Schedule all bots ---

    # Every 30 minutes: website monitor
    scheduler.add_job(
        job_website_monitor,
        "interval",
        minutes=30,
        id="website_monitor",
        name="Website Monitor",
        max_instances=1,
        misfire_grace_time=300,
    )

    # Every 2 hours: welcome emails for new subscribers
    scheduler.add_job(
        job_lead_capture_welcome,
        "interval",
        hours=2,
        id="lead_capture_welcome",
        name="Lead Capture Welcome",
        max_instances=1,
        misfire_grace_time=600,
    )

    # Daily at 6:00 AM ET: content extractor
    scheduler.add_job(
        job_content_extractor,
        "cron",
        hour=6,
        minute=0,
        id="content_extractor",
        name="Content Extractor",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Daily at 6:30 AM ET: blog SEO bot (after content extractor fills queue)
    scheduler.add_job(
        job_blog_seo_bot,
        "cron",
        hour=6,
        minute=30,
        id="blog_seo_bot",
        name="Blog SEO Bot",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Daily at 7:00 AM ET: admin morning briefing
    scheduler.add_job(
        job_admin_morning_briefing,
        "cron",
        hour=7,
        minute=0,
        id="admin_morning_briefing",
        name="Admin Morning Briefing",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Daily at 8:00 AM ET: analytics bot
    scheduler.add_job(
        job_analytics_bot,
        "cron",
        hour=8,
        minute=0,
        id="analytics_bot",
        name="Analytics Bot",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Daily at 10:00 AM ET: affiliate revenue bot
    scheduler.add_job(
        job_affiliate_revenue_bot,
        "cron",
        hour=10,
        minute=0,
        id="affiliate_revenue_bot",
        name="Affiliate Revenue Bot",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Daily at 12:00 PM ET: YouTube bot
    scheduler.add_job(
        job_youtube_bot,
        "cron",
        hour=12,
        minute=0,
        id="youtube_bot",
        name="YouTube Bot",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Daily at 3:00 PM ET: email sequence queue only
    scheduler.add_job(
        job_email_sequence_only,
        "cron",
        hour=15,
        minute=0,
        id="email_sequence_daily",
        name="Email Sequence Queue",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Monday at 9:00 AM ET: full newsletter + sequences
    scheduler.add_job(
        job_email_marketing_full,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        id="email_marketing_newsletter",
        name="Email Marketing Newsletter",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Weekly Sunday at 6:00 AM ET: competitor research
    scheduler.add_job(
        job_competitor_bot,
        "cron",
        day_of_week="sun",
        hour=6,
        minute=0,
        id="competitor_bot",
        name="Competitor Bot",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Weekly Sunday at 6:30 AM ET: offer optimizer
    scheduler.add_job(
        job_offer_optimizer_bot,
        "cron",
        day_of_week="sun",
        hour=6,
        minute=30,
        id="offer_optimizer_bot",
        name="Offer Optimizer Bot",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Weekly Sunday at 7:00 AM ET: reputation bot
    scheduler.add_job(
        job_reputation_bot,
        "cron",
        day_of_week="sun",
        hour=7,
        minute=0,
        id="reputation_bot",
        name="Reputation Bot",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Every 2 hours: affiliate Gmail monitor (checks for approval emails)
    scheduler.add_job(
        job_affiliate_gmail_monitor,
        "interval",
        hours=2,
        id="affiliate_gmail_monitor",
        name="Affiliate Gmail Monitor",
        max_instances=1,
        misfire_grace_time=600,
    )

    # Daily 10:00 AM ET: YouTube Short #1
    scheduler.add_job(
        job_youtube_shorts,
        "cron",
        hour=10,
        minute=0,
        id="youtube_shorts_am",
        name="YouTube Shorts AM",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Every hour 8AM-10PM ET: Fiverr Message Check (fast response = higher ranking)
    scheduler.add_job(
        job_fiverr_responder,
        "cron",
        hour="8-22",
        minute=15,
        id="fiverr_responder_hourly",
        name="Fiverr Responder (Hourly)",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Every hour 8AM-11PM ET: LinkedIn Message Monitor
    scheduler.add_job(
        job_linkedin_monitor,
        "cron",
        hour="8-23",
        minute=30,
        id="linkedin_monitor_hourly",
        name="LinkedIn Monitor (Hourly)",
        max_instances=1,
        misfire_grace_time=1800,
    )

    # Daily 4:00 PM ET: YouTube Short #2
    scheduler.add_job(
        job_youtube_shorts,
        "cron",
        hour=16,
        minute=0,
        id="youtube_shorts_pm",
        name="YouTube Shorts PM",
        max_instances=1,
        misfire_grace_time=1800,
    )

    print("\n  Scheduled jobs:")
    for job in scheduler.get_jobs():
        next_run = getattr(job, "next_run_time", "starts on scheduler launch")
        print(f"    [{job.id}] — next run: {next_run}")

    print(f"\n  Timezone: America/New_York")
    print("  Scheduler running. Press Ctrl+C to stop.\n")
    print("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped by user.")
        scheduler.shutdown(wait=False)
        print("Goodbye.")
