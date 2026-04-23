"""
PayPal Deposit Monitor
Scrapes bosaibot@gmail.com for PayPal "You've received a payment" emails and
fires an instant Telegram notification the moment money lands.

Every detected deposit is appended to bots/state/paypal_deposits.json so the
revenue_monitor can aggregate lifetime receipts without re-reading Gmail.

Runs every 15 minutes via the bots scheduler.
"""
from __future__ import annotations

import email
import imaplib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bots.shared.db_helpers import log_bot_event
from bots.shared.notifier import notify

load_dotenv()
logger = logging.getLogger(__name__)

BOT_NAME = "paypal_deposit_monitor"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

STATE_PATH = Path(__file__).parent / "state" / "paypal_deposits.json"
SEEN_UIDS_PATH = Path(__file__).parent / "state" / "paypal_seen_uids.json"

# Senders to watch
SENDER_DOMAINS = {"paypal.com", "email.paypal.com", "e.paypal.com", "service.paypal.com"}

# Subject patterns that indicate money IN (not outgoing, not disputes)
DEPOSIT_SUBJECT_PATTERNS = [
    r"you've got money",
    r"you've received",
    r"you received a payment",
    r"received .* payment",
    r"payment received",
    r"sent you \$",
    r"transfer of \$",
    r"deposited to your paypal",
    r"funds? are available",
]

# Subject patterns to IGNORE (refunds, outgoing payments, etc.)
IGNORE_SUBJECT_PATTERNS = [
    r"you sent",
    r"refund",
    r"reversed",
    r"dispute",
    r"your statement",
    r"security code",
    r"verification",
    r"welcome",
    r"monthly summary",
]

AMOUNT_REGEX = re.compile(r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")


def _decode_subject(s: str) -> str:
    parts = decode_header(s or "")
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _body_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
    else:
        try:
            return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def _extract_amount(text: str) -> Optional[float]:
    matches = AMOUNT_REGEX.findall(text)
    if not matches:
        return None
    # PayPal notification emails usually list the amount before "to you" or "in your balance"
    # First $ match is typically the deposit amount
    try:
        return float(matches[0].replace(",", ""))
    except ValueError:
        return None


def _matches_deposit(subject: str) -> bool:
    s = subject.lower()
    if any(re.search(pat, s) for pat in IGNORE_SUBJECT_PATTERNS):
        return False
    return any(re.search(pat, s) for pat in DEPOSIT_SUBJECT_PATTERNS)


def _load_json(p: Path, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default


def _save_json(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def run_paypal_deposit_monitor() -> dict:
    user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
    pw = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_PASSWORD")
    if not user or not pw:
        logger.error("no Gmail credentials available")
        return {"scanned": 0, "new_deposits": 0, "error": "no_credentials"}

    seen = set(_load_json(SEEN_UIDS_PATH, []))
    deposits = _load_json(STATE_PATH, [])

    new_deposits = []
    scanned = 0

    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        imap.login(user, pw)
        imap.select("INBOX")

        typ, data = imap.search(None, '(FROM "paypal.com")')
        if typ != "OK":
            logger.warning("IMAP search failed")
            imap.logout()
            return {"scanned": 0, "new_deposits": 0}

        uids = (data[0] or b"").split()
        recent = uids[-50:]  # scan last 50 only

        for raw_uid in recent:
            uid = raw_uid.decode()
            if uid in seen:
                continue
            scanned += 1
            typ, mdata = imap.fetch(raw_uid, "(RFC822)")
            if typ != "OK" or not mdata or not mdata[0]:
                seen.add(uid)
                continue
            msg = email.message_from_bytes(mdata[0][1])
            from_addr = parseaddr(msg.get("From", ""))[1].lower()
            domain = from_addr.split("@")[-1] if "@" in from_addr else ""
            if not any(domain.endswith(d) for d in SENDER_DOMAINS):
                seen.add(uid)
                continue

            subject = _decode_subject(msg.get("Subject", ""))
            if not _matches_deposit(subject):
                seen.add(uid)
                continue

            body = _body_text(msg)
            amount = _extract_amount(subject) or _extract_amount(body)
            if not amount or amount <= 0:
                seen.add(uid)
                continue

            try:
                received_at = parsedate_to_datetime(msg.get("Date", "")).isoformat()
            except Exception:
                received_at = datetime.now(timezone.utc).isoformat()

            deposit = {
                "uid": uid,
                "amount": amount,
                "subject": subject[:160],
                "from": from_addr,
                "received_at": received_at,
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }
            new_deposits.append(deposit)
            deposits.append(deposit)
            seen.add(uid)

            notify(
                f"💵 <b>PayPal deposit: ${amount:,.2f}</b>\n\n"
                f"<i>{subject[:120]}</i>\n\n"
                f"From: {from_addr}\n"
                f"At: {received_at}",
                level="money",
                use_telegram=True,
            )
            log_bot_event(BOT_NAME, "deposit", f"${amount} — {subject[:60]}")

        imap.logout()
    except Exception as e:
        logger.exception(f"PayPal monitor failed: {e}")
        return {"scanned": scanned, "new_deposits": len(new_deposits), "error": str(e)[:120]}

    _save_json(SEEN_UIDS_PATH, sorted(seen)[-500:])
    _save_json(STATE_PATH, deposits[-500:])

    return {"scanned": scanned, "new_deposits": len(new_deposits)}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    print(json.dumps(run_paypal_deposit_monitor(), indent=2))
