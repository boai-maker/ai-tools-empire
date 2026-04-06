"""
Bot 4: YouTube Bot
Manages YouTube content strategy and community posts.
"""
import logging
from datetime import datetime

from bots.shared.ai_client import ask_claude, generate_content
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from database.db import get_conn
from config import config

logger = logging.getLogger(__name__)

BOT_NAME = "youtube_bot"


def _ensure_social_queue(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS social_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            content TEXT NOT NULL,
            posted INTEGER DEFAULT 0,
            posted_at TEXT,
            scheduled_for TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def generate_video_script(topic: str, duration_minutes: int = 5) -> str:
    """
    Generates a YouTube script for an AI tool review/comparison video.
    """
    word_count = duration_minutes * 130  # ~130 words per minute speaking

    prompt = f"""Write a complete YouTube video script for AI Tools Empire about: {topic}

Target duration: {duration_minutes} minutes (~{word_count} words when spoken)

Include these sections clearly labeled:
[HOOK] - First 15 seconds that grab attention
[INTRO] - Brief channel intro and what we'll cover (30 sec)
[MAIN CONTENT] - Core review/comparison with timestamps
[DEMO NOTES] - What to show on screen
[PROS/CONS] - Quick breakdown
[PRICING] - Current pricing tiers
[VERDICT] - Who it's for and overall score
[CTA] - Call to action (subscribe + visit aitoolsempire.co for deals)
[END SCREEN] - Final 20 seconds

Make it conversational, informative, and engaging. Include natural transitions.
Mention affiliate deals available at aitoolsempire.co."""

    system = (
        "You are a YouTube script writer for AI Tools Empire, a channel that reviews "
        "and compares AI tools for businesses and marketers. Write in a friendly, "
        "knowledgeable voice. Scripts should feel natural when spoken aloud."
    )

    return ask_claude(prompt, system=system, max_tokens=3000)


def generate_video_ideas(n: int = 5) -> list:
    """
    Generates n video ideas for the AI Tools Empire YouTube channel.
    Returns list of {title, description, keywords, thumbnail_hook}.
    """
    prompt = f"""Generate {n} YouTube video ideas for AI Tools Empire (aitoolsempire.co).

This channel reviews and compares AI tools for business owners, marketers, and freelancers.
Videos that perform well are: tool comparisons, "best X tools for Y", tutorials, income-generating AI stacks.

For each idea provide:
TITLE: [YouTube title with numbers/power words, under 60 chars]
DESCRIPTION: [2-sentence video description]
KEYWORDS: [5-7 comma-separated SEO keywords]
THUMBNAIL_HOOK: [Text/visual concept for the thumbnail]
---

Generate {n} ideas in this exact format."""

    response = ask_claude(prompt, max_tokens=2000)

    ideas = []
    if not response:
        return ideas

    blocks = response.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        idea = {"title": "", "description": "", "keywords": "", "thumbnail_hook": ""}
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("TITLE:"):
                idea["title"] = line[6:].strip()
            elif line.startswith("DESCRIPTION:"):
                idea["description"] = line[12:].strip()
            elif line.startswith("KEYWORDS:"):
                idea["keywords"] = line[9:].strip()
            elif line.startswith("THUMBNAIL_HOOK:"):
                idea["thumbnail_hook"] = line[15:].strip()

        if idea["title"]:
            ideas.append(idea)

    return ideas[:n]


def generate_community_post_content(topic: str = None) -> str:
    """
    Generates a YouTube Community tab post (~150 words, engaging, with CTA).
    """
    if not topic:
        topic = "a new AI tool that's changing how people work"

    prompt = f"""Write a YouTube Community post for AI Tools Empire about: {topic}

Requirements:
- 120-160 words
- Conversational and engaging tone
- Ask a question to encourage comments
- Include a soft CTA to visit aitoolsempire.co for the full review or deals
- Use line breaks for readability (community posts don't support markdown)
- End with a question like "Which AI tools are you using right now?" or similar

Write only the post content, no labels."""

    return ask_claude(prompt, max_tokens=300)


def get_pending_community_posts() -> list:
    """
    Returns unposted YouTube community posts from social_queue.
    """
    try:
        conn = get_conn()
        _ensure_social_queue(conn)
        rows = conn.execute(
            "SELECT * FROM social_queue WHERE platform='youtube' AND posted=0 ORDER BY created_at ASC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_pending_community_posts error: {e}")
        return []


def queue_community_post(content: str, scheduled_for: str = None) -> bool:
    """
    Inserts a community post into social_queue. Returns True on success.
    """
    try:
        conn = get_conn()
        _ensure_social_queue(conn)
        conn.execute(
            "INSERT INTO social_queue (platform, content, scheduled_for) VALUES (?, ?, ?)",
            ("youtube", content, scheduled_for)
        )
        conn.commit()
        conn.close()
        logger.info("Queued YouTube community post")
        return True
    except Exception as e:
        logger.error(f"queue_community_post error: {e}")
        return False


def run_youtube_bot() -> dict:
    """
    Generates video ideas and queues community posts.
    Returns {"video_ideas": n, "posts_queued": n}
    """
    logger.info("YouTube Bot: starting run")
    result = {"video_ideas": 0, "posts_queued": 0}

    try:
        # Generate 3 video ideas
        ideas = generate_video_ideas(n=3)
        result["video_ideas"] = len(ideas)

        if ideas:
            # Log ideas to bot_events for reference
            ideas_summary = "; ".join([i.get("title", "") for i in ideas])
            log_bot_event(BOT_NAME, "video_ideas_generated", f"Generated {len(ideas)} ideas: {ideas_summary}")
            logger.info(f"YouTube Bot: generated {len(ideas)} video ideas")

        # Queue a community post if none are pending
        pending = get_pending_community_posts()
        if not pending:
            # Pick a topic from recent video ideas
            topic = ideas[0].get("title", "") if ideas else None
            content = generate_community_post_content(topic=topic)

            if content:
                queued = queue_community_post(content)
                if queued:
                    result["posts_queued"] = 1
                    log_bot_event(BOT_NAME, "post_queued", f"Community post queued: {content[:100]}...")
        else:
            logger.info(f"YouTube Bot: {len(pending)} pending post(s) already queued — skipping")

    except Exception as e:
        logger.error(f"YouTube Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    return result
