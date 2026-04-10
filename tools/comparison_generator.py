"""
Comparison Table Data Generator
================================
Provides structured data for the comparison_table.html Jinja2 macro.

Usage in main.py article route:
    from tools.comparison_generator import get_comparison_data
    ctx["comparison"] = get_comparison_data(slug)

Usage in article.html template:
    {% if comparison %}
      {% from 'macros/comparison_table.html' import render_comparison %}
      {{ render_comparison(**comparison) }}
    {% endif %}

CLI (print JSON for a slug):
    python tools/comparison_generator.py surfer-seo-vs-semrush-complete-comparison-2024
"""
import json
import sys

# ---------------------------------------------------------------------------
# Tool attribute database
# ---------------------------------------------------------------------------
TOOLS = {
    "jasper": {
        "name": "Jasper AI",
        "logo_emoji": "✍️",
        "price": "from $49/mo",
        "free_plan": "No (7-day trial)",
        "starting_price": "$49/mo",
        "best_for": "Long-form content & brand voice",
        "templates": "50+",
        "seo_mode": "Yes (Surfer integration)",
        "brand_voice": "Yes",
        "chrome_ext": "Yes",
        "api": "Yes",
        "affiliate_url": "https://jasper.ai",
    },
    "copyai": {
        "name": "Copy.ai",
        "logo_emoji": "📝",
        "price": "Free / $49/mo",
        "free_plan": "Yes (2,000 words/mo)",
        "starting_price": "$49/mo (Pro)",
        "best_for": "Short-form copy & social media",
        "templates": "90+",
        "seo_mode": "No",
        "brand_voice": "Limited",
        "chrome_ext": "Yes",
        "api": "Yes",
        "affiliate_url": "https://copy.ai",
    },
    "writesonic": {
        "name": "Writesonic",
        "logo_emoji": "⚡",
        "price": "Free / $13/mo",
        "free_plan": "Yes (10,000 words)",
        "starting_price": "$13/mo",
        "best_for": "Budget-friendly long-form writing",
        "templates": "100+",
        "seo_mode": "Yes (Surfer integration)",
        "brand_voice": "Yes",
        "chrome_ext": "Yes",
        "api": "Yes",
        "affiliate_url": "https://writesonic.com",
    },
    "surfer": {
        "name": "Surfer SEO",
        "logo_emoji": "🏄",
        "price": "from $89/mo",
        "free_plan": "No (7-day trial)",
        "starting_price": "$89/mo",
        "best_for": "On-page SEO optimization",
        "content_editor": "Yes",
        "keyword_research": "Yes",
        "audit_tool": "Yes",
        "integrations": "Google Docs, WordPress, Jasper",
        "api": "Yes",
        "affiliate_url": "https://surferseo.com",
    },
    "semrush": {
        "name": "SEMrush",
        "logo_emoji": "📊",
        "price": "from $130/mo",
        "free_plan": "Limited (10 queries/day)",
        "starting_price": "$130/mo",
        "best_for": "All-in-one SEO & competitive analysis",
        "content_editor": "Yes",
        "keyword_research": "Yes",
        "audit_tool": "Yes",
        "backlink_analysis": "Yes",
        "api": "Yes",
        "affiliate_url": "https://semrush.com",
    },
    "ahrefs": {
        "name": "Ahrefs",
        "logo_emoji": "🔗",
        "price": "from $99/mo",
        "free_plan": "Webmaster Tools (free)",
        "starting_price": "$99/mo",
        "best_for": "Backlink analysis & keyword research",
        "content_editor": "Yes (AI features)",
        "keyword_research": "Yes",
        "audit_tool": "Yes",
        "backlink_analysis": "Yes (industry-leading)",
        "api": "Yes",
        "affiliate_url": "https://ahrefs.com",
    },
    "elevenlabs": {
        "name": "ElevenLabs",
        "logo_emoji": "🎙️",
        "price": "Free / $5/mo",
        "free_plan": "Yes (10,000 chars/mo)",
        "starting_price": "$5/mo",
        "best_for": "Realistic AI voice generation",
        "voice_cloning": "Yes",
        "languages": "29+",
        "api": "Yes",
        "affiliate_url": "https://elevenlabs.io",
    },
    "murf": {
        "name": "Murf AI",
        "logo_emoji": "🎤",
        "price": "Free / $29/mo",
        "free_plan": "Yes (10 min audio, no download)",
        "starting_price": "$29/mo",
        "best_for": "Business voiceovers & presentations",
        "voice_cloning": "Custom voices (Enterprise)",
        "languages": "20+",
        "api": "Yes",
        "affiliate_url": "https://murf.ai",
    },
    "pictory": {
        "name": "Pictory AI",
        "logo_emoji": "🎬",
        "price": "from $19/mo",
        "free_plan": "No (3 free videos trial)",
        "starting_price": "$19/mo",
        "best_for": "Article-to-video conversion",
        "auto_captions": "Yes",
        "brand_kit": "Yes (Professional+)",
        "api": "No",
        "affiliate_url": "https://pictory.ai",
    },
    "invideo": {
        "name": "InVideo AI",
        "logo_emoji": "🎥",
        "price": "Free / $25/mo",
        "free_plan": "Yes (watermarked)",
        "starting_price": "$25/mo",
        "best_for": "AI-scripted social & YouTube videos",
        "auto_captions": "Yes",
        "brand_kit": "Yes",
        "api": "No",
        "affiliate_url": "https://invideo.io",
    },
    "getresponse": {
        "name": "GetResponse",
        "logo_emoji": "📧",
        "price": "Free / $19/mo",
        "free_plan": "Yes (500 contacts)",
        "starting_price": "$19/mo",
        "best_for": "Email marketing + automation",
        "automation": "Yes",
        "landing_pages": "Yes",
        "webinars": "Yes (paid plans)",
        "api": "Yes",
        "affiliate_url": "https://getresponse.com",
    },
    "chatgpt": {
        "name": "ChatGPT (Plus)",
        "logo_emoji": "🤖",
        "price": "Free / $20/mo",
        "free_plan": "Yes (GPT-3.5)",
        "starting_price": "$20/mo (Plus)",
        "best_for": "General AI assistant & writing",
        "api": "Yes (separate pricing)",
        "affiliate_url": "https://chat.openai.com",
    },
    "claude": {
        "name": "Claude Pro",
        "logo_emoji": "🧠",
        "price": "Free / $20/mo",
        "free_plan": "Yes (Claude 3 Haiku)",
        "starting_price": "$20/mo (Pro)",
        "best_for": "Long documents & nuanced reasoning",
        "api": "Yes (separate pricing)",
        "affiliate_url": "https://claude.ai",
    },
    "midjourney": {
        "name": "Midjourney",
        "logo_emoji": "🎨",
        "price": "from $10/mo",
        "free_plan": "No",
        "starting_price": "$10/mo",
        "best_for": "Artistic & photorealistic AI images",
        "api": "No (Discord-based)",
        "affiliate_url": "https://midjourney.com",
    },
    "dalle3": {
        "name": "DALL-E 3",
        "logo_emoji": "🖼️",
        "price": "Included with ChatGPT Plus",
        "free_plan": "Limited (via Bing Image Creator)",
        "starting_price": "$20/mo (via ChatGPT Plus)",
        "best_for": "Prompt-accurate photorealistic images",
        "api": "Yes (OpenAI API)",
        "affiliate_url": "https://openai.com/dall-e-3",
    },
}

# ---------------------------------------------------------------------------
# Comparison definitions per slug
# ---------------------------------------------------------------------------
COMPARISONS = {
    "jasper-ai-vs-copyai-2026-comparison": {
        "tool_a": TOOLS["jasper"],
        "tool_b": TOOLS["copyai"],
        "winner": "a",
        "rows": [
            {"feature": "Free Plan", "a": "No (7-day trial)", "b": "Yes (2,000 words/mo)", "winner": "b"},
            {"feature": "Starting Price", "a": "$49/mo", "b": "$49/mo", "winner": "tie"},
            {"feature": "Templates", "a": "50+", "b": "90+", "winner": "b"},
            {"feature": "SEO Mode", "a": "Yes (Surfer)", "b": "No", "winner": "a"},
            {"feature": "Brand Voice", "a": "Yes", "b": "Limited", "winner": "a"},
            {"feature": "Long-form Editor", "a": "Yes", "b": "Limited", "winner": "a"},
            {"feature": "Chrome Extension", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "API Access", "a": "Yes", "b": "Yes", "winner": "tie"},
        ],
        "cta_a": {"label": "Try Jasper Free", "url": "https://jasper.ai"},
        "cta_b": {"label": "Try Copy.ai Free", "url": "https://copy.ai"},
    },
    "jasper-ai-vs-copyai-which-is-better-in-2026": "jasper-ai-vs-copyai-2026-comparison",
    "jasper-ai-vs-copy-ai-which-is-better-in-2026": "jasper-ai-vs-copyai-2026-comparison",
    "copy-ai-vs-jasper-ai-2026-which-ai-writer-should-you-buy": "jasper-ai-vs-copyai-2026-comparison",

    "copyai-vs-writesonic-which-ai-writer-is-worth-your-money": {
        "tool_a": TOOLS["copyai"],
        "tool_b": TOOLS["writesonic"],
        "winner": "b",
        "rows": [
            {"feature": "Free Plan", "a": "Yes (2,000 words)", "b": "Yes (10,000 words)", "winner": "b"},
            {"feature": "Starting Price", "a": "$49/mo (Pro)", "b": "$13/mo", "winner": "b"},
            {"feature": "Templates", "a": "90+", "b": "100+", "winner": "b"},
            {"feature": "SEO Mode", "a": "No", "b": "Yes (Surfer)", "winner": "b"},
            {"feature": "Brand Voice", "a": "Limited", "b": "Yes", "winner": "b"},
            {"feature": "Long-form Editor", "a": "Limited", "b": "Yes", "winner": "b"},
            {"feature": "Chrome Extension", "a": "Yes", "b": "Yes", "winner": "tie"},
        ],
        "cta_a": {"label": "Try Copy.ai Free", "url": "https://copy.ai"},
        "cta_b": {"label": "Try Writesonic Free", "url": "https://writesonic.com"},
    },

    "surfer-seo-vs-semrush-complete-comparison-2024": {
        "tool_a": TOOLS["surfer"],
        "tool_b": TOOLS["semrush"],
        "winner": "a",
        "rows": [
            {"feature": "Free Plan", "a": "No (7-day trial)", "b": "Limited (10 queries/day)", "winner": "b"},
            {"feature": "Starting Price", "a": "$89/mo", "b": "$130/mo", "winner": "a"},
            {"feature": "Content Editor", "a": "Yes (core feature)", "b": "Yes (SEO Writing Assistant)", "winner": "a"},
            {"feature": "Keyword Research", "a": "Yes", "b": "Yes (more data)", "winner": "b"},
            {"feature": "Backlink Analysis", "a": "No", "b": "Yes", "winner": "b"},
            {"feature": "Site Audit", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "On-page Optimization", "a": "Best in class", "b": "Good", "winner": "a"},
            {"feature": "Best For", "a": "Content + On-page SEO", "b": "Full SEO suite", "winner": "tie"},
        ],
        "cta_a": {"label": "Try Surfer SEO", "url": "https://surferseo.com"},
        "cta_b": {"label": "Try SEMrush Free", "url": "https://semrush.com"},
    },
    "surfer-seo-vs-semrush-full-comparison-2024-guide": "surfer-seo-vs-semrush-complete-comparison-2024",

    "ahrefs-vs-semrush-2026-which-seo-tool-wins": {
        "tool_a": TOOLS["ahrefs"],
        "tool_b": TOOLS["semrush"],
        "winner": "tie",
        "rows": [
            {"feature": "Free Plan", "a": "Webmaster Tools", "b": "Limited (10/day)", "winner": "a"},
            {"feature": "Starting Price", "a": "$99/mo", "b": "$130/mo", "winner": "a"},
            {"feature": "Backlink Index", "a": "Largest (35T+ links)", "b": "43B+ backlinks", "winner": "a"},
            {"feature": "Keyword Research", "a": "Yes (10B+ keywords)", "b": "Yes (25B+ keywords)", "winner": "b"},
            {"feature": "Site Audit", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "Content Tools", "a": "Yes", "b": "Yes (SEO Writing Asst)", "winner": "b"},
            {"feature": "PPC / Ad Data", "a": "Limited", "b": "Yes", "winner": "b"},
            {"feature": "UI / Ease of use", "a": "Cleaner", "b": "More complex", "winner": "a"},
        ],
        "cta_a": {"label": "Try Ahrefs", "url": "https://ahrefs.com"},
        "cta_b": {"label": "Try SEMrush Free", "url": "https://semrush.com"},
    },
    "semrush-vs-ahrefs-2026-which-seo-tool-wins": "ahrefs-vs-semrush-2026-which-seo-tool-wins",

    "elevenlabs-vs-murf-ai-best-ai-voice-generator-2026": {
        "tool_a": TOOLS["elevenlabs"],
        "tool_b": TOOLS["murf"],
        "winner": "a",
        "rows": [
            {"feature": "Free Plan", "a": "Yes (10,000 chars)", "b": "Yes (10 min, no download)", "winner": "a"},
            {"feature": "Starting Price", "a": "$5/mo", "b": "$29/mo", "winner": "a"},
            {"feature": "Voice Realism", "a": "Best in class", "b": "Very good", "winner": "a"},
            {"feature": "Voice Cloning", "a": "Yes (all plans)", "b": "Enterprise only", "winner": "a"},
            {"feature": "Languages", "a": "29+", "b": "20+", "winner": "a"},
            {"feature": "API Access", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "Team Features", "a": "Limited", "b": "Yes", "winner": "b"},
            {"feature": "Best For", "a": "Realism & cloning", "b": "Business voiceovers", "winner": "tie"},
        ],
        "cta_a": {"label": "Try ElevenLabs Free", "url": "https://elevenlabs.io"},
        "cta_b": {"label": "Try Murf Free", "url": "https://murf.ai"},
    },
    "elevenlabs-vs-murf-ai-which-ai-voice-generator-wins-in-2024": "elevenlabs-vs-murf-ai-best-ai-voice-generator-2026",

    "pictory-vs-invideo-ai-best-ai-video-creator-in-2024": {
        "tool_a": TOOLS["pictory"],
        "tool_b": TOOLS["invideo"],
        "winner": "tie",
        "rows": [
            {"feature": "Free Plan", "a": "3 videos trial", "b": "Yes (watermarked)", "winner": "b"},
            {"feature": "Starting Price", "a": "$19/mo", "b": "$25/mo", "winner": "a"},
            {"feature": "Article → Video", "a": "Yes (core feature)", "b": "Yes", "winner": "a"},
            {"feature": "AI Script Writing", "a": "Limited", "b": "Yes", "winner": "b"},
            {"feature": "Auto Captions", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "Brand Kit", "a": "Yes (Professional+)", "b": "Yes", "winner": "tie"},
            {"feature": "Best For", "a": "Blog-to-video", "b": "Social & YouTube shorts", "winner": "tie"},
        ],
        "cta_a": {"label": "Try Pictory", "url": "https://pictory.ai"},
        "cta_b": {"label": "Try InVideo Free", "url": "https://invideo.io"},
    },

    "chatgpt-plus-vs-claude-pro-which-ai-is-worth-20-month": {
        "tool_a": TOOLS["chatgpt"],
        "tool_b": TOOLS["claude"],
        "winner": "tie",
        "rows": [
            {"feature": "Free Plan", "a": "Yes (GPT-3.5)", "b": "Yes (Claude 3 Haiku)", "winner": "tie"},
            {"feature": "Paid Price", "a": "$20/mo", "b": "$20/mo", "winner": "tie"},
            {"feature": "Context Window", "a": "128K tokens", "b": "200K tokens", "winner": "b"},
            {"feature": "Image Generation", "a": "Yes (DALL-E 3)", "b": "No", "winner": "a"},
            {"feature": "Web Browsing", "a": "Yes", "b": "No", "winner": "a"},
            {"feature": "Code Interpreter", "a": "Yes", "b": "Yes (Artifacts)", "winner": "tie"},
            {"feature": "Long Document Analysis", "a": "Good", "b": "Best in class", "winner": "b"},
            {"feature": "Best For", "a": "Versatility + images", "b": "Long docs + reasoning", "winner": "tie"},
        ],
        "cta_a": {"label": "Try ChatGPT Plus", "url": "https://chat.openai.com"},
        "cta_b": {"label": "Try Claude Pro", "url": "https://claude.ai"},
    },

    "midjourney-vs-dall-e-3-best-ai-image-generator-for-2026": {
        "tool_a": TOOLS["midjourney"],
        "tool_b": TOOLS["dalle3"],
        "winner": "a",
        "rows": [
            {"feature": "Free Plan", "a": "No", "b": "Limited (Bing)", "winner": "b"},
            {"feature": "Starting Price", "a": "$10/mo", "b": "$20/mo (ChatGPT Plus)", "winner": "a"},
            {"feature": "Image Quality", "a": "Best artistic quality", "b": "Best prompt accuracy", "winner": "tie"},
            {"feature": "Photorealism", "a": "Excellent", "b": "Excellent", "winner": "tie"},
            {"feature": "Interface", "a": "Discord only", "b": "Web / API", "winner": "b"},
            {"feature": "API Access", "a": "No", "b": "Yes", "winner": "b"},
            {"feature": "Styles & Control", "a": "Extensive (v6)", "b": "Limited", "winner": "a"},
        ],
        "cta_a": {"label": "Try Midjourney", "url": "https://midjourney.com"},
        "cta_b": {"label": "Try DALL-E 3", "url": "https://openai.com/dall-e-3"},
    },

    "getresponse-vs-mailchimp-2026-which-email-tool-is-better": {
        "tool_a": TOOLS["getresponse"],
        "tool_b": {
            "name": "Mailchimp",
            "logo_emoji": "🐵",
            "price": "Free / $13/mo",
        },
        "winner": "a",
        "rows": [
            {"feature": "Free Plan", "a": "Yes (500 contacts)", "b": "Yes (500 contacts)", "winner": "tie"},
            {"feature": "Starting Price", "a": "$19/mo", "b": "$13/mo", "winner": "b"},
            {"feature": "Marketing Automation", "a": "Yes (all plans)", "b": "Basic (paid only)", "winner": "a"},
            {"feature": "Landing Pages", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "Webinars", "a": "Yes", "b": "No", "winner": "a"},
            {"feature": "Affiliate Friendly", "a": "Yes", "b": "Restricted", "winner": "a"},
            {"feature": "Deliverability", "a": "Excellent", "b": "Good", "winner": "a"},
        ],
        "cta_a": {"label": "Try GetResponse Free", "url": "https://getresponse.com"},
        "cta_b": {"label": "Try Mailchimp Free", "url": "https://mailchimp.com"},
    },

    "runway-ml-vs-capcut-ai-best-ai-video-editor-for-creators": {
        "tool_a": {
            "name": "Runway ML",
            "logo_emoji": "🎞️",
            "price": "Free / $12/mo",
        },
        "tool_b": {
            "name": "CapCut AI",
            "logo_emoji": "✂️",
            "price": "Free / $7.99/mo",
        },
        "winner": "tie",
        "rows": [
            {"feature": "Free Plan", "a": "Yes (125 credits)", "b": "Yes", "winner": "tie"},
            {"feature": "Starting Price", "a": "$12/mo", "b": "$7.99/mo", "winner": "b"},
            {"feature": "AI Video Generation", "a": "Yes (Gen-2)", "b": "No", "winner": "a"},
            {"feature": "Auto Captions", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "Green Screen / BG Remove", "a": "Yes", "b": "Yes", "winner": "tie"},
            {"feature": "Best For", "a": "AI-generated video content", "b": "Social media editing", "winner": "tie"},
        ],
        "cta_a": {"label": "Try Runway ML", "url": "https://runwayml.com"},
        "cta_b": {"label": "Try CapCut Free", "url": "https://capcut.com"},
    },
}


def get_comparison_data(slug: str):
    """Return comparison table kwargs for a given article slug, or None."""
    data = COMPARISONS.get(slug)
    if data is None:
        return None
    # Handle alias slugs (string value = redirect to canonical key)
    if isinstance(data, str):
        data = COMPARISONS.get(data)
    return data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/comparison_generator.py <slug>")
        print("\nAvailable slugs:")
        for k in COMPARISONS:
            print(f"  {k}")
        sys.exit(0)
    slug = sys.argv[1]
    result = get_comparison_data(slug)
    if result:
        # Print without large tool objects
        out = {k: v for k, v in result.items() if k != "tool_a" and k != "tool_b"}
        out["tool_a_name"] = result["tool_a"]["name"]
        out["tool_b_name"] = result["tool_b"]["name"]
        print(json.dumps(out, indent=2))
    else:
        print(f"No comparison data for: {slug}")
