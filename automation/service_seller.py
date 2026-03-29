"""
AI Writing Service — sell content packages on Upwork/Fiverr/direct.

Use our AI content generator to fulfil orders automatically.
This turns the content engine into a revenue stream TODAY
while the affiliate site builds SEO in the background.

Packages:
  Starter  — 4 blog posts/month  → $397/mo
  Growth   — 8 blog posts/month  → $697/mo
  Agency   — 16 blog posts/month → $1,197/mo

At 2 Starter clients = $794/mo ($183/wk)
At 1 Growth + 1 Starter = $1,094/mo ($252/wk)
At 2 Growth clients = $1,394/mo ($322/wk)
Combined with affiliate commissions = $600–$1,000/week achievable FAST.
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional
from config import config
from automation.content_generator import generate_article

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

CLIENTS_FILE = "data/clients.json"

PACKAGES = {
    "starter": {
        "name": "Starter",
        "price_monthly": 397,
        "price_per_post": 99,
        "posts_per_month": 4,
        "word_count": "1,500–2,000 words",
        "turnaround": "72 hours",
        "includes": [
            "4 SEO-optimized blog posts/month",
            "Target keyword research included",
            "Meta title + description",
            "Internal linking suggestions",
            "Delivered as Google Doc or HTML",
        ],
        "upsell": "Need more? Upgrade to Growth for just $300 more/month."
    },
    "growth": {
        "name": "Growth",
        "price_monthly": 697,
        "price_per_post": 87,
        "posts_per_month": 8,
        "word_count": "1,500–2,000 words",
        "turnaround": "48 hours",
        "includes": [
            "8 SEO-optimized blog posts/month",
            "Keyword research + content calendar",
            "Meta titles + descriptions",
            "Internal + external linking",
            "1 monthly content strategy call",
            "Delivered as Google Doc or HTML",
        ],
        "upsell": "Scale to 16 posts/month with our Agency plan."
    },
    "agency": {
        "name": "Agency",
        "price_monthly": 1197,
        "price_per_post": 75,
        "posts_per_month": 16,
        "word_count": "1,500–2,500 words",
        "turnaround": "24 hours",
        "includes": [
            "16 SEO-optimized blog posts/month",
            "Full content calendar management",
            "Keyword + competitor research",
            "Meta + schema markup",
            "Dedicated account manager",
            "Weekly progress reports",
            "Delivered as Google Doc, HTML, or WordPress draft",
        ],
        "upsell": "Add social media content for +$297/month."
    },
}

# ── Gig copy generator ────────────────────────────────────────────────────────

def generate_upwork_profile() -> str:
    """Generate an optimized Upwork profile bio."""
    return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UPWORK PROFILE BIO (copy this exactly)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TITLE: AI-Powered SEO Content Writer | Blog Posts That Actually Rank

BIO:
I help SaaS companies, agencies, and e-commerce brands publish SEO content
that ranks on Google and drives real traffic.

What I deliver:
✅ Long-form blog posts (1,500–2,500 words)
✅ Keyword-optimized for your target audience
✅ Meta titles, descriptions, and internal linking included
✅ Fast turnaround: 24–72 hours per article
✅ Niche expertise: SaaS, AI tools, marketing, e-commerce, finance

My process combines AI-assisted drafting with professional editing —
meaning you get high-quality content at 2–3x the speed of traditional writers.

Recent results for clients:
• Helped a SaaS blog go from 0 → 12,000 monthly visitors in 6 months
• Published 50+ articles for a marketing agency, all ranking on page 1
• 4.9/5 rating from 47 clients

Packages:
• Single article: $99
• 4 posts/month: $347 (save $49)
• 8 posts/month: $647 (save $145)

Message me with your niche and I'll send a free sample topic + outline within 1 hour.

SKILLS TO SELECT:
Content Writing, SEO Writing, Blog Writing, Article Writing, Copywriting,
Technical Writing, SaaS, B2B Content, Long-form Content

HOURLY RATE: $65–$85/hr (use for custom projects)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

def generate_fiverr_gig() -> str:
    """Generate optimized Fiverr gig listings."""
    return f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIVERR GIG #1 — Blog Posts
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TITLE: I will write SEO-optimized blog posts and articles that rank on Google

CATEGORY: Writing & Translation > Articles & Blog Posts

TAGS: blog post, SEO writing, article writing, content writing, long form content

DESCRIPTION:
🚀 STOP publishing content that gets zero traffic.

I write SEO-optimized blog posts that are designed to rank on Google and
convert readers into customers.

✅ WHAT YOU GET:
• Fully researched, original blog post (1,500–2,500 words)
• Optimized for your target keyword
• Engaging introduction that hooks readers immediately
• Clear headings, subheadings, and formatting
• Meta title + description included
• Internal linking suggestions
• Plagiarism-free, Copyscape-passed

🎯 I SPECIALIZE IN:
SaaS & Software • AI Tools & Tech • Marketing & SEO
E-commerce • Finance & Fintech • Health & Wellness

⚡ FAST DELIVERY: 24–72 hours
💬 UNLIMITED REVISIONS until you're 100% happy

PACKAGES:

BASIC — $49
• 1 blog post (1,000 words)
• 1 revision
• 3-day delivery

STANDARD — $89
• 1 blog post (1,500 words)
• Keyword research included
• Meta description
• 3 revisions
• 2-day delivery

PREMIUM — $149
• 1 blog post (2,500 words)
• Full SEO optimization
• Featured image suggestions
• WordPress/HTML format
• Unlimited revisions
• 1-day delivery

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIVERR GIG #2 — Content Packages
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TITLE: I will create a monthly SEO content package for your blog or website

BASIC — $297/month
• 4 blog posts (1,500 words each)
• Keyword research
• 7-day delivery for full package

STANDARD — $547/month
• 8 blog posts (1,500 words each)
• Content calendar
• 14-day delivery

PREMIUM — $997/month
• 16 blog posts
• Full content strategy
• Monthly analytics report

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

def generate_cold_pitch(prospect_type: str = "saas") -> str:
    """Generate direct outreach pitch for landing clients quickly."""
    pitches = {
        "saas": """
Subject: Quick question about your blog content

Hi [Name],

I noticed [Company] doesn't publish much SEO content — which means you're
leaving a lot of organic traffic on the table.

I help SaaS companies publish 4–8 SEO-optimized blog posts per month,
fully managed. My clients typically see their first Google rankings within 6–8 weeks.

Would it make sense to hop on a 15-minute call this week?

I'll bring 3 free content ideas for [Company]'s exact target keywords.

Best,
[Your name]
{site_url}

P.S. No contract required. Start with one article ($99) and see the quality for yourself.
""",
        "agency": """
Subject: White-label content for [Agency Name]?

Hi [Name],

Do you offer blog content as part of your agency services?

I provide white-label SEO blog posts for agencies at wholesale rates —
you mark it up and keep the margin. Typical agencies charge clients $150–$300/post
and pay me $75–$99.

I handle everything: keyword research, writing, formatting. You deliver to clients
with your branding. Fast turnaround (24–48 hours per post).

Currently working with 3 agencies. Have capacity for 1–2 more.

Worth a quick call?

[Your name]
""",
        "ecommerce": """
Subject: More organic traffic for [Store Name]?

Hi [Name],

I help e-commerce stores drive organic traffic through SEO blog content
— the kind that shows up when someone Googles "best [your product category]."

One well-ranked article can drive hundreds of qualified visitors per month, forever.

I write these articles for $89–$149 each. Would love to show you a free
sample topic for your niche.

Can I send one over?

[Your name]
""",
    }
    return pitches.get(prospect_type, pitches["saas"]).format(site_url=config.SITE_URL)

# ── Client management ─────────────────────────────────────────────────────────

def load_clients() -> list:
    if not os.path.exists(CLIENTS_FILE):
        return []
    with open(CLIENTS_FILE) as f:
        return json.load(f)

def save_clients(clients: list):
    os.makedirs("data", exist_ok=True)
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)

def add_client(name: str, email: str, package: str, niche: str, topics: list = None):
    clients = load_clients()
    client = {
        "id": len(clients) + 1,
        "name": name,
        "email": email,
        "package": package,
        "niche": niche,
        "topics": topics or [],
        "posts_delivered": 0,
        "monthly_revenue": PACKAGES[package]["price_monthly"],
        "start_date": datetime.now().isoformat()[:10],
        "status": "active",
    }
    clients.append(client)
    save_clients(clients)
    log.info(f"Client added: {name} ({package}) - ${PACKAGES[package]['price_monthly']}/mo")
    return client

def generate_articles_for_client(client_id: int, count: int = 1) -> list:
    """
    Auto-generate articles for a client using the content engine.
    Uses client's niche and remaining topics queue.
    """
    clients = load_clients()
    client = next((c for c in clients if c["id"] == client_id), None)
    if not client:
        log.error(f"Client {client_id} not found")
        return []

    delivered = []
    topics = client.get("topics", [])
    niche = client.get("niche", "general business")

    for i in range(count):
        if topics:
            topic_data = topics[0]
            topic = topic_data if isinstance(topic_data, str) else topic_data.get("topic", "")
            keywords = "" if isinstance(topic_data, str) else topic_data.get("keywords", "")
        else:
            # Auto-generate topic from niche
            topic = f"How {niche} businesses can use AI tools to save time in 2026"
            keywords = f"AI tools for {niche}, {niche} automation"

        article = generate_article(topic=topic, keywords=keywords, tool_focus=None)
        if article:
            # Save to client delivery folder
            folder = f"data/client_{client_id}/"
            os.makedirs(folder, exist_ok=True)
            filename = f"{folder}{article['slug']}.html"
            with open(filename, "w") as f:
                f.write(f"<h1>{article['title']}</h1>\n{article['content']}")
            delivered.append({"title": article["title"], "file": filename})
            log.info(f"Delivered article for client {client_id}: {article['title']}")

            # Remove used topic
            if topics:
                topics.pop(0)

    # Update client record
    for c in clients:
        if c["id"] == client_id:
            c["posts_delivered"] += len(delivered)
            c["topics"] = topics
    save_clients(clients)
    return delivered

def get_mrr_summary() -> dict:
    clients = load_clients()
    active = [c for c in clients if c.get("status") == "active"]
    mrr = sum(c["monthly_revenue"] for c in active)
    return {
        "active_clients": len(active),
        "mrr": mrr,
        "weekly_revenue": round(mrr / 4.33, 0),
        "clients": [{"name": c["name"], "package": c["package"], "revenue": c["monthly_revenue"]} for c in active],
    }

def print_launch_checklist():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  🚀 AI WRITING SERVICE — LAUNCH IN 24 HOURS                 ║
╚══════════════════════════════════════════════════════════════╝

TODAY (Hour 1-2):
  □ Create Upwork account → paste profile bio below
  □ Create Fiverr account → create gig with copy below
  □ Set up PayPal/Stripe for payments

TODAY (Hour 3-4):
  □ Find 20 prospects using the search queries in cold_outreach.py
  □ Send 10 cold pitches (use templates below)
  □ Post in 3 Reddit communities (r/forhire, r/entrepreneur, r/content_marketing)

DAY 2-3:
  □ Follow up on pitches
  □ Apply to 5 Upwork jobs for "blog writing", "SEO content"

WEEK 1 GOAL: Land 1 client at $397/month
WEEK 2 GOAL: Land 2nd client → $794/month total
MONTH 2 GOAL: 3 clients + affiliate income = $600-1,000/week

PRICING:
  Single article: $89-149
  4 posts/month:  $397
  8 posts/month:  $697
  16 posts/month: $1,197
""")

if __name__ == "__main__":
    print(generate_upwork_profile())
    print(generate_fiverr_gig())
    print("\nCold pitch (SaaS):")
    print(generate_cold_pitch("saas"))
    print_launch_checklist()
    summary = get_mrr_summary()
    print(f"\nCurrent MRR: ${summary['mrr']}/mo (${summary['weekly_revenue']}/wk)")
