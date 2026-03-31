#!/usr/bin/env python3
"""
AI Tools Empire — Daily Content Scheduler
Runs 3 article generations per day at 7 AM, 12 PM, and 5 PM.
Launch once and keep it running: nohup python3 scheduler.py &
"""

import time
import logging
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


def run_generation():
    """Run one batch of article generation."""
    try:
        from database.db import init_db
        from automation.content_generator import run_content_generation
        init_db()
        result = run_content_generation(count=3)
        log.info(f"Content generation complete: {result}")
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
