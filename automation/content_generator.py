"""
Automated AI content generation pipeline.
Uses Claude to write SEO-optimized articles targeting high-intent keywords.
Runs daily via scheduler — generates 3 articles per day automatically.
"""
import anthropic
import json
import re
import logging
from datetime import datetime
from typing import Optional
from slugify import slugify
from config import config
from database.db import save_article, add_to_queue, get_next_queued_topic, mark_queue_item_done
from affiliate.links import AFFILIATE_PROGRAMS, CATEGORIES

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# ── High-intent article topics that attract buyer-intent traffic ──────────────
SEED_TOPICS = [
    # Comparisons (highest converting traffic)
    {"topic": "Jasper AI vs Copy.ai: Which is Better in 2026?", "keywords": "jasper vs copy ai, best ai writing tool 2026", "tool_focus": "jasper", "priority": 9},
    {"topic": "Surfer SEO vs Semrush: Full Comparison", "keywords": "surfer seo vs semrush, best seo tool", "tool_focus": "surfer", "priority": 9},
    {"topic": "ElevenLabs vs Murf AI: Best AI Voice Generator?", "keywords": "elevenlabs vs murf, best ai voice generator 2026", "tool_focus": "elevenlabs", "priority": 9},
    {"topic": "Pictory vs InVideo AI: Best AI Video Creator?", "keywords": "pictory vs invideo, best ai video tool", "tool_focus": "pictory", "priority": 8},
    {"topic": "Writesonic vs Jasper AI: Which AI Writer Wins?", "keywords": "writesonic vs jasper, ai content writer comparison", "tool_focus": "writesonic", "priority": 8},
    {"topic": "Fireflies AI vs Otter.ai: Best Meeting AI Notetaker?", "keywords": "fireflies vs otter ai, best meeting transcription", "tool_focus": "fireflies", "priority": 8},
    # Reviews (high trust, high conversion)
    {"topic": "Jasper AI Review 2026: Is It Worth $49/Month?", "keywords": "jasper ai review, jasper ai pricing, is jasper worth it", "tool_focus": "jasper", "priority": 8},
    {"topic": "Semrush Review 2026: The Complete Guide", "keywords": "semrush review 2026, semrush pricing, semrush worth it", "tool_focus": "semrush", "priority": 8},
    {"topic": "Surfer SEO Review: The Best AI SEO Tool?", "keywords": "surfer seo review, surfer seo pricing", "tool_focus": "surfer", "priority": 7},
    {"topic": "Copy.ai Review 2026: Features, Pricing & Verdict", "keywords": "copy ai review, copy.ai pricing, copy.ai features", "tool_focus": "copyai", "priority": 7},
    {"topic": "ElevenLabs Review: The Most Realistic AI Voices?", "keywords": "elevenlabs review, elevenlabs pricing, elevenlabs features", "tool_focus": "elevenlabs", "priority": 7},
    {"topic": "Descript Review 2026: Best AI Video Editor?", "keywords": "descript review, descript pricing, descript tutorial", "tool_focus": "descript", "priority": 7},
    # Listicles (high traffic, good for building authority)
    {"topic": "10 Best AI Writing Tools in 2026 (Ranked & Reviewed)", "keywords": "best ai writing tools, top ai writers, ai writing software", "tool_focus": None, "priority": 9},
    {"topic": "7 Best AI SEO Tools That Actually Work in 2026", "keywords": "best ai seo tools, ai seo software, seo automation tools", "tool_focus": "surfer", "priority": 8},
    {"topic": "Best AI Video Generators in 2026 (Free & Paid)", "keywords": "best ai video generator, ai video creation tools, text to video ai", "tool_focus": "pictory", "priority": 8},
    {"topic": "12 Best AI Tools for Content Creators in 2026", "keywords": "best ai tools for content creators, ai tools list", "tool_focus": None, "priority": 8},
    {"topic": "10 Best AI Voice Generators (Ranked by Realism)", "keywords": "best ai voice generator, text to speech ai, realistic ai voices", "tool_focus": "elevenlabs", "priority": 7},
    {"topic": "Best AI Productivity Tools for Remote Teams 2026", "keywords": "best ai productivity tools, ai tools for teams, remote work ai", "tool_focus": "fireflies", "priority": 7},
    # How-to guides (long-tail, low competition)
    {"topic": "How to Use AI Writing Tools to 10x Your Content Output", "keywords": "how to use ai writing tools, ai content creation guide", "tool_focus": "jasper", "priority": 6},
    {"topic": "How to Do AI-Powered SEO in 2026 (Step-by-Step)", "keywords": "ai seo guide, how to use ai for seo, ai content optimization", "tool_focus": "surfer", "priority": 6},
    {"topic": "How to Create YouTube Videos with AI (No Filming Required)", "keywords": "create youtube videos with ai, ai youtube automation", "tool_focus": "pictory", "priority": 6},
    {"topic": "How to Clone Your Voice with AI (ElevenLabs Tutorial)", "keywords": "clone voice with ai, voice cloning tutorial, elevenlabs tutorial", "tool_focus": "elevenlabs", "priority": 6},
    # Pricing guides (captures bottom-of-funnel buyers)
    {"topic": "Jasper AI Pricing 2026: Which Plan Is Right For You?", "keywords": "jasper ai pricing, jasper ai plans, jasper ai cost", "tool_focus": "jasper", "priority": 8},
    {"topic": "Semrush Pricing 2026: Is There a Cheaper Alternative?", "keywords": "semrush pricing, semrush cost, semrush discount", "tool_focus": "semrush", "priority": 8},
    {"topic": "Copy.ai Free vs Paid: Is the Pro Plan Worth It?", "keywords": "copy ai pricing, copy ai free plan, copy ai pro", "tool_focus": "copyai", "priority": 7},
    # Alternative searches (steal competitor traffic)
    {"topic": "Best Jasper AI Alternatives in 2026 (Cheaper Options)", "keywords": "jasper ai alternatives, alternatives to jasper ai, cheaper ai writing tools", "tool_focus": "copyai", "priority": 8},
    {"topic": "Best Semrush Alternatives in 2026 (Free & Paid)", "keywords": "semrush alternatives, free semrush alternative, cheap seo tools", "tool_focus": "surfer", "priority": 8},
    {"topic": "Best Grammarly Alternatives for 2026", "keywords": "grammarly alternatives, best grammar checker, ai grammar tools", "tool_focus": "jasper", "priority": 7},
]

def build_article_prompt(topic: str, keywords: str, tool_focus: str = None) -> str:
    tool_info = ""
    if tool_focus and tool_focus in AFFILIATE_PROGRAMS:
        t = AFFILIATE_PROGRAMS[tool_focus]
        tool_info = f"""
Featured affiliate tool: {t['name']}
Affiliate URL: {t['signup_url']}
Commission: {t['commission']}
Description: {t['description']}
Rating: {t['rating']}/5

Include this tool prominently. Use the affiliate URL naturally 3-4 times as anchor text like "Try {t['name']} free", "{t['name']} →", or "Get started with {t['name']}".
"""

    other_tools = []
    for k, v in AFFILIATE_PROGRAMS.items():
        if k != tool_focus:
            other_tools.append(f"- {v['name']}: {v['signup_url']} ({v['commission']})")
    other_tools_str = "\n".join(other_tools[:6])

    return f"""Write a comprehensive, SEO-optimized blog article for an affiliate marketing website in the AI tools niche.

TOPIC: {topic}
TARGET KEYWORDS: {keywords}
{tool_info}

OTHER TOOLS TO MENTION (include 2-3 naturally):
{other_tools_str}

REQUIREMENTS:
1. Write in HTML format (use <h2>, <h3>, <p>, <ul>, <li>, <strong>, <a> tags)
2. Length: 1500-2500 words
3. Structure:
   - Opening hook (2-3 sentences that grab attention)
   - Quick answer/TL;DR box (use <div class="tldr-box">)
   - Main content with H2 sections
   - Comparison tables where relevant (use <table class="comparison-table">)
   - Pros/cons lists
   - Pricing section
   - Final verdict with clear recommendation
   - CTA button at end (use <a href="URL" class="cta-button">)
4. SEO optimization:
   - Include target keywords naturally (2-3% density)
   - Use semantic keywords throughout
   - Internal linking placeholder: <a href="/articles/RELATED_SLUG">RELATED TEXT</a>
5. Tone: Expert, helpful, honest — like a trusted advisor. Not salesy.
6. Include specific data, statistics, and real examples
7. IMPORTANT: Make affiliate links feel natural — embedded in context, not pushy

Return a JSON object with EXACTLY this structure:
{{
  "title": "exact article title",
  "meta_description": "155-char SEO meta description with keyword",
  "category": "writing|seo|video|audio|productivity",
  "tags": "comma,separated,tags",
  "content": "full HTML article content here"
}}

Return ONLY the JSON, no markdown, no explanation."""

def generate_article(topic: str, keywords: str, tool_focus: str = None) -> Optional[dict]:
    """Generate a single SEO article using Claude."""
    log.info(f"Generating article: {topic}")

    prompt = build_article_prompt(topic, keywords, tool_focus)

    try:
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text.strip()
        # Clean up any markdown code blocks
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)
        slug = slugify(data["title"])[:80]

        return {
            "slug": slug,
            "title": data["title"],
            "meta_description": data["meta_description"],
            "content": data["content"],
            "category": data.get("category", "writing"),
            "tags": data.get("tags", ""),
            "featured_tool": tool_focus or "",
        }
    except json.JSONDecodeError as e:
        log.error(f"JSON parse error for '{topic}': {e}")
        return None
    except Exception as e:
        log.error(f"Error generating article '{topic}': {e}")
        return None

def populate_initial_queue():
    """Seed the content queue with initial topics."""
    for item in SEED_TOPICS:
        add_to_queue(item["topic"], item["keywords"], item.get("tool_focus"), item.get("priority", 5))
    log.info(f"Added {len(SEED_TOPICS)} topics to content queue.")

def run_content_generation(count: int = 3):
    """Main automation function — called by scheduler daily."""
    log.info(f"=== Content generation run: generating {count} articles ===")
    generated = 0
    failed = 0

    for _ in range(count):
        queued = get_next_queued_topic()
        if not queued:
            log.info("Content queue empty — using seed topics")
            populate_initial_queue()
            queued = get_next_queued_topic()
            if not queued:
                break

        article = generate_article(
            topic=queued["topic"],
            keywords=queued["keywords"],
            tool_focus=queued.get("tool_focus")
        )

        if article:
            saved = save_article(
                slug=article["slug"],
                title=article["title"],
                meta_description=article["meta_description"],
                content=article["content"],
                category=article["category"],
                tags=article["tags"],
                featured_tool=article["featured_tool"],
            )
            if saved:
                mark_queue_item_done(queued["id"])
                log.info(f"Published: {article['title']}")
                generated += 1
            else:
                log.warning(f"Article already exists: {article['slug']}")
                mark_queue_item_done(queued["id"])
        else:
            failed += 1

    log.info(f"Content run complete: {generated} generated, {failed} failed")
    return {"generated": generated, "failed": failed}

if __name__ == "__main__":
    from database.db import init_db
    init_db()
    populate_initial_queue()
    result = run_content_generation(count=3)
    print(f"Done: {result}")
