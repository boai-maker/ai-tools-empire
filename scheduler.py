#!/usr/bin/env python3
"""
AI Tools Empire — Daily Content Scheduler
Runs 3 article generations per day at 7 AM, 12 PM, and 5 PM.
Launch once and keep it running: nohup python3 scheduler.py &
"""

import time
import logging
import urllib.request
import urllib.parse
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("/Users/kennethbonnet/ai-tools-empire/logs/scheduler.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("scheduler")

# Hours of day to generate articles (24h format)
GENERATION_HOURS = [7, 12, 17]  # 7 AM, 12 PM, 5 PM

_ran_this_hour = set()  # track which hours we've already fired today


SITE_URL = "https://aitoolsempire.co"
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"

PING_ENDPOINTS = [
    f"https://www.google.com/ping?sitemap={urllib.parse.quote(SITEMAP_URL)}",
    f"https://www.bing.com/ping?sitemap={urllib.parse.quote(SITEMAP_URL)}",
]


def ping_search_engines():
    """Notify Google and Bing of updated sitemap."""
    for url in PING_ENDPOINTS:
        try:
            urllib.request.urlopen(url, timeout=10)
            log.info(f"Sitemap ping OK: {url[:60]}")
        except Exception as e:
            log.warning(f"Sitemap ping failed: {e}")


def run_generation():
    """Run one batch of article generation."""
    try:
        from database.db import init_db
        from automation.content_generator import run_content_generation
        init_db()
        result = run_content_generation(count=3)
        log.info(f"Content generation complete: {result}")
        if result.get("generated", 0) > 0:
            ping_search_engines()
        return result
    except Exception as e:
        log.error(f"Content generation error: {e}")
        return {"generated": 0, "failed": 0}


def main():
    log.info("=== AI Tools Empire Scheduler started ===")
    log.info(f"Will generate articles at hours: {GENERATION_HOURS}")

    global _ran_this_hour
    last_day = datetime.now().day

    while True:
        now = datetime.now()
        hour = now.hour
        day = now.day

        # Reset hourly tracker on new day
        if day != last_day:
            _ran_this_hour = set()
            last_day = day
            log.info(f"New day ({now.strftime('%Y-%m-%d')}) — hourly tracker reset")

        # Fire if we're in a scheduled hour and haven't fired yet this hour
        if hour in GENERATION_HOURS and hour not in _ran_this_hour:
            log.info(f"Scheduled trigger at {now.strftime('%H:%M')} — starting content run")
            result = run_generation()
            _ran_this_hour.add(hour)
            log.info(f"Done: {result['generated']} articles generated, {result['failed']} failed")

        # Sleep 60 seconds between checks
        time.sleep(60)


if __name__ == "__main__":
    main()
