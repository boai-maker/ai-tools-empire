"""
Stack Audit Engine — the $99 Claude-powered audit product.

Flow:
  1. Customer submits their current AI tool stack on /stack-audit
  2. Row is created in stack_audits table with status='awaiting_payment'
  3. Customer pays via Gumroad → admin flips status to 'paid'
     (either manually from admin UI, or via Gumroad webhook)
  4. This engine picks up 'paid' rows, runs the audit with Claude, emails
     the 3-line report + affiliate recommendations, sets status='delivered'

Runnable ad-hoc:
    python3 -m bots.stack_audit_engine
or scheduled (every 10 min) from run_bots.py.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event
from bots.shared.email_sender import send_email
from bots.shared.notifier import notify
from database.db import get_conn

logger = logging.getLogger(__name__)
BOT_NAME = "stack_audit_engine"

FORBIDDEN_CHARS = {"\u2014": ". ", "\u2013": " to "}


def _sanitize(text: str) -> str:
    for bad, good in FORBIDDEN_CHARS.items():
        text = text.replace(bad, good)
    return text


AUDIT_PROMPT = """You are auditing a paying customer's AI tool stack. They gave you $99 for a clear, specific 3-line audit: what to DROP, what to KEEP, and what to ADD.

Customer stack (as they pasted it):
---
{stack}
---

Context about our recommendation preferences (only mention when genuinely the best fit — never shoehorn):
- Pictory AI (pictory.ai) — excellent for repurposing written content into video. Good for content marketers, podcasters.
- ElevenLabs (elevenlabs.io) — best-in-class AI voice cloning + TTS. For creators, audio-first publishers.
- Murf AI (get.murf.ai) — conservative, voiceover-focused, used by e-learning and corporate.
- Fireflies (fireflies.ai) — meeting transcription + summaries. Highest value for sales teams, agencies, consultants.

Audit rules — DO NOT violate:
1. The three lines must be literal one-sentence recommendations with specific tool names, not generic categories.
2. If the customer is paying for duplicated tools in one category (e.g. ChatGPT Plus + Claude Pro), call out the exact duplication in the DROP line.
3. If nothing in the stack needs dropping, write "DROP: nothing — your stack is lean." Don't invent a drop.
4. The ADD line should match their workflow, not just pitch our affiliates. Only include our tools when they genuinely help.
5. NO em dashes in output. Use periods or commas.
6. NO "I hope this helps". NO "Let me know if...". NO follow-up questions.

Output strict JSON and nothing else:
{{
  "drop": "DROP: <specific tool(s) and one-sentence reason>",
  "keep": "KEEP: <specific tool(s) and one-sentence reason>",
  "add":  "ADD: <specific tool name, link if affiliate, and one-sentence reason>",
  "reasoning_notes": "<2-3 sentences of internal reasoning the operator sees but the customer does not>",
  "affiliate_links": ["pictory" | "elevenlabs" | "murf" | "fireflies"]
}}
"""


def run_audit(stack_text: str) -> dict:
    """Call Claude, return structured audit dict."""
    prompt = AUDIT_PROMPT.format(stack=stack_text.strip()[:2000])
    reply = (ask_claude(prompt, max_tokens=700) or "").strip()
    if reply.startswith("```"):
        reply = reply.strip("`")
        if reply.startswith("json"):
            reply = reply[4:].strip()
    try:
        data = json.loads(reply)
    except Exception as e:
        logger.warning(f"audit JSON parse failed: {e}; raw: {reply[:200]}")
        # Best-effort fallback — split into 3 roughly equal lines
        lines = [ln.strip() for ln in reply.splitlines() if ln.strip()]
        data = {
            "drop": lines[0] if lines else "DROP: Your stack needs a closer look. Reply with more detail.",
            "keep": lines[1] if len(lines) > 1 else "KEEP: Your highest-signal tool.",
            "add":  lines[2] if len(lines) > 2 else "ADD: See email body.",
            "reasoning_notes": "parser fallback",
            "affiliate_links": [],
        }
    for k in ("drop", "keep", "add"):
        data[k] = _sanitize(str(data.get(k, ""))).strip()
    return data


def _render_email_html(audit: dict, stack: str) -> str:
    affiliate_urls = {
        "pictory":    "https://aitoolsempire.co/go/pictory",
        "elevenlabs": "https://aitoolsempire.co/go/elevenlabs",
        "murf":       "https://aitoolsempire.co/go/murf",
        "fireflies":  "https://aitoolsempire.co/go/fireflies",
    }
    affiliate_links = audit.get("affiliate_links") or []
    cta_html = ""
    if affiliate_links:
        cta_items = []
        for key in affiliate_links:
            if key in affiliate_urls:
                cta_items.append(f'<a href="{affiliate_urls[key]}" style="color:#10b981;font-weight:600;">{key.title()}</a>')
        if cta_items:
            cta_html = (
                f'<p style="margin:24px 0 0;font-size:13px;color:#94a3b8;">'
                f'Tools mentioned above you can try directly: {" · ".join(cta_items)}'
                f'</p>'
            )
    return f"""\
<!DOCTYPE html><html><body style="font-family:-apple-system,Inter,sans-serif;background:#0f172a;color:#f8fafc;padding:32px;max-width:640px;margin:0 auto;">
<h1 style="font-size:22px;font-weight:800;margin:0 0 16px;color:#f8fafc;">Your AI stack audit</h1>
<p style="margin:0 0 24px;color:#94a3b8;font-size:14px;line-height:1.6;">
  Here's the 3-line audit you paid for. Short by design — you do not need another 2000-word report to know what to do on Monday morning.
</p>

<div style="background:#1e293b;border-left:4px solid #ef4444;padding:16px 20px;border-radius:8px;margin-bottom:12px;">
  <div style="font-size:12px;font-weight:700;color:#ef4444;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">DROP</div>
  <div style="color:#f8fafc;font-size:15px;line-height:1.5;">{audit.get('drop','')[:600]}</div>
</div>

<div style="background:#1e293b;border-left:4px solid #10b981;padding:16px 20px;border-radius:8px;margin-bottom:12px;">
  <div style="font-size:12px;font-weight:700;color:#10b981;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">KEEP</div>
  <div style="color:#f8fafc;font-size:15px;line-height:1.5;">{audit.get('keep','')[:600]}</div>
</div>

<div style="background:#1e293b;border-left:4px solid #f59e0b;padding:16px 20px;border-radius:8px;margin-bottom:12px;">
  <div style="font-size:12px;font-weight:700;color:#f59e0b;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">ADD</div>
  <div style="color:#f8fafc;font-size:15px;line-height:1.5;">{audit.get('add','')[:600]}</div>
</div>

{cta_html}

<p style="margin:32px 0 0;font-size:12px;color:#64748b;line-height:1.5;">
  Your stack, as you submitted it:<br>
  <span style="color:#94a3b8;white-space:pre-wrap;">{stack[:1500]}</span>
</p>

<hr style="border:none;border-top:1px solid #334155;margin:32px 0 16px;">
<p style="font-size:11px;color:#64748b;line-height:1.5;margin:0;">
  Questions? Reply to this email directly.<br>
  — Kenneth, AI Tools Empire
</p>
</body></html>"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add paid-flow columns to stack_audits table."""
    cur = conn.execute("PRAGMA table_info(stack_audits);")
    cols = {r[1] for r in cur.fetchall()}
    stmts = []
    if "paid_at" not in cols:
        stmts.append("ALTER TABLE stack_audits ADD COLUMN paid_at TEXT")
    if "gumroad_sale_id" not in cols:
        stmts.append("ALTER TABLE stack_audits ADD COLUMN gumroad_sale_id TEXT")
    if "audit_json" not in cols:
        stmts.append("ALTER TABLE stack_audits ADD COLUMN audit_json TEXT")
    if "delivered_at" not in cols:
        stmts.append("ALTER TABLE stack_audits ADD COLUMN delivered_at TEXT")
    for s in stmts:
        conn.execute(s)
    conn.commit()


def mark_paid(row_id: int, gumroad_sale_id: str = "") -> bool:
    conn = get_conn()
    try:
        _ensure_columns(conn)
        cur = conn.execute(
            "UPDATE stack_audits SET status='paid', paid_at=?, gumroad_sale_id=? "
            "WHERE id=? AND status IN ('pending','awaiting_payment')",
            (datetime.now(timezone.utc).isoformat(), gumroad_sale_id, row_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def mark_paid_by_email(email: str, gumroad_sale_id: str = "") -> int:
    """Fallback used by Gumroad webhook when all we have is the buyer's email.
    Marks the most recent unpaid submission for that email."""
    conn = get_conn()
    try:
        _ensure_columns(conn)
        row = conn.execute(
            "SELECT id FROM stack_audits WHERE email=? AND status IN ('pending','awaiting_payment') "
            "ORDER BY id DESC LIMIT 1",
            (email.lower().strip(),),
        ).fetchone()
        if not row:
            return 0
        cur = conn.execute(
            "UPDATE stack_audits SET status='paid', paid_at=?, gumroad_sale_id=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), gumroad_sale_id, row[0]),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def run_pending_audits(limit: int = 10) -> dict:
    conn = get_conn()
    _ensure_columns(conn)
    rows = conn.execute(
        "SELECT id, email, stack FROM stack_audits WHERE status='paid' "
        "AND (delivered_at IS NULL OR delivered_at = '') "
        "ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    processed = delivered = failed = 0
    for row in rows:
        processed += 1
        try:
            audit = run_audit(row["stack"])
            html = _render_email_html(audit, row["stack"])
            send_email(
                to=row["email"],
                subject="Your AI stack audit is ready",
                body_html=html,
            )
            conn.execute(
                "UPDATE stack_audits SET status='delivered', delivered_at=?, audit_json=?, audited_at=? WHERE id=?",
                (
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(audit),
                    datetime.now(timezone.utc).isoformat(),
                    row["id"],
                ),
            )
            conn.commit()
            log_bot_event(BOT_NAME, "delivered", f"id={row['id']} to {row['email']}")
            notify(f"📦 Stack Audit delivered to {row['email']} (id={row['id']})", level="money", use_telegram=True)
            delivered += 1
        except Exception as e:
            logger.exception(f"audit delivery failed for id={row['id']}: {e}")
            conn.execute(
                "UPDATE stack_audits SET status='failed' WHERE id=?",
                (row["id"],),
            )
            conn.commit()
            failed += 1
    conn.close()
    summary = {"processed": processed, "delivered": delivered, "failed": failed}
    if processed > 0:
        log_bot_event(BOT_NAME, "run", json.dumps(summary))
    return summary


def nudge_awaiting_payment(min_hours: float = 3, max_days: float = 7,
                            max_per_run: int = 5,
                            max_nudges_per_row: int = 3,
                            min_hours_between_nudges: float = 12) -> dict:
    """Abandoned-cart nudge for Stack Audit checkouts.

    Sends UP TO 3 reminders per row, spaced 12+ hours apart. Once a
    customer either pays (status flips to 'paid') OR hits the 3-nudge cap
    OR the row is older than max_days, no more reminders fire.

    Schema: `nudged_at` (timestamp of last nudge) + `nudge_count` (int).
    Both lazily ALTERed in if missing. Eligibility:
      - status in (awaiting_payment, pending)
      - >= min_hours since submission
      - <= max_days old
      - nudge_count < max_nudges_per_row
      - last nudge was either never OR >= min_hours_between_nudges ago

    From audit 2026-04-27: id=4 (5.8 days, pending) + id=7 (~26h,
    awaiting_payment) had been sitting with zero follow-up.
    """
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    _ensure_columns(conn)

    # Add nudge tracking columns lazily — don't fail if they already exist.
    cur = conn.execute("PRAGMA table_info(stack_audits);")
    cols = {r[1] for r in cur.fetchall()}
    for col_name, col_type in [("nudged_at", "TEXT"), ("nudge_count", "INTEGER DEFAULT 0")]:
        if col_name not in cols:
            try:
                conn.execute(f"ALTER TABLE stack_audits ADD COLUMN {col_name} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

    payment_url = (os.environ.get("STACK_AUDIT_PAYMENT_URL")
                   or "https://bosaibot.gumroad.com/l/euvbhm")

    cooldown_days = min_hours_between_nudges / 24.0

    # Eligibility: time-since-submit window + nudge cap + cooldown since last nudge.
    rows = conn.execute(
        """
        SELECT id, email, submitted_at, status,
               COALESCE(nudge_count, 0) AS n_count,
               nudged_at
        FROM stack_audits
        WHERE status IN ('awaiting_payment','pending')
          AND julianday('now') - julianday(submitted_at) BETWEEN ? AND ?
          AND COALESCE(nudge_count, 0) < ?
          AND (nudged_at IS NULL OR nudged_at = ''
               OR julianday('now') - julianday(nudged_at) >= ?)
        ORDER BY submitted_at ASC
        LIMIT ?
        """,
        (min_hours / 24.0, max_days, max_nudges_per_row, cooldown_days, max_per_run),
    ).fetchall()

    sent = 0
    skipped = 0
    for r in rows:
        try:
            html = _render_nudge_html(r["email"], payment_url, r["submitted_at"])
            send_email(
                to=r["email"],
                subject="Your AI Stack Audit is ready (just need payment)",
                body_html=html,
            )
            conn.execute(
                "UPDATE stack_audits SET nudged_at=?, "
                "nudge_count=COALESCE(nudge_count,0)+1 WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), r["id"]),
            )
            conn.commit()
            log_bot_event(BOT_NAME, "nudge_sent",
                          f"id={r['id']} to {r['email']} ({r['status']}) #{r['n_count']+1}")
            sent += 1
        except Exception as e:
            logger.exception(f"nudge failed id={r['id']}: {e}")
            skipped += 1

    conn.close()
    summary = {"sent": sent, "skipped": skipped, "candidates": len(rows)}
    if sent > 0:
        notify(
            f"📧 Stack Audit nudge: sent {sent} reminder(s) for abandoned checkouts.",
            level="info", use_telegram=True,
        )
    if rows:
        log_bot_event(BOT_NAME, "nudge_run", json.dumps(summary))
    return summary


def _render_nudge_html(email: str, payment_url: str, submitted_at: str) -> str:
    """Friendly, short. One CTA. Doesn't leak that this is automated chase —
    framed as a check-in that the audit is reserved and ready to run."""
    return f"""
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1a2438; line-height: 1.5;">
  <p>Hi —</p>
  <p>Quick check-in. You started a <strong>$99 AI Stack Audit</strong> on
  AI Tools Empire and we have your stack saved on our end, ready to run.</p>
  <p>It looks like the checkout didn't go through. If you still want it,
  here's the same link to complete it:</p>
  <p style="text-align: center; margin: 28px 0;">
    <a href="{payment_url}" style="display: inline-block; background: #10b981; color: #fff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 16px;">Complete checkout — $99</a>
  </p>
  <p style="font-size: 14px; color: #4a5874;">As a reminder, you'll get a
  full written audit of your AI stack within 24 hours: tools you're paying
  for that you should drop, free alternatives we'd swap in, and three
  workflows we'd add to claw back ~5 hours/week.</p>
  <p style="font-size: 13px; color: #6c84ad; margin-top: 28px;">
    If you're no longer interested, just ignore this — we won't bug you again.
    Reply with any questions.
  </p>
  <p style="font-size: 13px; color: #6c84ad;">— Kenneth, AI Tools Empire</p>
</body>
</html>
""".strip()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--nudge", action="store_true",
                   help="Run abandoned-cart nudges instead of audit delivery.")
    args = p.parse_args()
    if args.nudge:
        print(json.dumps(nudge_awaiting_payment(), indent=2))
    else:
        print(json.dumps(run_pending_audits(), indent=2))
