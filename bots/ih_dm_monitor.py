"""
Indie Hackers DM Monitor.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Polls bosaibot@gmail.com over IMAP for Indie Hackers notification emails.
Detects DMs by subject pattern, extracts sender / message / thread URL,
inserts pending rows into the `ih_dms` table for the drafter to handle.

Re-uses the Gmail credentials from `bots/gmail_telegram_forwarder.py`.
Never marks emails as read.
"""
from __future__ import annotations
import os
import re
import sys
import json
import imaplib
import email
import html
from email.header import decode_header
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bots.shared.standards import get_logger, tg, STATE_DIR
from database.db import get_conn

log = get_logger("ih_dm_monitor")
STATE_FILE = os.path.join(STATE_DIR, "ih_dm_monitor.json")
SMTP_USER = os.getenv("SMTP_USER", "bosaibot@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

MAX_PER_RUN = 30

# Subject patterns that indicate an Indie Hackers DM/reply notification.
IH_SUBJECT_PATTERNS = [
    re.compile(r"messaged you on Indie Hackers", re.IGNORECASE),
    re.compile(r"new message from", re.IGNORECASE),
    re.compile(r"your post got a reply", re.IGNORECASE),
    re.compile(r"you have a new message", re.IGNORECASE),
    re.compile(r"replied to your", re.IGNORECASE),
    re.compile(r"on (your )?Indie Hackers", re.IGNORECASE),
]

IH_FROM_HINT = re.compile(r"indiehackers\.com|indie hackers", re.IGNORECASE)

THREAD_URL_RE = re.compile(
    r"https?://(?:www\.)?indiehackers\.com/(?:[^\s\"'<>]+)",
    re.IGNORECASE,
)


def ensure_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ih_dms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_uid TEXT UNIQUE,
            sender TEXT,
            message_text TEXT,
            thread_url TEXT,
            received_at TEXT DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            draft_reply TEXT,
            draft_confidence REAL,
            approved_at TEXT,
            sent_at TEXT,
            send_method TEXT
        )
    """)
    conn.commit()
    conn.close()


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen_uids": [], "last_run": None, "queued_count": 0}
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"seen_uids": [], "last_run": None, "queued_count": 0}


def save_state(state):
    state["seen_uids"] = state["seen_uids"][-3000:]
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def decode_str(raw: str) -> str:
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


def is_ih_dm(frm: str, subj: str, body: str) -> bool:
    """Heuristic — subject matches IH DM pattern OR sender is IH + body has DM markers."""
    s = subj or ""
    f = frm or ""
    for pat in IH_SUBJECT_PATTERNS:
        if pat.search(s):
            return True
    if IH_FROM_HINT.search(f) and re.search(r"message|reply|replied|comment", s, re.IGNORECASE):
        return True
    return False


def parse_sender(subject: str, body: str) -> str:
    """Extract the IH username from subject like '<sender> messaged you on Indie Hackers'."""
    if not subject:
        subject = ""
    m = re.match(r"^([^,]+?)\s+(?:messaged|replied|commented|sent)", subject, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"new message from\s+(.+?)(?:\s+on|\s*$)", subject, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback — try body
    m = re.search(r"(?:from|by)\s+([A-Za-z0-9_\-]+)", body or "")
    if m:
        return m.group(1).strip()
    return "(unknown)"


def parse_thread_url(body: str) -> str:
    if not body:
        return ""
    matches = THREAD_URL_RE.findall(body)
    # Prefer URLs that look thread-y over generic homepage links
    preferred = [u for u in matches if any(seg in u.lower() for seg in ("/post/", "/comment", "/message", "/thread", "/m/", "/inbox"))]
    if preferred:
        return preferred[0].strip(".,)>\"'")
    if matches:
        return matches[0].strip(".,)>\"'")
    return ""


def parse_message_text(body: str) -> str:
    """Pull the quoted message body from the IH email. Falls back to the first ~600 chars."""
    if not body:
        return ""
    # IH notifications typically wrap message between quotes or after 'said:'.
    m = re.search(r'(?:said|wrote|messaged)[:\s]+["“]?(.{20,800}?)["”]?(?:\s*(?:View|Reply|Open in)|\Z)', body, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    # Strip footer noise
    cleaned = re.sub(r"unsubscribe.*$", "", body, flags=re.IGNORECASE | re.DOTALL).strip()
    return cleaned[:600]


def insert_dm(email_uid: str, sender: str, message_text: str, thread_url: str) -> int | None:
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO ih_dms (email_uid, sender, message_text, thread_url, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (email_uid, sender, message_text, thread_url))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        # UNIQUE constraint (already inserted) — ignore
        log.debug(f"insert skipped for uid={email_uid}: {e}")
        return None
    finally:
        conn.close()


def run():
    log.info("=== IH DM Monitor ===")
    if not SMTP_PASSWORD:
        log.error("No SMTP_PASSWORD — aborting")
        return {"queued": 0, "scanned": 0, "error": "no_smtp"}

    ensure_table()
    state = load_state()
    seen = set(state.get("seen_uids", []))
    queued = 0
    scanned = 0

    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com")
        M.login(SMTP_USER, SMTP_PASSWORD)
        M.select("inbox", readonly=True)

        today = datetime.now().strftime("%d-%b-%Y")
        yest = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
        typ, data = M.uid("search", None, "SINCE", yest)
        uids = data[0].split() if data and data[0] else []
        log.info(f"Scanning {len(uids)} UIDs since {yest}")

        for uid in uids:
            uid_str = uid.decode() if isinstance(uid, bytes) else uid
            if uid_str in seen:
                continue
            scanned += 1
            typ, msg_data = M.uid("fetch", uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            frm = decode_str(msg.get("From", ""))
            subj = decode_str(msg.get("Subject", ""))
            body = extract_body(msg)

            if not is_ih_dm(frm, subj, body):
                seen.add(uid_str)
                continue

            sender = parse_sender(subj, body)
            thread_url = parse_thread_url(body)
            message_text = parse_message_text(body)

            new_id = insert_dm(uid_str, sender, message_text, thread_url)
            if new_id:
                queued += 1
                log.info(f"Queued IH DM #{new_id} from {sender} (uid={uid_str})")
            seen.add(uid_str)

            if queued >= MAX_PER_RUN:
                log.warning(f"Hit per-run cap of {MAX_PER_RUN}")
                break

        M.logout()
    except Exception as e:
        log.exception(f"Monitor error: {e}")
        tg(f"⚠️ IH DM monitor error: {e}", "warning")
        return {"queued": queued, "scanned": scanned, "error": str(e)}

    state["seen_uids"] = list(seen)
    state["last_run"] = datetime.utcnow().isoformat()
    state["queued_count"] = state.get("queued_count", 0) + queued
    save_state(state)

    log.info(f"Queued {queued} new IH DMs (scanned {scanned})")
    return {"queued": queued, "scanned": scanned}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
