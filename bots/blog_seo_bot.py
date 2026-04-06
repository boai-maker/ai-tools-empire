"""
Bot 5: Blog/SEO Publishing Bot
Generates and publishes SEO-optimized blog articles.
"""
import re
import logging
from datetime import datetime

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event, upsert_bot_state, get_article_count
from database.db import get_conn, save_article, get_next_queued_topic, mark_queue_item_done

logger = logging.getLogger(__name__)

BOT_NAME = "blog_seo_bot"


def generate_article_slug(title: str) -> str:
    """Converts a title to a URL-safe slug."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:80]


def generate_seo_article(topic: str, keywords: str, tool_focus: str = None) -> dict:
    """
    Uses Claude to write a full SEO article.
    Returns {title, slug, meta_description, content, category, tags, featured_tool}.
    Content is 800-1200 words in HTML format with H2/H3 headings, bullet points,
    and [AFFILIATE:tool_name] placeholders.
    """
    tool_context = f"Featured tool to highlight: {tool_focus}" if tool_focus else "Cover the topic generally with multiple tool mentions."

    prompt = f"""Write a complete, SEO-optimized blog article for AI Tools Empire (aitoolsempire.co).

Topic: {topic}
Target keywords: {keywords}
{tool_context}

Requirements:
1. Title: Compelling, SEO-friendly, includes primary keyword (put on first line as: TITLE: ...)
2. Meta description: 150-160 characters (put on second line as: META: ...)
3. Category: one of [reviews, comparisons, tutorials, news, guides] (put as: CATEGORY: ...)
4. Tags: 5-7 comma-separated tags (put as: TAGS: ...)
5. Featured tool: the main tool name (put as: FEATURED_TOOL: ...)
6. Content: 900-1100 words of HTML content

HTML content requirements:
- Use <h2> and <h3> tags for headings
- Use <p> tags for paragraphs
- Use <ul><li> for bullet points
- Use <strong> for emphasis on important points
- Include 2-3 [AFFILIATE:tool_name] placeholders where tool signup links should appear
  Example: <a href="[AFFILIATE:jasper]">Try Jasper free</a>
- Include a compelling intro paragraph
- Include a "Key Takeaways" section with bullet points
- End with a clear CTA to sign up for tools or visit aitoolsempire.co
- Do NOT include <html>, <head>, or <body> tags — just the article content

Write the full output in this format:
TITLE: [title here]
META: [meta description here]
CATEGORY: [category]
TAGS: [tag1, tag2, tag3, tag4, tag5]
FEATURED_TOOL: [tool name]
CONTENT:
[HTML content here]"""

    system = (
        "You are an expert SEO content writer for AI Tools Empire. "
        "Write authoritative, helpful content that ranks well and converts readers to affiliate tool signups. "
        "Always write complete, publication-ready articles — never truncate."
    )

    response = ask_claude(prompt, system=system, max_tokens=3000)

    if not response:
        logger.error("generate_seo_article: empty response from Claude")
        return {}

    # Parse the response
    article = {
        "title": "",
        "slug": "",
        "meta_description": "",
        "content": "",
        "category": "guides",
        "tags": "",
        "featured_tool": tool_focus or "",
    }

    lines = response.split("\n")
    content_started = False
    content_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("TITLE:"):
            article["title"] = stripped[6:].strip()
        elif stripped.startswith("META:"):
            article["meta_description"] = stripped[5:].strip()
        elif stripped.startswith("CATEGORY:"):
            article["category"] = stripped[9:].strip().lower()
        elif stripped.startswith("TAGS:"):
            article["tags"] = stripped[5:].strip()
        elif stripped.startswith("FEATURED_TOOL:"):
            article["featured_tool"] = stripped[14:].strip()
        elif stripped == "CONTENT:":
            content_started = True
        elif content_started:
            content_lines.append(line)

    article["content"] = "\n".join(content_lines).strip()

    if article["title"]:
        article["slug"] = generate_article_slug(article["title"])

    # Fallbacks
    if not article["title"]:
        article["title"] = topic
        article["slug"] = generate_article_slug(topic)
    if not article["meta_description"]:
        article["meta_description"] = f"Discover the best {topic} tools and strategies. Expert reviews and comparisons at AI Tools Empire."[:160]
    if not article["content"]:
        article["content"] = f"<p>{response}</p>"

    return article


def publish_article(article_data: dict) -> bool:
    """
    Publishes an article via save_article from database/db.py.
    Returns True if saved successfully.
    """
    if not article_data or not article_data.get("title") or not article_data.get("content"):
        logger.warning("publish_article: missing title or content")
        return False

    success = save_article(
        slug=article_data.get("slug", ""),
        title=article_data.get("title", ""),
        meta_description=article_data.get("meta_description", ""),
        content=article_data.get("content", ""),
        category=article_data.get("category", "guides"),
        tags=article_data.get("tags", ""),
        featured_tool=article_data.get("featured_tool", ""),
    )

    if success:
        logger.info(f"Published article: {article_data.get('title', '')}")
    else:
        logger.warning(f"Article already exists or failed to save: {article_data.get('slug', '')}")

    return success


def process_content_queue(max_articles: int = 2) -> int:
    """
    Gets pending items from content_queue, generates and publishes articles.
    Marks each item done after publishing. Returns count published.
    """
    published = 0

    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM content_queue WHERE status='pending'
        ORDER BY priority DESC, created_at ASC
        LIMIT ?
    """, (max_articles,)).fetchall()
    conn.close()

    items = [dict(r) for r in rows]

    for item in items:
        try:
            logger.info(f"Processing queue item: {item['topic']}")
            article = generate_seo_article(
                topic=item["topic"],
                keywords=item.get("keywords", ""),
                tool_focus=item.get("tool_focus"),
            )

            if article and publish_article(article):
                mark_queue_item_done(item["id"])
                published += 1
                log_bot_event(
                    BOT_NAME,
                    "article_published",
                    f"Published: {article.get('title', item['topic'])}"
                )
            else:
                logger.warning(f"Failed to publish article for topic: {item['topic']}")

        except Exception as e:
            logger.error(f"Error processing queue item '{item['topic']}': {e}")

    return published


def run_blog_seo_bot() -> dict:
    """
    Processes up to 2 articles from queue.
    Also generates a starter article if fewer than 5 articles exist.
    Saves last_run. Returns {"published": n}.
    """
    logger.info("Blog SEO Bot: starting run")
    total_published = 0

    try:
        # Process content queue
        published = process_content_queue(max_articles=2)
        total_published += published

        # Check if we need a starter article
        article_count = get_article_count()
        if article_count < 5:
            logger.info(f"Only {article_count} articles found — generating starter article")

            starter_topics = [
                ("Best AI Writing Tools 2024: Complete Comparison Guide", "ai writing tools, best ai writers, jasper vs copy.ai", "jasper"),
                ("How to Use ChatGPT for Business: 10 Practical Strategies", "chatgpt for business, ai productivity, chatgpt tips", "general"),
                ("Top 5 AI Video Creation Tools Reviewed", "ai video tools, pictory review, ai video generator", "pictory"),
                ("AI Tools for Marketing: The Ultimate 2024 Guide", "ai marketing tools, ai for marketers, marketing automation", "general"),
                ("Jasper AI Review 2024: Is It Worth It?", "jasper ai review, jasper review, jasper ai pricing", "jasper"),
            ]

            # Pick a topic not already in articles
            conn = get_conn()
            existing_slugs = {
                r[0] for r in conn.execute("SELECT slug FROM articles").fetchall()
            }
            conn.close()

            for topic_title, keywords, tool in starter_topics:
                slug = generate_article_slug(topic_title)
                if slug not in existing_slugs:
                    article = generate_seo_article(
                        topic=topic_title,
                        keywords=keywords,
                        tool_focus=tool if tool != "general" else None,
                    )
                    if article and publish_article(article):
                        total_published += 1
                        log_bot_event(BOT_NAME, "starter_article", f"Published starter: {article.get('title', topic_title)}")
                    break

    except Exception as e:
        logger.error(f"Blog SEO Bot error: {e}")
        log_bot_event(BOT_NAME, "error", str(e))

    upsert_bot_state(BOT_NAME, "last_run", datetime.utcnow().isoformat())
    logger.info(f"Blog SEO Bot: published {total_published} articles")
    return {"published": total_published}
