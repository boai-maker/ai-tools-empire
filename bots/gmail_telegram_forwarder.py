"""
Gmail → Telegram Forwarder.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kenny can't access bosaibot@gmail.com right now. This bot forwards
every new inbox message to Telegram (Kenny Claude chat) so he sees
everything without needing Gmail.

• Runs every 10 minutes via APScheduler.
• Uses IMAP IDLE on Gmail.
• Tracks seen message-ids in state file to avoid duplicates.
• Classifies: form submission, affiliate approval, sales lead,
  surplus reply, generic.
• Body preview: 800 chars max, strips HTML.
• Does NOT mark messages as read in Gmail (keeps them unread
  for when Kenny returns).
"""
import os
import re
import sys
import json
import imaplib
import email
import html
from email.header import decode_header
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bots.shared.standards import get_logger, tg, STATE_DIR

log = get_logger("gmail_fwd")
STATE_FILE = os.path.join(STATE_DIR, "gmail_forwarder.json")
SMTP_USER = os.getenv("SMTP_USER", "bosaibot@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

MAX_BODY = 800
MAX_PER_RUN = 20  # Telegram flood protection


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen_ids": [], "last_run": None, "forwarded_count": 0}
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"seen_ids": [], "last_run": None, "forwarded_count": 0}


def save_state(state):
    # Cap seen_ids to last 2000 to stay light
    state["seen_ids"] = state["seen_ids"][-2000:]
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def decode(raw: str) -> str:
    if not raw:
        return ""
    try:
        parts = decode_header(raw)
        out = []
        for txt, enc in parts:
            if isinstance(txt, bytes):
                out.append(txt.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(txt)
        return "".join(out)
    except Exception:
        return raw or ""


def strip_html(s: str) -> str:
    s = re.sub(r"<script[^>]*>.*?</script>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<style[^>]*>.*?</style>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    h = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    return strip_html(h)
                except Exception:
                    continue
    else:
        try:
            raw = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
            if msg.get_content_type() == "text/html":
                return strip_html(raw)
            return raw
        except Exception:
            return msg.get_payload() or ""
    return ""


def classify(frm: str, subj: str, body: str) -> str:
    f = (frm or "").lower()
    s = (subj or "").lower()
    b = (body or "").lower()
    if "contact form" in s or "[contact]" in s or "website contact" in s:
        return "📝 FORM"
    if any(k in f for k in ("partnerstack", "impact.com", "rewardful", "cj.com", "shareasale")):
        return "💼 AFFILIATE"
    if any(k in s for k in ("surplus", "unclaimed funds", "overage")):
        return "💰 SURPLUS REPLY"
    if any(k in s for k in ("cash offer", "off-market", "assignment", "wholesale")):
        return "🏠 WHOLESALE REPLY"
    if "kalshi" in f or "kalshi" in s:
        return "📈 KALSHI"
    if any(k in s for k in ("receipt", "invoice", "payment", "paypal")):
        return "💳 BILLING"
    if any(k in s for k in ("verification", "code", "otp", "one-time")):
        return "🔐 OTP/CODE"
    return "📧 GENERIC"


def format_forward(label: str, frm: str, subj: str, date: str, body: str) -> str:
    body_clean = body.replace("\r", " ").strip()
    if len(body_clean) > MAX_BODY:
        body_clean = body_clean[:MAX_BODY] + "…"
    return (
        f"{label} — NEW EMAIL\n\n"
        f"<b>From:</b> {html.escape(frm[:80])}\n"
        f"<b>Subject:</b> {html.escape(subj[:120])}\n"
        f"<b>Date:</b> {date[:30]}\n"
        f"\n{html.escape(body_clean)}"
    )


def run():
    log.info("=== Gmail → Telegram forwarder ===")
    if not SMTP_PASSWORD:
        log.error("No SMTP_PASSWORD — aborting")
        return
    state = load_state()
    seen = set(state["seen_ids"])
    forwarded_now = 0
    skipped = 0
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(SMTP_USER, SMTP_PASSWORD)
        M.select("inbox", readonly=True)  # never mark as read

        # Fetch all UIDs from today and yesterday to catch everything
        typ, data = M.uid("search", None, "SINCE", (datetime.now().strftime("%d-%b-%Y")))
        uids = data[0].split() if data and data[0] else []
        # Also check yesterday for boundary messages
        from datetime import timedelta
        yest = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        typ2, data2 = M.uid("search", None, "SINCE", yest)
        uids2 = data2[0].split() if data2 and data2[0] else []
        all_uids = list(dict.fromkeys(uids2 + uids))  # dedupe, preserve order
        log.info(f"Scanning {len(all_uids)} recent UIDs")

        for uid in all_uids:
            uid_str = uid.decode() if isinstance(uid, bytes) else uid
            if uid_str in seen:
                continue
            typ, msg_data = M.uid("fetch", uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            msg_id = msg.get("Message-ID", f"uid-{uid_str}").strip()
            if msg_id in seen or uid_str in seen:
                continue

            frm = decode(msg.get("From", ""))
            subj = decode(msg.get("Subject", "(no subject)"))
            date = msg.get("Date", "")
            body = extract_body(msg)
            label = classify(frm, subj, body)

            text = format_forward(label, frm, subj, date, body)
            ok = tg(text, "info")
            if ok:
                forwarded_now += 1
                seen.add(uid_str)
                seen.add(msg_id)
            else:
                skipped += 1

            if forwarded_now >= MAX_PER_RUN:
                log.warning(f"Hit per-run cap of {MAX_PER_RUN}, will continue next cycle")
                break

        M.logout()
    except Exception as e:
        log.exception(f"Forwarder error: {e}")
        tg(f"⚠️ Gmail forwarder error: {e}", "warning")
        return

    state["seen_ids"] = list(seen)
    state["last_run"] = datetime.utcnow().isoformat()
    state["forwarded_count"] = state.get("forwarded_count", 0) + forwarded_now
    save_state(state)

    log.info(f"Forwarded {forwarded_now} new, skipped {skipped}")
    return {"forwarded": forwarded_now, "skipped": skipped}


if __name__ == "__main__":
    run()
