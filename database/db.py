"""
SQLite database — stores articles, subscribers, clicks, analytics.
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "../data.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Articles table
    c.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            meta_description TEXT,
            content TEXT NOT NULL,
            category TEXT,
            tags TEXT,
            featured_tool TEXT,
            status TEXT DEFAULT 'published',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            views INTEGER DEFAULT 0,
            affiliate_clicks INTEGER DEFAULT 0
        )
    """)

    # Subscribers table
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            status TEXT DEFAULT 'active',
            source TEXT DEFAULT 'website',
            subscribed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            welcome_sent INTEGER DEFAULT 0,
            emails_received INTEGER DEFAULT 0
        )
    """)

    # Affiliate clicks table
    c.execute("""
        CREATE TABLE IF NOT EXISTS affiliate_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_key TEXT NOT NULL,
            source_page TEXT,
            ip_hash TEXT,
            clicked_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Analytics events
    c.execute("""
        CREATE TABLE IF NOT EXISTS page_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            referrer TEXT,
            user_agent TEXT,
            ip_hash TEXT,
            viewed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Scheduled content queue
    c.execute("""
        CREATE TABLE IF NOT EXISTS content_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            keywords TEXT,
            tool_focus TEXT,
            priority INTEGER DEFAULT 5,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            published_at TEXT
        )
    """)

    # Email campaigns
    c.execute("""
        CREATE TABLE IF NOT EXISTS email_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            content TEXT NOT NULL,
            campaign_type TEXT DEFAULT 'newsletter',
            sent_count INTEGER DEFAULT 0,
            open_rate REAL DEFAULT 0,
            click_rate REAL DEFAULT 0,
            status TEXT DEFAULT 'draft',
            scheduled_at TEXT,
            sent_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("Database initialized.")

# --- Articles ---
def save_article(slug, title, meta_description, content, category, tags, featured_tool):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO articles (slug, title, meta_description, content, category, tags, featured_tool)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (slug, title, meta_description, content, category, tags, featured_tool))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_articles(limit=20, offset=0, category=None, status='published'):
    conn = get_conn()
    if category:
        rows = conn.execute("""
            SELECT * FROM articles WHERE status=? AND category=?
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """, (status, category, limit, offset)).fetchall()
    else:
        rows = conn.execute("""
            SELECT * FROM articles WHERE status=?
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        """, (status, limit, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_article_by_slug(slug):
    conn = get_conn()
    row = conn.execute("SELECT * FROM articles WHERE slug=?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None

def increment_views(slug):
    conn = get_conn()
    conn.execute("UPDATE articles SET views = views + 1 WHERE slug=?", (slug,))
    conn.commit()
    conn.close()

# --- Subscribers ---
def add_subscriber(email, name="", source="website"):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO subscribers (email, name, source)
            VALUES (?, ?, ?)
        """, (email.lower().strip(), name.strip(), source))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_subscribers(status='active'):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM subscribers WHERE status=?", (status,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_subscriber_count():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM subscribers WHERE status='active'").fetchone()[0]
    conn.close()
    return count

def mark_welcome_sent(email):
    conn = get_conn()
    conn.execute("UPDATE subscribers SET welcome_sent=1 WHERE email=?", (email,))
    conn.commit()
    conn.close()

# --- Clicks ---
def log_click(tool_key, source_page, ip_hash):
    conn = get_conn()
    conn.execute("""
        INSERT INTO affiliate_clicks (tool_key, source_page, ip_hash)
        VALUES (?, ?, ?)
    """, (tool_key, source_page, ip_hash))
    conn.commit()
    conn.close()

# --- Analytics ---
def log_pageview(path, referrer, user_agent, ip_hash):
    conn = get_conn()
    conn.execute("""
        INSERT INTO page_views (path, referrer, user_agent, ip_hash) VALUES (?, ?, ?, ?)
    """, (path, referrer, user_agent, ip_hash))
    conn.commit()
    conn.close()

def get_analytics_summary():
    conn = get_conn()
    total_views = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
    today_views = conn.execute("""
        SELECT COUNT(*) FROM page_views WHERE DATE(viewed_at) = DATE('now')
    """).fetchone()[0]
    total_clicks = conn.execute("SELECT COUNT(*) FROM affiliate_clicks").fetchone()[0]
    subscribers = conn.execute("SELECT COUNT(*) FROM subscribers WHERE status='active'").fetchone()[0]
    articles = conn.execute("SELECT COUNT(*) FROM articles WHERE status='published'").fetchone()[0]
    top_clicked = conn.execute("""
        SELECT tool_key, COUNT(*) as cnt FROM affiliate_clicks
        GROUP BY tool_key ORDER BY cnt DESC LIMIT 5
    """).fetchall()
    conn.close()
    return {
        "total_views": total_views,
        "today_views": today_views,
        "total_clicks": total_clicks,
        "subscribers": subscribers,
        "articles": articles,
        "top_clicked": [dict(r) for r in top_clicked],
    }

# --- Content Queue ---
def add_to_queue(topic, keywords, tool_focus=None, priority=5):
    conn = get_conn()
    conn.execute("""
        INSERT INTO content_queue (topic, keywords, tool_focus, priority)
        VALUES (?, ?, ?, ?)
    """, (topic, keywords, tool_focus, priority))
    conn.commit()
    conn.close()

def get_next_queued_topic():
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM content_queue WHERE status='pending'
        ORDER BY priority DESC, created_at ASC LIMIT 1
    """).fetchone()
    conn.close()
    return dict(row) if row else None

def mark_queue_item_done(item_id):
    conn = get_conn()
    conn.execute("""
        UPDATE content_queue SET status='done', published_at=CURRENT_TIMESTAMP WHERE id=?
    """, (item_id,))
    conn.commit()
    conn.close()
