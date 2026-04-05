"""
Internal Linking Engine
Automatically injects contextual links to related articles within content.
This boosts on-page SEO by creating a strong internal link graph.
"""
import re
from database.db import get_articles


# Tool name → keyword patterns to match in article body
TOOL_KEYWORDS = {
    "jasper": ["Jasper AI", "Jasper.ai", "Jasper"],
    "copyai": ["Copy.ai", "Copy AI", "CopyAI"],
    "surfer": ["Surfer SEO", "SurferSEO"],
    "semrush": ["SEMrush", "Semrush"],
    "elevenlabs": ["ElevenLabs", "Eleven Labs"],
    "murf": ["Murf AI", "Murf.ai", "Murf"],
    "descript": ["Descript"],
    "pictory": ["Pictory AI", "Pictory"],
    "invideo": ["InVideo AI", "InVideo"],
    "writesonic": ["Writesonic"],
    "fireflies": ["Fireflies AI", "Fireflies"],
    "synthesia": ["Synthesia"],
    "chatgpt": ["ChatGPT", "GPT-4", "GPT-3"],
    "midjourney": ["Midjourney"],
}


def inject_internal_links(content: str, current_slug: str, max_links: int = 4) -> str:
    """
    Inject contextual internal links into article HTML content.
    - Skips the current article's own slug
    - Only links the FIRST occurrence of each keyword
    - Skips matches already inside an <a> tag
    - Injects at most `max_links` unique links per article
    """
    if not content:
        return content

    # Get all published articles
    all_articles = get_articles(limit=200)
    # Build slug → title map, excluding current article
    slug_title = {
        a["slug"]: a["title"]
        for a in all_articles
        if a["slug"] != current_slug
    }

    links_added = 0
    used_slugs = set()

    # Build candidate matches: (keyword, slug, title)
    # Prefer longer keywords first to avoid partial matches
    candidates = []
    for article in all_articles:
        if article["slug"] == current_slug:
            continue
        title = article["title"]
        slug = article["slug"]
        # Try to extract meaningful anchor text from the title (first 60 chars)
        anchor = title[:60].rsplit(" ", 1)[0] if len(title) > 60 else title
        candidates.append((anchor, slug))

    # Sort by length descending so longer phrases match first
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    for anchor_text, slug in candidates:
        if links_added >= max_links:
            break
        if slug in used_slugs:
            continue

        # Escape for regex
        escaped = re.escape(anchor_text)
        # Match the keyword only when NOT already inside an anchor tag
        # Use a simple approach: replace first occurrence outside <a>...</a>
        link_html = f'<a href="/articles/{slug}" title="{slug_title.get(slug, anchor_text)}">{anchor_text}</a>'

        # Only replace the first occurrence that isn't inside an existing tag
        pattern = r'(?<!href="[^"]{0,200})(?<!title="[^"]{0,200})' + escaped
        try:
            new_content, count = re.subn(
                r'(?<!["\'>])' + escaped + r'(?!["\'])',
                link_html,
                content,
                count=1,
                flags=re.IGNORECASE,
            )
        except re.error:
            continue

        if count > 0:
            # Verify the replacement didn't break existing links
            # (rough check: if the replacement created nested <a> tags, revert)
            nested = re.search(r'<a[^>]*>[^<]*<a', new_content)
            if not nested:
                content = new_content
                used_slugs.add(slug)
                links_added += 1

    return content
