"""
Surplus Funds Runner — master orchestrator.
Runs the full cycle: scrape → skip trace → outreach → follow up.
Called by the scheduler every 4 hours.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.standards import BotResult, get_logger, safe_run

log = get_logger("surplus_runner")


@safe_run("surplus_funds")
def run_surplus_funds() -> BotResult:
    """Full surplus funds cycle."""
    from bots.surplus_funds.scraper import run_scraper, init_db
    from bots.surplus_funds.pipeline import run_pipeline

    # Initialize DB if needed
    init_db()

    # Step 1: Scrape counties for new leads
    log.info("Step 1: Scraping counties...")
    scrape_result = run_scraper()

    # Step 2: Process leads through pipeline
    log.info("Step 2: Processing pipeline...")
    pipeline_result = run_pipeline()

    return BotResult(
        "surplus_funds",
        success=True,
        produced={
            "scraper": scrape_result,
            "pipeline": pipeline_result,
        },
    )


if __name__ == "__main__":
    result = run_surplus_funds()
    d = result.to_dict() if hasattr(result, "to_dict") else result
    import json
    print(json.dumps(d, indent=2))
