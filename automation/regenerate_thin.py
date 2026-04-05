#!/usr/bin/env python3
"""
Regenerate all thin articles (< 8000 chars) with Claude Sonnet for proper SEO length.
Run once: python3 automation/regenerate_thin.py
"""
import sqlite3
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.content_generator import generate_article, build_article_prompt
from database.db import init_db

# Map article titles to keywords for regeneration
TOPIC_MAP = {
    "Jasper AI vs Copy.ai": {"keywords": "jasper ai vs copy ai, best ai writing tool 2026", "tool": "jasper"},
    "Semrush Review": {"keywords": "semrush review 2026, semrush pricing, is semrush worth it", "tool": "semrush"},
    "10 Best AI Writing Tools for Content Creators": {"keywords": "best ai writing tools for content creators 2026", "tool": None},
    "ElevenLabs Review": {"keywords": "elevenlabs review 2026, elevenlabs pricing, elevenlabs features", "tool": "elevenlabs"},
    "How to Build an AI Content Workflow": {"keywords": "ai content workflow, ai writing process, automate content creation", "tool": "jasper"},
    "Pictory AI Review": {"keywords": "pictory ai review, pictory pricing, pictory vs competitors", "tool": "pictory"},
    "Surfer SEO Review": {"keywords": "surfer seo review 2026, surfer seo pricing, is surfer seo worth it", "tool": "surfer"},
    "Copy.ai Review": {"keywords": "copy ai review 2026, copy.ai pricing, copy.ai features", "tool": "copyai"},
    "InVideo AI Review": {"keywords": "invideo ai review, invideo pricing, invideo ai features", "tool": "invideo"},
    "Writesonic Review": {"keywords": "writesonic review 2026, writesonic pricing, writesonic vs jasper", "tool": "writesonic"},
    "Fireflies AI Review": {"keywords": "fireflies ai review, fireflies pricing, best meeting notetaker", "tool": "fireflies"},
    "Murf AI Review": {"keywords": "murf ai review 2026, murf ai pricing, murf ai voice generator", "tool": "murf"},
    "Best AI Tools for Freelancers": {"keywords": "best ai tools for freelancers 2026, freelance ai software", "tool": None},
    "Descript Review": {"keywords": "descript review 2026, descript pricing, descript ai video editor", "tool": "descript"},
    "Jasper AI Pricing": {"keywords": "jasper ai pricing 2026, jasper ai plans, jasper ai cost", "tool": "jasper"},
    "AI Tools for Small Business": {"keywords": "ai tools for small business 2026, best ai software for business", "tool": None},
    "Surfer SEO vs Semrush": {"keywords": "surfer seo vs semrush, best seo tool comparison 2026", "tool": "surfer"},
    "How to Use AI Tools to Start a Profitable Blog": {"keywords": "how to start a blog with ai tools, ai blogging guide 2026", "tool": "jasper"},
    "ElevenLabs vs Murf AI": {"keywords": "elevenlabs vs murf ai, best ai voice generator 2026", "tool": "elevenlabs"},
    "The Ultimate Guide to AI Content Marketing": {"keywords": "ai content marketing guide 2026, ai marketing strategy", "tool": "jasper"},
    "10 Best AI Writing Tools in 2026": {"keywords": "best ai writing tools 2026, top ai writers ranked", "tool": None},
    "ChatGPT vs Claude vs Gemini": {"keywords": "chatgpt vs claude vs gemini 2026, best ai chatbot for business", "tool": None},
    "How to Make $5,000/Month with AI Writing Tools": {"keywords": "make money with ai writing tools, ai writing income", "tool": "jasper"},
    "Midjourney vs DALL-E 3": {"keywords": "midjourney vs dalle 3, best ai image generator 2026", "tool": None},
    "10 AI Tools That Pay for Themselves": {"keywords": "ai tools that pay for themselves, roi ai tools, best value ai software", "tool": None},
    "How to Use Jasper AI": {"keywords": "how to use jasper ai, jasper ai tutorial 2026", "tool": "jasper"},
    "Notion AI vs ClickUp AI": {"keywords": "notion ai vs clickup ai, best ai productivity tool 2026", "tool": None},
    "Best AI SEO Tools": {"keywords": "best ai seo tools 2026, ai seo software ranked", "tool": "surfer"},
    "Synthesia Review": {"keywords": "synthesia review 2026, synthesia pricing, synthesia ai video", "tool": "synthesia"},
    "How to Build a $10K/Month Affiliate Blog": {"keywords": "affiliate blog with ai tools, how to make money with ai blog", "tool": "jasper"},
    "ElevenLabs Review 2026": {"keywords": "elevenlabs review 2026, elevenlabs voice cloning, elevenlabs pricing", "tool": "elevenlabs"},
    "Copy.ai vs Writesonic": {"keywords": "copy ai vs writesonic 2026, best ai copywriting tool", "tool": "copyai"},
    "5 Ways AI Tools Can Double Your Freelance Income": {"keywords": "ai tools for freelancers income, double freelance income ai", "tool": None},
    "Runway ML vs CapCut AI": {"keywords": "runway ml vs capcut ai, best ai video editor 2026", "tool": None},
    "The Complete Guide to AI Prompt Engineering": {"keywords": "ai prompt engineering guide 2026, how to write ai prompts", "tool": None},
    "Ahrefs vs SEMrush": {"keywords": "ahrefs vs semrush 2026, best seo tool ahrefs semrush", "tool": "semrush"},
}

def find_keywords(title):
    for key, val in TOPIC_MAP.items():
        if key.lower() in title.lower():
            return val["keywords"], val["tool"]
    return title, None

def regenerate_all():
    init_db()
    conn = sqlite3.connect('data.db')
    thin = conn.execute(
        "SELECT id, slug, title, category, featured_tool FROM articles WHERE LENGTH(content) < 8000 ORDER BY id ASC"
    ).fetchall()
    conn.close()

    print(f"Regenerating {len(thin)} thin articles with Claude Sonnet...")
    success = 0
    failed = 0

    for i, (art_id, slug, title, category, tool_focus) in enumerate(thin):
        keywords, tool = find_keywords(title)
        tool = tool or tool_focus or None

        print(f"\n[{i+1}/{len(thin)}] {title[:60]}")
        print(f"  keywords: {keywords[:50]} | tool: {tool}")

        article = generate_article(topic=title, keywords=keywords, tool_focus=tool)

        if article and len(article["content"]) > 8000:
            conn = sqlite3.connect('data.db')
            conn.execute(
                "UPDATE articles SET title=?, meta_description=?, content=?, tags=?, updated_at=datetime('now') WHERE id=?",
                (article["title"], article["meta_description"], article["content"], article["tags"], art_id)
            )
            conn.commit()
            conn.close()
            words = len(article["content"].split())
            print(f"  ✅ Updated: {words} words")
            success += 1
        else:
            content_len = len(article["content"]) if article else 0
            print(f"  ❌ Too short ({content_len} chars) or failed — skipping")
            failed += 1

        # Small delay to avoid API rate limits
        if i < len(thin) - 1:
            time.sleep(2)

    print(f"\n=== Done: {success} updated, {failed} failed ===")

if __name__ == "__main__":
    regenerate_all()
