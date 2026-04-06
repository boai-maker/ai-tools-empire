"""
Bot 12: Offer / Funnel Optimization Bot
Optimizes offers and conversion funnels using analytics data.
"""
import logging
from datetime import datetime

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import (
    log_bot_event,
    upsert_bot_state,
    get_article_count,
    get_subscriber_count,
    get_today_views,
    get_total_views,
    get_affiliate_click_totals,
)
from database.db import get_conn

logger = logging.getLogger(__name__)

BOT_NAME = "offer_optimizer_bot"


def analyze_conversion_funnel() -> dict:
    """
    Analyzes views → clicks → subscribers conversion rates from DB.
    """
    try:
        total_views = get_total_views()
        total_clicks = sum(get_affiliate_click_totals().values())
        subscribers = get_subscriber_count()

        # View → Click conversion
        view_to_click = round((total_clicks / total_views * 100), 2) if total_views > 0 else 0.0

        # View → Subscriber conversion
        view_to_sub = round((subscribers / total_views * 100), 2) if total_views > 0 else 0.0

        # Click → (estimated) revenue
        estimated_revenue = total_clicks * 2.0

        # Articles performance
        conn = get_conn()
        avg_views = conn.execute(
            "SELECT AVG(views) FROM articles WHERE status='published'"
        ).fetchone()[0] or 0

        zero_view_articles = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE status='published' AND views=0"
        ).fetchone()[0]
        conn.close()

        return {
            "total_views": total_views,
            "total_clicks": total_clicks,
            "total_subscribers": subscribers,
            "view_to_click_rate": view_to_click,
            "view_to_subscriber_rate": view_to_sub,
            "estimated_total_revenue": round(estimated_revenue, 2),
            "avg_article_views": round(avg_views, 1),
            "zero_view_articles": zero_view_articles,
        }
    except Exception as e:
        logger.error(f"analyze_conversion_funnel error: {e}")
        return {}


def generate_ab_test_ideas() -> list:
    """
    Uses Claude to suggest 5 A/B test ideas for the site.
    Returns list of {element, variant_a, variant_b, hypothesis, expected_lift}.
    """
    funnel = analyze_conversion_funnel()

    prompt = f"""Generate 5 A/B test ideas for AI Tools Empire (aitoolsempire.co), an AI tool review site.

Current metrics:
- View to click rate: {funnel.get('view_to_click_rate', 0):.2f}%
- View to subscriber rate: {funnel.get('view_to_subscriber_rate', 0):.2f}%
- Articles with zero views: {funnel.get('zero_view_articles', 0)}

Suggest 5 A/B tests that could meaningfully improve conversions. Focus on:
- Newsletter signup CTAs (placement, copy, incentive)
- Affiliate link CTAs (button text, color, placement)
- Article headlines and meta descriptions
- Tool comparison tables vs. prose reviews
- Homepage layout and hero section

ELEMENT: [what to test]
VARIANT_A: [current/control version]
VARIANT_B: [challenger version]
HYPOTHESIS: [why B might outperform A]
EXPECTED_LIFT: [expected conversion lift e.g. "10-20%"]
---

List all 5 tests in this format."""

    response = ask_claude(prompt, max_tokens=1500)

    tests = []
    if not response:
        return tests

    blocks = response.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        test = {
            "element": "",
            "variant_a": "",
            "variant_b": "",
            "hypothesis": "",
            "expected_lift": "",
        }
        for line in block.split("\n"):
            stripped = line.strip()
            if stripped.startswith("ELEMENT:"):
                test["element"] = stripped[8:].strip()
            elif stripped.startswith("VARIANT_A:"):
                test["variant_a"] = stripped[10:].strip()
            elif stripped.startswith("VARIANT_B:"):
                test["variant_b"] = stripped[10:].strip()
            elif stripped.startswith("HYPOTHESIS:"):
                test["hypothesis"] = stripped[11:].strip()
            elif stripped.startswith("EXPECTED_LIFT:"):
                test["expected_lift"] = stripped[14:].strip()

        if test["element"]:
            tests.append(test)

    return tests[:5]


def generate_offer_recommendations() -> str:
    """
    Uses Claude to recommend promotional offers based on top-performing tools.
    """
    click_totals = get_affiliate_click_totals()

    top_tools = sorted(
        [{"tool": k, "clicks": v} for k, v in click_totals.items()],
        key=lambda x: x["clicks"],
        reverse=True
    )[:5]

    top_tools_text = "\n".join([
        f"- {t['tool']}: {t['clicks']} clicks"
        for t in top_tools
    ]) if top_tools else "No click data yet"

    funnel = analyze_conversion_funnel()

    prompt = f"""Generate promotional offer recommendations for AI Tools Empire based on this data:

Top performing affiliate tools:
{top_tools_text}

Funnel metrics:
- View to click: {funnel.get('view_to_click_rate', 0):.2f}%
- View to subscriber: {funnel.get('view_to_subscriber_rate', 0):.2f}%

Recommend:
1. Which tools to feature in a "Deals" page or email blast right now
2. Bundle offers or comparison articles that would drive more clicks
3. Seasonal promotional opportunities for AI tools
4. Lead magnet ideas that align with top-performing tools
5. Upsell/cross-sell sequences for existing subscribers

Be specific with copy suggestions and conversion tactics."""

    return ask_claude(prompt, max_tokens=1200)


def run_offer_optimizer_bot() -> dict:
    """
    Runs funnel analysis, generates A/B tests and recommendations.
    Logs to bot_events. Returns summary.
    """
    logger.info("Offer Optimizer Bot: starting run")

    result = {
        "funnel_analyzed": False,
        "ab_tests_generated": 0,
        "recommendations_generated": False,
    }

    try:
        funnel = analyze_conversion_funnel()
        result["funnel_analyzed"] = bool(funnel)

        if funnel:
            upsert_bot_state(BOT_NAME, "latest_funnel", str(funnel))

        ab_tests = generate_ab_test_ideas()
        result["ab_tests_generated"] = len(ab_tests)

        if ab_tests:
            tests_summary = "; ".join([t["element"][:40] for t in ab_tests])
            upsert_bot_state(BOT_NAME, "latest_ab_tests", tests_summary)

        recommendations = generate_offer_recommendations()
        result["recommendations_generated"] = bool(recommendations)

        if recommendations:
            upsert_bot_state(BOT_NAME, "latest_recommendations", recommendations[:600])

        log_bot_event(
            BOT_NAME,
            "optimization_run",
            f"Funnel: view→click {funnel.get('view_to_click_rate', 0):.2f}%, "
            f"view→sub {funnel.get('view_to_subscriber_rate', 0):.2f}%. "
            f"A/B tests: {len(ab_tests)}"
        )

    except Exception as e:
        logger.error(f"Offer Optimizer Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
