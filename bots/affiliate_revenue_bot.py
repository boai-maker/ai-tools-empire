"""
Bot 8: Affiliate Revenue Tracking Bot
Tracks and optimizes affiliate revenue.
"""
import logging
from datetime import datetime, timedelta

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import (
    log_bot_event,
    upsert_bot_state,
    get_affiliate_click_totals,
    get_today_views,
)
from database.db import get_conn
from config import config

logger = logging.getLogger(__name__)

BOT_NAME = "affiliate_revenue_bot"

# Affiliate signup URLs
AFFILIATE_URLS = {
    "jasper": "https://www.jasper.ai/free-trial",
    "copyai": "https://www.copy.ai/",
    "elevenlabs": "https://try.elevenlabs.io/i3pg30ciu5n8",
    "fireflies": "https://fireflies.ai/?ref=kenneth39",
    "pictory": "https://pictory.ai?ref=kenneth46",
    "semrush": "https://www.semrush.com/",
    "surfer": "https://surferseo.com/",
    "writesonic": "https://writesonic.com/",
    "canva": "https://www.canva.com/",
    "grammarly": "https://www.grammarly.com/",
    "invideo": "https://invideo.io/",
    "murf": "https://murf.ai/",
    "descript": "https://www.descript.com/",
    "speechify": "https://speechify.com/",
    "getresponse": "https://www.getresponse.com/",
    "hubspot": "https://www.hubspot.com/",
    "quillbot": "https://quillbot.com/",
    "kit": "https://kit.com/",
    "webflow": "https://webflow.com/",
    "synthesia": "https://www.synthesia.io/",
    "runway": "https://runwayml.com/",
}

AVG_REVENUE_PER_CLICK = 2.0  # $2 average estimated revenue per click


def get_top_performing_tools(limit: int = 5) -> list:
    """
    Returns top tools by click count with estimated revenue.
    """
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT tool_key, COUNT(*) as clicks
            FROM affiliate_clicks
            GROUP BY tool_key
            ORDER BY clicks DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

        return [
            {
                "tool_key": r["tool_key"],
                "clicks": r["clicks"],
                "estimated_revenue": round(r["clicks"] * AVG_REVENUE_PER_CLICK, 2),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"get_top_performing_tools error: {e}")
        return []


def get_click_trends() -> dict:
    """
    Returns affiliate clicks by day for the last 7 days.
    """
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT DATE(clicked_at) as day, COUNT(*) as clicks
            FROM affiliate_clicks
            WHERE clicked_at >= DATE('now', '-7 days')
            GROUP BY DATE(clicked_at)
            ORDER BY day ASC
        """).fetchall()
        conn.close()

        return {r["day"]: r["clicks"] for r in rows}
    except Exception as e:
        logger.error(f"get_click_trends error: {e}")
        return {}


def generate_optimization_recommendations() -> str:
    """
    Uses Claude to analyze click data and suggest promotion strategies.
    """
    top_tools = get_top_performing_tools(limit=10)
    trends = get_click_trends()
    totals = get_affiliate_click_totals()

    if not totals:
        return "No affiliate click data available yet. Start by publishing articles with affiliate links."

    tools_summary = "\n".join([
        f"- {t['tool_key']}: {t['clicks']} clicks (~${t['estimated_revenue']} revenue)"
        for t in top_tools
    ]) if top_tools else "No top tools data"

    trends_summary = "\n".join([
        f"- {day}: {clicks} clicks"
        for day, clicks in list(trends.items())[-7:]
    ]) if trends else "No trend data"

    prompt = f"""Analyze this affiliate click data for AI Tools Empire and provide 5 specific optimization recommendations:

Top performing tools:
{tools_summary}

7-day click trends:
{trends_summary}

Total clicks by tool:
{', '.join([f"{k}: {v}" for k, v in list(totals.items())[:10]])}

Provide 5 actionable recommendations to increase affiliate revenue:
1. Which tools to feature more prominently
2. Content opportunities based on what's performing
3. Placement/CTA optimization ideas
4. New tools to add to the site
5. Seasonal or trending opportunities

Be specific and practical."""

    return ask_claude(prompt, max_tokens=1000)


def inject_affiliate_links_in_content(content: str) -> str:
    """
    Replaces [AFFILIATE:tool_name] placeholders with real affiliate URLs.
    """
    import re

    def replace_match(m):
        tool_name = m.group(1).lower().strip()
        url = AFFILIATE_URLS.get(tool_name)
        if url:
            return url
        # Try partial match
        for key, val in AFFILIATE_URLS.items():
            if tool_name in key or key in tool_name:
                return val
        # Default to site URL
        return f"{config.SITE_URL}/tools"

    pattern = r"\[AFFILIATE:([^\]]+)\]"
    return re.sub(pattern, replace_match, content)


def run_affiliate_revenue_bot() -> dict:
    """
    Generates daily affiliate report, logs to bot_events.
    Returns {top_tool, total_clicks_today, estimated_daily_revenue}.
    """
    logger.info("Affiliate Revenue Bot: starting run")

    result = {
        "top_tool": "none",
        "total_clicks_today": 0,
        "estimated_daily_revenue": 0.0,
    }

    try:
        # Today's clicks
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        conn = get_conn()
        today_clicks = conn.execute("""
            SELECT COUNT(*) as cnt FROM affiliate_clicks
            WHERE DATE(clicked_at) = ?
        """, (today_str,)).fetchone()["cnt"]

        top_today = conn.execute("""
            SELECT tool_key, COUNT(*) as cnt FROM affiliate_clicks
            WHERE DATE(clicked_at) = ?
            GROUP BY tool_key ORDER BY cnt DESC LIMIT 1
        """, (today_str,)).fetchone()
        conn.close()

        result["total_clicks_today"] = today_clicks
        result["estimated_daily_revenue"] = round(today_clicks * AVG_REVENUE_PER_CLICK, 2)

        if top_today:
            result["top_tool"] = top_today["tool_key"]

        # Get recommendations
        recommendations = generate_optimization_recommendations()

        # Build report summary
        top_tools = get_top_performing_tools(limit=5)
        top_tools_text = ", ".join([f"{t['tool_key']} ({t['clicks']})" for t in top_tools]) if top_tools else "none"

        report_details = (
            f"Today: {today_clicks} clicks, ~${result['estimated_daily_revenue']} revenue. "
            f"Top tool today: {result['top_tool']}. "
            f"All-time top tools: {top_tools_text}"
        )

        log_bot_event(BOT_NAME, "daily_report", report_details)

        if recommendations:
            upsert_bot_state(BOT_NAME, "latest_recommendations", recommendations[:500])

        logger.info(f"Affiliate Revenue Bot: {today_clicks} clicks today, ${result['estimated_daily_revenue']} est. revenue")

    except Exception as e:
        logger.error(f"Affiliate Revenue Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
