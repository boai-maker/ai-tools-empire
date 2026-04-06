"""
Bot 7: Email Marketing Bot
Manages newsletters and email sequences.
"""
import logging
from datetime import datetime

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from bots.shared.email_sender import send_email, send_bulk_email
from database.db import get_conn, get_subscribers, get_due_sequence_emails, mark_sequence_sent
from config import config

logger = logging.getLogger(__name__)

BOT_NAME = "email_marketing_bot"


def generate_newsletter_content(theme: str = None) -> dict:
    """
    Generates a weekly newsletter.
    Returns {subject, body_html, body_text}.
    """
    if not theme:
        theme = "the latest AI tools making waves this week"

    prompt = f"""Write a weekly email newsletter for AI Tools Empire subscribers about: {theme}

Requirements:
- Subject line: compelling, under 60 characters (format: SUBJECT: ...)
- 400-600 words of content
- Highlight 2-3 specific AI tools with brief reviews
- Include real value — tips, insights, why these tools matter
- Include affiliate link placeholders: [AFFILIATE:tool_name]
  Example: <a href="[AFFILIATE:jasper]">Try Jasper free →</a>
- Friendly, direct tone from Kenny (the founder)
- End with a CTA to check out the full reviews at aitoolsempire.co
- Format as HTML with inline styles (no external CSS)

Format your response:
SUBJECT: [subject line]
BODY_HTML:
[full HTML email body here]"""

    system = (
        "You are Kenny from AI Tools Empire, writing a weekly newsletter. "
        "Be genuine, helpful, and share real value. Don't oversell — "
        "be the trusted friend who knows AI tools inside and out."
    )

    response = ask_claude(prompt, system=system, max_tokens=2500)

    if not response:
        return {
            "subject": "This Week's Top AI Tools",
            "body_html": "<p>Newsletter content unavailable this week.</p>",
            "body_text": "Newsletter content unavailable this week.",
        }

    subject = "This Week's Top AI Tools"
    body_html = ""
    body_started = False

    lines = response.split("\n")
    body_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("SUBJECT:"):
            subject = stripped[8:].strip()
        elif stripped == "BODY_HTML:":
            body_started = True
        elif body_started:
            body_lines.append(line)

    raw_body = "\n".join(body_lines).strip()

    # Wrap in a proper email template
    body_html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333; background: #f9f9f9;">
    <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);">

    <div style="text-align: center; margin-bottom: 25px; padding-bottom: 20px; border-bottom: 2px solid #667eea;">
        <h1 style="color: #667eea; margin: 0; font-size: 24px;">AI Tools Empire</h1>
        <p style="color: #666; margin: 5px 0 0 0; font-size: 14px;">Your Weekly AI Tools Digest</p>
    </div>

    {raw_body if raw_body else "<p>Check out the latest AI tool reviews at aitoolsempire.co!</p>"}

    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; text-align: center;">
        <a href="{config.SITE_URL}" style="background: #667eea; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold;">
            Visit AI Tools Empire →
        </a>
    </div>

    <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">
    <p style="font-size: 11px; color: #999; text-align: center;">
        You're receiving this because you subscribed at <a href="{config.SITE_URL}" style="color: #999;">{config.SITE_URL}</a>.<br>
        <a href="{config.SITE_URL}/unsubscribe" style="color: #999;">Unsubscribe</a> ·
        <a href="{config.SITE_URL}/privacy" style="color: #999;">Privacy Policy</a>
    </p>
    </div>
    </body></html>
    """

    # Generate plain text version
    import re
    body_text = re.sub(r"<[^>]+>", "", raw_body).strip()
    body_text += f"\n\nVisit AI Tools Empire: {config.SITE_URL}"

    return {"subject": subject, "body_html": body_html, "body_text": body_text}


def send_newsletter_to_all() -> dict:
    """
    Gets active subscribers, sends newsletter, logs to email_campaigns.
    Returns {sent: n, failed: n}.
    """
    try:
        newsletter = generate_newsletter_content()
        subscribers = get_subscribers(status="active")

        if not subscribers:
            logger.info("No active subscribers for newsletter")
            return {"sent": 0, "failed": 0}

        recipients = [sub["email"] for sub in subscribers]
        result = send_bulk_email(recipients, newsletter["subject"], newsletter["body_html"])

        # Log to email_campaigns
        conn = get_conn()
        conn.execute("""
            INSERT INTO email_campaigns (subject, content, campaign_type, sent_count, status, sent_at)
            VALUES (?, ?, 'newsletter', ?, 'sent', CURRENT_TIMESTAMP)
        """, (newsletter["subject"], newsletter["body_html"], result["sent"]))
        conn.commit()
        conn.close()

        log_bot_event(
            BOT_NAME,
            "newsletter_sent",
            f"Newsletter sent to {result['sent']} subscribers. Failed: {result['failed']}"
        )
        logger.info(f"Newsletter sent: {result['sent']} sent, {result['failed']} failed")
        return result

    except Exception as e:
        logger.error(f"send_newsletter_to_all error: {e}")
        return {"sent": 0, "failed": 0}


def _generate_sequence_email(seq_num: int, name: str) -> dict:
    """Generates a personalized onboarding sequence email."""
    first_name = name.split()[0] if name else "there"

    sequence_topics = {
        1: ("Your AI Tools Journey Starts Here", "welcome and what to expect"),
        2: ("The 3 AI Tools Every Business Needs", "essential AI tools for productivity"),
        3: ("How I Saved 10 Hours/Week With These AI Tools", "real productivity wins with AI"),
        4: ("The AI Tools Most People Overlook (But Shouldn't)", "hidden gem AI tools"),
        5: ("Your Exclusive AI Tools Deal + Next Steps", "exclusive deals and CTA"),
    }

    topic_title, topic_desc = sequence_topics.get(seq_num, ("AI Tools Update", "AI tools tips"))

    prompt = f"""Write email #{seq_num} of a 5-email onboarding sequence for AI Tools Empire.

Recipient's first name: {first_name}
Email topic: {topic_title} — {topic_desc}

Requirements:
- Subject line (format: SUBJECT: ...)
- 200-350 words of content
- Personalize with first name at the start
- Valuable, non-salesy content
- One clear CTA at the end (visit a relevant page on aitoolsempire.co)
- Include one mention of a specific AI tool with [AFFILIATE:tool_name] placeholder
- HTML format with inline styles

Format:
SUBJECT: [subject]
BODY:
[HTML content]"""

    response = ask_claude(prompt, max_tokens=1200)

    if not response:
        return {
            "subject": topic_title,
            "body_html": f"<p>Hey {first_name}, check out our latest AI tool reviews at {config.SITE_URL}!</p>",
        }

    subject = topic_title
    body_lines = []
    body_started = False

    for line in response.split("\n"):
        stripped = line.strip()
        if stripped.startswith("SUBJECT:"):
            subject = stripped[8:].strip()
        elif stripped == "BODY:":
            body_started = True
        elif body_started:
            body_lines.append(line)

    body_html = "\n".join(body_lines).strip()
    if not body_html:
        body_html = f"<p>Hey {first_name}! {response}</p>"

    # Wrap in email template
    body_html = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
    <div style="padding: 20px; background: #fff; border-radius: 8px;">
    <p style="color: #667eea; font-size: 14px; margin: 0 0 20px 0;">AI Tools Empire</p>
    {body_html}
    <hr style="border: none; border-top: 1px solid #eee; margin: 25px 0;">
    <p style="font-size: 11px; color: #999; text-align: center;">
        <a href="{config.SITE_URL}/unsubscribe" style="color: #999;">Unsubscribe</a>
    </p>
    </div>
    </body></html>
    """

    return {"subject": subject, "body_html": body_html}


def process_sequence_queue() -> int:
    """
    Gets due sequence emails, generates personalized content, sends them.
    Returns count sent.
    """
    sent_count = 0

    try:
        due_emails = get_due_sequence_emails()

        if not due_emails:
            logger.debug("No sequence emails due")
            return 0

        logger.info(f"Processing {len(due_emails)} sequence emails")

        for item in due_emails:
            try:
                email = item["email"]
                name = item.get("name", "") or ""
                seq_num = item["seq_num"]
                queue_id = item["id"]

                email_content = _generate_sequence_email(seq_num, name)
                success = send_email(
                    email,
                    email_content["subject"],
                    email_content["body_html"],
                )

                if success:
                    mark_sequence_sent(queue_id)
                    sent_count += 1
                    logger.info(f"Sequence email {seq_num} sent to {email}")
                else:
                    logger.warning(f"Failed to send sequence email {seq_num} to {email}")

            except Exception as e:
                logger.error(f"Error processing sequence item {item.get('id')}: {e}")

    except Exception as e:
        logger.error(f"process_sequence_queue error: {e}")

    return sent_count


def run_email_marketing_bot() -> dict:
    """
    Processes sequence queue. Sends newsletter on Mondays.
    """
    logger.info("Email Marketing Bot: starting run")

    result = {
        "sequence_emails_sent": 0,
        "newsletter_sent": False,
        "newsletter_recipients": 0,
    }

    try:
        # Always process sequence queue
        seq_sent = process_sequence_queue()
        result["sequence_emails_sent"] = seq_sent

        # Send newsletter on Mondays
        today = datetime.utcnow().weekday()  # 0 = Monday
        if today == 0:
            logger.info("It's Monday — sending weekly newsletter")
            newsletter_result = send_newsletter_to_all()
            result["newsletter_sent"] = newsletter_result["sent"] > 0
            result["newsletter_recipients"] = newsletter_result["sent"]

        log_bot_event(
            BOT_NAME,
            "run_complete",
            f"Sequence: {seq_sent} sent. Newsletter: {result.get('newsletter_recipients', 0)} recipients"
        )

    except Exception as e:
        logger.error(f"Email Marketing Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
