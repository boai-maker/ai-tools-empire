"""
Indie Hackers DM Sender.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sends approved DM replies. Two modes:

A. Playwright + saved storage_state at ~/.config/ih_session.json
   (preferred — fully automatic).
B. Telegram-tap fallback — if no session file, send Kenneth the
   thread URL + reply text in a copy-paste block.

Run once interactively to capture the session:
   python -m bots.ih_dm_sender --capture-session
"""
from __future__ import annotations
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bots.shared.standards import get_logger, tg
from database.db import get_conn

log = get_logger("ih_dm_sender")

SESSION_PATH = Path.home() / ".config" / "ih_session.json"
PLAYWRIGHT_TIMEOUT = 25_000  # ms


def fetch_dm(dm_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM ih_dms WHERE id=?", (dm_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_sent(dm_id: int, method: str, auto: bool = False):
    conn = get_conn()
    method_label = f"auto_{method}" if auto else method
    conn.execute(
        "UPDATE ih_dms SET status='sent', sent_at=CURRENT_TIMESTAMP, send_method=? WHERE id=?",
        (method_label, dm_id),
    )
    conn.commit()
    conn.close()


def have_session() -> bool:
    return SESSION_PATH.exists() and SESSION_PATH.stat().st_size > 50


def send_via_playwright(thread_url: str, reply: str) -> tuple[bool, str]:
    """Open IH thread with saved cookies, type reply, click send. Returns (success, error)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright not installed (pip install playwright && playwright install chromium)"

    if not thread_url:
        return False, "no thread URL"
    if not have_session():
        return False, "no session file"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(SESSION_PATH))
            page = context.new_page()
            page.set_default_timeout(PLAYWRIGHT_TIMEOUT)
            page.goto(thread_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            # Try a few possible selectors for IH's reply input.
            selectors = [
                "textarea[placeholder*='reply' i]",
                "textarea[placeholder*='message' i]",
                "textarea[placeholder*='comment' i]",
                "div[contenteditable='true']",
                "textarea",
            ]
            input_handle = None
            for sel in selectors:
                try:
                    input_handle = page.wait_for_selector(sel, timeout=3000)
                    if input_handle:
                        break
                except Exception:
                    continue

            if not input_handle:
                browser.close()
                return False, "could not find reply input on page"

            input_handle.click()
            input_handle.fill(reply)
            page.wait_for_timeout(500)

            # Click Send / Reply / Submit button.
            btn_texts = ["Send", "Reply", "Post", "Submit", "Comment"]
            clicked = False
            for txt in btn_texts:
                try:
                    btn = page.get_by_role("button", name=txt, exact=False)
                    if btn and btn.count() > 0:
                        btn.first.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                # Last resort — Cmd/Ctrl+Enter
                page.keyboard.press("Meta+Enter")

            page.wait_for_timeout(2500)
            browser.close()
            return True, ""
    except Exception as e:
        return False, str(e)


def send_via_telegram_tap(dm: dict, reply: str) -> bool:
    thread = dm.get("thread_url") or "(no thread URL parsed — search inbox on indiehackers.com)"
    msg = (
        f"✅ Approved DM #{dm['id']} → <b>{dm['sender']}</b>\n"
        f"Open thread: {thread}\n\n"
        f"<b>Reply (copy-paste):</b>\n"
        f"<pre>{reply}</pre>"
    )
    return tg(msg, level="success")


def send_one(dm_id: int, auto: bool = False) -> dict:
    """Send a single approved DM. Returns dict with sent/method/error."""
    dm = fetch_dm(dm_id)
    if not dm:
        return {"sent": False, "error": "not_found"}
    if dm["status"] not in ("approved", "drafted"):
        # Allow drafted only if explicitly auto (drafter just promoted it)
        if not (auto and dm["status"] == "approved"):
            log.info(f"DM #{dm_id} status={dm['status']} — skip send")
            return {"sent": False, "error": f"bad_status:{dm['status']}"}
    reply = dm.get("draft_reply") or ""
    if not reply.strip():
        return {"sent": False, "error": "empty_reply"}

    if have_session() and dm.get("thread_url"):
        ok, err = send_via_playwright(dm["thread_url"], reply)
        if ok:
            mark_sent(dm_id, "playwright", auto=auto)
            log.info(f"DM #{dm_id} sent via Playwright")
            return {"sent": True, "method": "playwright"}
        log.warning(f"Playwright send failed for DM #{dm_id}: {err}. Falling back to telegram_tap.")
        tg(f"⚠️ Playwright IH send failed for DM #{dm_id}: {err}. Falling back to manual.", "warning")

    # Fallback
    if send_via_telegram_tap(dm, reply):
        mark_sent(dm_id, "telegram_tap", auto=auto)
        log.info(f"DM #{dm_id} handed to Kenneth via Telegram tap")
        return {"sent": True, "method": "telegram_tap"}
    return {"sent": False, "error": "telegram_failed"}


def send_all_approved() -> dict:
    """Loop through every status='approved' row and try to send."""
    conn = get_conn()
    rows = conn.execute("SELECT id FROM ih_dms WHERE status='approved'").fetchall()
    conn.close()
    sent = 0
    failed = 0
    for r in rows:
        result = send_one(r["id"], auto=False)
        if result.get("sent"):
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed}


def capture_session():
    """One-time: launch headed Chromium, let Kenneth log in, save cookies."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Launching Chromium. Log in at indiehackers.com, then come back here and press Enter.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.indiehackers.com/login")
        input("Press Enter after logging in...")
        context.storage_state(path=str(SESSION_PATH))
        browser.close()
    print(f"Session saved to {SESSION_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-session", action="store_true", help="One-time login to save cookies.")
    parser.add_argument("--send", type=int, default=None, help="Send a specific DM id.")
    parser.add_argument("--send-all", action="store_true", help="Send all approved DMs.")
    args = parser.parse_args()

    if args.capture_session:
        capture_session()
    elif args.send is not None:
        result = send_one(args.send)
        print(json.dumps(result, indent=2))
    elif args.send_all:
        result = send_all_approved()
        print(json.dumps(result, indent=2))
    else:
        # Default: dry-run summary
        conn = get_conn()
        counts = conn.execute("SELECT status, COUNT(*) FROM ih_dms GROUP BY status").fetchall()
        conn.close()
        print("ih_dms status counts:")
        for s, n in counts:
            print(f"  {s}: {n}")
        print(f"Session file present: {have_session()}  ({SESSION_PATH})")
