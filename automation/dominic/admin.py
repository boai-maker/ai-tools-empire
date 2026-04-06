"""
Admin control interface for Dominic.
Provides CLI and programmatic control over Dominic's behavior.
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.db import (
    get_dom_config, set_dom_config, get_dom_conn,
    get_content_by_id, update_content_status, get_pending_content
)
from automation.dominic.logger import log_action, log_error, get_recent_logs

# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------

def pause_dominic() -> bool:
    """Pause Dominic — sets DOMINIC_PAUSED=true in dom_config."""
    set_dom_config("paused", "true")
    set_dom_config("paused_at", datetime.utcnow().isoformat())
    log_action("pause", "admin", "paused", "Dominic paused by admin")
    try:
        from automation.dominic.telegram_notifier import send_message
        send_message("⏸️ <b>Dominic is now PAUSED.</b>\nSend /resume to restart.")
    except Exception:
        pass
    return True


def resume_dominic() -> bool:
    """Resume Dominic — sets DOMINIC_PAUSED=false in dom_config."""
    set_dom_config("paused", "false")
    set_dom_config("resumed_at", datetime.utcnow().isoformat())
    log_action("resume", "admin", "running", "Dominic resumed by admin")
    try:
        from automation.dominic.telegram_notifier import send_message
        send_message("▶️ <b>Dominic is now RUNNING.</b>\nAll systems go.")
    except Exception:
        pass
    return True


def set_mode(mode: str) -> bool:
    """Set operating mode: 'autonomous' or 'approval'."""
    mode = mode.lower().strip()
    if mode not in ("autonomous", "approval"):
        log_error("admin", f"Invalid mode: {mode}", "set_mode")
        return False
    set_dom_config("mode", mode)
    log_action("set_mode", "admin", "ok", f"mode={mode}")
    try:
        from automation.dominic.telegram_notifier import send_message
        emoji = "🤖" if mode == "autonomous" else "🔔"
        send_message(f"{emoji} <b>Dominic mode set to: {mode.upper()}</b>")
    except Exception:
        pass
    return True


def is_paused() -> bool:
    """Return True if Dominic is currently paused."""
    # Check env first
    import os
    env_paused = os.getenv("DOMINIC_PAUSED", "false").lower()
    if env_paused in ("true", "1"):
        return True
    # Check DB config (can be set at runtime)
    db_paused = get_dom_config("paused", "false").lower()
    return db_paused in ("true", "1")


def get_current_mode() -> str:
    """Return current operating mode from DB or env."""
    import os
    db_mode = get_dom_config("mode", "")
    if db_mode in ("autonomous", "approval"):
        return db_mode
    return os.getenv("DOMINIC_MODE", "autonomous").lower()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def get_status() -> Dict:
    """Return full status dict with all Dominic metrics."""
    conn = get_dom_conn()

    counts = {}
    for status in ("draft", "queued", "approved", "published", "failed", "skipped", "awaiting_approval"):
        row = conn.execute(
            "SELECT COUNT(*) FROM dom_content WHERE status=?", (status,)
        ).fetchone()
        counts[status] = row[0] if row else 0

    # Recent history
    recent = conn.execute(
        """SELECT platform, content_summary, published_at
           FROM dom_history
           ORDER BY published_at DESC LIMIT 5"""
    ).fetchall()

    # Next scheduled
    next_post = conn.execute(
        """SELECT ds.scheduled_for, ds.platform, dc.headline
           FROM dom_schedule ds
           LEFT JOIN dom_content dc ON ds.content_id = dc.id
           WHERE ds.status='pending'
           ORDER BY ds.scheduled_for ASC LIMIT 1"""
    ).fetchone()

    conn.close()

    return {
        "paused": is_paused(),
        "mode": get_current_mode(),
        "content_counts": counts,
        "recent_posts": [dict(r) for r in recent],
        "next_scheduled": dict(next_post) if next_post else None,
        "last_action": get_dom_config("last_action", "N/A"),
        "last_post": get_dom_config("last_post", "N/A"),
        "checked_at": datetime.utcnow().isoformat(),
    }


def get_queue_summary() -> Dict:
    """Return counts of pending/queued/published content."""
    conn = get_dom_conn()
    summary = {}
    for status in ("draft", "queued", "approved", "published", "failed", "awaiting_approval"):
        row = conn.execute(
            "SELECT COUNT(*) FROM dom_content WHERE status=?", (status,)
        ).fetchone()
        summary[status] = row[0] if row else 0
    # Scheduled
    row = conn.execute(
        "SELECT COUNT(*) FROM dom_schedule WHERE status='pending'"
    ).fetchone()
    summary["scheduled_pending"] = row[0] if row else 0
    conn.close()
    return summary


# ---------------------------------------------------------------------------
# Content management
# ---------------------------------------------------------------------------

def approve_content(content_id: int) -> bool:
    """Approve a draft/awaiting_approval content for publishing."""
    content = get_content_by_id(content_id)
    if not content:
        log_error("admin", f"Content not found: {content_id}", "approve_content")
        return False

    update_content_status(content_id, "approved")
    log_action("approve", "admin", "approved", f"content_id={content_id}")

    # In autonomous mode, immediately try to publish
    if get_current_mode() == "autonomous":
        try:
            from automation.dominic.publisher import publish_with_retry
            platform = content.get("platform") or "twitter"
            publish_with_retry(platform, content_id)
        except Exception as e:
            log_error("admin", str(e), f"auto-publish after approve content_id={content_id}")

    return True


def reject_content(content_id: int) -> bool:
    """Reject a draft — sets status to skipped."""
    update_content_status(content_id, "skipped")
    log_action("reject", "admin", "skipped", f"content_id={content_id}")
    return True


def force_post(content_id: int) -> bool:
    """Bypass schedule and post immediately."""
    content = get_content_by_id(content_id)
    if not content:
        log_error("admin", f"Content not found: {content_id}", "force_post")
        return False

    platform = content.get("platform") or "twitter"
    update_content_status(content_id, "approved")

    try:
        from automation.dominic.publisher import publish_with_retry
        success, url = publish_with_retry(platform, content_id)
        log_action("force_post", "admin", "success" if success else "failed",
                   f"content_id={content_id}, url={url}")
        return success
    except Exception as e:
        log_error("admin", str(e), f"force_post content_id={content_id}")
        return False


def reset_failed() -> int:
    """Reset all failed posts back to queued status. Returns count."""
    conn = get_dom_conn()
    cursor = conn.execute(
        "UPDATE dom_content SET status='queued', retry_count=0 WHERE status='failed'"
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    log_action("reset_failed", "admin", "ok", f"reset {count} items")
    return count


# ---------------------------------------------------------------------------
# Telegram command handler
# ---------------------------------------------------------------------------

def handle_telegram_command(command: str, args: List[str] = None) -> str:
    """
    Process Telegram bot commands.
    Returns response text.
    """
    args = args or []
    cmd = command.lower().strip().lstrip("/")

    if cmd == "pause":
        pause_dominic()
        return "Dominic is now PAUSED. Send /resume to restart."

    elif cmd == "resume":
        resume_dominic()
        return "Dominic is now RUNNING."

    elif cmd == "status":
        s = get_status()
        counts = s.get("content_counts", {})
        mode = s.get("mode", "?")
        paused = "PAUSED" if s.get("paused") else "RUNNING"
        next_post = s.get("next_scheduled") or {}
        next_info = (
            f"{next_post.get('scheduled_for','?')[:16]} | {next_post.get('platform','?')} | {(next_post.get('headline') or '')[:40]}"
            if next_post else "None scheduled"
        )
        return (
            f"Dominic Status: {paused}\n"
            f"Mode: {mode}\n"
            f"Queue: draft={counts.get('draft',0)} | queued={counts.get('queued',0)} | "
            f"approved={counts.get('approved',0)} | published={counts.get('published',0)}\n"
            f"Failed: {counts.get('failed',0)}\n"
            f"Next post: {next_info}\n"
            f"Last action: {s.get('last_action','?')[:80]}"
        )

    elif cmd.startswith("approve_"):
        try:
            content_id = int(cmd.split("_", 1)[1])
            ok = approve_content(content_id)
            return f"Content #{content_id} {'approved and queued for posting.' if ok else 'not found.'}"
        except (ValueError, IndexError):
            return "Usage: /approve_<content_id>"

    elif cmd.startswith("reject_"):
        try:
            content_id = int(cmd.split("_", 1)[1])
            ok = reject_content(content_id)
            return f"Content #{content_id} {'rejected.' if ok else 'not found.'}"
        except (ValueError, IndexError):
            return "Usage: /reject_<content_id>"

    elif cmd.startswith("force_"):
        try:
            content_id = int(cmd.split("_", 1)[1])
            ok = force_post(content_id)
            return f"Force post #{content_id}: {'success' if ok else 'failed — check logs'}."
        except (ValueError, IndexError):
            return "Usage: /force_<content_id>"

    elif cmd == "mode":
        if args:
            ok = set_mode(args[0])
            return f"Mode set to {args[0]}." if ok else f"Invalid mode: {args[0]}"
        return f"Current mode: {get_current_mode()}. Use /mode autonomous or /mode approval"

    elif cmd == "queue":
        q = get_queue_summary()
        return (
            f"Queue Summary:\n"
            f"Draft: {q.get('draft',0)}\n"
            f"Queued: {q.get('queued',0)}\n"
            f"Approved: {q.get('approved',0)}\n"
            f"Awaiting approval: {q.get('awaiting_approval',0)}\n"
            f"Published: {q.get('published',0)}\n"
            f"Failed: {q.get('failed',0)}\n"
            f"Scheduled pending: {q.get('scheduled_pending',0)}"
        )

    elif cmd == "reset_failed":
        count = reset_failed()
        return f"Reset {count} failed posts to queued."

    elif cmd == "logs":
        lines = get_recent_logs(20)
        return "\n".join(lines[-15:]) if lines else "No logs found."

    elif cmd == "help":
        return (
            "Dominic Commands:\n"
            "/pause — pause all posting\n"
            "/resume — resume posting\n"
            "/status — full status report\n"
            "/queue — content queue counts\n"
            "/mode [autonomous|approval] — get/set mode\n"
            "/approve_<id> — approve content for posting\n"
            "/reject_<id> — reject content\n"
            "/force_<id> — force post immediately\n"
            "/reset_failed — reset failed posts to queued\n"
            "/logs — recent log lines"
        )

    else:
        return f"Unknown command: /{cmd}\nSend /help for available commands."


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_status() -> None:
    s = get_status()
    print(f"\nDominic Status")
    print(f"  State:  {'PAUSED' if s['paused'] else 'RUNNING'}")
    print(f"  Mode:   {s['mode']}")
    counts = s.get("content_counts", {})
    print(f"  Queue:  draft={counts.get('draft',0)} | queued={counts.get('queued',0)} | "
          f"published={counts.get('published',0)} | failed={counts.get('failed',0)}")
    next_post = s.get("next_scheduled")
    if next_post:
        print(f"  Next:   {next_post.get('scheduled_for','?')[:16]} | {next_post.get('platform','?')}")
    print(f"  Last:   {s.get('last_action','N/A')[:80]}")


def main():
    parser = argparse.ArgumentParser(description="Dominic Admin CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("pause", help="Pause Dominic")
    subparsers.add_parser("resume", help="Resume Dominic")
    subparsers.add_parser("status", help="Show status")
    subparsers.add_parser("queue", help="Show queue summary")

    mode_parser = subparsers.add_parser("mode", help="Get or set mode")
    mode_parser.add_argument("value", nargs="?", choices=["autonomous", "approval"],
                             help="Mode to set")

    approve_parser = subparsers.add_parser("approve", help="Approve content")
    approve_parser.add_argument("content_id", type=int)

    reject_parser = subparsers.add_parser("reject", help="Reject content")
    reject_parser.add_argument("content_id", type=int)

    force_parser = subparsers.add_parser("force", help="Force post now")
    force_parser.add_argument("content_id", type=int)

    subparsers.add_parser("reset_failed", help="Reset failed posts")

    logs_parser = subparsers.add_parser("logs", help="Show recent logs")
    logs_parser.add_argument("-n", type=int, default=20, help="Number of lines")

    args = parser.parse_args()

    # Initialize DB
    try:
        from automation.dominic.db import init_dominic_db
        init_dominic_db()
    except Exception as e:
        print(f"DB init error: {e}")

    if args.command == "pause":
        pause_dominic()
        print("Dominic paused.")

    elif args.command == "resume":
        resume_dominic()
        print("Dominic resumed.")

    elif args.command == "status":
        _print_status()

    elif args.command == "queue":
        q = get_queue_summary()
        for k, v in q.items():
            print(f"  {k}: {v}")

    elif args.command == "mode":
        if args.value:
            ok = set_mode(args.value)
            print(f"Mode set to {args.value}." if ok else "Failed.")
        else:
            print(f"Current mode: {get_current_mode()}")

    elif args.command == "approve":
        ok = approve_content(args.content_id)
        print(f"Content #{args.content_id} {'approved.' if ok else 'not found.'}")

    elif args.command == "reject":
        ok = reject_content(args.content_id)
        print(f"Content #{args.content_id} {'rejected.' if ok else 'not found.'}")

    elif args.command == "force":
        ok = force_post(args.content_id)
        print(f"Force post: {'success' if ok else 'failed'}")

    elif args.command == "reset_failed":
        count = reset_failed()
        print(f"Reset {count} failed posts.")

    elif args.command == "logs":
        lines = get_recent_logs(args.n)
        for line in lines:
            print(line)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
