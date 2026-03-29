"""
Cold Outreach Automation — fastest path to affiliate commissions.

Strategy:
  1. Find prospects (marketing agencies, content creators, SaaS founders)
  2. Send personalized cold emails with soft affiliate recommendations
  3. Follow up automatically on day 3 and day 7

Target personas (highest affiliate conversion rates):
  - Marketing agencies (need Jasper, Semrush, Surfer) → $200-400/conversion
  - Content creators / bloggers (need Jasper, Writesonic) → $50-150/conversion
  - Small SaaS founders (need Semrush, Surfer SEO) → $200+/conversion
  - YouTubers / video creators (need Pictory, InVideo, Descript) → $100-200/conversion
  - Podcasters (need Descript, Murf, ElevenLabs) → $80-150/conversion

How to find leads (free methods in find_leads_free()):
  - LinkedIn Sales Navigator search exports
  - Apollo.io free tier (50 leads/day free)
  - Hunter.io domain search
  - Reddit user scraping (people asking about tools)
  - Twitter/X search for buying signals
"""

import csv
import json
import logging
import os
import time
import resend
from datetime import datetime, timedelta
from typing import Optional
from config import config
from affiliate.links import AFFILIATE_PROGRAMS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

resend.api_key = config.RESEND_API_KEY

# ── Prospect database (CSV-based, no extra DB needed) ──────────────────────
PROSPECTS_FILE = "data/prospects.csv"
SENT_LOG_FILE  = "data/outreach_sent.csv"

PROSPECT_FIELDS = ["email","name","company","persona","source","status","added_date","last_contact","notes"]

def init_prospect_files():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(PROSPECTS_FILE):
        with open(PROSPECTS_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=PROSPECT_FIELDS).writeheader()
    if not os.path.exists(SENT_LOG_FILE):
        with open(SENT_LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=["email","sequence_step","subject","sent_at","opened","clicked"]).writeheader()

def add_prospect(email: str, name: str, company: str, persona: str, source: str, notes: str = ""):
    init_prospect_files()
    # Check for duplicates
    prospects = load_prospects()
    if any(p["email"].lower() == email.lower() for p in prospects):
        log.info(f"Prospect already exists: {email}")
        return False
    with open(PROSPECTS_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PROSPECT_FIELDS)
        writer.writerow({
            "email": email.lower().strip(),
            "name": name,
            "company": company,
            "persona": persona,
            "source": source,
            "status": "new",
            "added_date": datetime.now().isoformat()[:10],
            "last_contact": "",
            "notes": notes,
        })
    log.info(f"Prospect added: {name} <{email}> [{persona}]")
    return True

def load_prospects(status_filter: str = None):
    init_prospect_files()
    prospects = []
    with open(PROSPECTS_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if status_filter is None or row.get("status") == status_filter:
                prospects.append(row)
    return prospects

def update_prospect_status(email: str, status: str):
    prospects = load_prospects()
    updated = []
    for p in prospects:
        if p["email"].lower() == email.lower():
            p["status"] = status
            p["last_contact"] = datetime.now().isoformat()[:10]
        updated.append(p)
    with open(PROSPECTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PROSPECT_FIELDS)
        writer.writeheader()
        writer.writerows(updated)

def log_sent(email: str, step: int, subject: str):
    with open(SENT_LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["email","sequence_step","subject","sent_at","opened","clicked"])
        writer.writerow({
            "email": email,
            "sequence_step": step,
            "subject": subject,
            "sent_at": datetime.now().isoformat(),
            "opened": 0,
            "clicked": 0,
        })

# ── Email sequence templates ─────────────────────────────────────────────────

def get_recommended_tools(persona: str) -> list[dict]:
    """Pick the best 2-3 tools for each persona."""
    mapping = {
        "marketing_agency": ["semrush", "jasper", "surfer"],
        "content_creator":  ["jasper", "copyai", "writesonic"],
        "saas_founder":     ["semrush", "surfer", "fireflies"],
        "youtuber":         ["pictory", "invideo", "descript"],
        "podcaster":        ["descript", "murf", "elevenlabs"],
        "blogger":          ["jasper", "surfer", "writesonic"],
        "ecommerce":        ["jasper", "semrush", "copyai"],
        "freelancer":       ["jasper", "copyai", "fireflies"],
    }
    keys = mapping.get(persona, ["jasper", "surfer", "semrush"])
    return [AFFILIATE_PROGRAMS[k] for k in keys if k in AFFILIATE_PROGRAMS]

def build_email_sequence(prospect: dict) -> list[dict]:
    """Build a 3-email sequence tailored to the prospect's persona."""
    name_first = prospect["name"].split()[0] if prospect["name"] else "there"
    company    = prospect["company"] or "your business"
    persona    = prospect["persona"]
    tools      = get_recommended_tools(persona)

    tool1, tool2 = tools[0], tools[1] if len(tools) > 1 else tools[0]

    # ── Persona-specific pain points ──
    pain_points = {
        "marketing_agency":  ("spending hours on SEO research and content", "Surfer SEO + Jasper cut content time by 70%"),
        "content_creator":   ("staring at blank pages and writer's block", "Copy.ai writers 10x their output"),
        "saas_founder":      ("manual SEO and competitor tracking", "Semrush automates all of it"),
        "youtuber":          ("spending 8+ hours editing each video", "Pictory AI turns scripts into videos in minutes"),
        "podcaster":         ("manual editing and transcription", "Descript edits podcasts like a Google Doc"),
        "blogger":           ("writing 2,000-word articles from scratch", "Jasper AI writes full drafts in 20 minutes"),
        "ecommerce":         ("writing product descriptions at scale", "Jasper AI generates 100 descriptions in an hour"),
        "freelancer":        ("manual meeting notes and follow-ups", "Fireflies records, transcribes, and summarizes every call"),
    }
    problem, solution = pain_points.get(persona, ("doing everything manually", "AI tools automate 70% of the work"))

    # Email 1: Value-first, no hard sell
    email1_subject = f"Quick question about {company}'s content workflow"
    email1_html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;color:#1e293b;line-height:1.7;">
  <p>Hi {name_first},</p>
  <p>I run <a href="{config.SITE_URL}" style="color:#6366f1;">{config.SITE_NAME}</a> — we test and review AI tools for businesses like {company}.</p>
  <p>Quick question: is your team still {problem}?</p>
  <p>I ask because {solution} — and I put together a free guide on exactly which tools work best for {persona.replace('_',' ')}s:</p>
  <p style="text-align:center;margin:24px 0;">
    <a href="{config.SITE_URL}/tools" style="background:#6366f1;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;">
      View Free AI Tools Guide →
    </a>
  </p>
  <p>The one I'd start with for {company} is <strong><a href="{tool1['signup_url']}" style="color:#6366f1;">{tool1['name']}</a></strong> ({tool1['description']}).</p>
  <p>They have a free trial — no credit card needed. Worth 15 minutes to test.</p>
  <p style="color:#64748b;">
    {name_first}, if this isn't relevant, just say the word and I won't bother you again.<br><br>
    — The {config.SITE_NAME} Team
  </p>
  <p style="font-size:11px;color:#94a3b8;">Disclosure: We earn a small commission if you sign up through our links, at no extra cost to you.</p>
</div>
"""

    # Email 2: Social proof + tool comparison (Day 3)
    email2_subject = f"How {company} could save 10+ hours/week with AI"
    email2_html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;color:#1e293b;line-height:1.7;">
  <p>Hi {name_first},</p>
  <p>Sent you a note a few days ago about AI tools for {persona.replace('_',' ')}s — just wanted to follow up with something concrete.</p>
  <p>We just published a comparison of the top 2 tools for your use case:</p>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin:20px 0;">
    <div style="display:flex;justify-content:space-between;margin-bottom:12px;">
      <div><strong style="font-size:16px;">{tool1['name']}</strong><br>
        <span style="color:#64748b;font-size:14px;">{tool1['description']}</span><br>
        <span style="color:#10b981;font-weight:700;font-size:13px;">Rating: {'⭐' * int(tool1['rating'])} ({tool1['rating']})</span>
      </div>
    </div>
    <div style="display:flex;justify-content:space-between;">
      <div><strong style="font-size:16px;">{tool2['name']}</strong><br>
        <span style="color:#64748b;font-size:14px;">{tool2['description']}</span><br>
        <span style="color:#10b981;font-weight:700;font-size:13px;">Rating: {'⭐' * int(tool2['rating'])} ({tool2['rating']})</span>
      </div>
    </div>
  </div>
  <p>For {persona.replace('_',' ')}s, <strong>{tool1['name']}</strong> usually wins. Here's the free trial link:</p>
  <p style="text-align:center;margin:24px 0;">
    <a href="{tool1['signup_url']}" style="background:#10b981;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700;display:inline-block;">
      Try {tool1['name']} Free →
    </a>
  </p>
  <p style="color:#64748b;font-size:14px;">— {config.SITE_NAME} Team</p>
  <p style="font-size:11px;color:#94a3b8;">Affiliate disclosure: we earn a commission on signups at no cost to you. <a href="{config.SITE_URL}/unsubscribe?email={prospect['email']}">Unsubscribe</a></p>
</div>
"""

    # Email 3: Last chance + deal (Day 7)
    email3_subject = f"Last note — free trial expires soon for {tool1['name']}"
    email3_html = f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:560px;color:#1e293b;line-height:1.7;">
  <p>Hi {name_first},</p>
  <p>Last email on this — I know your inbox is busy.</p>
  <p>I've seen {persona.replace('_',' ')}s save 10–15 hours per week after switching to AI tools. The free trial for <strong>{tool1['name']}</strong> is the lowest-friction way to find out if it's worth it for {company}.</p>
  <p><strong>What you get on the free trial:</strong></p>
  <ul style="color:#475569;">
    <li>{tool1['description']}</li>
    <li>No credit card required</li>
    <li>Cancel anytime</li>
  </ul>
  <p style="text-align:center;margin:24px 0;">
    <a href="{tool1['signup_url']}" style="background:#6366f1;color:white;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block;">
      Start Free Trial → {tool1['name']}
    </a>
  </p>
  <p style="color:#94a3b8;font-size:13px;">This is my last note. Hope it was helpful regardless!</p>
  <p style="color:#64748b;font-size:14px;">— {config.SITE_NAME} Team</p>
  <p style="font-size:11px;color:#94a3b8;">Affiliate disclosure: we earn a commission on signups. <a href="{config.SITE_URL}/unsubscribe?email={prospect['email']}">Unsubscribe</a></p>
</div>
"""

    return [
        {"step": 1, "delay_days": 0,  "subject": email1_subject, "html": email1_html},
        {"step": 2, "delay_days": 3,  "subject": email2_subject, "html": email2_html},
        {"step": 3, "delay_days": 7,  "subject": email3_subject, "html": email3_html},
    ]

def send_sequence_step(prospect: dict, step: int) -> bool:
    """Send one email from the sequence to a prospect."""
    sequence = build_email_sequence(prospect)
    email_data = next((e for e in sequence if e["step"] == step), None)
    if not email_data:
        return False

    try:
        resend.Emails.send({
            "from": f"{config.FROM_NAME} <{config.FROM_EMAIL}>",
            "to": [prospect["email"]],
            "subject": email_data["subject"],
            "html": email_data["html"],
        })
        log_sent(prospect["email"], step, email_data["subject"])
        log.info(f"Sent step {step} to {prospect['email']}: {email_data['subject']}")
        return True
    except Exception as e:
        log.error(f"Failed to send to {prospect['email']}: {e}")
        return False

def run_outreach_sequences():
    """
    Main automation function — called daily by scheduler.
    Sends the right sequence step to each prospect based on timing.
    """
    prospects = load_prospects()
    sent_count = 0

    for prospect in prospects:
        status = prospect.get("status", "new")
        added  = prospect.get("added_date", "")
        last   = prospect.get("last_contact", "")

        if status == "new":
            # Send step 1 immediately
            if send_sequence_step(prospect, 1):
                update_prospect_status(prospect["email"], "step1_sent")
                sent_count += 1
                time.sleep(2)  # Respect send rate limits

        elif status == "step1_sent" and added:
            # Send step 2 after 3 days
            days_since = (datetime.now() - datetime.fromisoformat(last or added)).days
            if days_since >= 3:
                if send_sequence_step(prospect, 2):
                    update_prospect_status(prospect["email"], "step2_sent")
                    sent_count += 1
                    time.sleep(2)

        elif status == "step2_sent" and last:
            # Send step 3 after 4 more days (7 days from step 1)
            days_since = (datetime.now() - datetime.fromisoformat(last)).days
            if days_since >= 4:
                if send_sequence_step(prospect, 3):
                    update_prospect_status(prospect["email"], "completed")
                    sent_count += 1
                    time.sleep(2)

    log.info(f"Outreach run complete: {sent_count} emails sent")
    return sent_count

# ── Lead sourcing helpers ────────────────────────────────────────────────────

def import_prospects_from_csv(filepath: str, persona: str, source: str):
    """
    Import prospects from a CSV file.
    CSV must have columns: email, name, company (at minimum)
    Use Apollo.io, Hunter.io, or LinkedIn exports.
    """
    imported = 0
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email   = row.get("email", "").strip()
            name    = row.get("name", row.get("first_name", "")).strip()
            company = row.get("company", row.get("organization", "")).strip()
            if email and "@" in email:
                if add_prospect(email, name, company, persona, source):
                    imported += 1
    log.info(f"Imported {imported} prospects from {filepath}")
    return imported

def generate_prospect_search_queries() -> dict:
    """
    Returns ready-to-use search queries for finding prospects on each platform.
    Use these manually or with Apollo.io/Hunter.io API.
    """
    return {
        "apollo_io": {
            "description": "Apollo.io has 50 free exports/day. Use these filters:",
            "marketing_agency": {
                "title": ["Marketing Manager", "Content Manager", "SEO Manager", "Head of Content", "Digital Marketing Director"],
                "industry": ["Marketing and Advertising", "Internet"],
                "company_size": ["1-50", "51-200"],
            },
            "saas_founder": {
                "title": ["Founder", "CEO", "Co-Founder"],
                "industry": ["Computer Software", "Internet", "Information Technology"],
                "company_size": ["1-50"],
            },
            "content_creator": {
                "title": ["Content Creator", "Blogger", "Influencer", "Newsletter Writer"],
                "keywords": ["Substack", "newsletter", "content creator"],
            },
        },
        "twitter_x_search": {
            "description": "Search Twitter/X for buying signals. DM or email found in bio.",
            "queries": [
                '"looking for" AI writing tool',
                '"best AI tool" for content',
                '"jasper ai" alternative',
                '"need help with" SEO tools',
                '"anyone recommend" AI',
                'frustrated "ai writing"',
            ],
        },
        "reddit": {
            "description": "Find people asking for tool recommendations — they are hot leads.",
            "subreddits": ["r/SEO", "r/content_marketing", "r/Entrepreneur", "r/blogging", "r/marketing"],
            "search_terms": ["best AI writing tool", "recommend AI tool", "jasper alternative", "semrush alternative"],
        },
        "linkedin": {
            "description": "LinkedIn free search — filter by title and industry.",
            "searches": [
                "title:\"Content Manager\" industry:\"Marketing\"",
                "title:\"SEO Manager\" company size:1-50",
                "title:\"Founder\" industry:\"Computer Software\" 1-50 employees",
            ],
        },
        "hunter_io": {
            "description": "Hunter.io finds emails for any domain. 25 free/month.",
            "process": "Find agency websites → enter domain in Hunter.io → get emails → import",
        },
    }

def get_outreach_stats() -> dict:
    """Get current outreach performance stats."""
    init_prospect_files()
    prospects = load_prospects()
    sent_log = []
    with open(SENT_LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        sent_log = list(reader)

    status_counts = {}
    for p in prospects:
        s = p.get("status", "new")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "total_prospects": len(prospects),
        "total_emails_sent": len(sent_log),
        "status_breakdown": status_counts,
        "completed_sequences": status_counts.get("completed", 0),
        "est_conversions": round(len(prospects) * 0.03, 1),  # ~3% industry avg
        "est_revenue": round(len(prospects) * 0.03 * 150, 0),  # ~$150 avg commission
    }

if __name__ == "__main__":
    init_prospect_files()
    # Example: add test prospect
    add_prospect(
        email="test@marketingagency.com",
        name="Sarah Johnson",
        company="Bright Digital Agency",
        persona="marketing_agency",
        source="manual",
        notes="Agency with 12 clients, uses no AI tools currently"
    )
    stats = get_outreach_stats()
    print(f"Outreach stats: {json.dumps(stats, indent=2)}")
    queries = generate_prospect_search_queries()
    print(f"\nProspect search queries ready: {list(queries.keys())}")
