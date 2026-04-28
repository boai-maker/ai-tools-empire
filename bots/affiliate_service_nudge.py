"""Abandoned-cart nudge for the $29 AI Affiliate Application Service.

Sister of bots/stack_audit_engine.py:nudge_awaiting_payment — same pattern,
different table. Targets affiliate_service_orders rows in 'awaiting_payment'
status > 12h and < 7d old, sends ONE reminder, marks `nudged_at`.

Wired to a daily 11:15am ET cron in run_bots.py (15 min after stack-audit
nudge so they don't both fire at the exact same minute).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from bots.shared.db_helpers import log_bot_event
from bots.shared.email_sender import send_email
from bots.shared.notifier import notify
from database.db import get_conn

BOT_NAME = "affiliate_service_nudge"
logger = logging.getLogger(BOT_NAME)


def _render_nudge_html(email: str, payment_url: str, site_url: str) -> str:
    return f"""<!DOCTYPE html>
<html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; color: #1a2438; line-height: 1.5;">
  <p>Hi —</p>
  <p>Quick check-in. You started a <strong>$29 AI Affiliate Application Service</strong>
  order on AI Tools Empire ({site_url}) and we've got your details ready to go.</p>
  <p>It looks like the checkout didn't go through. Same link to complete it:</p>
  <p style="text-align: center; margin: 28px 0;">
    <a href="{payment_url}" style="display: inline-block; background: #10b981; color: #fff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 16px;">Complete checkout — $29</a>
  </p>
  <p style="font-size: 14px; color: #4a5874;">As a reminder, you'll get applications to 30+ vetted AI affiliate programs submitted within 48 hours, plus a status report at day 7 and day 30.</p>
  <p style="font-size: 13px; color: #6c84ad; margin-top: 28px;">If you're no longer interested, just ignore this — we won't bug you again. Reply with any questions.</p>
  <p style="font-size: 13px; color: #6c84ad;">— Kenneth, AI Tools Empire</p>
</body></html>""".strip()


def nudge_awaiting_payment(min_hours: float = 3, max_days: float = 7,
                            max_per_run: int = 5,
                            max_nudges_per_row: int = 3,
                            min_hours_between_nudges: float = 12) -> dict:
    """Up to 3 reminders per row, 12+ hours apart. Sister of
    bots/stack_audit_engine.py:nudge_awaiting_payment."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row

    # Add nudge tracking columns lazily.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(affiliate_service_orders);").fetchall()}
    for col_name, col_type in [("nudged_at", "TEXT"), ("nudge_count", "INTEGER DEFAULT 0")]:
        if col_name not in cols:
            try:
                conn.execute(
                    f"ALTER TABLE affiliate_service_orders ADD COLUMN {col_name} {col_type}"
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass

    payment_url = os.environ.get(
        "AFFILIATE_SERVICE_PAYMENT_URL", "https://bosaibot.gumroad.com/l/jpsrxd"
    )

    cooldown_days = min_hours_between_nudges / 24.0

    rows = conn.execute(
        """
        SELECT id, email, site_url, submitted_at,
               COALESCE(nudge_count, 0) AS n_count
        FROM affiliate_service_orders
        WHERE status = 'awaiting_payment'
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
    for r in rows:
        try:
            html = _render_nudge_html(r["email"], payment_url, r["site_url"] or "your site")
            send_email(
                to=r["email"],
                subject="Your AI Affiliate Application Service is ready (just need payment)",
                body_html=html,
            )
            conn.execute(
                "UPDATE affiliate_service_orders SET nudged_at=?, "
                "nudge_count=COALESCE(nudge_count,0)+1 WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), r["id"]),
            )
            conn.commit()
            log_bot_event(BOT_NAME, "nudge_sent",
                          f"id={r['id']} to {r['email']} #{r['n_count']+1}")
            sent += 1
        except Exception as e:
            logger.exception(f"affiliate_service nudge failed id={r['id']}: {e}")

    conn.close()
    summary = {"sent": sent, "candidates": len(rows)}
    if sent > 0:
        notify(
            f"📧 Affiliate Service nudge: sent {sent} reminder(s) for abandoned $29 checkouts.",
            level="info", use_telegram=True,
        )
    if rows:
        log_bot_event(BOT_NAME, "nudge_run", json.dumps(summary))
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    print(json.dumps(nudge_awaiting_payment(), indent=2))
