"""
LinkedIn Message Monitor Bot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monitors Gmail for LinkedIn message/connection notifications.
Extracts sender name, message preview, and type.
Sends alerts to Telegram with draft responses.

LinkedIn has NO public messaging API, so this monitors email notifications.

Ensure LinkedIn email notifications are ON:
  linkedin.com → Settings → Communications → Email → Messages = ON
"""

import os
import re
import json
import time
import imaplib
import email
import logging
from datetime import datetime, timedelta
from email.header import decode_header

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("linkedin_monitor")

SMTP_USER = config.SMTP_USER or os.getenv("SMTP_USER", "")
SMTP_PASSWORD = config.SMTP_PASSWORD or os.getenv("SMTP_PASSWORD", "")
BOT_TOKEN = os.getenv("CLAUDE_BOT_TOKEN", "8620859605:AAFyqpnfFNj-Usgx0J1ZmxLyzQxw8T2s5Pk")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6194068092")
IMAP_HOST = "imap.gmail.com"

_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_DIR, "linkedin_monitor_state.json")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_check": "", "seen_ids": []}


def save_state(state: dict):
    state["seen_ids"] = state["seen_ids"][-200:]
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def tg_send(text: str):
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")


def decode_mime(header_value: str) -> str:
    if not header_value:
        return ""
    parts = decode_header(header_value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def classify_linkedin_email(subject: str, body: str) -> str:
    """Classify LinkedIn notification type."""
    s = subject.lower()
    b = body.lower()

    if "sent you a message" in s or "new message" in s or "messaged you" in s:
        return "message"
    if "wants to connect" in s or "connection request" in s or "invitation" in s:
        return "connection"
    if "viewed your profile" in s:
        return "profile_view"
    if "appeared in" in s and "search" in s:
        return "search_appearance"
    if "endorsed" in s:
        return "endorsement"
    if "commented" in s or "liked" in s or "reacted" in s:
        return "engagement"
    if "job" in s or "hiring" in s or "opportunity" in s:
        return "job_alert"
    if "inmail" in s.lower():
        return "inmail"
    return "other"


def extract_sender_name(subject: str, body: str) -> str:
    """Extract the person's name from LinkedIn notification."""
    # Common patterns: "John Smith sent you a message", "John Smith wants to connect"
    patterns = [
        r"^(.+?)\s+(?:sent you|wants to connect|messaged you|viewed your|endorsed|commented|liked)",
        r"^(.+?)\s+(?:has|is)\s+",
        r"New message from\s+(.+?)[\s:,]",
    ]
    for pat in patterns:
        m = re.search(pat, subject, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Clean up LinkedIn prefixes
            name = re.sub(r"^(Re:\s*|Fwd:\s*)", "", name, flags=re.IGNORECASE).strip()
            if len(name) > 2 and len(name) < 60:
                return name
    return "Someone"


def extract_message_preview(body: str) -> str:
    """Extract the actual message content from LinkedIn email body."""
    # Strip HTML
    text = re.sub(r"<[^>]+>", " ", body)
    text = re.sub(r"\s+", " ", text).strip()

    # Look for quoted message content
    patterns = [
        r'"([^"]{10,500})"',
        r"(?:wrote|says?|message):\s*(.{10,400})",
        r"(?:Hi|Hello|Hey)[\s,]+.{5,300}",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1 if m.lastindex else 0).strip()[:300]

    # Fallback: grab first meaningful chunk after common LinkedIn boilerplate
    text = re.sub(r".*?(View (message|profile)|Reply to)", "", text, flags=re.IGNORECASE)
    if len(text) > 20:
        return text[:300].strip()

    return "(preview not available)"


def draft_response(msg_type: str, sender: str, preview: str) -> str:
    """Draft a contextual response."""
    if msg_type == "message":
        if any(w in preview.lower() for w in ["resume", "cv", "job", "career", "hire", "interview"]):
            return (
                f"Hi {sender}! Thanks for reaching out.\n\n"
                f"I'd be happy to help with your resume. Could you send it over? "
                f"I'll take a look and give you specific feedback on what to improve.\n\n"
                f"I do professional resume rewrites for $49 (ATS-optimized, 24-hour delivery) "
                f"if you want a full overhaul after seeing the feedback."
            )
        return (
            f"Hi {sender}! Thanks for the message.\n\n"
            f"I appreciate you reaching out. How can I help?"
        )
    elif msg_type == "connection":
        return (
            f"Accept this connection request from {sender}. "
            f"Then send: 'Thanks for connecting, {sender}! What do you do?'"
        )
    elif msg_type == "inmail":
        return (
            f"Hi {sender}! Thanks for reaching out via InMail.\n\n"
            f"I appreciate you taking the time. I'd love to hear more about "
            f"what you have in mind. Could you share some details?"
        )
    elif msg_type == "profile_view":
        return f"{sender} viewed your profile. Consider sending them a connection request."
    elif msg_type == "engagement":
        return f"{sender} engaged with your post. Consider replying to build the relationship."
    return f"LinkedIn notification from {sender}. Check your inbox."


def check_linkedin_emails() -> list:
    """Check Gmail for new LinkedIn notification emails."""
    if not SMTP_USER or not SMTP_PASSWORD:
        log.error("Gmail credentials not configured")
        return []

    notifications = []
    state = load_state()
    seen_ids = set(state.get("seen_ids", []))

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(SMTP_USER, SMTP_PASSWORD)
        mail.select("inbox")

        since_date = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(FROM "linkedin" SINCE "{since_date}" UNSEEN)')

        if not data[0]:
            log.info("No new LinkedIn emails")
            mail.logout()
            return []

        email_ids = data[0].split()
        log.info(f"Found {len(email_ids)} unread LinkedIn emails")

        for eid in email_ids[-15:]:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            message_id = msg.get("Message-ID", eid.decode())
            if message_id in seen_ids:
                continue

            subject = decode_mime(msg.get("Subject", ""))
            from_addr = decode_mime(msg.get("From", ""))

            # Only process emails actually from LinkedIn
            if "linkedin" not in from_addr.lower():
                continue

            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        break
                    elif ct == "text/html" and not body:
                        raw = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        body = re.sub(r"<[^>]+>", " ", raw)
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

            msg_type = classify_linkedin_email(subject, body)
            sender = extract_sender_name(subject, body)
            preview = extract_message_preview(body)

            notifications.append({
                "type": msg_type,
                "sender": sender,
                "subject": subject,
                "preview": preview,
                "message_id": message_id,
                "received_at": msg.get("Date", ""),
            })

        mail.logout()

    except Exception as e:
        log.error(f"Gmail check failed: {e}")

    return notifications


def run_linkedin_monitor():
    """Main function — check for LinkedIn notifications and alert on Telegram."""
    log.info("Checking LinkedIn notifications...")
    state = load_state()

    notifications = check_linkedin_emails()

    if not notifications:
        log.info("No new LinkedIn notifications")
        return {"checked": True, "new_notifications": 0}

    seen_ids = state.get("seen_ids", [])
    messages = [n for n in notifications if n["type"] == "message"]
    connections = [n for n in notifications if n["type"] == "connection"]
    inmails = [n for n in notifications if n["type"] == "inmail"]
    others = [n for n in notifications if n["type"] not in ("message", "connection", "inmail")]

    # Priority alerts: messages and InMails first
    for n in messages + inmails:
        response = draft_response(n["type"], n["sender"], n["preview"])
        emoji = "💬" if n["type"] == "message" else "📧"

        tg_text = (
            f"{emoji} <b>LinkedIn {n['type'].upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>From:</b> {n['sender']}\n"
            f"<b>Subject:</b> {n['subject'][:80]}\n"
            f"<b>Preview:</b> {n['preview'][:200]}\n\n"
            f"<b>📝 Suggested Reply:</b>\n"
            f"<code>{response[:400]}</code>\n\n"
            f"👉 Reply: https://www.linkedin.com/messaging/"
        )
        tg_send(tg_text)
        seen_ids.append(n["message_id"])

    # Connection requests
    for n in connections:
        response = draft_response(n["type"], n["sender"], n["preview"])
        tg_text = (
            f"🤝 <b>LinkedIn CONNECTION REQUEST</b>\n"
            f"<b>From:</b> {n['sender']}\n\n"
            f"<b>Action:</b> {response}\n\n"
            f"👉 https://www.linkedin.com/mynetwork/"
        )
        tg_send(tg_text)
        seen_ids.append(n["message_id"])

    # Batch other notifications
    if others:
        summary_lines = []
        for n in others:
            icon = {"profile_view": "👁", "engagement": "👍", "job_alert": "💼", "endorsement": "⭐"}.get(n["type"], "📌")
            summary_lines.append(f"{icon} {n['type']}: {n['sender']} — {n['subject'][:60]}")
            seen_ids.append(n["message_id"])

        if summary_lines:
            tg_text = (
                f"📊 <b>LinkedIn Activity Summary</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                + "\n".join(summary_lines[:10])
            )
            tg_send(tg_text)

    state["seen_ids"] = seen_ids
    state["last_check"] = datetime.now().isoformat()
    save_state(state)

    total = len(notifications)
    log.info(f"Processed {total} LinkedIn notifications ({len(messages)} messages, {len(connections)} connections)")
    return {"checked": True, "new_notifications": total, "messages": len(messages), "connections": len(connections)}


if __name__ == "__main__":
    result = run_linkedin_monitor()
    print(f"Result: {result}")
