"""
Comparison Page Generator — autonomous SEO + affiliate revenue asset.

Generates full `[tool_a]-vs-[tool_b]` comparison articles that:
- Rank for high-intent "X vs Y" queries (5-10× conversion of informational)
- Embed affiliate links to BOTH tools (dual-earning)
- Match the brand voice in SITE_CONTEXT / automation/dominic/CLAUDE.md
- Refuse to fabricate features — any field marked "unknown" stays "unknown"

Usage (CLI):
    python3 -m automation.comparison_page_generator pictory descript
    python3 -m automation.comparison_page_generator --pairs pictory:descript,murf:playht,elevenlabs:speechify

Library:
    from automation.comparison_page_generator import generate_comparison_article
    article = generate_comparison_article("pictory", "descript")

Publishes to the same `articles` table as the existing blog pipeline via
`database.db.save_article()`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic

from affiliate.links import AFFILIATE_PROGRAMS
from config import config
from database.db import save_article, get_article_by_slug

# Per SITE_CONTEXT hard rule — never downgrade the model
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 3500

BANNED_PHRASES = [
    "delve", "unleash", "game-changer", "in today's fast-paced world",
    "revolutionize", "let's dive in", "it's important to note",
    "in conclusion", "the power of", "unlock", "seamlessly",
    "leverage", "empower", "cutting-edge", "at the end of the day",
]


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:90]


def _has_banned_phrase(text: str) -> list:
    lower = text.lower()
    return [p for p in BANNED_PHRASES if p in lower]


def _affiliate_url(key: str) -> str:
    """Resolve to the /go/ redirect on our own site so clicks get tracked
    and affiliate IDs stay server-side (no leakage into scraped HTML)."""
    return f"https://aitoolsempire.co/go/{key}"


def _extract_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _build_prompt(tool_a_key: str, tool_b_key: str) -> str:
    a = AFFILIATE_PROGRAMS[tool_a_key]
    b = AFFILIATE_PROGRAMS[tool_b_key]

    a_url = _affiliate_url(tool_a_key)
    b_url = _affiliate_url(tool_b_key)

    return f"""You are writing a comparison article for AI Tools Empire — an affiliate-review site for solopreneurs, content creators, and SEO/marketing operators. Target readers are decision-makers with budgets comparing two tools side by side.

## Tool A: {a['name']}
- Category:    {a.get('category','?')}
- Description: {a.get('description','?')}
- Commission:  {a.get('commission','?')}
- Rating:      {a.get('rating','?')}
- Reviews:     {a.get('reviews','?')}
- Affiliate URL (use THIS exact URL, with link text "{a['name']}" or "Try {a['name']}"): {a_url}

## Tool B: {b['name']}
- Category:    {b.get('category','?')}
- Description: {b.get('description','?')}
- Commission:  {b.get('commission','?')}
- Rating:      {b.get('rating','?')}
- Reviews:     {b.get('reviews','?')}
- Affiliate URL (use THIS exact URL, with link text "{b['name']}" or "Try {b['name']}"): {b_url}

## Your job
Write ONE comparison article, 900-1400 words, in the structure below. Output strict JSON. No prose outside the JSON.

## Brand voice — non-negotiable
- Second person ("you"). Never corporate "we".
- Sharp, dry, specific. Short sentences. 8 words beats 18.
- Use concrete numbers and specific details. If you don't know something, WRITE "price not listed publicly" or "I don't have that detail" — do NOT invent.
- No fluff openers ("In today's fast-paced world"). No cliché closers ("At the end of the day"). No "game-changer", "revolutionize", "unleash", "let's dive in", "delve", "unlock", "seamlessly", "leverage", "empower", "cutting-edge".

## Must include
- One H1 with both tool names (include the year 2026) — under 70 characters if possible.
- A 2-3 sentence intro that TELLS the reader who should pick each tool (don't bury the lede).
- An `overview` H2 section — short paragraph on each tool (3-4 sentences).
- A `head-to-head` H2 section with structured bullets comparing: pricing, ease of use, best-for use case, limitations. Do not fabricate — if a tool's limitation is unknown, write "verify on their pricing page before committing".
- A `when to pick {a['name']}` H2 section with 2-3 specific buyer personas/use cases.
- A `when to pick {b['name']}` H2 section with 2-3 specific buyer personas/use cases.
- A `verdict` H2 with a one-paragraph recommendation — pick a winner for the most common use case, name it, and say why.
- At least TWO affiliate links to each tool (total 4 minimum), wrapped in proper HTML `<a href="...">` tags. Anchor text varies — don't use the same phrasing twice.
- A short FAQ with 3 questions (e.g., "Which is cheaper?" "Can I use both?" "Does X have a free tier?"). Honest answers.

## Output format (strict JSON, nothing else)

{{
  "title":            "<string, under 70 chars, must include both tool names + '2026'>",
  "meta_description": "<string, under 160 chars, action-oriented, specific to who should pick which>",
  "category":         "<one of: writing, seo, video, audio, productivity, ecommerce, design, analytics>",
  "tags":             "<comma-separated tags, no more than 8>",
  "featured_tool":    "<'{tool_a_key}' if the article's verdict favors Tool A, else '{tool_b_key}'>",
  "content_html":     "<full HTML body — no <html>/<head>/<body> wrappers, just content sections starting from H1>",
  "word_count":       <integer>,
  "verdict_tool":     "<'{tool_a_key}' or '{tool_b_key}'>"
}}
"""


def generate_comparison_article(tool_a_key: str, tool_b_key: str) -> Optional[Dict]:
    """
    Generate + save a comparison article. Returns the saved article dict or None on failure.
    Idempotent — if an article with the generated slug already exists, returns None.
    """
    if tool_a_key not in AFFILIATE_PROGRAMS:
        raise ValueError(f"Unknown tool: {tool_a_key}")
    if tool_b_key not in AFFILIATE_PROGRAMS:
        raise ValueError(f"Unknown tool: {tool_b_key}")
    if tool_a_key == tool_b_key:
        raise ValueError("Cannot compare a tool to itself")

    a_name = AFFILIATE_PROGRAMS[tool_a_key]["name"]
    b_name = AFFILIATE_PROGRAMS[tool_b_key]["name"]
    print(f"▶ Generating: {a_name} vs {b_name}")

    prompt = _build_prompt(tool_a_key, tool_b_key)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text if resp.content else ""

    parsed = _extract_json(raw)
    if not parsed:
        print(f"  ❌ JSON parse failed — raw head: {raw[:200]}")
        return None

    # Post-validate against banned phrases
    content = parsed.get("content_html", "")
    hits = _has_banned_phrase(content)
    if hits:
        print(f"  ⚠️  Banned phrases in content: {hits} — keeping anyway, flag for editorial review")

    # Compute slug from title; fall back to canonical form
    title = parsed.get("title", f"{a_name} vs {b_name}: 2026 Comparison")
    slug = _slugify(title)
    if get_article_by_slug(slug):
        print(f"  ⏭️  Article already exists: {slug}")
        return None

    # Save to DB
    saved = save_article(
        slug=slug,
        title=title,
        meta_description=parsed.get("meta_description", "")[:160],
        content=content,
        category=parsed.get("category", "comparison"),
        tags=parsed.get("tags", f"{tool_a_key},{tool_b_key},comparison,2026"),
        featured_tool=parsed.get("featured_tool", tool_a_key),
    )
    if not saved:
        print(f"  ❌ DB save failed for {slug}")
        return None

    print(f"  ✅ Published: https://aitoolsempire.co/articles/{slug}")
    print(f"     wc={parsed.get('word_count','?')} verdict={parsed.get('verdict_tool','?')}")

    return {
        "slug":           slug,
        "title":          title,
        "word_count":     parsed.get("word_count", 0),
        "verdict_tool":   parsed.get("verdict_tool", tool_a_key),
        "banned_hits":    hits,
        "url":            f"https://aitoolsempire.co/articles/{slug}",
    }


def generate_batch(pairs: list[Tuple[str, str]]) -> Dict:
    """Run the generator over multiple pairs. Continues on individual failures."""
    results = {"generated": [], "failed": [], "skipped": []}
    for a, b in pairs:
        try:
            result = generate_comparison_article(a, b)
            if result is None:
                results["skipped"].append(f"{a}_vs_{b}")
            else:
                results["generated"].append(result)
        except Exception as e:
            print(f"  ❌ Error on {a} vs {b}: {e}")
            results["failed"].append({"pair": f"{a}_vs_{b}", "error": str(e)})
    return results


def _parse_pairs_arg(s: str) -> list[Tuple[str, str]]:
    pairs = []
    for p in s.split(","):
        p = p.strip()
        if not p:
            continue
        if ":" not in p:
            raise ValueError(f"Bad pair format (expected a:b): {p!r}")
        a, b = p.split(":", 1)
        pairs.append((a.strip(), b.strip()))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate AI-tool comparison articles.")
    parser.add_argument("tool_a", nargs="?", help="First tool key (from AFFILIATE_PROGRAMS)")
    parser.add_argument("tool_b", nargs="?", help="Second tool key")
    parser.add_argument("--pairs", help="Comma-separated a:b pairs (e.g. pictory:descript,murf:playht)")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt but don't call Claude or save")
    args = parser.parse_args()

    if args.pairs:
        pairs = _parse_pairs_arg(args.pairs)
    elif args.tool_a and args.tool_b:
        pairs = [(args.tool_a, args.tool_b)]
    else:
        parser.error("Provide either two positional tool keys or --pairs")

    if args.dry_run:
        for a, b in pairs:
            print(f"--- Prompt for {a} vs {b} ---")
            print(_build_prompt(a, b))
        return 0

    results = generate_batch(pairs)
    print()
    print(f"=== SUMMARY: {len(results['generated'])} generated, "
          f"{len(results['skipped'])} skipped, {len(results['failed'])} failed ===")
    return 0 if results["generated"] or not pairs else 1


if __name__ == "__main__":
    sys.exit(main())
