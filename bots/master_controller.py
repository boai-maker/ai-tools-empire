"""
Bot 1: Master Controller
Orchestrates all other bots and provides system health checks.
"""
import logging
from datetime import datetime

from bots.shared.db_helpers import (
    get_article_count,
    get_subscriber_count,
    log_bot_event,
    get_bot_events,
    get_bot_state,
    upsert_bot_state,
)

logger = logging.getLogger(__name__)

BOT_NAME = "master_controller"


def run_health_check() -> dict:
    """
    Checks when each bot last ran by reading bot_state.
    Returns a status dict with last_run timestamps for each bot.
    """
    bots = [
        "website_monitor",
        "content_extractor",
        "youtube_bot",
        "blog_seo_bot",
        "lead_capture_bot",
        "email_marketing_bot",
        "affiliate_revenue_bot",
        "support_bot",
        "analytics_bot",
        "competitor_bot",
        "offer_optimizer_bot",
        "reputation_bot",
        "admin_notification_bot",
    ]

    status = {}
    for bot in bots:
        last_run = get_bot_state(bot, "last_run", default="never")
        status[bot] = {"last_run": last_run}

    log_bot_event(BOT_NAME, "health_check", f"Health check completed for {len(bots)} bots")
    return status


def run_daily_cycle() -> None:
    """
    Runs the core daily revenue-generating bots in sequence.
    Errors in one bot do not stop others.
    """
    logger.info("Master Controller: starting daily cycle")
    log_bot_event(BOT_NAME, "daily_cycle_start", "Daily cycle initiated")

    # Import here to avoid circular imports at module load
    from bots.blog_seo_bot import run_blog_seo_bot
    from bots.affiliate_revenue_bot import run_affiliate_revenue_bot
    from bots.analytics_bot import run_analytics_bot

    cycle_results = {}

    try:
        logger.info("Daily cycle: running blog_seo_bot")
        result = run_blog_seo_bot()
        cycle_results["blog_seo_bot"] = result
        logger.info(f"blog_seo_bot result: {result}")
    except Exception as e:
        logger.error(f"Daily cycle — blog_seo_bot failed: {e}")
        cycle_results["blog_seo_bot"] = {"error": str(e)}

    try:
        logger.info("Daily cycle: running affiliate_revenue_bot")
        result = run_affiliate_revenue_bot()
        cycle_results["affiliate_revenue_bot"] = result
        logger.info(f"affiliate_revenue_bot result: {result}")
    except Exception as e:
        logger.error(f"Daily cycle — affiliate_revenue_bot failed: {e}")
        cycle_results["affiliate_revenue_bot"] = {"error": str(e)}

    try:
        logger.info("Daily cycle: running analytics_bot")
        result = run_analytics_bot()
        cycle_results["analytics_bot"] = result
        logger.info(f"analytics_bot result: {result}")
    except Exception as e:
        logger.error(f"Daily cycle — analytics_bot failed: {e}")
        cycle_results["analytics_bot"] = {"error": str(e)}

    log_bot_event(BOT_NAME, "daily_cycle_complete", str(cycle_results))
    upsert_bot_state(BOT_NAME, "last_daily_cycle", datetime.utcnow().isoformat())
    logger.info("Master Controller: daily cycle complete")


def run_hourly_cycle() -> None:
    """
    Runs lightweight bots that should check frequently.
    """
    logger.info("Master Controller: starting hourly cycle")

    from bots.website_monitor import run_website_monitor
    from bots.lead_capture_bot import run_lead_capture_bot

    try:
        run_website_monitor()
    except Exception as e:
        logger.error(f"Hourly cycle — website_monitor failed: {e}")

    try:
        run_lead_capture_bot()
    except Exception as e:
        logger.error(f"Hourly cycle — lead_capture_bot failed: {e}")

    upsert_bot_state(BOT_NAME, "last_hourly_cycle", datetime.utcnow().isoformat())
    logger.info("Master Controller: hourly cycle complete")


def run_weekly_cycle() -> None:
    """
    Runs strategic research and optimization bots weekly.
    """
    logger.info("Master Controller: starting weekly cycle")
    log_bot_event(BOT_NAME, "weekly_cycle_start", "Weekly cycle initiated")

    from bots.competitor_bot import run_competitor_bot
    from bots.offer_optimizer_bot import run_offer_optimizer_bot
    from bots.reputation_bot import run_reputation_bot
    from bots.email_marketing_bot import run_email_marketing_bot

    cycle_results = {}

    for bot_name, bot_fn in [
        ("competitor_bot", run_competitor_bot),
        ("offer_optimizer_bot", run_offer_optimizer_bot),
        ("reputation_bot", run_reputation_bot),
        ("email_marketing_bot", run_email_marketing_bot),
    ]:
        try:
            logger.info(f"Weekly cycle: running {bot_name}")
            result = bot_fn()
            cycle_results[bot_name] = result
        except Exception as e:
            logger.error(f"Weekly cycle — {bot_name} failed: {e}")
            cycle_results[bot_name] = {"error": str(e)}

    log_bot_event(BOT_NAME, "weekly_cycle_complete", str(cycle_results))
    upsert_bot_state(BOT_NAME, "last_weekly_cycle", datetime.utcnow().isoformat())
    logger.info("Master Controller: weekly cycle complete")


def get_system_status() -> dict:
    """
    Returns full system status snapshot.
    """
    try:
        article_count = get_article_count()
        subscriber_count = get_subscriber_count()
        recent_events = get_bot_events(limit=20)
        health = run_health_check()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "article_count": article_count,
            "subscriber_count": subscriber_count,
            "bot_health": health,
            "recent_events": recent_events,
            "status": "operational",
        }
    except Exception as e:
        logger.error(f"get_system_status error: {e}")
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "status": "error",
            "error": str(e),
        }
