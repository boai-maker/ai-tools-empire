"""
YouTube content generator for Dominic.
Generates full YouTube content packages using Claude.
"""
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from automation.dominic.config import get_config
from automation.dominic.db import save_content
from automation.dominic.logger import log_action, log_error

# ---------------------------------------------------------------------------
# Templates / Constants
# ---------------------------------------------------------------------------

YOUTUBE_TITLE_FORMULAS = [
    "I Tested {n} AI Tools for {use_case} — Here's the Honest Truth",
    "{Tool} Review ({year}): Is It Actually Worth It?",
    "The Only AI Tool Guide You'll Ever Need for {use_case}",
    "{Tool} vs {Tool2}: Which One Should You Use?",
    "How I {outcome} Using Only AI Tools (Step-by-Step)",
    "Stop Wasting Money on AI Tools — Watch This First",
    "{n} Free AI Tools That Replace Expensive Software",
    "The Complete Beginner's Guide to {topic} with AI",
    "AI Tools That Actually Changed My {workflow} in {year}",
    "I Used AI Tools for {timeframe} — Here's What Happened",
]

YOUTUBE_DESCRIPTION_TEMPLATES = [
    """In this video, I'm reviewing {title_short} and breaking down exactly what it does well, what it doesn't, and whether it's worth your money.

⏱️ Timestamps:
{timestamps}

🔗 Resources Mentioned:
{resources}

📌 About AI Tools Empire:
We test and review AI tools so you don't have to. No sponsored opinions — just honest, in-depth breakdowns.

🌐 Website: https://aitoolsempire.co
📧 Newsletter: https://aitoolsempire.co/newsletter

#AItools #{tool_tag} #AIReview
""",
    """In today's video, I'm walking you through {title_short} from start to finish.

This is the complete guide — no fluff, no filler. Just exactly what works.

⏱️ What We Cover:
{timestamps}

💡 All tools mentioned:
{resources}

If this was useful, subscribe for weekly AI tool reviews and tutorials.

🌐 https://aitoolsempire.co

#{tool_tag} #AItools #Productivity
""",
]

THUMBNAIL_PROMPT_TEMPLATES = [
    "Bold YouTube thumbnail with dark background. Large white text: '{hook_text}'. A glowing AI circuit brain graphic on the right. Red accent highlights. Professional tech style, high contrast. NO faces. 1280x720px.",
    "Split-screen YouTube thumbnail. Left side: '{tool1}' logo with red X. Right side: '{tool2}' logo with green checkmark. Text overlay: 'WHICH WINS?' in bold yellow. Dark background. Crisp, professional.",
    "YouTube thumbnail: person (no face, just hands on keyboard) with floating AI tool UI panels around them. Bold text overlay: '{headline}'. Deep blue gradient background. Clean and modern.",
    "High-impact YouTube thumbnail. Central bold text: '{headline}'. Around it, 4-6 small AI tool logos arranged in a grid. Bright orange accent colors. Black background. Tech/SaaS aesthetic.",
    "YouTube thumbnail: A computer screen showing an AI tool interface. Dramatic lighting. Bold text overlay: '{hook_text}'. Subtitle text: '{sub_text}'. Clean, professional, high resolution.",
    "Minimalist YouTube thumbnail. Large bold number '{number}' in neon green. Text beside it: '{headline}'. Dark background with subtle grid pattern. AI / tech aesthetic.",
    "YouTube thumbnail: Before/After split. Left side (red tint, messy): '{before_label}'. Right side (green tint, clean): '{after_label}'. Bold 'VS' in center. Professional quality.",
    "YouTube thumbnail: Money/growth theme. Dollar signs and upward arrow graphics. Bold text: '{headline}'. Subtitle: '{sub_text}'. Dark background with gold accents.",
    "YouTube thumbnail: Glowing laptop screen floating in dark space. Screen shows AI tool dashboard. Bold text overlay above: '{headline}'. Futuristic, cinematic look.",
    "YouTube thumbnail: Attention-grabbing warning style. Yellow caution tape across dark background. Bold text: '{headline}'. Urgent, clean, high-contrast design.",
]


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------

def _call_claude(prompt: str, max_tokens: int = 1500) -> str:
    try:
        import anthropic
        cfg = get_config()
        client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        response = client.messages.create(
            model=cfg.claude_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else ""
    except Exception as e:
        log_error("youtube_gen", str(e), "_call_claude")
        return ""


# ---------------------------------------------------------------------------
# Generation functions
# ---------------------------------------------------------------------------

def generate_title(topic: str) -> str:
    """
    Generate 5 YouTube title options, return the best one.
    """
    cfg = get_config()
    year = datetime.utcnow().year

    prompt = f"""You are a YouTube SEO expert for AI Tools Empire (aitoolsempire.co).
Generate 5 YouTube video title options for this topic: "{topic}"

Rules:
- Under 70 characters each
- Optimized for search AND click-through rate
- Use numbers where natural (e.g., "5 AI Tools", "I Tested 10...")
- Include the year {year} where relevant
- Avoid clickbait without substance
- Audience: content creators, marketers, small businesses using AI tools

Return as a numbered list (1-5). No explanation."""

    raw = _call_claude(prompt, max_tokens=400)
    titles = []
    for line in raw.strip().split("\n"):
        line = re.sub(r"^\d+[\.\)]\s*", "", line.strip())
        if len(line) > 10:
            titles.append(line)

    if not titles:
        return f"The Complete Guide to {topic} with AI Tools ({year})"

    # Pick the best: prefer titles with numbers, year, or action words
    def score_title(t: str) -> float:
        s = 0.0
        if any(c.isdigit() for c in t):
            s += 0.3
        if str(year) in t:
            s += 0.2
        if len(t) <= 60:
            s += 0.2
        for word in ["tested", "honest", "review", "guide", "best", "free", "how"]:
            if word.lower() in t.lower():
                s += 0.1
        return s

    titles.sort(key=score_title, reverse=True)
    return titles[0]


def generate_description(title: str, topic: str, tags: List[str]) -> str:
    """Generate a full SEO-optimized YouTube description."""
    cfg = get_config()
    tag_str = " ".join(f"#{t.replace(' ','')}" for t in tags[:5])

    prompt = f"""Write a complete YouTube video description for:
Title: {title}
Topic: {topic}
Site: {cfg.site_url}
Tags: {tag_str}

Include:
1. Opening paragraph (2-3 sentences) — hooks viewer, explains what video covers
2. "What you'll learn:" section (4-6 bullet points)
3. Timestamps placeholder (00:00, 01:30, etc. with generic labels)
4. Resources/Links section mentioning {cfg.site_url}
5. Brief channel description (AI Tools Empire — honest AI tool reviews)
6. 3-5 relevant hashtags at the end

Keep it natural, informative, and SEO-friendly. Total: 250-400 words."""

    desc = _call_claude(prompt, max_tokens=800)
    if not desc:
        return f"""In this video, we cover everything you need to know about {topic}.

🔗 More AI tool reviews: {cfg.site_url}

Subscribe for weekly AI tool content.

{tag_str}"""
    return desc.strip()


def generate_tags(title: str, topic: str) -> List[str]:
    """Generate 15-20 YouTube tags."""
    prompt = f"""Generate 18 YouTube tags for a video titled: "{title}" about: "{topic}"

Rules:
- Mix of broad tags and specific tags
- Include "AI tools", "artificial intelligence", "productivity" and related terms
- Include tool-specific tags where relevant
- Include {datetime.utcnow().year} where applicable
- Mix short and long-tail tags

Return as a comma-separated list. No explanation. No hashtags (#), just words."""

    raw = _call_claude(prompt, max_tokens=200)
    if raw:
        tags = [t.strip().strip('"').strip("'") for t in raw.split(",") if t.strip()]
        return tags[:20]

    # Fallback tags
    return [
        "AI tools", "artificial intelligence", "productivity", "AI review",
        topic, "best AI tools", "AI tools 2025", "content creation AI",
        "AI for business", "machine learning tools", "AI software",
        "tech review", "AI tutorial", "AI tools comparison", "ChatGPT alternatives",
        "AI writing tools", "automation tools", "AI apps",
    ]


def generate_outline(title: str, topic: str) -> str:
    """Generate a full video outline with timestamps."""
    prompt = f"""Create a detailed video outline for a YouTube video:
Title: {title}
Topic: {topic}

Format:
00:00 - Intro & Hook (30s)
00:30 - [Section name] (X min)
...

Include:
- Attention-grabbing intro (hook, what they'll learn)
- 4-6 main sections with clear learning objectives
- Practical demonstration or examples section
- Pros/Cons or comparison section (if applicable)
- Summary and recommendation
- CTA outro

Make timestamps realistic (10-15 min video). Be specific, not generic."""

    outline = _call_claude(prompt, max_tokens=600)
    if not outline:
        return f"""00:00 - Intro & Hook
01:00 - What is {topic}?
03:00 - Key Features Breakdown
06:00 - Practical Demo
09:00 - Pros & Cons
11:30 - Final Verdict & Recommendation
13:00 - Resources & Links"""
    return outline.strip()


def generate_script(title: str, outline: str, word_count: int = 1500) -> str:
    """Generate a full video script."""
    cfg = get_config()

    prompt = f"""Write a full YouTube video script for:
Title: {title}
Site: {cfg.site_url}
Target length: ~{word_count} words

Outline:
{outline}

Script guidelines:
- Conversational, engaging, direct — like a knowledgeable friend explaining things
- Start with a strong hook in the first 15 seconds (question, bold claim, or surprising fact)
- Include [B-ROLL: description] notes where relevant
- Include clear transitions between sections
- Natural speech patterns — short sentences work well
- End with clear CTA: "Like, subscribe, and visit {cfg.site_url} for more"
- NO hollow filler phrases like "Today we're going to be talking about..."

Format: Full script with section headers matching the outline."""

    script = _call_claude(prompt, max_tokens=3000)
    if not script:
        return f"""[HOOK]
Here's the truth about {title}: most people are doing it wrong. By the end of this video, you'll know exactly what works.

[MAIN CONTENT]
Let's break this down...

[CTA]
If this helped you, hit subscribe and visit {cfg.site_url} for the full breakdown and links to everything mentioned."""

    return script.strip()


def generate_thumbnail_prompt(title: str) -> str:
    """Generate a detailed image generation prompt for thumbnail."""
    import random
    words = title.split()
    hook_text = title[:35] if len(title) > 35 else title
    sub_text = "Full Honest Review"
    template = random.choice(THUMBNAIL_PROMPT_TEMPLATES)

    return template.format(
        hook_text=hook_text,
        headline=title[:50],
        sub_text=sub_text,
        tool1="Tool A",
        tool2="Tool B",
        before_label="Hours of manual work",
        after_label="AI does it in minutes",
        number=str(random.choice([5, 7, 10, 12])),
        n=str(random.choice([5, 7, 10])),
        tool_tag=words[0].upper() if words else "AI",
    )


def generate_video_concept(idea_dict: Dict) -> Dict:
    """
    Generate a full video concept from an idea dict.
    Returns dict with title, description, tags, outline, thumbnail_prompt.
    """
    headline = idea_dict.get("headline") or ""
    body = idea_dict.get("body") or ""
    topic = f"{headline}. {body[:200]}"

    title = generate_title(topic)
    tags = generate_tags(title, topic)
    outline = generate_outline(title, topic)
    description = generate_description(title, topic, tags)
    thumbnail_prompt = generate_thumbnail_prompt(title)

    concept = {
        "title": title,
        "description": description,
        "tags": tags,
        "outline": outline,
        "thumbnail_prompt": thumbnail_prompt,
        "source_idea": idea_dict,
    }

    log_action("video_concept", "youtube_gen", "ok", title[:60])

    # Auto-enqueue for the video engine so it actually gets rendered
    try:
        enqueue_for_video_engine({
            "headline": title,
            "body": idea_dict.get("body", ""),
            "url": idea_dict.get("url", ""),
            "id": idea_dict.get("id"),
        }, format_type="long")
    except Exception as e:
        log_error("youtube_gen", f"enqueue failed: {e}", "generate_video_concept")

    return concept


def generate_full_package(idea_dict: Dict) -> Dict:
    """
    Generate a complete YouTube content package.
    Returns concept + full script.
    """
    concept = generate_video_concept(idea_dict)
    script = generate_script(concept["title"], concept["outline"])

    package = {
        **concept,
        "script": script,
        "word_count": len(script.split()),
        "generated_at": datetime.utcnow().isoformat(),
    }

    log_action("full_package", "youtube_gen", "ok", concept["title"][:60])
    return package


def enqueue_for_video_engine(idea_dict: Dict, format_type: str = "long") -> bool:
    """
    Convert a Dominic idea into a VideoSpec and append it to the unified
    video engine's queue. The engine's scheduled run will pick it up
    automatically. Dedup'd by topic inside the queue helper.
    """
    try:
        from bots.video_engine import enqueue
    except Exception as e:
        log_error("youtube_gen", f"video_engine import failed: {e}", "enqueue")
        return False

    headline = idea_dict.get("headline") or ""
    body = idea_dict.get("body") or ""
    spec = {
        "format_type": format_type,
        "topic": headline,
        "tool": idea_dict.get("tool", ""),
        "angle": (body[:200] or headline)[:200],
        "pain": idea_dict.get("pain", ""),
        "url": idea_dict.get("url", ""),
        "emoji": idea_dict.get("emoji", "🎬"),
        "category": idea_dict.get("category", "AI Tools"),
        "source": "dominic",
        "dominic_id": idea_dict.get("id"),
    }
    ok = enqueue(spec)
    log_action("enqueue_video_spec", "youtube_gen", "ok" if ok else "skip", headline[:60])
    return ok


def save_video_draft(package: Dict) -> Optional[int]:
    """Save a YouTube video package to dom_content as a draft."""
    title = package.get("title") or ""
    description = package.get("description") or ""
    script = package.get("script") or ""
    source_idea = package.get("source_idea") or {}

    # Store script + outline + tags in body as JSON summary
    body_data = {
        "description": description[:500],
        "outline": package.get("outline", ""),
        "tags": package.get("tags", []),
        "thumbnail_prompt": package.get("thumbnail_prompt", ""),
        "script_preview": script[:500],
        "word_count": package.get("word_count", 0),
    }

    content_id = save_content(
        headline=title,
        body=json.dumps(body_data, ensure_ascii=False),
        content_type="video_topic",
        platform="youtube",
        confidence=source_idea.get("confidence", 0.6),
        url=source_idea.get("url", ""),
        source_title=source_idea.get("source_title", ""),
        status="draft",
    )

    if content_id:
        log_action("save_video_draft", "youtube_gen", "ok", f"id={content_id}, title={title[:50]}")
    else:
        log_error("youtube_gen", "Failed to save video draft", title[:50])

    return content_id
