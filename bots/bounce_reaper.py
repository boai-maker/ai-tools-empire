"""
Bounce Reaper
Scans Gmail's [Gmail]/Trash folder for deleted messages tied to bounced
outreach and marks the corresponding leads in the wholesale CRM as dead so
the Pipeline Hunter never emails them again.

Detection strategy — we treat a trash message as a bounce signal if ANY of:
  (a) sender is a known mailer-daemon / bounce responder domain
  (b) subject matches a bounce / undeliverable / does-not-exist pattern
  (c) body contains one of the phrases Kenneth explicitly mentioned
      (e.g. "email is no longer active", "no longer at this address")

From each matching message we extract candidate email addresses:
  - original-recipient / final-recipient headers (RFC 3464)
  - the most common "@" tokens in the body
  - X-Failed-Recipients header

Every candidate is:
  - added to a persisted "do not email" list (bots/state/bad_emails.json)
  - if it matches a row in ~/Desktop/wholesale-re/crm/crm.db, the property's
    seller_email / contact_email is cleared and status is set to 'dead' with
    a note recording the reaper run time.

Safe to run repeatedly — UIDs and emails are deduped against prior state.
"""
from __future__ import annotations

import email
import imaplib
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Iterable, Set

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bots.shared.db_helpers import log_bot_event
from bots.shared.notifier import notify

load_dotenv()
logger = logging.getLogger(__name__)

BOT_NAME = "bounce_reaper"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
WHOLESALE_DB = Path.home() / "Desktop" / "wholesale-re" / "crm" / "crm.db"
BAD_EMAILS_PATH = Path(__file__).parent / "state" / "bad_emails.json"
SEEN_UIDS_PATH = Path(__file__).parent / "state" / "bounce_reaper_seen_uids.json"

# Strong bounce signals
MAILER_DOMAINS = (
    "mailer-daemon", "postmaster", "bounce", "notify.googledomains",
)
BOUNCE_SUBJECT_PATTERNS = [
    r"undelivered",
    r"undeliverable",
    r"delivery.*(failed|failure|notification|status)",
    r"mail delivery (failed|subsystem|failure)",
    r"returned mail",
    r"could not be delivered",
    r"failure notice",
    r"rejected your message",
    r"address (rejected|not found)",
    r"no longer (works|active|in service)",
    r"does not exist",
]
BOUNCE_BODY_PATTERNS = [
    r"no longer (works|valid|active|in service)",
    r"email (is|address is) no longer",
    r"does not exist",
    r"user unknown",
    r"no such user",
    r"recipient (address|not found)",
    r"address rejected",
    r"mailbox (full|unavailable|not found)",
    r"undelivered mail returned to sender",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Domains we *never* treat as bad recipients even when they appear in a
# bounce (our own, plus common platform / no-reply senders).
IGNORED_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "mail.google.com",
    "aitoolsempire.co",
    "aitoolsempire.com",
    "bosaibot@gmail.com",
}
IGNORED_LOCAL_PREFIXES = ("noreply", "no-reply", "mailer-daemon", "postmaster", "bounces")


def _load_set(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()))
    except Exception:
        return set()


def _save_set(path: Path, values: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(values), indent=2))


def _extract_candidate_emails(msg: email.message.Message, subject: str, body: str) -> Set[str]:
    candidates: Set[str] = set()

    for header in ("X-Failed-Recipients", "Original-Recipient", "Final-Recipient", "Delivered-To"):
        v = msg.get(header, "")
        if v:
            for found in EMAIL_RE.findall(v):
                candidates.add(found.lower())

    for found in EMAIL_RE.findall(subject or ""):
        candidates.add(found.lower())
    for found in EMAIL_RE.findall(body or ""):
        candidates.add(found.lower())

    # Filter: drop our own domains + mailer daemons
    cleaned = set()
    for e in candidates:
        if not e or "@" not in e:
            continue
        local, _, domain = e.partition("@")
        if domain in IGNORED_DOMAINS:
            continue
        if any(local.startswith(p) for p in IGNORED_LOCAL_PREFIXES):
            continue
        cleaned.add(e)
    return cleaned


def _body_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    continue
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )
    except Exception:
        return ""


def _looks_like_bounce(from_addr: str, subject: str, body: str) -> bool:
    sender = (from_addr or "").lower()
    if any(d in sender for d in MAILER_DOMAINS):
        return True
    s = (subject or "").lower()
    if any(re.search(p, s) for p in BOUNCE_SUBJECT_PATTERNS):
        return True
    b = (body or "").lower()[:4000]
    if any(re.search(p, b) for p in BOUNCE_BODY_PATTERNS):
        return True
    return False


def _mark_dead_in_crm(bad_emails: Set[str]) -> dict:
    if not WHOLESALE_DB.exists() or not bad_emails:
        return {"updated": 0, "emails_cleared": 0}
    conn = sqlite3.connect(str(WHOLESALE_DB))
    conn.row_factory = sqlite3.Row
    updated = 0
    cleared = 0
    note = f"marked dead by bounce_reaper at {datetime.now(timezone.utc).isoformat()}"
    try:
        for addr in sorted(bad_emails):
            rows = conn.execute(
                "SELECT id, address, seller_email, contact_email, status, notes "
                "FROM properties "
                "WHERE LOWER(seller_email)=? OR LOWER(contact_email)=?",
                (addr.lower(), addr.lower()),
            ).fetchall()
            for row in rows:
                new_notes = ((row["notes"] or "") + "\n" + note).strip()
                conn.execute(
                    "UPDATE properties SET "
                    "seller_email=NULL, contact_email=NULL, status='dead', notes=? "
                    "WHERE id=?",
                    (new_notes, row["id"]),
                )
                updated += 1
                cleared += sum(1 for c in (row["seller_email"], row["contact_email"]) if c)
                log_bot_event(
                    BOT_NAME,
                    "crm_marked_dead",
                    f"{row['address']} ({addr}) — previously {row['status']}",
                )
        conn.commit()
    finally:
        conn.close()
    return {"updated": updated, "emails_cleared": cleared}


def run_bounce_reaper() -> dict:
    user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
    pw = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_PASSWORD")
    if not user or not pw:
        return {"error": "no_credentials"}

    seen = _load_set(SEEN_UIDS_PATH)
    bad = _load_set(BAD_EMAILS_PATH)

    scanned = bounces = new_bad = 0

    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(user, pw)
        # Gmail's All-Mail and Trash are reached via its special labels
        for mailbox in ('"[Gmail]/Trash"', '"[Gmail]/Bin"'):
            typ, _ = imap.select(mailbox, readonly=True)
            if typ != "OK":
                continue
            typ, data = imap.search(None, "ALL")
            if typ != "OK":
                continue
            uids = (data[0] or b"").split()
            for raw_uid in uids[-200:]:
                uid_key = f"{mailbox}:{raw_uid.decode()}"
                if uid_key in seen:
                    continue
                scanned += 1
                typ, mdata = imap.fetch(raw_uid, "(RFC822)")
                if typ != "OK" or not mdata or not mdata[0]:
                    seen.add(uid_key)
                    continue
                msg = email.message_from_bytes(mdata[0][1])
                from_addr = parseaddr(msg.get("From", ""))[1].lower()
                subject = msg.get("Subject", "")
                body = _body_text(msg)
                if not _looks_like_bounce(from_addr, subject, body):
                    seen.add(uid_key)
                    continue
                bounces += 1
                for addr in _extract_candidate_emails(msg, subject, body):
                    if addr not in bad:
                        bad.add(addr)
                        new_bad += 1
                seen.add(uid_key)
            imap.close()
        imap.logout()
    except Exception as e:
        logger.exception(f"bounce_reaper IMAP: {e}")
        return {"error": str(e)[:200]}

    _save_set(SEEN_UIDS_PATH, seen)
    _save_set(BAD_EMAILS_PATH, bad)

    crm = _mark_dead_in_crm(bad)

    msg = (
        f"🧹 Bounce reaper — scanned {scanned} trash msgs | "
        f"bounce hits: {bounces} | new bad emails: {new_bad} | "
        f"CRM rows marked dead: {crm['updated']} | emails wiped: {crm['emails_cleared']}"
    )
    logger.info(msg)
    if bounces > 0 or crm["updated"] > 0:
        notify(msg, level="info", use_telegram=True)
    log_bot_event(BOT_NAME, "run", msg)

    return {
        "scanned_trash": scanned,
        "bounce_hits": bounces,
        "new_bad_emails": new_bad,
        "crm_rows_marked_dead": crm["updated"],
        "emails_wiped": crm["emails_cleared"],
        "bad_emails_total": len(bad),
    }


def get_bad_email_set() -> Set[str]:
    """Loaded lazily by Pipeline Hunter's pre_send_check to skip known bounces."""
    return _load_set(BAD_EMAILS_PATH)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    print(json.dumps(run_bounce_reaper(), indent=2))
