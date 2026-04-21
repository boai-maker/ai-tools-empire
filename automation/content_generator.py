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
    # New high-traffic comparisons
    {"topic": "ChatGPT Plus vs Claude Pro: Which AI Is Worth $20/Month?", "keywords": "chatgpt plus vs claude pro, best ai subscription 2026", "tool_focus": None, "priority": 9},
    {"topic": "Canva AI vs Adobe Firefly: Best AI Design Tool in 2026?", "keywords": "canva ai vs adobe firefly, best ai design tool 2026", "tool_focus": None, "priority": 8},
    {"topic": "Jasper AI vs Writesonic: Which Writes Better Content?", "keywords": "jasper vs writesonic 2026, best ai writer comparison", "tool_focus": "jasper", "priority": 8},
    {"topic": "Otter.ai vs Fireflies.ai: Best AI Meeting Tool in 2026?", "keywords": "otter ai vs fireflies ai, best meeting transcription tool", "tool_focus": "fireflies", "priority": 8},
    {"topic": "Midjourney vs Stable Diffusion: Best AI Art Generator?", "keywords": "midjourney vs stable diffusion, best ai art generator 2026", "tool_focus": None, "priority": 8},
    {"topic": "Claude AI vs ChatGPT: Which is Better for Business in 2026?", "keywords": "claude vs chatgpt, claude ai review, best ai chatbot 2026", "tool_focus": None, "priority": 9},
    {"topic": "Ahrefs vs Moz: Which SEO Tool Is Worth It in 2026?", "keywords": "ahrefs vs moz, best seo tool 2026, ahrefs moz comparison", "tool_focus": "semrush", "priority": 8},
    {"topic": "HubSpot vs ActiveCampaign: Best AI Marketing Tool?", "keywords": "hubspot vs activecampaign, best email marketing platform 2026", "tool_focus": None, "priority": 7},
    # New reviews
    {"topic": "Perplexity AI Review 2026: The Google Killer?", "keywords": "perplexity ai review, perplexity vs google, best ai search engine", "tool_focus": None, "priority": 8},
    {"topic": "Notion AI Review 2026: Is It Worth the Upgrade?", "keywords": "notion ai review 2026, notion ai features, notion ai pricing", "tool_focus": None, "priority": 7},
    {"topic": "Otter.ai Review 2026: Best AI Meeting Transcription?", "keywords": "otter ai review 2026, otter ai pricing, otter ai features", "tool_focus": "fireflies", "priority": 7},
    {"topic": "Canva AI Review 2026: Is Magic Studio Worth It?", "keywords": "canva ai review, canva magic studio, canva ai features 2026", "tool_focus": None, "priority": 7},
    {"topic": "HeyGen Review 2026: Best AI Video Avatar Tool?", "keywords": "heygen review, heygen pricing, heygen ai video", "tool_focus": "synthesia", "priority": 7},
    {"topic": "Loom AI Review 2026: Best AI Video Messaging Tool?", "keywords": "loom ai review, loom pricing, loom ai features", "tool_focus": None, "priority": 6},
    # New listicles
    {"topic": "10 Best AI Tools for Social Media Marketing in 2026", "keywords": "best ai tools for social media, ai social media marketing 2026", "tool_focus": "jasper", "priority": 8},
    {"topic": "7 Best AI Chatbots for Customer Service in 2026", "keywords": "best ai chatbots for customer service, ai customer support tools", "tool_focus": None, "priority": 7},
    {"topic": "Best Free AI Tools in 2026 (No Credit Card Required)", "keywords": "best free ai tools 2026, free ai software, no cost ai tools", "tool_focus": None, "priority": 9},
    {"topic": "10 Best AI Tools for Students in 2026 (Free & Paid)", "keywords": "best ai tools for students, ai study tools 2026", "tool_focus": None, "priority": 8},
    {"topic": "Best AI Tools for Real Estate Agents in 2026", "keywords": "ai tools for real estate, best real estate ai software 2026", "tool_focus": None, "priority": 7},
    {"topic": "Best AI Writing Tools for Bloggers in 2026 (Ranked)", "keywords": "best ai writing tools for bloggers, ai blogging tools 2026", "tool_focus": "jasper", "priority": 8},
    {"topic": "5 Best AI Tools for YouTube Creators in 2026", "keywords": "best ai tools for youtube, ai youtube tools 2026", "tool_focus": "pictory", "priority": 8},
    # How-to money guides (high intent)
    {"topic": "How to Make Money with AI in 2026 (7 Proven Methods)", "keywords": "how to make money with ai 2026, ai income ideas, earn money ai", "tool_focus": "jasper", "priority": 9},
    {"topic": "How to Start an AI Affiliate Marketing Business in 2026", "keywords": "ai affiliate marketing 2026, how to start affiliate marketing ai", "tool_focus": "jasper", "priority": 9},
    {"topic": "How to Use Claude AI for Business: Complete Guide 2026", "keywords": "how to use claude ai for business, claude ai business guide", "tool_focus": None, "priority": 8},
    {"topic": "How to Write SEO Content with AI Tools (Step-by-Step)", "keywords": "how to write seo content with ai, ai seo writing guide", "tool_focus": "surfer", "priority": 8},
    {"topic": "How to Build a Passive Income Blog with AI in 2026", "keywords": "passive income blog with ai, ai blog income 2026", "tool_focus": "jasper", "priority": 8},
    # Pricing deep-dives
    {"topic": "ElevenLabs Pricing 2026: Which Plan Is Right for You?", "keywords": "elevenlabs pricing, elevenlabs plans, elevenlabs cost 2026", "tool_focus": "elevenlabs", "priority": 8},
    {"topic": "Surfer SEO Pricing 2026: Is It Worth the Cost?", "keywords": "surfer seo pricing 2026, surfer seo cost, surfer seo plans", "tool_focus": "surfer", "priority": 8},
    {"topic": "Pictory AI Pricing 2026: Free vs Paid Plans Compared", "keywords": "pictory ai pricing, pictory plans, pictory ai cost", "tool_focus": "pictory", "priority": 7},
    {"topic": "Writesonic Pricing 2026: Best Plan for Your Budget?", "keywords": "writesonic pricing 2026, writesonic plans, writesonic cost", "tool_focus": "writesonic", "priority": 7},
    # Fresh Q2-2026 topics (added 2026-04-21 after SEED pool exhaustion)
    {"topic": "GPT-5 vs Claude 4.7: Which AI Model Wins in Late 2026?", "keywords": "gpt-5 vs claude 4.7, best ai model 2026, claude vs chatgpt late 2026", "tool_focus": None, "priority": 9},
    {"topic": "Best AI Coding Assistants in 2026 (Cursor, Copilot, Claude Code)", "keywords": "best ai coding assistant 2026, cursor vs copilot, claude code review", "tool_focus": None, "priority": 9},
    {"topic": "Best AI Agents You Can Use Today (No Code Required) 2026", "keywords": "best ai agents 2026, no-code ai agents, autonomous ai tools", "tool_focus": None, "priority": 9},
    {"topic": "How to Use AI to Write a Book in 30 Days (2026 Method)", "keywords": "write book with ai 2026, ai book writing, how to write book ai", "tool_focus": "jasper", "priority": 8},
    {"topic": "Best AI Tools for Podcasters in 2026 (Edit, Host, Grow)", "keywords": "best ai tools for podcasters 2026, ai podcast editing, podcast ai tools", "tool_focus": "fireflies", "priority": 8},
    {"topic": "Best AI Resume Builders 2026: Land More Interviews", "keywords": "best ai resume builder 2026, ai cv generator, resume ai tools", "tool_focus": None, "priority": 8},
    {"topic": "Best AI Email Writing Tools for Cold Outreach in 2026", "keywords": "best ai email writer 2026, ai cold email tools, sales email ai", "tool_focus": "jasper", "priority": 8},
    {"topic": "How to Build an AI Newsletter Business in 2026 (Step-by-Step)", "keywords": "ai newsletter business 2026, how to start newsletter ai, ai content newsletter", "tool_focus": "kit", "priority": 8},
    {"topic": "Best AI Tools for E-commerce Sellers in 2026", "keywords": "best ai tools for ecommerce 2026, ai ecommerce tools, shopify ai tools", "tool_focus": None, "priority": 8},
    {"topic": "Cursor vs GitHub Copilot 2026: Which AI Code Editor Wins?", "keywords": "cursor vs github copilot 2026, best ai code editor, cursor review 2026", "tool_focus": None, "priority": 9},
    {"topic": "Best AI Photo Editors in 2026 (Background, Retouch, Generate)", "keywords": "best ai photo editor 2026, ai image editing tools, photo ai generator", "tool_focus": None, "priority": 7},
    {"topic": "How to Automate Your Business with AI in 2026 (No Engineers)", "keywords": "automate business with ai 2026, business automation ai tools, no-code ai automation", "tool_focus": None, "priority": 9},
    {"topic": "Best AI Scheduling Tools for Small Teams 2026", "keywords": "best ai scheduling tools 2026, ai meeting scheduler, calendar ai tools", "tool_focus": None, "priority": 7},
    {"topic": "Runway Gen-3 vs Sora vs Veo: Best AI Video Model in 2026?", "keywords": "runway vs sora vs veo 2026, best ai video model, text to video ai comparison", "tool_focus": "pictory", "priority": 9},
    {"topic": "How to Start a Faceless YouTube Channel with AI in 2026", "keywords": "faceless youtube channel 2026, ai youtube automation, make money youtube ai", "tool_focus": "pictory", "priority": 9},
    {"topic": "Best AI Logo Generators 2026 (Free & Paid, Tested)", "keywords": "best ai logo generator 2026, ai logo maker, free logo ai", "tool_focus": None, "priority": 7},
    {"topic": "AI Agent Builders Compared: n8n, Make, Zapier, Claude Projects", "keywords": "ai agent builder comparison 2026, n8n vs make vs zapier, best ai workflow tool", "tool_focus": None, "priority": 8},
    {"topic": "How to Use AI to 10x Your Freelance Writing Income in 2026", "keywords": "ai freelance writing 2026, make money writing with ai, ai writer income", "tool_focus": "jasper", "priority": 8},
    {"topic": "Best AI Tools for Realtors & Real Estate Investors 2026", "keywords": "ai tools for realtors 2026, real estate ai software, ai real estate investing", "tool_focus": None, "priority": 8},
    {"topic": "Best AI Data Analysis Tools 2026 (For Non-Technical Users)", "keywords": "best ai data analysis 2026, ai analytics tools, no-code data ai", "tool_focus": None, "priority": 7},
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

CRITICAL LENGTH REQUIREMENT: The article MUST be 2000-2500 words. Google does NOT rank thin content.
Each H2 section must have 3-5 detailed paragraphs (150-200 words each). Do not summarize or bullet-only.
Write full, detailed, helpful prose like a professional journalist would. Thin content gets penalized.

REQUIREMENTS:
1. Write in HTML format (use <h2>, <h3>, <p>, <ul>, <li>, <strong>, <a> tags)
2. Length: MINIMUM 2000 words — count carefully, each H2 section needs 150-250 words of paragraphs
3. Structure:
   - Opening hook (2-3 engaging sentences + context paragraph 100+ words)
   - Quick TL;DR summary box (use <div class="tldr-box">) with 5-6 bullet points
   - 6-8 H2 sections, each with 2-4 paragraphs of detailed analysis
   - Comparison table where relevant (use <table class="comparison-table">)
   - Dedicated Pricing section with real price data
   - Pros/cons section for each tool
   - Who should use it / Use cases section
   - Final verdict with clear recommendation paragraph (150+ words)
   - CTA button at end (use <a href="URL" class="cta-button">)
4. SEO optimization:
   - Include target keywords naturally in intro, one H2 heading, and conclusion
   - Use semantic/LSI keywords throughout
   - Internal linking: <a href="/articles/RELATED_SLUG">RELATED TEXT</a> (2-3 links)
5. Tone: Expert, helpful, honest — like a trusted advisor who has used the tool. Not salesy.
6. Include specific features, use cases, limitations, and real-world examples
7. Make affiliate links feel natural — embedded in useful context ("you can try it at...")

Return a JSON object with EXACTLY this structure:
{{
  "title": "exact article title (50-60 chars, include primary keyword)",
  "meta_description": "150-160 char SEO meta description with primary keyword in first 60 chars",
  "category": "writing|seo|video|audio|productivity",
  "tags": "comma,separated,tags",
  "content": "full HTML article content — MUST BE 2000+ WORDS"
}}

Return ONLY the JSON object. No markdown fences, no explanation, no preamble."""

def generate_article(topic: str, keywords: str, tool_focus: str = None) -> Optional[dict]:
    """Generate a single SEO article using Claude."""
    log.info(f"Generating article: {topic}")

    prompt = build_article_prompt(topic, keywords, tool_focus)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = message.content[0].text.strip()
        # Clean up any markdown code blocks
        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: extract fields via regex for robustly escaped HTML content
            def extract_field(text, field):
                # Match "field": "value" where value may contain escaped chars
                pattern = rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)\"'
                m = re.search(pattern, text, re.DOTALL)
                return m.group(1) if m else None

            # For content field, use a broader match between first "content": " and last closing
            content_match = re.search(r'"content"\s*:\s*"(.*)"(?:\s*[,}])', raw, re.DOTALL)
            if not content_match:
                log.error(f"Could not extract content for '{topic}'")
                return None

            title = extract_field(raw, "title") or topic
            meta = extract_field(raw, "meta_description") or f"Read our review of {topic}"
            category = extract_field(raw, "category") or "writing"
            tags = extract_field(raw, "tags") or ""
            content_raw = content_match.group(1)
            # Unescape JSON string escapes
            content_raw = content_raw.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').replace('\\\\', '\\')
            data = {"title": title, "meta_description": meta, "content": content_raw, "category": category, "tags": tags}

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
                # Inject affiliate CTAs into the new article
                try:
                    import sys, os
                    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    from inject_affiliate_ctas import inject_ctas_into_content, CATEGORY_TOOL_MAP
                    primary = article["featured_tool"] or (CATEGORY_TOOL_MAP.get(article["category"], ["jasper"])[0])
                    cat_tools = CATEGORY_TOOL_MAP.get(article["category"], ["jasper"])
                    secondary = next((t for t in cat_tools if t != primary), None)
                    new_content = inject_ctas_into_content(article["content"], primary, secondary)
                    if new_content != article["content"]:
                        from database.db import get_conn
                        conn = get_conn()
                        conn.execute("UPDATE articles SET content=? WHERE slug=?", (new_content, article["slug"]))
                        conn.commit()
                        conn.close()
                        log.info(f"CTAs injected into: {article['title']}")
                except Exception as cta_err:
                    log.warning(f"CTA injection failed: {cta_err}")
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
