"""
Content calendar and scheduling engine for Dominic.
Manages posting slots for Twitter and YouTube.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.db import (
    get_dom_conn, insert_schedule_row, update_schedule_status,
    get_pending_content, get_content_by_id, update_content_status
)
from automation.dominic.logger import log_action, log_error

# ---------------------------------------------------------------------------
# Posting schedule configuration
# ---------------------------------------------------------------------------
# Twitter: 2 posts on alternating days, 9 AM and 6 PM Eastern
# YouTube: 1 draft every 2 days, noon Eastern

TWITTER_POST_HOURS = [9, 18]        # 9 AM, 6 PM Eastern
YOUTUBE_POST_HOUR = 12              # Noon Eastern
TWITTER_EVERY_N_DAYS = 1           # Post on alternating days (tracked by slot counter)
YOUTUBE_EVERY_N_DAYS = 2           # Every 2 days


def _get_tz():
    """Return pytz timezone or None."""
    try:
        import pytz
        cfg = get_config()
        return pytz.timezone(cfg.timezone)
    except Exception:
        return None


def _now_local() -> datetime:
    """Return current local datetime in configured timezone."""
    tz = _get_tz()
    if tz:
        try:
            import pytz
            return datetime.now(tz).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.utcnow()


def _slot_datetime(base_date: datetime, hour: int) -> str:
    """Return ISO datetime string for base_date at given hour."""
    slot = base_date.replace(hour=hour, minute=0, second=0, microsecond=0)
    return slot.isoformat()


# ---------------------------------------------------------------------------
# Core scheduling
# ---------------------------------------------------------------------------

def find_next_slot(platform: str) -> str:
    """
    Find the next available posting slot for a platform.
    Returns ISO datetime string.
    """
    now = _now_local()
    conn = get_dom_conn()

    if platform == "twitter":
        # Try today's remaining slots, then future days
        for day_offset in range(0, 14):
            check_date = now + timedelta(days=day_offset)
            for hour in TWITTER_POST_HOURS:
                candidate = _slot_datetime(check_date, hour)
                cand_dt = check_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                if cand_dt <= now:
                    continue
                # Check if slot is taken
                existing = conn.execute(
                    """SELECT COUNT(*) FROM dom_schedule
                       WHERE platform='twitter'
                       AND scheduled_for = ?
                       AND status != 'cancelled'""",
                    (candidate,)
                ).fetchone()[0]
                if existing == 0:
                    conn.close()
                    return candidate

    elif platform == "youtube":
        for day_offset in range(0, 30):
            check_date = now + timedelta(days=day_offset)
            # Alternate days for YouTube
            if day_offset % YOUTUBE_EVERY_N_DAYS != 0:
                continue
            candidate = _slot_datetime(check_date, YOUTUBE_POST_HOUR)
            cand_dt = check_date.replace(hour=YOUTUBE_POST_HOUR, minute=0, second=0, microsecond=0)
            if cand_dt <= now:
                continue
            existing = conn.execute(
                """SELECT COUNT(*) FROM dom_schedule
                   WHERE platform='youtube'
                   AND scheduled_for = ?
                   AND status != 'cancelled'""",
                (candidate,)
            ).fetchone()[0]
            if existing == 0:
                conn.close()
                return candidate

    conn.close()
    # Fallback: 1 week from now
    return (now + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0).isoformat()


def schedule_content(content_id: int, platform: str, when: str) -> int:
    """
    Schedule a content item for posting.
    Returns schedule row id.
    """
    # Update content status to queued
    update_content_status(content_id, "queued")

    row_id = insert_schedule_row(content_id, platform, when)
    log_action("schedule_content", "planner", "ok",
               f"content_id={content_id}, platform={platform}, when={when}")
    return row_id


def get_upcoming_schedule(days: int = 7) -> List[Dict]:
    """Return all scheduled posts for the next N days."""
    now = _now_local()
    until = (now + timedelta(days=days)).isoformat()
    conn = get_dom_conn()
    rows = conn.execute(
        """SELECT ds.id, ds.content_id, ds.platform, ds.scheduled_for, ds.status,
                  dc.headline, dc.content_type, dc.confidence
           FROM dom_schedule ds
           LEFT JOIN dom_content dc ON ds.content_id = dc.id
           WHERE ds.status = 'pending'
           AND ds.scheduled_for <= ?
           ORDER BY ds.scheduled_for ASC""",
        (until,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_schedule() -> List[Dict]:
    """Return today's scheduled posts."""
    return get_upcoming_schedule(days=1)


def plan_week() -> Dict:
    """
    Generate a weekly content plan for Twitter + YouTube.
    Fills next 7 days with available content from the queue.
    Returns dict with platform -> list of scheduled slots.
    """
    plan = {"twitter": [], "youtube": []}
    now = _now_local()

    # Twitter: 2 posts per day on alternating days (days 0, 2, 4, 6)
    twitter_content = get_pending_content("twitter", limit=20)
    twitter_idx = 0
    for day_offset in range(0, 7, 1):  # Post every day
        check_date = now + timedelta(days=day_offset)
        for hour in TWITTER_POST_HOURS:
            if twitter_idx >= len(twitter_content):
                break
            cand_dt = check_date.replace(hour=hour, minute=0, second=0, microsecond=0)
            if cand_dt <= now:
                continue
            slot = cand_dt.isoformat()

            # Check not already scheduled at this slot
            conn = get_dom_conn()
            existing = conn.execute(
                "SELECT COUNT(*) FROM dom_schedule WHERE platform='twitter' AND scheduled_for=? AND status!='cancelled'",
                (slot,)
            ).fetchone()[0]
            conn.close()

            if existing == 0:
                c = twitter_content[twitter_idx]
                sid = schedule_content(c["id"], "twitter", slot)
                plan["twitter"].append({
                    "schedule_id": sid,
                    "content_id": c["id"],
                    "headline": c.get("headline", ""),
                    "scheduled_for": slot,
                })
                twitter_idx += 1

    # YouTube: 1 per 2 days
    youtube_content = get_pending_content("youtube", limit=10)
    yt_idx = 0
    for day_offset in range(0, 14, YOUTUBE_EVERY_N_DAYS):
        if yt_idx >= len(youtube_content):
            break
        check_date = now + timedelta(days=day_offset)
        cand_dt = check_date.replace(hour=YOUTUBE_POST_HOUR, minute=0, second=0, microsecond=0)
        if cand_dt <= now:
            continue
        slot = cand_dt.isoformat()

        conn = get_dom_conn()
        existing = conn.execute(
            "SELECT COUNT(*) FROM dom_schedule WHERE platform='youtube' AND scheduled_for=? AND status!='cancelled'",
            (slot,)
        ).fetchone()[0]
        conn.close()

        if existing == 0:
            c = youtube_content[yt_idx]
            sid = schedule_content(c["id"], "youtube", slot)
            plan["youtube"].append({
                "schedule_id": sid,
                "content_id": c["id"],
                "headline": c.get("headline", ""),
                "scheduled_for": slot,
            })
            yt_idx += 1

    log_action("plan_week", "planner", "ok",
               f"twitter={len(plan['twitter'])}, youtube={len(plan['youtube'])}")
    return plan


def backfill_empty_slots() -> int:
    """
    Fill gaps in the next 7 days with queued content.
    Returns count of slots filled.
    """
    filled = 0
    now = _now_local()

    for platform in ["twitter", "youtube"]:
        queued = get_pending_content(platform, limit=10)
        for item in queued:
            slot = find_next_slot(platform)
            slot_dt = datetime.fromisoformat(slot)
            if (slot_dt - now).days > 7:
                break  # Don't schedule more than 7 days out
            schedule_content(item["id"], platform, slot)
            filled += 1

    log_action("backfill", "planner", "ok", f"filled={filled}")
    return filled


def rebalance_schedule() -> None:
    """
    Re-order pending scheduled posts by confidence score.
    Higher confidence posts get earlier slots.
    """
    conn = get_dom_conn()
    pending = conn.execute(
        """SELECT ds.id, ds.content_id, ds.platform, ds.scheduled_for, dc.confidence
           FROM dom_schedule ds
           JOIN dom_content dc ON ds.content_id = dc.id
           WHERE ds.status = 'pending'
           ORDER BY ds.platform, ds.scheduled_for ASC"""
    ).fetchall()
    conn.close()

    # Group by platform
    by_platform: Dict[str, List] = {}
    for row in pending:
        p = row["platform"]
        if p not in by_platform:
            by_platform[p] = []
        by_platform[p].append(dict(row))

    for platform, items in by_platform.items():
        # Sort slots chronologically
        slots = sorted(set(item["scheduled_for"] for item in items))
        # Sort content by confidence descending
        items_sorted = sorted(items, key=lambda x: x.get("confidence", 0), reverse=True)

        conn = get_dom_conn()
        for i, (slot, item) in enumerate(zip(slots, items_sorted)):
            conn.execute(
                "UPDATE dom_schedule SET scheduled_for=? WHERE id=?",
                (slot, item["id"])
            )
        conn.commit()
        conn.close()

    log_action("rebalance_schedule", "planner", "ok", "done")


def cancel_scheduled(schedule_id: int) -> bool:
    """Cancel a scheduled post by schedule row id."""
    try:
        update_schedule_status(schedule_id, "cancelled")
        # Revert content to queued
        conn = get_dom_conn()
        row = conn.execute("SELECT content_id FROM dom_schedule WHERE id=?", (schedule_id,)).fetchone()
        conn.close()
        if row:
            update_content_status(row[0], "queued")
        log_action("cancel_scheduled", "planner", "ok", f"schedule_id={schedule_id}")
        return True
    except Exception as e:
        log_error("planner", str(e), f"cancel_scheduled id={schedule_id}")
        return False
