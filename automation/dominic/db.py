"""
Dominic database layer.
Creates and manages all dom_* tables in the existing data.db.
"""
import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config

_cfg = get_config()
DB_PATH = _cfg.db_path


def get_dom_conn() -> sqlite3.Connection:
    """Return a connection to the shared data.db with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_dominic_db() -> None:
    """Create all Dominic tables if they do not already exist."""
    conn = get_dom_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS dom_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            source_title TEXT,
            content_type TEXT,
            platform TEXT,
            headline TEXT,
            body TEXT,
            status TEXT DEFAULT 'draft',
            confidence REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            scheduled_for TEXT,
            published_at TEXT,
            publish_url TEXT,
            telegram_notified INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS dom_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            external_id TEXT,
            content_summary TEXT,
            full_content TEXT,
            published_at TEXT DEFAULT CURRENT_TIMESTAMP,
            publish_url TEXT,
            likes INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            retweets INTEGER DEFAULT 0,
            content_id INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS dom_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS dom_crawl_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            crawled_at TEXT DEFAULT CURRENT_TIMESTAMP,
            articles_found INTEGER DEFAULT 0,
            new_ideas INTEGER DEFAULT 0,
            status TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS dom_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id INTEGER,
            platform TEXT,
            scheduled_for TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes for performance
    c.execute("CREATE INDEX IF NOT EXISTS idx_dom_content_status ON dom_content(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dom_content_platform ON dom_content(platform)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dom_schedule_status ON dom_schedule(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dom_schedule_scheduled_for ON dom_schedule(scheduled_for)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dom_history_platform ON dom_history(platform)")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def get_pending_content(platform: str = None, limit: int = 10) -> List[Dict]:
    """Return queued/approved content ready to post."""
    conn = get_dom_conn()
    if platform and platform != "both":
        rows = conn.execute(
            """SELECT * FROM dom_content
               WHERE status IN ('queued','approved')
               AND (platform = ? OR platform = 'both')
               ORDER BY confidence DESC, created_at ASC
               LIMIT ?""",
            (platform, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM dom_content
               WHERE status IN ('queued','approved')
               ORDER BY confidence DESC, created_at ASC
               LIMIT ?""",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_draft_content(limit: int = 20) -> List[Dict]:
    """Return draft content awaiting review or scoring."""
    conn = get_dom_conn()
    rows = conn.execute(
        "SELECT * FROM dom_content WHERE status='draft' ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_published(content_id: int, publish_url: str, external_id: str = None) -> None:
    """Mark content as published and record in history."""
    conn = get_dom_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE dom_content SET status='published', published_at=?, publish_url=? WHERE id=?",
        (now, publish_url, content_id)
    )
    # Fetch content for history
    row = conn.execute("SELECT * FROM dom_content WHERE id=?", (content_id,)).fetchone()
    if row:
        row = dict(row)
        conn.execute(
            """INSERT INTO dom_history
               (platform, external_id, content_summary, full_content, published_at, publish_url, content_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                row.get("platform"),
                external_id or "",
                (row.get("headline") or "")[:200],
                row.get("body") or "",
                now,
                publish_url,
                content_id,
            )
        )
    conn.commit()
    conn.close()


def mark_failed(content_id: int, reason: str = "") -> None:
    """Increment retry count; mark failed after 3 tries."""
    conn = get_dom_conn()
    conn.execute(
        "UPDATE dom_content SET retry_count = retry_count + 1 WHERE id=?",
        (content_id,)
    )
    row = conn.execute("SELECT retry_count FROM dom_content WHERE id=?", (content_id,)).fetchone()
    if row and row[0] >= 3:
        conn.execute(
            "UPDATE dom_content SET status='failed' WHERE id=?",
            (content_id,)
        )
    conn.commit()
    conn.close()


def is_duplicate(headline: str, threshold: float = 0.85) -> bool:
    """Check whether headline is too similar to existing content."""
    import difflib
    conn = get_dom_conn()
    existing = conn.execute(
        "SELECT headline FROM dom_content ORDER BY created_at DESC LIMIT 500"
    ).fetchall()
    conn.close()
    headline_lower = headline.lower().strip()
    for row in existing:
        existing_hl = (row[0] or "").lower().strip()
        ratio = difflib.SequenceMatcher(None, headline_lower, existing_hl).ratio()
        if ratio >= threshold:
            return True
    return False


def save_content(
    headline: str,
    body: str,
    content_type: str,
    platform: str,
    confidence: float = 0.0,
    url: str = "",
    source_title: str = "",
    status: str = "draft",
    scheduled_for: str = None,
) -> Optional[int]:
    """Insert a new content row and return its id. Returns None on error."""
    conn = get_dom_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO dom_content
               (url, source_title, content_type, platform, headline, body,
                status, confidence, scheduled_for)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, source_title, content_type, platform, headline, body,
             status, confidence, scheduled_for)
        )
        content_id = cursor.lastrowid
        conn.commit()
        return content_id
    except Exception as e:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_dom_config(key: str, default: str = "") -> str:
    """Retrieve a value from dom_config."""
    conn = get_dom_conn()
    row = conn.execute("SELECT value FROM dom_config WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def set_dom_config(key: str, value: str) -> None:
    """Upsert a value into dom_config."""
    conn = get_dom_conn()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO dom_config (key, value, updated_at) VALUES (?, ?, ?)",
        (key, str(value), now)
    )
    conn.commit()
    conn.close()


def get_content_by_id(content_id: int) -> Optional[Dict]:
    """Fetch a single content row by id."""
    conn = get_dom_conn()
    row = conn.execute("SELECT * FROM dom_content WHERE id=?", (content_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_content_status(content_id: int, status: str) -> None:
    """Update only the status of a content row."""
    conn = get_dom_conn()
    conn.execute("UPDATE dom_content SET status=? WHERE id=?", (status, content_id))
    conn.commit()
    conn.close()


def get_schedule_row(schedule_id: int) -> Optional[Dict]:
    conn = get_dom_conn()
    row = conn.execute("SELECT * FROM dom_schedule WHERE id=?", (schedule_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_due_schedule_rows(platform: str = None) -> List[Dict]:
    """Return dom_schedule rows that are due (scheduled_for <= now, status=pending)."""
    conn = get_dom_conn()
    now = datetime.utcnow().isoformat()
    if platform:
        rows = conn.execute(
            """SELECT ds.*, dc.headline, dc.body, dc.content_type, dc.confidence
               FROM dom_schedule ds
               JOIN dom_content dc ON ds.content_id = dc.id
               WHERE ds.status='pending'
               AND ds.scheduled_for <= ?
               AND ds.platform = ?
               AND dc.status IN ('queued','approved')
               ORDER BY ds.scheduled_for ASC""",
            (now, platform)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT ds.*, dc.headline, dc.body, dc.content_type, dc.confidence
               FROM dom_schedule ds
               JOIN dom_content dc ON ds.content_id = dc.id
               WHERE ds.status='pending'
               AND ds.scheduled_for <= ?
               AND dc.status IN ('queued','approved')
               ORDER BY ds.scheduled_for ASC""",
            (now,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_schedule_status(schedule_id: int, status: str) -> None:
    conn = get_dom_conn()
    conn.execute("UPDATE dom_schedule SET status=? WHERE id=?", (status, schedule_id))
    conn.commit()
    conn.close()


def insert_schedule_row(content_id: int, platform: str, scheduled_for: str) -> int:
    conn = get_dom_conn()
    cursor = conn.execute(
        "INSERT INTO dom_schedule (content_id, platform, scheduled_for) VALUES (?, ?, ?)",
        (content_id, platform, scheduled_for)
    )
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_history_stats(days: int = 7) -> Dict:
    """Return basic stats from dom_history for the past N days."""
    conn = get_dom_conn()
    from_dt = datetime.utcnow().isoformat()
    rows = conn.execute(
        """SELECT platform, COUNT(*) as cnt,
           SUM(likes) as total_likes, SUM(retweets) as total_rt, SUM(views) as total_views
           FROM dom_history
           WHERE published_at >= datetime('now', ?)
           GROUP BY platform""",
        (f"-{days} days",)
    ).fetchall()
    conn.close()
    return {r["platform"]: dict(r) for r in rows}


def log_crawl(url: str, articles_found: int, new_ideas: int, status: str) -> None:
    conn = get_dom_conn()
    conn.execute(
        "INSERT INTO dom_crawl_log (url, articles_found, new_ideas, status) VALUES (?, ?, ?, ?)",
        (url, articles_found, new_ideas, status)
    )
    conn.commit()
    conn.close()


def get_crawled_urls(limit: int = 2000) -> set:
    """Return set of URLs already crawled."""
    conn = get_dom_conn()
    rows = conn.execute(
        "SELECT DISTINCT url FROM dom_crawl_log ORDER BY crawled_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}
