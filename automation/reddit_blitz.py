"""
Reddit Traffic Blitz — drive immediate affiliate traffic.

Reddit is the #1 fastest free traffic source for this niche.
Real people asking "what AI tool should I use?" = hot buyers.

Rules to avoid bans:
  - Be genuinely helpful FIRST, mention tools second
  - Use 80/20: 80% value, 20% soft mention
  - Never post the same content twice
  - Engage with comments immediately after posting
  - Build karma first (5+ non-promotional comments before posting)
"""

import random
from datetime import datetime
from config import config
from affiliate.links import AFFILIATE_PROGRAMS

# ── Target subreddits with monthly active users ───────────────────────────────
TARGET_SUBREDDITS = {
    "r/SEO":                {"members": "130k",  "best_flair": "Discussion",  "persona": "seo"},
    "r/content_marketing":  {"members": "80k",   "best_flair": "Resource",    "persona": "content_creator"},
    "r/Entrepreneur":       {"members": "3.2M",  "best_flair": "Resources",   "persona": "saas_founder"},
    "r/blogging":           {"members": "230k",  "best_flair": "Tools",       "persona": "blogger"},
    "r/marketing":          {"members": "1.4M",  "best_flair": "Discussion",  "persona": "marketing_agency"},
    "r/digital_marketing":  {"members": "180k",  "best_flair": "Tools",       "persona": "marketing_agency"},
    "r/artificial":         {"members": "860k",  "best_flair": "Discussion",  "persona": "general"},
    "r/ChatGPT":            {"members": "5M",    "best_flair": "Other",       "persona": "general"},
    "r/MachineLearning":    {"members": "2.8M",  "best_flair": "Discussion",  "persona": "technical"},
    "r/SaaS":               {"members": "120k",  "best_flair": "Resource",    "persona": "saas_founder"},
    "r/Upwork":             {"members": "90k",   "best_flair": "Discussion",  "persona": "freelancer"},
    "r/freelance":          {"members": "310k",  "best_flair": "Discussion",  "persona": "freelancer"},
    "r/podcasting":         {"members": "270k",  "best_flair": "Tools",       "persona": "podcaster"},
    "r/NewTubers":          {"members": "500k",  "best_flair": "Resources",   "persona": "youtuber"},
    "r/juststart":          {"members": "80k",   "best_flair": "Resource",    "persona": "blogger"},
    "r/passive_income":     {"members": "690k",  "best_flair": "Discussion",  "persona": "general"},
    "r/forhire":            {"members": "750k",  "best_flair": "[FOR HIRE]",  "persona": "service_sell"},
}

# ── Pre-written high-value posts (rotate these) ──────────────────────────────

POSTS = [
    {
        "subreddits": ["r/SEO", "r/digital_marketing", "r/marketing"],
        "title": "I tested 12 AI SEO tools for 3 months. Here's what actually worked (honest breakdown)",
        "body": """After spending way too much money testing AI SEO tools, I put together an honest breakdown for anyone wondering which ones are worth it.

**The short version:**
- Surfer SEO is still the best for on-page optimization (NLP scoring actually works)
- Semrush is worth it if you need competitor research + keyword data in one place
- Most "AI content writers" are still average at best for SEO-optimized content

**What I actually use now:**
1. **Semrush** for keyword research and competitor analysis
2. **Surfer SEO** for optimizing individual articles before publishing
3. **Jasper AI** for first drafts (still needs editing but saves 60%+ of writing time)

**What didn't work:**
- Generic AI writers that don't understand search intent
- Tools that promise "instant ranking" (no such thing)
- Anything under $20/month (you get what you pay for)

If anyone wants the full comparison with screenshots and actual ranking data, I wrote it up here: [{site_url}/articles](https://www.google.com) — happy to answer questions in the comments too.

What AI SEO tools is everyone else using? Curious if I missed anything good.""",
        "value_score": 9,
    },
    {
        "subreddits": ["r/blogging", "r/content_marketing", "r/juststart"],
        "title": "My blogging income grew 4x after switching to AI tools. Here's my exact stack (Month 14 update)",
        "body": """14 months ago I was writing 2 articles/week manually, earning about $800/month from my blog.

Today I'm at ~$3,200/month publishing 5 articles/week.

The difference? Switching to an AI-assisted workflow. Here's exactly what changed:

**Before:**
- 4-5 hours to write one 2,000-word article
- 2 articles/week maximum
- Inconsistent quality

**After (my current stack):**
- **Jasper AI** — first draft in 30 minutes
- **Surfer SEO** — optimization in 20 minutes
- **Grammarly** — final edit in 10 minutes
- Total: ~1 hour per article

**The math:**
- Same hours → 5x more content
- More content → more traffic
- More traffic → more affiliate income

I wrote up the full workflow with specific prompts I use in Jasper: [{site_url}]({site_url})

Happy to share more details in the comments. What's your current article production process?""",
        "value_score": 8,
    },
    {
        "subreddits": ["r/Entrepreneur", "r/SaaS"],
        "title": "Honest review after 6 months: which AI tools are actually worth paying for?",
        "body": """Running a small SaaS, so I've tried basically every AI tool out there. Here's my honest take after 6 months of actually using them (not just testing):

**Worth every penny:**

🔥 **Semrush** ($130/mo) — If you're doing any SEO, this pays for itself. Found 3 competitor gaps that brought in 2k new visitors/month.

🔥 **Jasper AI** ($49/mo) — Writes first drafts of blog posts, emails, ad copy. Cut my content time by 70%.

🔥 **Fireflies.ai** ($18/mo) — Records and summarizes every sales call. Never miss an action item again.

**Good but not essential:**

👍 Writesonic — cheaper Jasper alternative, slightly worse quality

👍 Surfer SEO — great if you publish content regularly

**Overrated:**
- Most $10-15/month AI writers — quality isn't there yet
- Anything promising "write and rank automatically" — doesn't work

Full breakdown with pricing and who each tool is best for: [{site_url}/tools]({site_url}/tools)

What's in your AI stack? Always looking for things I might be missing.""",
        "value_score": 9,
    },
    {
        "subreddits": ["r/podcasting", "r/NewTubers"],
        "title": "The AI tools that saved my content creation workflow (no more 8-hour editing sessions)",
        "body": """I used to spend 8 hours editing a 45-minute podcast episode. Now it takes 45 minutes. Here's what changed:

**Descript** ($24/mo) changed everything for me:
- Edit audio/video by editing the transcript (delete a word = deletes the audio)
- Remove filler words automatically
- Overdub lets me fix recording mistakes without re-recording

For video content specifically:
- **Pictory AI** turns my podcast audio into YouTube clips automatically
- **ElevenLabs** for voiceovers on any clips where audio quality isn't great

The combo of Descript + Pictory basically doubled my content output without any extra recording time.

Wrote up the full workflow here if anyone wants the details: [{site_url}]({site_url})

Anyone else found AI tools that cut their production time? Would love to hear what's working.""",
        "value_score": 8,
    },
    {
        "subreddits": ["r/passive_income", "r/Entrepreneur"],
        "title": "Building an AI-powered affiliate site: 6-month honest report ($0 → $2,400/mo)",
        "body": """6 months ago I started an affiliate site in the AI tools niche. Here's the honest numbers:

**Month 1:** $47 (first commissions from social traffic)
**Month 2:** $183 (SEO starting to trickle in)
**Month 3:** $441 (first page-1 rankings)
**Month 4:** $892 (compounding)
**Month 5:** $1,640
**Month 6:** $2,400+

**What worked:**
- Targeting "X vs Y" comparison keywords (highest buyer intent)
- "Best X for Y" listicles
- Pricing pages ("Is Jasper worth it?")
- Building an email list from day 1

**What didn't work:**
- Generic "what is AI" content (zero conversion)
- Trying to rank for head terms immediately
- Publishing without proper keyword research

The AI tools niche pays well because commissions are 20-50% recurring. One sign-up to Semrush = $200.

Happy to answer questions on the strategy. Full breakdown of how I set it up at {site_url}.""",
        "value_score": 10,
    },
    # FOR HIRE post (r/forhire)
    {
        "subreddits": ["r/forhire", "r/freelance", "r/Upwork"],
        "title": "[FOR HIRE] SEO Blog Writing — AI-assisted, human-edited | $89/post | Fast delivery",
        "body": """**[FOR HIRE] SEO Content Writer — Blog Posts That Rank**

I write SEO-optimized blog posts for SaaS, e-commerce, and marketing businesses.

**What you get:**
- 1,500–2,500 word blog post
- Keyword-optimized (you provide target keyword or I research it)
- Meta title + description
- Internal linking suggestions
- Delivered in Google Doc or HTML format
- Plagiarism-free, human-edited

**Pricing:**
- Single article: $89–$149 depending on length/complexity
- Monthly package (4 posts): $347/month
- Monthly package (8 posts): $647/month

**My specialties:** SaaS, AI tools, marketing, e-commerce, finance, tech

**Samples + portfolio:** {site_url}

**Turnaround:** 24–72 hours

Message me with your niche and target keyword for a free topic outline.""",
        "value_score": 7,
    },
]

COMMENT_REPLIES = [
    "Great question! I actually wrote a full breakdown here: {site_url}/articles — hope it helps",
    "We tested this exact comparison — full results at {site_url}/tools if you want the details",
    "I covered this recently. Short answer: {tool_name} is better for {use_case}. Full breakdown: {site_url}",
    "For {persona}s specifically, I'd go with {tool_name} — did a full review at {site_url}",
]

def get_posts_for_subreddit(subreddit: str) -> list:
    """Get all pre-written posts suitable for a given subreddit."""
    return [p for p in POSTS if subreddit in p["subreddits"]]

def format_post(post: dict) -> dict:
    """Format a post with site URL and affiliate links."""
    body = post["body"].format(
        site_url=config.SITE_URL,
        jasper_url=AFFILIATE_PROGRAMS["jasper"]["signup_url"],
        surfer_url=AFFILIATE_PROGRAMS["surfer"]["signup_url"],
    )
    return {**post, "body": body}

def get_weekly_posting_schedule() -> list:
    """
    Returns a 7-day posting schedule.
    Post 1–2 times/day across different subreddits.
    """
    schedule = []
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    subreddits = list(TARGET_SUBREDDITS.keys())

    for i, day in enumerate(days):
        subs = subreddits[i*2 : i*2+2]  # 2 per day
        day_posts = []
        for sub in subs:
            posts = get_posts_for_subreddit(sub)
            if posts:
                post = random.choice(posts)
                day_posts.append({
                    "day": day,
                    "subreddit": sub,
                    "title": post["title"],
                    "body_preview": post["body"][:150] + "...",
                    "members": TARGET_SUBREDDITS[sub]["members"],
                })
        schedule.extend(day_posts)
    return schedule

def print_posting_guide():
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  📱 REDDIT TRAFFIC BLITZ — 7-DAY PLAN                       ║
╚══════════════════════════════════════════════════════════════╝

GOAL: 500–2,000 visitors from Reddit in week 1
CONVERSION RATE: ~2% → 10–40 affiliate clicks → $100–$400

RULES (avoid getting banned):
  ✅ Comment 5× before posting (build karma)
  ✅ 80% value, 20% self-promotion
  ✅ Respond to every comment within 1 hour
  ✅ Vary post content (never duplicate)
  ✅ Don't post affiliate links directly — link to your site

POSTING SCHEDULE:
""")
    schedule = get_weekly_posting_schedule()
    for item in schedule:
        print(f"  {item['day']:10} → {item['subreddit']:30} ({item['members']} members)")
        print(f"             \"{item['title'][:60]}...\"")
        print()

def get_karma_building_comments() -> list:
    """
    Post these helpful comments first to build Reddit karma.
    Aim for 5+ upvotes before posting your own threads.
    """
    return [
        {
            "subreddit": "r/SEO",
            "context": "Any post asking about AI writing tools for SEO",
            "comment": "The combination of Surfer SEO (for optimization) + an AI writer (for drafting) is unbeatable for content velocity. You still need to edit, but it cuts the time per article by 60-70%.",
        },
        {
            "subreddit": "r/blogging",
            "context": "Post about content production speed",
            "comment": "The best mental shift for me was treating AI as a first-draft tool, not a publishing tool. Let it write the skeleton, then you add your voice and expertise. Output went from 2 to 6 posts/week.",
        },
        {
            "subreddit": "r/Entrepreneur",
            "context": "Post about tools for small business",
            "comment": "For a small team the highest ROI AI tools are: (1) Jasper/Copy.ai for content, (2) Fireflies for meeting notes, (3) Semrush if you're doing SEO. The time savings compound fast.",
        },
        {
            "subreddit": "r/podcasting",
            "context": "Post about editing time",
            "comment": "Descript completely changed my editing workflow. The transcript-based editing sounds weird until you try it — cutting a 5-minute ramble becomes a 30-second job.",
        },
        {
            "subreddit": "r/passive_income",
            "context": "Post about affiliate marketing",
            "comment": "AI tool affiliate programs have some of the best structures: 20-50% recurring commissions + 30-120 day cookies. One Semrush sale pays $200. Worth building content around.",
        },
    ]

if __name__ == "__main__":
    print_posting_guide()
    print("\n📝 PRE-WRITTEN POSTS FOR TODAY:\n")
    for sub in ["r/SEO", "r/Entrepreneur", "r/blogging"]:
        posts = get_posts_for_subreddit(sub)
        if posts:
            p = format_post(posts[0])
            print(f"SUBREDDIT: {sub}")
            print(f"TITLE: {p['title']}")
            print(f"BODY:\n{p['body'][:500]}...\n")
            print("─" * 60)

    print("\n💬 KARMA-BUILDING COMMENTS:")
    for c in get_karma_building_comments():
        print(f"\n{c['subreddit']} — Post about: {c['context']}")
        print(f"Comment: {c['comment']}")
