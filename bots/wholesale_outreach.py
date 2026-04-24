"""
Wholesale Outreach — Pipeline Hunter for motivated sellers.

Pulls eligible properties from the wholesale CRM, drafts a cash-offer email
via Claude, sends via Gmail SMTP, logs every send to the outreach table,
respects every hard rule in ai-tools-empire/CLAUDE.md:

- max 1 email per property per 48 hours
- max 5 follow-ups per day (initial contact has no cap)
- never contact bounced / bad emails (bounce_reaper's set)
- offer price always 5-10K BELOW asking
- no Proof of Funds mentioned (handled manually if seller asks)
- follow-up cadence: Day 1 → 3 → 7 → 14 → 30

Entry points:
    python3 -m bots.wholesale_outreach --dry-run           # show drafts only
    python3 -m bots.wholesale_outreach --dry-run --limit 5
    python3 -m bots.wholesale_outreach --live              # actually send
"""
from __future__ import annotations

import argparse
import email.utils
import json
import logging
import os
import smtplib
import sqlite3
import ssl
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event
from bots.shared.notifier import notify
from bots.bounce_reaper import get_bad_email_set

load_dotenv()
logger = logging.getLogger(__name__)

BOT_NAME = "wholesale_outreach"
WHOLESALE_DB = Path.home() / "Desktop" / "wholesale-re" / "crm" / "crm.db"
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_NAME = os.getenv("WHOLESALE_SENDER_NAME", "Kenneth Bonnet")

# CLAUDE.md hard rules
MIN_HOURS_BETWEEN = 48
MAX_FOLLOWUPS_PER_DAY = 5
FOLLOWUP_CADENCE_DAYS = [3, 7, 14, 30]
OFFER_DISCOUNT_LOW = 5000
OFFER_DISCOUNT_HIGH = 10000

ELIGIBLE_STATUSES = ("new", "lead", "qualified", "offered")

FORBIDDEN_CHARS = {"\u2014": ". ", "\u2013": " to ", "\u2012": "-", "\u2015": "-"}


def _sanitize(text: str) -> str:
    """Belt + suspenders: strip em/en dashes even if Claude slipped one in."""
    for bad, good in FORBIDDEN_CHARS.items():
        text = text.replace(bad, good)
    return text


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(WHOLESALE_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _has_email(prop: sqlite3.Row) -> Optional[str]:
    for fld in ("seller_email", "contact_email"):
        v = prop[fld] if fld in prop.keys() else None
        if v:
            v = v.strip()
            if v:
                return v
    return None


def _last_outreach(conn: sqlite3.Connection, property_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT sent_at, followup_sent, response FROM outreach "
        "WHERE property_id=? ORDER BY id DESC LIMIT 1",
        (property_id,),
    ).fetchone()
    return dict(row) if row else None


def _hours_since(ts_str: str) -> float:
    try:
        t = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except Exception:
        return 10_000.0
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600.0


def _followups_sent_today(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM outreach "
        "WHERE followup_sent >= 1 AND DATE(sent_at) = DATE('now')"
    ).fetchone()
    return int(row[0] or 0)


def _select_candidates(
    conn: sqlite3.Connection, bad_emails: set, limit: int
) -> tuple[list[dict], list[dict]]:
    """Returns (initial_candidates, followup_candidates)."""
    rows = conn.execute(
        f"SELECT * FROM properties WHERE status IN ({','.join('?' * len(ELIGIBLE_STATUSES))}) "
        "AND ((seller_email IS NOT NULL AND seller_email != '') "
        "OR (contact_email IS NOT NULL AND contact_email != '')) "
        "AND status != 'dead' "
        "ORDER BY created_at DESC",
        ELIGIBLE_STATUSES,
    ).fetchall()

    initials = []
    followups = []
    for row in rows:
        email_addr = _has_email(row)
        if not email_addr or email_addr.lower() in bad_emails:
            continue
        last = _last_outreach(conn, row["id"])
        if last is None:
            initials.append({"prop": dict(row), "email": email_addr})
            continue
        # Respect 48-hour floor
        if _hours_since(last["sent_at"]) < MIN_HOURS_BETWEEN:
            continue
        if last.get("response"):
            continue  # they replied — do not follow up
        sends_so_far = (last.get("followup_sent") or 0) + 1
        if sends_so_far > len(FOLLOWUP_CADENCE_DAYS):
            continue  # exhausted cadence
        # Check cadence day
        days_since = _hours_since(last["sent_at"]) / 24
        required_gap = FOLLOWUP_CADENCE_DAYS[sends_so_far - 1] if sends_so_far - 1 < len(FOLLOWUP_CADENCE_DAYS) else 30
        if days_since < required_gap:
            continue
        followups.append({"prop": dict(row), "email": email_addr, "step": sends_so_far})
        if len(initials) + len(followups) >= limit:
            break
    return initials[:limit], followups[: max(0, limit - len(initials))]


def _offer_range(prop: dict) -> tuple[int, int]:
    price = int(prop.get("price") or 0)
    if price <= 0:
        return (0, 0)
    return (max(0, price - OFFER_DISCOUNT_HIGH), max(0, price - OFFER_DISCOUNT_LOW))


def _draft_initial(prop: dict) -> dict:
    lo, hi = _offer_range(prop)
    offer_line = (
        f"My cash offer range for a fast close is ${lo:,} to ${hi:,}, "
        f"depending on condition at walk-through."
        if lo > 0
        else "I can put a cash offer together as soon as we're aligned on numbers."
    )
    motivation = prop.get("motivation") or prop.get("distress_signals") or ""
    motivation_line = (
        " If holding costs are part of what you are weighing, I can close in 7 to 14 days with no inspection contingency."
        if motivation else ""
    )
    prompt = f"""Write a short cold email to the owner of a distressed-looking property. You are a wholesale real estate investor offering a fast cash sale — 7-14 day close, no showings, no inspections.

Property:
- Address: {prop.get('address')}, {prop.get('city')}, {prop.get('state')}
- Asking price / last market price: ${int(prop.get('price') or 0):,}
- Beds/baths/sqft: {prop.get('beds')} / {prop.get('baths')} / {prop.get('sqft')}
- Year built: {prop.get('year_built') or 'unknown'}
- Known motivation signals: {motivation or 'none specified'}
- Seller contact name: {prop.get('seller_name') or prop.get('contact_name') or 'there'}

Include in the email:
1. A one-line intro that mentions the property address specifically.
2. A sentence showing you understand their likely pain (overdue repairs, tenant problems, long on market, relocation, etc.) — only if a motivation signal is present; otherwise keep it neutral.
3. This offer line verbatim: "{offer_line}"{motivation_line}
4. A frictionless next step: "worth a quick text or 10-minute call this week?"

Hard rules — DO NOT violate:
- Do NOT mention Proof of Funds. Ever. If they ask, the operator will handle manually.
- Do NOT invent contact details (phone numbers, extensions, DMs, company names) that are not provided in this prompt. If you don't have a phone number, do not add one — the sign-off is just the first name.
- ABSOLUTELY NO em dashes (—). Use a period or comma instead. This rule has zero exceptions. Re-read your body before returning and replace any em dash.
- No en dashes (–) either.
- No exclamation marks. No "I hope this finds you well". No "I hope this email finds you well".
- Keep it under 110 words.
- Sign off with first name only ({SENDER_NAME.split()[0]}) on its own line. Nothing after it.
- Subject line: 4-6 words, natural, address-anchored or pain-anchored.

Output strict JSON and nothing else:
{{"subject": "...", "body": "..."}}"""
    reply = ask_claude(prompt, max_tokens=600) or ""
    reply = reply.strip()
    if reply.startswith("```"):
        reply = reply.strip("`")
        if reply.startswith("json"):
            reply = reply[4:].strip()
    try:
        data = json.loads(reply)
        return {"subject": _sanitize(data["subject"].strip()), "body": _sanitize(data["body"].strip())}
    except Exception:
        lines = [ln for ln in reply.splitlines() if ln.strip()]
        return {"subject": _sanitize((lines[0] if lines else f"Quick question on {prop.get('address')}")[:80]), "body": _sanitize("\n".join(lines[1:] or [reply]))}


def _draft_followup(prop: dict, step: int) -> dict:
    lo, hi = _offer_range(prop)
    prompt = f"""Write a short follow-up to an earlier cold email about buying a property for cash. This is follow-up #{step} in a Day 3 → 7 → 14 → 30 cadence. They have NOT replied to any previous message. Be shorter and more direct than the initial.

Property:
- Address: {prop.get('address')}, {prop.get('city')}, {prop.get('state')}
- Asking price: ${int(prop.get('price') or 0):,}
- Offer range: ${lo:,} — ${hi:,}
- Seller contact name: {prop.get('seller_name') or prop.get('contact_name') or 'there'}

Rules:
- Open with one line referencing the address and that you sent a note earlier.
- Single sentence re-stating the cash offer range.
- Single-sentence close: "Still open to chat, or should I stop emailing?" — give them an easy out.
- Under 70 words. NO em dashes (—). NO en dashes (–). Use periods. No exclamation marks. No Proof of Funds.
- Do NOT invent phone numbers or contact details not in this prompt.
- Sign off with first name only ({SENDER_NAME.split()[0]}) on its own line.
- Subject line: prefix "Re: " then 3-5 words.

Output strict JSON only:
{{"subject": "...", "body": "..."}}"""
    reply = ask_claude(prompt, max_tokens=400) or ""
    reply = reply.strip()
    if reply.startswith("```"):
        reply = reply.strip("`")
        if reply.startswith("json"):
            reply = reply[4:].strip()
    try:
        data = json.loads(reply)
        return {"subject": _sanitize(data["subject"].strip()), "body": _sanitize(data["body"].strip())}
    except Exception:
        lines = [ln for ln in reply.splitlines() if ln.strip()]
        return {"subject": _sanitize((lines[0] if lines else f"Re: {prop.get('address')}")[:80]), "body": _sanitize("\n".join(lines[1:] or [reply]))}


def _send_smtp(to_email: str, subject: str, body: str) -> str:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email.utils.formataddr((SENDER_NAME, SMTP_USER))
    msg["To"] = to_email
    msg["Reply-To"] = SMTP_USER
    message_id = email.utils.make_msgid(domain=SMTP_USER.split("@")[-1])
    msg["Message-ID"] = message_id
    msg.attach(MIMEText(body, "plain", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)
    return message_id


def _log_outreach(conn, property_id: int, subject: str, body: str, step: int) -> None:
    conn.execute(
        "INSERT INTO outreach(property_id, email_subject, email_body, sent_at, followup_sent, status) "
        "VALUES (?, ?, ?, ?, ?, 'sent')",
        (property_id, subject, body, datetime.now(timezone.utc).isoformat(), step),
    )
    conn.execute(
        "INSERT INTO activities(property_id, activity_type, summary, details, created_at) "
        "VALUES (?, 'outreach_sent', ?, ?, ?)",
        (
            property_id,
            f"wholesale outreach step {step}: {subject[:80]}",
            json.dumps({"subject": subject, "body_preview": body[:300]}),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def run_wholesale_outreach(dry_run: bool = True, limit: int = 25) -> dict:
    if not WHOLESALE_DB.exists():
        return {"error": "CRM DB not found"}
    if not dry_run and (not SMTP_USER or not SMTP_PASSWORD):
        return {"error": "SMTP creds missing"}

    bad_emails = set(get_bad_email_set())
    logger.info(f"bad_emails loaded: {len(bad_emails)} suppressed")

    conn = _conn()
    initials, followups = _select_candidates(conn, bad_emails, limit)
    followups_today = _followups_sent_today(conn)
    followups_slots = max(0, MAX_FOLLOWUPS_PER_DAY - followups_today)
    followups = followups[:followups_slots]

    drafts = []
    sent = skipped = failed = 0

    def _handle(prop_pack, step, is_followup):
        nonlocal sent, skipped, failed
        prop = prop_pack["prop"]
        addr = prop_pack["email"]
        try:
            drafter = _draft_followup if is_followup else _draft_initial
            draft = drafter(prop, step) if is_followup else drafter(prop)
        except Exception as e:
            logger.warning(f"draft failed for {addr}: {e}")
            failed += 1
            return
        draft.update({
            "to": addr,
            "property_id": prop["id"],
            "address": f"{prop.get('address')}, {prop.get('city')}, {prop.get('state')}",
            "is_followup": is_followup,
            "step": step,
        })
        drafts.append(draft)
        if dry_run:
            skipped += 1
            return
        try:
            _send_smtp(addr, draft["subject"], draft["body"])
            _log_outreach(conn, prop["id"], draft["subject"], draft["body"], step)
            sent += 1
            time.sleep(180)  # pace ~20/hr
        except Exception as e:
            logger.exception(f"send failed to {addr}: {e}")
            failed += 1

    for item in initials:
        _handle(item, step=0, is_followup=False)
    for item in followups:
        _handle(item, step=item["step"], is_followup=True)

    conn.close()

    summary = {
        "dry_run": dry_run,
        "bad_emails_suppressed": len(bad_emails),
        "initials_considered": len(initials),
        "followups_considered": len(followups),
        "followups_today_already": followups_today,
        "drafts": drafts[:limit],
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
    }

    log_bot_event(BOT_NAME, "run", json.dumps({k: v for k, v in summary.items() if k != "drafts"}))

    if not dry_run and sent > 0:
        notify(
            f"📬 Wholesale outreach: {sent} sent ({len(initials)} initial / "
            f"{len(followups)} follow-up), {failed} failed, "
            f"{len(bad_emails)} bad emails suppressed.",
            level="money",
            use_telegram=True,
        )
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    live = args.live and not args.dry_run
    print(json.dumps(run_wholesale_outreach(dry_run=not live, limit=args.limit), indent=2, default=str))
