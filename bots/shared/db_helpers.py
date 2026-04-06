"""
Shared database helpers for all bots.
"""
import logging
from datetime import datetime
from database.db import get_conn

logger = logging.getLogger(__name__)


def get_article_count() -> int:
    try:
        conn = get_conn()
        count = conn.execute("SELECT COUNT(*) FROM articles WHERE status='published'").fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"get_article_count error: {e}")
        return 0


def get_subscriber_count() -> int:
    try:
        conn = get_conn()
        count = conn.execute("SELECT COUNT(*) FROM subscribers WHERE status='active'").fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"get_subscriber_count error: {e}")
        return 0


def get_recent_articles(n: int = 5) -> list:
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM articles WHERE status='published' ORDER BY created_at DESC LIMIT ?",
            (n,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_recent_articles error: {e}")
        return []


def get_affiliate_click_totals() -> dict:
    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT tool_key, COUNT(*) as cnt FROM affiliate_clicks GROUP BY tool_key ORDER BY cnt DESC"
        ).fetchall()
        conn.close()
        return {r["tool_key"]: r["cnt"] for r in rows}
    except Exception as e:
        logger.error(f"get_affiliate_click_totals error: {e}")
        return {}


def get_today_views() -> int:
    try:
        conn = get_conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM page_views WHERE DATE(viewed_at) = DATE('now')"
        ).fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"get_today_views error: {e}")
        return 0


def get_total_views() -> int:
    try:
        conn = get_conn()
        count = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"get_total_views error: {e}")
        return 0


def _ensure_bot_events_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def log_bot_event(bot_name: str, event_type: str, details: str) -> None:
    try:
        conn = get_conn()
        _ensure_bot_events_table(conn)
        conn.execute(
            "INSERT INTO bot_events (bot_name, event_type, details) VALUES (?, ?, ?)",
            (bot_name, event_type, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"log_bot_event error: {e}")


def get_bot_events(bot_name: str = None, limit: int = 50) -> list:
    try:
        conn = get_conn()
        _ensure_bot_events_table(conn)
        if bot_name:
            rows = conn.execute(
                "SELECT * FROM bot_events WHERE bot_name=? ORDER BY created_at DESC LIMIT ?",
                (bot_name, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bot_events ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_bot_events error: {e}")
        return []


def _ensure_bot_state_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            bot_name TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (bot_name, key)
        )
    """)
    conn.commit()


def upsert_bot_state(bot_name: str, key: str, value: str) -> None:
    try:
        conn = get_conn()
        _ensure_bot_state_table(conn)
        conn.execute("""
            INSERT INTO bot_state (bot_name, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(bot_name, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """, (bot_name, key, value, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"upsert_bot_state error: {e}")


def get_bot_state(bot_name: str, key: str, default=None):
    try:
        conn = get_conn()
        _ensure_bot_state_table(conn)
        row = conn.execute(
            "SELECT value FROM bot_state WHERE bot_name=? AND key=?",
            (bot_name, key)
        ).fetchone()
        conn.close()
        if row:
            return row["value"]
        return default
    except Exception as e:
        logger.error(f"get_bot_state error: {e}")
        return default
