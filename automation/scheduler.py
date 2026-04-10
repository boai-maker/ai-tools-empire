"""
Master automation scheduler — the brain of the autonomous business.
Runs 24/7 and orchestrates all automated tasks.

Schedule:
  - 7:00 AM  → Generate 3 AI articles
  - 8:00 AM  → Post article tweet
  - 9:00 AM  → Send welcome emails to new subscribers
  - 12:00 PM → Post promo tweet
  - 4:00 PM  → Post article tweet
  - 6:00 PM  → Post promo tweet
  - Monday 9AM → Send weekly newsletter
"""
import sys
import os
# Ensure project root is on path so automation.* imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schedule
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/scheduler.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

def run_content_job():
    log.info("=== SCHEDULED: Content generation ===")
    try:
        from automation.content_generator import run_content_generation
        result = run_content_generation(count=3)
        log.info(f"Content job done: {result}")
    except Exception as e:
        log.error(f"Content job error: {e}")

def run_welcome_emails():
    log.info("=== SCHEDULED: Welcome emails ===")
    try:
        from automation.email_sender import send_welcome_to_pending
        sent = send_welcome_to_pending()
        log.info(f"Welcome emails sent: {sent}")
    except Exception as e:
        log.error(f"Welcome email error: {e}")

def run_newsletter():
    log.info("=== SCHEDULED: Weekly newsletter ===")
    try:
        from automation.email_sender import send_weekly_newsletter
        sent = send_weekly_newsletter()
        log.info(f"Newsletter sent to {sent} subscribers")
    except Exception as e:
        log.error(f"Newsletter error: {e}")

def run_article_tweet():
    log.info("=== SCHEDULED: Article tweet ===")
    try:
        from automation.social_poster import run_social_posting
        run_social_posting()
    except Exception as e:
        log.error(f"Article tweet error: {e}")

def run_promo_tweet():
    log.info("=== SCHEDULED: Promo tweet ===")
    try:
        from automation.social_poster import run_promo_tweet
        run_promo_tweet()
    except Exception as e:
        log.error(f"Promo tweet error: {e}")

def run_sequence_emails():
    log.info("=== SCHEDULED: Welcome sequence emails ===")
    try:
        from database.db import get_due_sequence_emails, mark_sequence_sent
        from automation.sequences.runner import send_sequence_email
        due = get_due_sequence_emails()
        sent = 0
        for item in due:
            ok = send_sequence_email(item["email"], item["name"] or "there", item["seq_num"])
            if ok:
                mark_sequence_sent(item["id"])
                sent += 1
                log.info(f"Sequence email {item['seq_num']} sent to {item['email']}")
            else:
                log.warning(f"Sequence email {item['seq_num']} failed for {item['email']}")
        log.info(f"Sequence emails sent: {sent}/{len(due)}")
    except Exception as e:
        log.error(f"Sequence email error: {e}")

def run_reddit_posting():
    log.info("=== SCHEDULED: Reddit posting ===")
    try:
        from automation.reddit_poster import run_reddit_posting as _post
        sent = _post(count=1)
        log.info(f"Reddit posts sent: {sent}")
    except Exception as e:
        log.error(f"Reddit posting error: {e}")

def run_youtube_community():
    log.info("=== SCHEDULED: YouTube community post ===")
    try:
        from automation.youtube_community import run_youtube_community_post
        sent = run_youtube_community_post()
        log.info(f"YouTube community posts sent: {sent}")
    except Exception as e:
        log.error(f"YouTube community error: {e}")

def run_cold_outreach():
    log.info("=== SCHEDULED: Cold outreach sequences ===")
    try:
        from automation.cold_outreach import run_outreach_sequences
        sent = run_outreach_sequences()
        log.info(f"Outreach emails sent: {sent}")
    except Exception as e:
        log.error(f"Cold outreach error: {e}")

def run_health_monitor():
    log.info("=== SCHEDULED: Health monitor ===")
    try:
        from analytics.monitor import run_full_monitor
        report = run_full_monitor()
        status = "✅ OK" if report["overall_ok"] else "❌ ISSUES"
        log.info(f"Health check: {status}")
    except Exception as e:
        log.error(f"Health monitor error: {e}")

def setup_schedule():
    # Content generation — 7 AM daily
    schedule.every().day.at("07:00").do(run_content_job)

    # Welcome emails — 9 AM daily
    schedule.every().day.at("09:00").do(run_welcome_emails)

    # Twitter/X — 2x/day (9 AM + 6 PM)
    schedule.every().day.at("09:00").do(run_article_tweet)
    schedule.every().day.at("18:00").do(run_promo_tweet)

    # Reddit — 2x/day (10 AM + 7 PM)
    schedule.every().day.at("10:00").do(run_reddit_posting)
    schedule.every().day.at("19:00").do(run_reddit_posting)

    # YouTube community — 1x/day (noon)
    schedule.every().day.at("12:00").do(run_youtube_community)

    # Weekly newsletter — Monday 9 AM
    schedule.every().monday.at("09:30").do(run_newsletter)

    # Cold outreach sequences — daily 10 AM
    schedule.every().day.at("10:00").do(run_cold_outreach)

    # Welcome sequence drip emails — every hour
    schedule.every().hour.do(run_sequence_emails)

    # Health monitoring — every hour
    schedule.every().hour.do(run_health_monitor)

    log.info("Scheduler configured:")
    for job in schedule.jobs:
        log.info(f"  {job}")

def run_scheduler():
    """Run the scheduler indefinitely."""
    log.info("=== AI Tools Empire Scheduler Starting ===")
    setup_schedule()

    # Run content generation immediately on first start
    log.info("Running initial content generation...")
    run_content_job()
    run_welcome_emails()

    log.info("Scheduler running. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    run_scheduler()
