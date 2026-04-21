"""
Wholesale Real Estate Email Monitor — UPGRADED (Master Bot Directive Phase 4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monitors Gmail for wholesale deal responses from sellers and buyers.
Sends Telegram alerts on positive responses.
Auto-sends 48-hour follow-up reminders.
Logs all responses to CRM at localhost:5050.

Bot category: outreach / response handler
Inputs: Gmail IMAP inbox
Outputs: Telegram alerts, CRM activity log, follow-up tasks
Stop conditions: critical data missing, CRM down >5min
"""

import os
import re
import json
import time
import imaplib
import email
from datetime import datetime, timedelta
from email.header import decode_header

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from bots.shared.standards import (
    Status, BotResult, get_logger, tg, safe_run, load_state, save_state, STATE_DIR
)
from bots.shared.crm_client import crm

log = get_logger("wholesale_monitor")

SMTP_USER = config.SMTP_USER or ""
SMTP_PASSWORD = config.SMTP_PASSWORD or ""
IMAP_HOST = "imap.gmail.com"

STATE_FILE = os.path.join(STATE_DIR, "wholesale_monitor.json")
DEALS_DIR = os.path.expanduser("~/Desktop/wholesale-re/deals")
OUTREACH_DIR = os.path.expanduser("~/Desktop/wholesale-re/outreach")


def _load_state() -> dict:
    state = load_state(STATE_FILE)
    if not state:
        state = {
            "last_check": "",
            "seen_ids": [],
            "sent_followups": [],
            "outreach_log": [],
        }
    return state


def _save_state(state: dict) -> None:
    state["seen_ids"] = state.get("seen_ids", [])[-300:]
    state["sent_followups"] = state.get("sent_followups", [])[-100:]
    save_state(STATE_FILE, state)


def tg_send(text: str) -> bool:
    """Legacy alias — routes through unified tg() in standards."""
    return tg(text, level="info")


def decode_mime(val: str) -> str:
    if not val:
        return ""
    parts = decode_header(val)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def classify_response(subject: str, body: str) -> str:
    """Classify a wholesale email response."""
    text = f"{subject} {body}".lower()

    positive = ["interested", "tell me more", "send details", "want to see", "let's talk",
                 "i'd like", "sounds good", "send the contract", "let me know", "i'm in",
                 "what's the address", "can you send", "yes", "accepted", "agree"]
    negative = ["not interested", "no thanks", "pass", "remove me", "unsubscribe",
                 "too high", "not for me", "can't do it", "decline"]
    maybe = ["maybe", "let me think", "need to check", "get back to you", "possibly",
             "depends", "what's your best", "counter"]

    if any(w in text for w in positive):
        return "INTERESTED"
    if any(w in text for w in negative):
        return "NOT_INTERESTED"
    if any(w in text for w in maybe):
        return "MAYBE"
    return "UNKNOWN"


def check_wholesale_emails() -> list:
    """Check for responses to wholesale deal emails."""
    if not SMTP_USER or not SMTP_PASSWORD:
        return []

    responses = []
    state = _load_state()
    seen = set(state.get("seen_ids", []))

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(SMTP_USER, SMTP_PASSWORD)
        mail.select("inbox")

        since = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        # IMAP OR is binary — using SINCE-only and filtering subjects in Python
        _, data = mail.search(None, f'(SINCE "{since}")')

        if not data[0]:
            mail.logout()
            return []

        subject_keywords = ("wholesale", "cash offer", "camelot", "lakewood", "ingledale", "peyton")

        for eid in data[0].split()[-50:]:
            _, msg_data = mail.fetch(eid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            mid = msg.get("Message-ID", eid.decode())
            if mid in seen:
                continue

            subject = decode_mime(msg.get("Subject", ""))
            from_addr = decode_mime(msg.get("From", ""))

            subj_lower = subject.lower()
            if not any(kw in subj_lower for kw in subject_keywords):
                continue

            # Skip our own sent emails
            if "bosaibot" in from_addr.lower():
                continue

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

            classification = classify_response(subject, body)

            responses.append({
                "from": from_addr,
                "subject": subject,
                "body_preview": body[:300],
                "classification": classification,
                "message_id": mid,
                "date": msg.get("Date", ""),
            })

        mail.logout()

    except Exception as e:
        log.error(f"Email check failed: {e}")

    return responses


def send_followup_reminders(state: dict):
    """Send 48-hour follow-up for unanswered outreach."""
    from automation.email_sender import _send_via_smtp

    outreach_log = state.get("outreach_log", [])
    sent_followups = set(state.get("sent_followups", []))
    now = datetime.now()

    for entry in outreach_log:
        deal_id = entry.get("deal_id", "")
        sent_at = entry.get("sent_at", "")
        to_email = entry.get("to", "") or entry.get("to_email", "")
        if not sent_at or deal_id in sent_followups:
            continue

        # HARD RULE: never self-send. If outreach_log entry didn't record a
        # recipient, skip — don't ship a follow-up to bosaibot.
        if not to_email or to_email.lower().strip() in ("", SMTP_USER.lower()):
            log.info(f"Skipping follow-up for {deal_id} — no external recipient recorded")
            state["sent_followups"].append(deal_id)
            continue

        try:
            sent_dt = datetime.fromisoformat(sent_at)
            if (now - sent_dt).total_seconds() > 48 * 3600:
                address = entry.get("address", "the property")
                followup_html = f"""
                <div style=\"font-family:sans-serif;padding:20px;\">
                  <p>Hi,</p>
                  <p>Just following up on my cash offer inquiry for <strong>{address}</strong> from a couple days ago.</p>
                  <p>I'm still interested and ready to move quickly. Is the seller open to discussing a cash offer?</p>
                  <p>Happy to work with your timeline.</p>
                  <p>Best,<br>Kenneth Bonnet<br>bosaibot@gmail.com</p>
                </div>
                """
                sent = _send_via_smtp(
                    [to_email],
                    f"[FOLLOWUP] Cash Offer: {address}",
                    followup_html,
                )
                if sent:
                    state["sent_followups"].append(deal_id)
                    log.info(f"48h follow-up sent for {deal_id} → {to_email}")
                    tg_send(f"📬 48-hour follow-up sent for {deal_id}: {address} → {to_email}")
        except Exception as e:
            log.warning(f"Follow-up error for {deal_id}: {e}")


@safe_run("wholesale_monitor")
def run_wholesale_monitor() -> BotResult:
    """
    Main function — check for wholesale responses + send follow-ups.

    Phase 4 upgrades:
      • Wrapped in @safe_run for error isolation
      • Returns BotResult for clean handoff to wholesale_agent skill
      • Uses unified tg() for Telegram
      • Logs all responses to CRM via crm.log_activity()
      • Creates CRM tasks for INTERESTED responses
      • Falls back gracefully if CRM is down
    """
    state = _load_state()

    # Drain any pending CRM writes from previous failed attempts
    crm.flush_pending()

    # Record initial outreach if not already done
    if not state.get("outreach_log"):
        state["outreach_log"] = [
            {"deal_id": "ATL-001", "address": "1314 Camelot Dr, Atlanta, GA 30349", "sent_at": datetime.now().isoformat()},
            {"deal_id": "ATL-002", "address": "615 Camelot Dr, Atlanta, GA 30349", "sent_at": datetime.now().isoformat()},
            {"deal_id": "ATL-003", "address": "3598 Ingledale Dr SW, Atlanta, GA 30331", "sent_at": datetime.now().isoformat()},
            {"deal_id": "ATL-004", "address": "3159 Lakewood Ave SW, Atlanta, GA 30310", "sent_at": datetime.now().isoformat()},
            {"deal_id": "ATL-005", "address": "257 Peyton Pl SW, Atlanta, GA 30311", "sent_at": datetime.now().isoformat()},
        ]

    # Check for responses
    responses = check_wholesale_emails()
    seen = state.get("seen_ids", [])
    interested_count = 0

    for r in responses:
        cls = r["classification"]
        icon = {"INTERESTED": "🟢", "MAYBE": "🟡", "NOT_INTERESTED": "🔴", "UNKNOWN": "⚪"}.get(cls, "⚪")

        if cls in ("INTERESTED", "MAYBE"):
            interested_count += 1
            tg(
                f"{icon} <b>WHOLESALE RESPONSE — {cls}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>From:</b> {r['from'][:60]}\n"
                f"<b>Subject:</b> {r['subject'][:60]}\n"
                f"<b>Preview:</b> {r['body_preview'][:200]}\n\n"
                f"⚡ Reply APPROVE on Telegram to send contract\n"
                f"👉 Check full email: mail.google.com",
                level="deal" if cls == "INTERESTED" else "info",
            )

            # Phase 7: Log to CRM and create follow-up task
            crm.log_activity(
                activity_type="wholesale_response",
                summary=f"{cls} response from {r['from'][:60]}",
                details={"subject": r['subject'], "preview": r['body_preview'][:300]},
            )
            if cls == "INTERESTED":
                crm.create_task(
                    task_type="send_contract",
                    description=f"Buyer interested: {r['from'][:60]} re: {r['subject'][:60]}",
                    priority="high",
                )

        seen.append(r["message_id"])
        log.info(f"Wholesale response: {cls} from {r['from'][:40]}")

    # Send 48h follow-ups
    send_followup_reminders(state)

    state["seen_ids"] = seen
    state["last_check"] = datetime.now().isoformat()
    _save_state(state)

    return BotResult(
        bot_name="wholesale_monitor",
        success=True,
        received={"emails_checked": len(responses)},
        produced={"interested": interested_count, "total_responses": len(responses)},
        next_bot="wholesale_agent" if interested_count > 0 else None,
        next_action="send_contract" if interested_count > 0 else "wait_for_responses",
    )


if __name__ == "__main__":
    result = run_wholesale_monitor()
    print(f"Result: {result}")
