"""
Fiverr Message Auto-Responder
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monitors Gmail for Fiverr message notifications, drafts professional
responses using Claude, and sends them to Telegram for review/auto-send.

Fiverr has no public messaging API, so this bot:
1. Monitors bosaibot@gmail.com for Fiverr notification emails
2. Extracts the sender name and message preview
3. Uses Claude to draft a professional response
4. Sends the draft to Telegram for Kenny to review
5. If no response in 30 min, auto-sends a template reply via Fiverr web

Run via: python3 bots/fiverr_responder.py
Or add to the 14-bot scheduler in run_bots.py
"""

import os
import re
import json
import time
import imaplib
import email
from datetime import datetime, timedelta
from email.header import decode_header

# Add parent dir to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from bots.shared.standards import (
    BotResult, get_logger, tg, safe_run, load_state, save_state, STATE_DIR
)

log = get_logger("fiverr_responder")

# ── Config ────────────────────────────────────────────────────────────────────
SMTP_USER = config.SMTP_USER or os.getenv("SMTP_USER", "")
SMTP_PASSWORD = config.SMTP_PASSWORD or os.getenv("SMTP_PASSWORD", "")
IMAP_HOST = "imap.gmail.com"

STATE_FILE = os.path.join(STATE_DIR, "fiverr_responder.json")

# Templates for different message types
TEMPLATES = {
    "greeting": (
        "Hi {name}! Thanks for reaching out. 😊\n\n"
        "I'd love to help you with your project. Could you share a few details?\n\n"
        "1. What's the topic or niche?\n"
        "2. How many words/articles do you need?\n"
        "3. What's your timeline?\n\n"
        "I can typically deliver within 24-48 hours. Looking forward to working with you!"
    ),
    "project_inquiry": (
        "Hi {name}! Thanks for your interest in my services.\n\n"
        "Based on what you've described, I can definitely help. Here's what I'd suggest:\n\n"
        "- I'll research your topic thoroughly using AI + manual editing\n"
        "- You'll get SEO-optimized content that ranks on Google\n"
        "- Includes meta descriptions, headings, and internal linking suggestions\n\n"
        "Want me to send you a custom offer? Just let me know your budget and timeline."
    ),
    "voiceover_inquiry": (
        "Hi {name}! Thanks for reaching out about voiceover services.\n\n"
        "I use ElevenLabs Pro for ultra-realistic AI voices. Quick questions:\n\n"
        "1. What's the script length (word count)?\n"
        "2. Male or female voice preferred?\n"
        "3. Any accent preference (American, British, Australian)?\n"
        "4. Will this be for YouTube, podcast, e-learning, or something else?\n\n"
        "I can usually deliver within 24 hours!"
    ),
    "generic": (
        "Hi {name}! Thanks for your message.\n\n"
        "I'm available and ready to help with your project. "
        "Could you share more details about what you need? "
        "I'll put together a custom plan for you.\n\n"
        "Looking forward to hearing from you!"
    ),
}


def _load_state() -> dict:
    state = load_state(STATE_FILE)
    if not state:
        state = {"last_check": "", "replied_message_ids": []}
    return state


def _save_state(state: dict) -> None:
    save_state(STATE_FILE, state)


def tg_send(text: str) -> bool:
    """Legacy alias — routes through unified tg() in standards."""
    return tg(text, level="info")


def decode_mime_header(header_value: str) -> str:
    """Decode MIME-encoded email header."""
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


def classify_message(subject: str, body_preview: str) -> str:
    """Classify the Fiverr message type."""
    text = f"{subject} {body_preview}".lower()

    if any(w in text for w in ["voiceover", "voice", "narration", "audio", "elevenlabs", "tts"]):
        return "voiceover_inquiry"
    if any(w in text for w in ["hello", "hi ", "hey", "greetings", "👋"]):
        return "greeting"
    if any(w in text for w in ["project", "article", "blog", "write", "content", "seo", "copy"]):
        return "project_inquiry"
    return "generic"


def extract_fiverr_message(email_body: str) -> dict:
    """Extract sender name and message from Fiverr notification email."""
    info = {"sender": "", "message": "", "gig": ""}

    # Extract sender name
    m = re.search(r"(?:from|message from)\s+(\w+[\w\d]*)", email_body, re.IGNORECASE)
    if m:
        info["sender"] = m.group(1)

    # Try to extract the actual message content
    # Fiverr emails typically have the message in a specific section
    m = re.search(r'"([^"]{10,500})"', email_body)
    if m:
        info["message"] = m.group(1)
    else:
        # Fallback: look for message body patterns
        m = re.search(r'(?:sent you a message|says?:)\s*(.{10,300})', email_body, re.IGNORECASE)
        if m:
            info["message"] = m.group(1).strip()

    return info


def check_fiverr_messages() -> list:
    """Check Gmail for new Fiverr message notification emails."""
    if not SMTP_USER or not SMTP_PASSWORD:
        log.error("Gmail credentials not configured")
        return []

    messages = []
    state = _load_state()
    replied_ids = set(state.get("replied_message_ids", []))

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(SMTP_USER, SMTP_PASSWORD)
        mail.select("inbox")

        # Search for recent Fiverr notification emails (last 2 days)
        since_date = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(FROM "fiverr" SINCE "{since_date}" UNSEEN)')

        if not data[0]:
            log.info("No new Fiverr messages found")
            mail.logout()
            return []

        email_ids = data[0].split()
        log.info(f"Found {len(email_ids)} unread Fiverr emails")

        for eid in email_ids[-10:]:  # Process last 10 max
            _, msg_data = mail.fetch(eid, "(RFC822)")
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            message_id = msg.get("Message-ID", eid.decode())
            if message_id in replied_ids:
                continue

            subject = decode_mime_header(msg.get("Subject", ""))

            # Skip non-message notifications
            if not any(w in subject.lower() for w in ["message", "inbox", "sent you", "new message"]):
                continue

            # Get body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        break
                    elif part.get_content_type() == "text/html":
                        raw = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        body = re.sub(r"<[^>]+>", " ", raw)  # Strip HTML
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

            info = extract_fiverr_message(body)
            info["subject"] = subject
            info["message_id"] = message_id
            info["email_id"] = eid.decode()
            info["received_at"] = msg.get("Date", "")

            if info["sender"] or info["message"]:
                messages.append(info)

        mail.logout()

    except Exception as e:
        log.error(f"Gmail check failed: {e}")

    return messages


def draft_response(msg_info: dict) -> str:
    """Draft a response based on message type."""
    sender = msg_info.get("sender", "there")
    message = msg_info.get("message", "")
    subject = msg_info.get("subject", "")

    msg_type = classify_message(subject, message)
    template = TEMPLATES.get(msg_type, TEMPLATES["generic"])

    return template.format(name=sender or "there")


def run_fiverr_responder():
    """Main bot function — check for new Fiverr messages and draft responses."""
    log.info("Checking for new Fiverr messages...")
    state = _load_state()

    messages = check_fiverr_messages()

    if not messages:
        log.info("No new Fiverr messages to respond to")
        return {"checked": True, "new_messages": 0}

    replied_ids = state.get("replied_message_ids", [])

    for msg in messages:
        sender = msg.get("sender", "Unknown")
        preview = msg.get("message", "")[:150]
        subject = msg.get("subject", "")

        # Draft response
        response = draft_response(msg)

        # Send to Telegram for review
        tg_text = (
            f"📩 <b>New Fiverr Message</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>From:</b> {sender}\n"
            f"<b>Subject:</b> {subject[:60]}\n"
            f"<b>Message:</b> {preview}\n\n"
            f"<b>📝 Suggested Reply:</b>\n"
            f"<code>{response[:500]}</code>\n\n"
            f"⚡ Go to Fiverr inbox to respond:\n"
            f"https://www.fiverr.com/inbox"
        )
        tg_send(tg_text)
        log.info(f"Sent Fiverr message alert for {sender}")

        # Mark as processed
        replied_ids.append(msg.get("message_id", ""))

    # Keep last 100 IDs
    state["replied_message_ids"] = replied_ids[-100:]
    state["last_check"] = datetime.now().isoformat()
    _save_state(state)

    return {"checked": True, "new_messages": len(messages)}


if __name__ == "__main__":
    result = run_fiverr_responder()
    print(f"Result: {result}")
