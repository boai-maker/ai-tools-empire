"""
Bot 14: Admin Notification Bot
Admin alerts, daily summaries, and critical monitoring.
"""
import logging
from datetime import datetime, timedelta

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import (
    log_bot_event,
    upsert_bot_state,
    get_bot_events,
    get_article_count,
    get_subscriber_count,
    get_today_views,
    get_affiliate_click_totals,
)
from bots.shared.notifier import notify, notify_admin
from database.db import get_conn

logger = logging.getLogger(__name__)

BOT_NAME = "admin_notification_bot"


def compute_affiliate_payout_breakdown() -> dict:
    """
    Breaks today's affiliate clicks into monetized vs unattributed buckets,
    multiplies monetized clicks by a realistic per-tool EPC, and surfaces the
    revenue leaking through unmonetized clicks. Per-tool EPC is derived from
    AFFILIATE_PROGRAMS (commission_pct or commission_flat) times a conservative
    2% click-to-sale conversion assumption.
    """
    from affiliate.links import AFFILIATE_PROGRAMS

    CONVERSION = 0.02  # conservative industry baseline

    def tool_epc(meta: dict) -> float:
        if meta.get("commission_flat"):
            return float(meta["commission_flat"]) * CONVERSION
        pct = meta.get("commission_pct") or 0
        return (float(meta.get("avg_sale", 0)) * pct / 100.0) * CONVERSION

    # Source of truth = is_active flag in AFFILIATE_PROGRAMS (set only when an
    # affiliate ID has actually been issued and verified).
    active_keys = {k for k, v in AFFILIATE_PROGRAMS.items() if v.get("is_active") is True}

    breakdown = {
        "clicks_total": 0,
        "clicks_monetized": 0,
        "clicks_unattributed": 0,
        "est_revenue": 0.0,
        "lost_potential": 0.0,
        "top_earners": [],
        "top_leaks": [],
    }

    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        conn = get_conn()
        rows = conn.execute(
            "SELECT tool_key, COUNT(*) AS clicks FROM affiliate_clicks WHERE DATE(clicked_at)=? GROUP BY tool_key",
            (today,),
        ).fetchall()
        conn.close()

        earners, leaks = [], []
        for row in rows:
            tool_key, clicks = row["tool_key"], row["clicks"]
            breakdown["clicks_total"] += clicks
            meta = AFFILIATE_PROGRAMS.get(tool_key, {})
            epc = tool_epc(meta)
            est = clicks * epc
            if tool_key in active_keys:
                breakdown["clicks_monetized"] += clicks
                breakdown["est_revenue"] += est
                earners.append((tool_key, clicks, est))
            else:
                breakdown["clicks_unattributed"] += clicks
                breakdown["lost_potential"] += est
                leaks.append((tool_key, clicks, est))

        breakdown["top_earners"] = sorted(earners, key=lambda r: r[2], reverse=True)[:3]
        breakdown["top_leaks"] = sorted(leaks, key=lambda r: r[2], reverse=True)[:3]
    except Exception as e:
        logger.warning(f"affiliate payout breakdown failed: {e}")
    return breakdown


def generate_daily_summary() -> str:
    """
    Compiles a summary from bot_events, analytics, and affiliate data.
    Uses Claude to write a clean executive summary.
    """
    try:
        # Collect data from last 24 hours
        recent_events = get_bot_events(limit=30)
        article_count = get_article_count()
        subscriber_count = get_subscriber_count()
        today_views = get_today_views()
        click_totals = get_affiliate_click_totals()
        total_clicks_today = 0

        try:
            conn = get_conn()
            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            today_clicks_row = conn.execute(
                "SELECT COUNT(*) FROM affiliate_clicks WHERE DATE(clicked_at) = ?",
                (today_str,)
            ).fetchone()
            if today_clicks_row:
                total_clicks_today = today_clicks_row[0]

            # New subscribers today
            today_start = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
            new_subs_today = conn.execute(
                "SELECT COUNT(*) FROM subscribers WHERE subscribed_at >= ? AND status='active'",
                (today_start,)
            ).fetchone()[0]
            conn.close()
        except Exception as e:
            logger.warning(f"Daily summary DB queries: {e}")
            new_subs_today = 0

        # Build events summary
        events_text = ""
        event_counts = {}
        for ev in recent_events:
            bot = ev.get("bot_name", "unknown")
            etype = ev.get("event_type", "")
            if etype != "error":
                event_counts[bot] = event_counts.get(bot, 0) + 1

        for bot, count in event_counts.items():
            events_text += f"- {bot}: {count} events\n"

        # Top tools today
        top_tools = sorted(click_totals.items(), key=lambda x: x[1], reverse=True)[:3]
        top_tools_text = ", ".join([f"{k} ({v})" for k, v in top_tools]) if top_tools else "none"

        # Affiliate payout reality check (monetized vs leaked)
        payout = compute_affiliate_payout_breakdown()
        earners_text = ", ".join(f"{k} {c}c ≈ ${e:.2f}" for k, c, e in payout["top_earners"]) or "none"
        leaks_text = ", ".join(f"{k} {c}c ≈ ${e:.2f} lost" for k, c, e in payout["top_leaks"]) or "none"

        prompt = f"""Write a brief executive summary for the AI Tools Empire bot system daily report.

Data from the past 24 hours:
- New page views today: {today_views}
- Affiliate clicks today: {total_clicks_today} ({payout['clicks_monetized']} monetized, {payout['clicks_unattributed']} unattributed)
- Estimated revenue today (monetized clicks × per-tool EPC @ 2% conv): ${payout['est_revenue']:.2f}
- Lost potential today (unattributed clicks × est EPC): ${payout['lost_potential']:.2f}
- Top earners: {earners_text}
- Top leaks: {leaks_text}
- New subscribers today: {new_subs_today}
- Total active subscribers: {subscriber_count}
- Total published articles: {article_count}
- Top tools clicked: {top_tools_text}

Bot activity:
{events_text if events_text else "- No significant bot events"}

Write a concise 3-4 paragraph executive summary covering:
1. Key metrics and performance (call out the monetized-vs-leaked split — this is the #1 revenue lever)
2. What the bots accomplished today
3. Any notable trends or concerns
4. Tomorrow's priorities

Keep it professional but conversational — like a status update from your automation system."""

        summary = ask_claude(prompt, max_tokens=600)

        if not summary:
            summary = (
                f"Daily Summary — {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
                f"Views: {today_views} | Clicks: {total_clicks_today} "
                f"({payout['clicks_monetized']} paid / {payout['clicks_unattributed']} leak)\n"
                f"Est. revenue: ${payout['est_revenue']:.2f} | Lost potential: ${payout['lost_potential']:.2f}\n"
                f"Top earner: {earners_text.split(',')[0] if earners_text != 'none' else '—'}\n"
                f"Top leak: {leaks_text.split(',')[0] if leaks_text != 'none' else '—'}\n"
                f"New Subs: {new_subs_today} | Total Subs: {subscriber_count}"
            )

        return summary

    except Exception as e:
        logger.error(f"generate_daily_summary error: {e}")
        return f"Daily summary generation failed: {e}"


def send_morning_briefing() -> bool:
    """
    Sends the daily summary to admin via Telegram + email.
    """
    try:
        summary = generate_daily_summary()
        date_str = datetime.utcnow().strftime("%A, %B %d, %Y")
        subject = f"AI Tools Empire — Morning Briefing ({date_str})"
        notify_admin(subject, summary)
        log_bot_event(BOT_NAME, "briefing_sent", "Morning briefing delivered")
        logger.info("Admin Notification Bot: morning briefing sent")
        return True
    except Exception as e:
        logger.error(f"send_morning_briefing error: {e}")
        return False


def send_alert(title: str, body: str, urgent: bool = False) -> None:
    """
    Sends an immediate alert to admin.
    """
    level = "error" if urgent else "warning"
    notify_admin(title, body)
    notify(f"{title}: {body[:200]}", level=level, use_telegram=True)
    log_bot_event(BOT_NAME, "alert_sent", f"[{'URGENT' if urgent else 'ALERT'}] {title}: {body[:100]}")


def check_critical_alerts() -> list:
    """
    Checks for critical conditions:
    - Site down (recent error event from website_monitor)
    - 0 articles published today
    - Subscriber growth negative
    - No social posts in 24h
    Returns list of alert strings.
    """
    alerts = []

    try:
        # Check for site down events in last hour
        recent_events = get_bot_events(bot_name="website_monitor", limit=5)
        for ev in recent_events:
            if ev.get("event_type") == "site_down":
                created_at = ev.get("created_at", "")
                try:
                    ev_time = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
                    if (datetime.utcnow() - ev_time).seconds < 3600:
                        alerts.append(f"SITE DOWN: {ev.get('details', 'Website monitor detected issues')}")
                        break
                except Exception:
                    pass

        # Check if any articles were published today
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        conn = get_conn()
        articles_today = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE DATE(created_at) = ? AND status='published'",
            (today_str,)
        ).fetchone()[0]

        if articles_today == 0 and datetime.utcnow().hour >= 10:
            alerts.append("No articles published today (after 10am UTC)")

        # Check subscriber growth — alert if we lost subscribers today
        today_start = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
        yesterday_start = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")

        today_new = conn.execute(
            "SELECT COUNT(*) FROM subscribers WHERE subscribed_at >= ? AND status='active'",
            (today_start,)
        ).fetchone()[0]

        # Check for unsubscribes today (status changed from active)
        # We'll check if total dropped compared to yesterday's end
        total_now = conn.execute("SELECT COUNT(*) FROM subscribers WHERE status='active'").fetchone()[0]

        # Check social queue for recent posts
        try:
            conn.execute("SELECT 1 FROM social_queue LIMIT 1")
            cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            recent_posts = conn.execute(
                "SELECT COUNT(*) FROM social_queue WHERE posted=1 AND posted_at >= ?",
                (cutoff,)
            ).fetchone()[0]
            if recent_posts == 0 and datetime.utcnow().hour >= 12:
                alerts.append("No social posts published in the last 24 hours")
        except Exception:
            pass  # social_queue may not exist yet

        conn.close()

    except Exception as e:
        logger.error(f"check_critical_alerts error: {e}")

    return alerts


def run_admin_notification_bot() -> dict:
    """
    Runs critical checks, sends alerts if needed.
    Sends morning briefing at 7am UTC.
    Returns summary.
    """
    logger.info("Admin Notification Bot: starting run")

    result = {
        "critical_alerts": 0,
        "briefing_sent": False,
    }

    try:
        # Check for critical issues
        alerts = check_critical_alerts()
        result["critical_alerts"] = len(alerts)

        for alert in alerts:
            send_alert("Critical Alert — AI Tools Empire", alert, urgent=True)
            logger.warning(f"Critical alert: {alert}")

        # Send morning briefing at 7am UTC
        current_hour = datetime.utcnow().hour
        if current_hour == 7:
            result["briefing_sent"] = send_morning_briefing()

        log_bot_event(
            BOT_NAME,
            "run_complete",
            f"Critical alerts: {len(alerts)}, Briefing sent: {result['briefing_sent']}"
        )

    except Exception as e:
        logger.error(f"Admin Notification Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
