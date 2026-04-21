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

# Optional Telegram (used for the new daily revenue report)
try:
    from bots.shared.standards import tg as _tg
except Exception:
    _tg = None

# Optional affiliate metadata (for per-tool revenue estimates)
try:
    from affiliate.links import AFFILIATE_PROGRAMS as _AFF_PROGRAMS
except Exception:
    _AFF_PROGRAMS = {}

logger = logging.getLogger(__name__)

BOT_NAME = "analytics_bot"


def get_top_articles(limit: int = 5) -> list:
    """Top articles ordered by views.

    `affiliate_clicks` is computed as a live JOIN on the affiliate_clicks events
    table — the `articles.affiliate_clicks` counter column is never written and
    should be treated as deprecated. Fix landed 2026-04-21 (attribution bug).
    """
    try:
        conn = get_conn()
        # Fuzzy LIKE match covers: bare paths (/articles/{slug}), full URLs
        # (https://aitoolsempire.co/articles/{slug}?utm_source=…), and
        # http/https/www variants. 'direct' clicks (SMS, emails, no referrer)
        # don't get attributed — intentional.
        rows = conn.execute("""
            SELECT a.id, a.slug, a.title, a.views, a.created_at,
                   COUNT(ac.id) AS affiliate_clicks
            FROM articles a
            LEFT JOIN affiliate_clicks ac
                   ON ac.source_page LIKE '%/articles/' || a.slug || '%'
                   OR ac.source_page LIKE '%/blog/'     || a.slug || '%'
            WHERE a.status = 'published'
            GROUP BY a.id
            ORDER BY a.views DESC
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


def get_revenue_report() -> dict:
    """
    Daily revenue-focused report. Distinguishes earning affiliates from leakage.
    Returns structured dict ready for Telegram formatting.
    """
    conn = get_conn()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    # Today's clicks per tool
    per_tool_today = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT tool_key, COUNT(*) FROM affiliate_clicks WHERE DATE(clicked_at)=? GROUP BY tool_key",
            (today_str,),
        ).fetchall()
    }

    # 14-day click totals per tool
    per_tool_14d = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT tool_key, COUNT(*) FROM affiliate_clicks WHERE clicked_at > datetime('now','-14 days') GROUP BY tool_key"
        ).fetchall()
    }

    # Top articles by attributed clicks (fuzzy JOIN; uses fixed attribution logic)
    top_articles = conn.execute("""
        SELECT a.slug, a.title, a.views, COUNT(ac.id) AS clicks
        FROM articles a
        LEFT JOIN affiliate_clicks ac
               ON ac.source_page LIKE '%/articles/' || a.slug || '%'
               OR ac.source_page LIKE '%/blog/'     || a.slug || '%'
        WHERE a.status = 'published'
        GROUP BY a.id
        HAVING clicks > 0
        ORDER BY clicks DESC
        LIMIT 10
    """).fetchall()

    conn.close()

    # Split clicks into earning vs leaking buckets
    earning_clicks = 0
    leaking_clicks = 0
    earning_rev_est = 0.0
    per_tool_detail = []
    for tool, clicks in sorted(per_tool_14d.items(), key=lambda x: -x[1]):
        meta = _AFF_PROGRAMS.get(tool, {})
        is_active = meta.get("is_active", False)
        mec = meta.get("monthly_est_commission", 0) or 0
        if is_active:
            earning_clicks += clicks
            # Rough est: each click ~1% chance to convert, full month of commission if converted
            earning_rev_est += clicks * 0.01 * mec
        else:
            leaking_clicks += clicks
        per_tool_detail.append({
            "tool":      tool,
            "clicks_14d": clicks,
            "clicks_today": per_tool_today.get(tool, 0),
            "is_active": is_active,
            "monthly_est_commission": mec,
        })

    total_clicks_14d = earning_clicks + leaking_clicks

    return {
        "date":             today_str,
        "total_clicks_14d": total_clicks_14d,
        "today_clicks":     sum(per_tool_today.values()),
        "earning_clicks":   earning_clicks,
        "leaking_clicks":   leaking_clicks,
        "earning_pct":      round(earning_clicks / total_clicks_14d * 100, 1) if total_clicks_14d else 0.0,
        "earning_rev_est_monthly": round(earning_rev_est, 2),
        "per_tool":         per_tool_detail,
        "top_articles":     [{"slug": r[0], "title": r[1], "views": r[2], "clicks": r[3]} for r in top_articles],
    }


def format_revenue_report(r: dict) -> str:
    """Compact HTML-friendly Telegram message for the daily revenue report."""
    per_tool = r.get("per_tool", [])
    top_articles = r.get("top_articles", [])

    tools_lines = []
    for t in per_tool[:8]:
        mark = "💰" if t["is_active"] else "🕳️"
        tools_lines.append(f"{mark} <b>{t['tool']}</b>: {t['clicks_14d']} (14d) / {t['clicks_today']} today")

    articles_lines = []
    for i, a in enumerate(top_articles[:5], 1):
        articles_lines.append(f"{i}. {(a['title'] or '')[:50]} — <b>{a['clicks']}</b> clicks / {a['views']} views")

    return (
        f"<b>📊 AI Tools Empire — Revenue Report {r['date']}</b>\n\n"
        f"<b>Today:</b> {r['today_clicks']} affiliate clicks\n"
        f"<b>14-day:</b> {r['total_clicks_14d']} total clicks\n"
        f"  💰 Earning: {r['earning_clicks']} ({r['earning_pct']}%)\n"
        f"  🕳️ Leaking: {r['leaking_clicks']} (pending/manual/dead programs)\n\n"
        f"<b>Est. monthly from current earning pace:</b> ${r['earning_rev_est_monthly']:.2f}\n\n"
        f"<b>Per-tool (14d / today):</b>\n" + "\n".join(tools_lines) + "\n\n"
        f"<b>Top attributed articles:</b>\n" + "\n".join(articles_lines)
    )


def run_daily_revenue_report() -> dict:
    """Generate + send the daily revenue report to Telegram. Safe to call anytime."""
    logger.info("Daily revenue report: starting")
    try:
        report = get_revenue_report()
        msg = format_revenue_report(report)
        if _tg is not None:
            _tg(msg, level="info")
        logger.info(
            f"Revenue report: earning={report['earning_clicks']} "
            f"leaking={report['leaking_clicks']} earning_pct={report['earning_pct']}% "
            f"est_monthly=${report['earning_rev_est_monthly']:.2f}"
        )
        return report
    except Exception as e:
        logger.error(f"run_daily_revenue_report error: {e}")
        return {"error": str(e)}


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
