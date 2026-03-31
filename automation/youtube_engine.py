"""
YouTube Engine — AI tool review videos drive fast affiliate traffic.

YouTube ranks NEW channels in days (not months like Google).
A single viral video can send 1,000+ clicks to your affiliate links.

Strategy:
  - Screen-share reviews (no camera needed)
  - 5–10 minute "X vs Y" or "Best X for Y" videos
  - Description packed with affiliate links
  - Generates video scripts + optimized descriptions automatically

Tools needed (free):
  - OBS Studio (free screen recorder)
  - CapCut or DaVinci Resolve (free editor)
  OR
  - Pictory AI (use your own affiliate link — pays for itself)
"""

import json
import logging
from config import config
from affiliate.links import AFFILIATE_PROGRAMS
from automation.content_generator import generate_article

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

VIDEO_TOPICS = [
    {"title": "Jasper AI vs Copy.ai — Which Is Better in 2026?",        "tool1": "jasper",     "tool2": "copyai",    "type": "comparison", "search_vol": "high"},
    {"title": "Surfer SEO Review 2026 — Is It Worth $89/Month?",         "tool1": "surfer",     "tool2": None,        "type": "review",     "search_vol": "high"},
    {"title": "ElevenLabs vs Murf AI — Best AI Voice Generator?",        "tool1": "elevenlabs", "tool2": "murf",      "type": "comparison", "search_vol": "high"},
    {"title": "I Tried 10 AI Writing Tools — Here's My Honest Ranking",  "tool1": "jasper",     "tool2": "copyai",    "type": "listicle",   "search_vol": "very_high"},
    {"title": "Pictory AI Tutorial — Create Videos From Blog Posts",     "tool1": "pictory",    "tool2": None,        "type": "tutorial",   "search_vol": "medium"},
    {"title": "Semrush Review — The HONEST Truth After 6 Months",        "tool1": "semrush",    "tool2": None,        "type": "review",     "search_vol": "high"},
    {"title": "How I Use AI Tools to Write 5 Blog Posts Per Week",       "tool1": "jasper",     "tool2": "surfer",    "type": "workflow",   "search_vol": "high"},
    {"title": "InVideo AI Tutorial — Text to Video in Minutes",          "tool1": "invideo",    "tool2": None,        "type": "tutorial",   "search_vol": "medium"},
    {"title": "Fireflies AI Review — Does It Replace a Note-Taker?",    "tool1": "fireflies",  "tool2": None,        "type": "review",     "search_vol": "medium"},
    {"title": "Descript Review — Edit Videos Like a Google Doc",         "tool1": "descript",   "tool2": None,        "type": "review",     "search_vol": "medium"},
    {"title": "Best AI Tools for Entrepreneurs in 2026 (Full Stack)",   "tool1": "jasper",     "tool2": "semrush",   "type": "listicle",   "search_vol": "very_high"},
    {"title": "Jasper AI Pricing 2026 — Which Plan Is Actually Worth It?","tool1": "jasper",    "tool2": None,        "type": "pricing",    "search_vol": "high"},
]

def generate_video_script(topic: dict) -> dict:
    """Generate a complete video script for a YouTube review."""
    tool1_data = AFFILIATE_PROGRAMS.get(topic["tool1"], {})
    tool2_data = AFFILIATE_PROGRAMS.get(topic.get("tool2", ""), {}) if topic.get("tool2") else None

    tool1_name = tool1_data.get("name", "")
    tool2_name = tool2_data.get("name", "") if tool2_data else ""

    if topic["type"] == "comparison":
        script = f"""
=== VIDEO SCRIPT: {topic['title']} ===
Duration: 8–12 minutes
Format: Screen share + voiceover (no camera needed)

[HOOK — 0:00–0:30]
"If you're trying to decide between {tool1_name} and {tool2_name}, I've tested both
for the past 3 months and I'm going to give you my honest verdict right now.
No sponsored content, just real results."

[INTRO — 0:30–1:30]
"Quick intro — I run {config.SITE_NAME}, where we test and review AI tools.
I'll leave links to both tools in the description — I do earn a commission
if you sign up, but that doesn't affect my review."

[OVERVIEW — 1:30–3:00]
"Let me start by showing you both dashboards side by side..."
[SCREEN: Open both tools, show home screen]

"{tool1_name}: {tool1_data.get('description', '')}. Costs ${tool1_data.get('avg_sale', 0)}/month."
"{tool2_name}: {tool2_data.get('description', '') if tool2_data else ''}."

[FEATURE COMPARISON — 3:00–7:00]
"Let me test both on the same task..."
[SCREEN: Type same prompt into both tools]

"Speed test: {tool1_name} vs {tool2_name}"
[SCREEN: Show output side by side]

"Quality comparison..."
[SCREEN: Read outputs aloud, give verdict]

"Pricing breakdown..."
[SCREEN: Show pricing pages for both]

[VERDICT — 7:00–8:30]
"So which one should you choose?"
"For [use case 1] → {tool1_name} wins because..."
"For [use case 2] → {tool2_name} wins because..."
"My personal pick: [winner] — here's why..."

[CTA — 8:30–9:00]
"If you want to try {tool1_name}, I've left a free trial link in the description.
Same for {tool2_name}. Both are free to start, no credit card needed."
"Hit subscribe if this was helpful — I post new AI tool reviews every week."

[END SCREEN — 9:00–9:15]
Show recommended videos
"""
    else:  # review
        script = f"""
=== VIDEO SCRIPT: {topic['title']} ===
Duration: 8–10 minutes
Format: Screen share + voiceover

[HOOK — 0:00–0:30]
"Is {tool1_name} actually worth ${tool1_data.get('avg_sale', 0)}/month?
I've been using it for 3 months and I'm going to show you exactly
what I got for my money — the good, the bad, and the ugly."

[INTRO — 0:30–1:00]
"I'm from {config.SITE_NAME}. I test AI tools so you don't have to.
Free trial link is in the description if you want to follow along."

[DEMO — 1:00–6:00]
"Let me show you the main features..."
[SCREEN: Live demo of the tool]

Feature 1: [demonstrate]
Feature 2: [demonstrate]
Feature 3: [demonstrate]

"Here's something I wish I knew before buying..."

[PRICING — 6:00–7:30]
"Now let's talk pricing..."
[SCREEN: Show pricing page]

"The [plan name] at ${tool1_data.get('avg_sale', 0)}/month includes..."
"For most people I'd recommend starting with [plan]."

[VERDICT — 7:30–8:30]
"My honest verdict: [positive/negative/depends]"
"Who should buy it: [specific use case]"
"Who should skip it: [specific use case]"
"Overall rating: {tool1_data.get('rating', 4.5)}/5"

[CTA — 8:30–9:00]
"Free trial link is in the description. No credit card required."
"Subscribe for more honest AI tool reviews every week."
"""

    return {
        "title": topic["title"],
        "script": script,
        "duration": "8–12 minutes",
        "search_volume": topic["search_vol"],
    }

def generate_video_description(topic: dict) -> str:
    """Generate SEO-optimized YouTube video description with affiliate links."""
    tool1_data = AFFILIATE_PROGRAMS.get(topic["tool1"], {})
    tool2_data = AFFILIATE_PROGRAMS.get(topic.get("tool2", ""), {}) if topic.get("tool2") else None

    tool1_name = tool1_data.get("name", "")
    tool2_name = tool2_data.get("name", "") if tool2_data else ""

    links_section = f"🔗 LINKS MENTIONED:\n"
    links_section += f"► {tool1_name} Free Trial → {tool1_data.get('signup_url', '')}\n"
    if tool2_data:
        links_section += f"► {tool2_name} Free Trial → {tool2_data.get('signup_url', '')}\n"
    links_section += f"► Full written review → {config.SITE_URL}/articles\n"
    links_section += f"► All AI tool comparisons → {config.SITE_URL}/tools\n"

    timestamps = """⏱️ TIMESTAMPS:
0:00 - Introduction
1:00 - Overview & First Impressions
3:00 - Feature Demo
6:00 - Pricing Breakdown
7:30 - Honest Verdict
8:30 - Final Recommendation"""

    description = f"""{topic['title']}

In this video I give my honest review of {tool1_name}{f' vs {tool2_name}' if tool2_name else ''} after using it for 3 months.

I cover:
✅ Key features and how they actually work
✅ Pricing breakdown and which plan is worth it
✅ Who should use it and who should skip it
✅ {f'Head-to-head comparison: {tool1_name} vs {tool2_name}' if tool2_name else 'Real-world results from 3 months of use'}

{links_section}

{timestamps}

📧 FREE WEEKLY NEWSLETTER: Get AI tool deals and reviews every Monday
→ {config.SITE_URL}/#subscribe

⚠️ AFFILIATE DISCLOSURE: Links above are affiliate links — I earn a small commission if you sign up, at no extra cost to you. This doesn't affect my review.

🔍 TAGS:
#{tool1_name.replace(' ','')} #{tool2_name.replace(' ','')} #aitools #aiwriting #artificialintelligence
#contentcreation #productivity #seotools #aireviews 2026"""

    return description

def generate_channel_strategy() -> str:
    return f"""
╔══════════════════════════════════════════════════════════════╗
║  📺 YOUTUBE CHANNEL STRATEGY — WEEKS 1–4                    ║
╚══════════════════════════════════════════════════════════════╝

CHANNEL SETUP (Day 1, 2 hours):
  □ Channel name: "AI Tools Empire" or "{config.SITE_NAME}"
  □ Banner: Use Canva free template
  □ Profile pic: Simple logo (Canva)
  □ Channel description: paste below
  □ Add links: website, newsletter, Twitter
  □ Enable monetization early (need 1k subs + 4k watch hours)

CHANNEL DESCRIPTION:
"Honest reviews and comparisons of the best AI tools for marketers,
creators, and entrepreneurs. New video every week.
No sponsored content — just real tests and real results.
Subscribe to {config.SITE_NAME}: {config.SITE_URL}"

POSTING SCHEDULE:
  Week 1: "I Tried 10 AI Writing Tools — Honest Ranking" (high search vol)
  Week 2: "Jasper AI vs Copy.ai" comparison (highest buyer intent)
  Week 3: "Surfer SEO Review 2026" (premium commission)
  Week 4: "Best AI Tools for [niche]" listicle (broad traffic)

RECORDING (no camera needed):
  □ OBS Studio (free) — record your screen
  □ Speak clearly into your mic (even laptop mic works to start)
  □ Show the tool's actual interface on screen
  □ Keep videos 8–12 minutes (best for YouTube algorithm)

EXPECTED RESULTS:
  Week 2–3: First views from search
  Month 1:  100–500 views/video
  Month 2:  First affiliate clicks from YouTube
  Month 3:  $50–$200/month from YouTube affiliate links
  Month 6+: $200–$800/month from YouTube alone

WHY YOUTUBE OVER TIKTOK:
  - YouTube affiliate links in description are clickable
  - Videos rank in Google search too (double traffic)
  - Long-form = higher purchase intent = better conversions
  - Watch time compounds (old videos keep earning)
"""

def export_all_scripts():
    """Export all video scripts to files for easy reference."""
    import os
    os.makedirs("data/youtube_scripts", exist_ok=True)
    for i, topic in enumerate(VIDEO_TOPICS):
        script_data = generate_video_script(topic)
        desc = generate_video_description(topic)
        filename = f"data/youtube_scripts/video_{i+1:02d}_{topic['type']}.txt"
        with open(filename, "w") as f:
            f.write(f"TITLE: {script_data['title']}\n")
            f.write(f"SEARCH VOLUME: {script_data['search_volume']}\n")
            f.write(f"DURATION: {script_data['duration']}\n\n")
            f.write("=" * 60 + "\n")
            f.write("SCRIPT:\n")
            f.write("=" * 60 + "\n")
            f.write(script_data["script"])
            f.write("\n\n" + "=" * 60 + "\n")
            f.write("YOUTUBE DESCRIPTION (copy-paste):\n")
            f.write("=" * 60 + "\n")
            f.write(desc)
        log.info(f"Script saved: {filename}")
    log.info(f"Exported {len(VIDEO_TOPICS)} video scripts to data/youtube_scripts/")
    return len(VIDEO_TOPICS)

if __name__ == "__main__":
    print(generate_channel_strategy())
    count = export_all_scripts()
    print(f"\n✅ {count} video scripts exported to data/youtube_scripts/")
    print("\nFirst video to record:")
    first = VIDEO_TOPICS[3]  # Highest search volume
    print(f"  Title: {first['title']}")
    script = generate_video_script(first)
    print(f"  Script preview:\n{script['script'][:400]}...")
