"""
Bot 10: Analytics Bot
Pulls and reports key site metrics.
"""
import logging
from datetime import datetime

from bots.shared.db_helpers import (
    log_bot_event,
    upsert_bot_state,
    get_article_count,
    get_subscriber_count,
    get_today_views,
    get_total_views,
    get_affiliate_click_totals,
)
from bots.shared.notifier import notify_admin
from database.db import get_conn

logger = logging.getLogger(__name__)

BOT_NAME = "analytics_bot"


def get_top_articles(limit: int = 5) -> list:
    """Returns top articles ordered by views."""
    try:
        conn = get_conn()
        rows = conn.execute("""
            SELECT id, slug, title, views, affiliate_clicks, created_at
            FROM articles
            WHERE status='published'
            ORDER BY views DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_top_articles error: {e}")
        return []


def get_full_analytics_report() -> dict:
    """
    Comprehensive analytics report combining all key metrics.
    """
    try:
        today_views = get_today_views()
        total_views = get_total_views()
        subscribers = get_subscriber_count()
        articles = get_article_count()
        click_totals = get_affiliate_click_totals()
        top_articles = get_top_articles(limit=5)

        # Total affiliate clicks
        total_clicks = sum(click_totals.values())

        # Top clicked tools (sorted)
        top_clicked_tools = sorted(
            [{"tool_key": k, "clicks": v} for k, v in click_totals.items()],
            key=lambda x: x["clicks"],
            reverse=True
        )[:5]

        # Conversion rate (clicks / views * 100)
        conversion_rate = round((total_clicks / total_views * 100), 2) if total_views > 0 else 0.0

        # Today's affiliate clicks
        conn = get_conn()
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        today_clicks = conn.execute(
            "SELECT COUNT(*) FROM affiliate_clicks WHERE DATE(clicked_at) = ?",
            (today_str,)
        ).fetchone()[0]
        conn.close()

        return {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "total_views": total_views,
            "today_views": today_views,
            "total_clicks": total_clicks,
            "today_clicks": today_clicks,
            "subscribers": subscribers,
            "articles": articles,
            "top_clicked_tools": top_clicked_tools,
            "top_articles": top_articles,
            "conversion_rate": conversion_rate,
            "estimated_revenue_today": round(today_clicks * 2.0, 2),
        }
    except Exception as e:
        logger.error(f"get_full_analytics_report error: {e}")
        return {
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "error": str(e),
        }


def format_daily_report(report: dict) -> str:
    """
    Formats analytics report as readable text for Telegram/email.
    """
    if "error" in report:
        return f"Analytics Report Error: {report['error']}"

    top_tools = report.get("top_clicked_tools", [])
    tools_text = ", ".join([f"{t['tool_key']} ({t['clicks']})" for t in top_tools]) if top_tools else "None"

    top_articles = report.get("top_articles", [])
    articles_text = ""
    for i, art in enumerate(top_articles[:3], 1):
        articles_text += f"\n  {i}. {art.get('title', 'Unknown')[:50]} ({art.get('views', 0)} views)"

    return f"""AI Tools Empire — Daily Analytics Report
Date: {report.get('date', 'N/A')}

TRAFFIC
  Today's views: {report.get('today_views', 0):,}
  Total views: {report.get('total_views', 0):,}

REVENUE
  Affiliate clicks today: {report.get('today_clicks', 0):,}
  Total affiliate clicks: {report.get('total_clicks', 0):,}
  Est. revenue today: ${report.get('estimated_revenue_today', 0):.2f}
  Conversion rate: {report.get('conversion_rate', 0):.2f}%

GROWTH
  Active subscribers: {report.get('subscribers', 0):,}
  Published articles: {report.get('articles', 0):,}

TOP TOOLS (all time): {tools_text}

TOP ARTICLES (by views):{articles_text if articles_text else " None yet"}"""


def run_analytics_bot() -> dict:
    """
    Generates daily report, sends morning briefing at 8am.
    Saves last_run. Returns the report dict.
    """
    logger.info("Analytics Bot: starting run")

    report = {}
    try:
        report = get_full_analytics_report()

        # Send morning report at 8am UTC
        current_hour = datetime.utcnow().hour
        if current_hour == 8:
            formatted = format_daily_report(report)
            notify_admin("Daily Analytics Report — AI Tools Empire", formatted)
            logger.info("Analytics Bot: morning report sent")

        log_bot_event(
            BOT_NAME,
            "report_generated",
            f"Views today: {report.get('today_views', 0)}, "
            f"Clicks today: {report.get('today_clicks', 0)}, "
            f"Subscribers: {report.get('subscribers', 0)}"
        )

    except Exception as e:
        logger.error(f"Analytics Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return report
