"""
Bot 6: Lead Capture / Conversion Bot
Optimizes lead capture and processes new subscribers.
"""
import logging
from datetime import datetime, timedelta

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from bots.shared.email_sender import send_email
from database.db import get_conn
from config import config

logger = logging.getLogger(__name__)

BOT_NAME = "lead_capture_bot"


def get_new_subscribers(hours: int = 24) -> list:
    """Returns subscribers added in the last N hours."""
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE subscribed_at >= ? AND status='active' ORDER BY subscribed_at DESC",
            (cutoff,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_new_subscribers error: {e}")
        return []


def generate_lead_magnet_ideas() -> list:
    """
    Uses Claude to generate 5 lead magnet ideas for an AI tools audience.
    Returns list of {title, description, format}.
    """
    prompt = """Generate 5 high-converting lead magnet ideas for AI Tools Empire (aitoolsempire.co).

The audience is: business owners, marketers, freelancers, and professionals who want to use AI tools to save time and make money.

For each lead magnet provide:
TITLE: [compelling title]
DESCRIPTION: [1-2 sentence description of value]
FORMAT: [PDF, checklist, video, email course, template, etc.]
---

Generate all 5 in this format."""

    response = ask_claude(prompt, max_tokens=1000)
    ideas = []

    if not response:
        return ideas

    blocks = response.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        idea = {"title": "", "description": "", "format": ""}
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("TITLE:"):
                idea["title"] = line[6:].strip()
            elif line.startswith("DESCRIPTION:"):
                idea["description"] = line[12:].strip()
            elif line.startswith("FORMAT:"):
                idea["format"] = line[7:].strip()

        if idea["title"]:
            ideas.append(idea)

    return ideas[:5]


def analyze_subscriber_growth() -> dict:
    """
    Returns subscriber growth stats: today, this_week, this_month, total, growth_rate.
    """
    try:
        conn = get_conn()
        now = datetime.utcnow()

        today_start = now.strftime("%Y-%m-%d 00:00:00")
        week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        month_start = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        total = conn.execute("SELECT COUNT(*) FROM subscribers WHERE status='active'").fetchone()[0]
        today_count = conn.execute(
            "SELECT COUNT(*) FROM subscribers WHERE subscribed_at >= ? AND status='active'",
            (today_start,)
        ).fetchone()[0]
        week_count = conn.execute(
            "SELECT COUNT(*) FROM subscribers WHERE subscribed_at >= ? AND status='active'",
            (week_start,)
        ).fetchone()[0]
        month_count = conn.execute(
            "SELECT COUNT(*) FROM subscribers WHERE subscribed_at >= ? AND status='active'",
            (month_start,)
        ).fetchone()[0]
        conn.close()

        # Simple growth rate: this month vs prior month estimate
        prior_total = total - month_count
        if prior_total > 0:
            rate = ((month_count / prior_total) * 100)
            growth_rate = f"+{rate:.1f}% this month"
        elif month_count > 0:
            growth_rate = "New growth this month"
        else:
            growth_rate = "No growth this month"

        return {
            "today": today_count,
            "this_week": week_count,
            "this_month": month_count,
            "total": total,
            "growth_rate": growth_rate,
        }
    except Exception as e:
        logger.error(f"analyze_subscriber_growth error: {e}")
        return {"today": 0, "this_week": 0, "this_month": 0, "total": 0, "growth_rate": "unknown"}


def send_welcome_if_needed() -> int:
    """
    Finds subscribers with welcome_sent=0, sends welcome email, marks welcome_sent=1.
    Returns count of welcome emails sent.
    """
    sent_count = 0

    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM subscribers WHERE welcome_sent=0 AND status='active' ORDER BY subscribed_at ASC LIMIT 50"
        ).fetchall()
        conn.close()

        subscribers = [dict(r) for r in rows]

        if not subscribers:
            logger.debug("No new subscribers needing welcome emails")
            return 0

        for sub in subscribers:
            email = sub.get("email", "")
            name = sub.get("name", "") or "Friend"

            subject = f"Welcome to AI Tools Empire, {name.split()[0] if name != 'Friend' else name}!"
            body_html = f"""
            <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 30px;">
                <h1 style="color: white; margin: 0; font-size: 28px;">Welcome to AI Tools Empire!</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0;">Your #1 resource for AI tool reviews &amp; deals</p>
            </div>

            <p style="font-size: 16px;">Hey {name},</p>

            <p>Welcome aboard! I'm so glad you joined the AI Tools Empire community.</p>

            <p>Here's what you can expect from me:</p>

            <ul style="line-height: 2;">
                <li>🔍 <strong>Honest AI tool reviews</strong> — I test tools so you don't have to</li>
                <li>💰 <strong>Exclusive deals</strong> — special discounts on top AI tools</li>
                <li>📚 <strong>Practical tutorials</strong> — how to actually use AI to save time &amp; make money</li>
                <li>📊 <strong>Comparisons</strong> — side-by-side breakdowns of competing tools</li>
            </ul>

            <p>As a first step, check out our most popular resource:</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{config.SITE_URL}/articles" style="background: #667eea; color: white; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 16px;">
                    Explore Top AI Tools →
                </a>
            </div>

            <p>Got questions? Just reply to this email — I personally read every message.</p>

            <p>Talk soon,<br>
            <strong>Kenny</strong><br>
            <em>Founder, AI Tools Empire</em></p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="font-size: 12px; color: #999; text-align: center;">
                You're receiving this because you subscribed at <a href="{config.SITE_URL}">{config.SITE_URL}</a>.<br>
                <a href="{config.SITE_URL}/unsubscribe?email={email}" style="color: #999;">Unsubscribe</a>
            </p>
            </body></html>
            """

            body_text = f"""Hey {name},

Welcome to AI Tools Empire! I'm glad you joined.

Here's what you can expect:
- Honest AI tool reviews
- Exclusive deals and discounts
- Practical tutorials
- Side-by-side tool comparisons

Explore our top articles: {config.SITE_URL}/articles

Questions? Just reply to this email.

Talk soon,
Kenny
Founder, AI Tools Empire

Unsubscribe: {config.SITE_URL}/unsubscribe?email={email}"""

            success = send_email(email, subject, body_html, body_text)

            if success:
                # Mark welcome sent
                conn = get_conn()
                conn.execute("UPDATE subscribers SET welcome_sent=1 WHERE email=?", (email,))
                conn.commit()
                conn.close()
                sent_count += 1
                logger.info(f"Welcome email sent to {email}")
            else:
                logger.warning(f"Failed to send welcome email to {email}")

    except Exception as e:
        logger.error(f"send_welcome_if_needed error: {e}")

    return sent_count


def run_lead_capture_bot() -> dict:
    """
    Runs growth analysis, sends welcome emails, logs activity.
    """
    logger.info("Lead Capture Bot: starting run")

    result = {
        "new_subscribers_24h": 0,
        "welcome_emails_sent": 0,
        "total_subscribers": 0,
        "growth_rate": "",
    }

    try:
        growth = analyze_subscriber_growth()
        result["new_subscribers_24h"] = growth["today"]
        result["total_subscribers"] = growth["total"]
        result["growth_rate"] = growth["growth_rate"]

        welcome_sent = send_welcome_if_needed()
        result["welcome_emails_sent"] = welcome_sent

        log_bot_event(
            BOT_NAME,
            "run_complete",
            f"New subs (24h): {growth['today']}, Total: {growth['total']}, Welcome sent: {welcome_sent}"
        )

        if growth["today"] > 0:
            logger.info(f"Lead Capture Bot: {growth['today']} new subscribers today")

    except Exception as e:
        logger.error(f"Lead Capture Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
