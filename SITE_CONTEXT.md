# AI Tools Empire — Site Context for Claude Cowork

Paste or upload this file at the start of a Cowork session so Claude has
full context about the site before collaborating.

---

## Identity

- **Site:** https://aitoolsempire.co
- **Owner:** Kenneth Bonnet (bosaibot@gmail.com)
- **Niche:** AI tools affiliate marketing for solopreneurs, content creators, freelancers, and SEO/marketing operators
- **One-line promise to the reader:** "Practical AI tool stacks you can use tonight — no fluff, affiliate-honest"
- **Started:** ~2026
- **Monetization:** affiliate commissions (primary), lead magnets, newsletter (secondary)
- **Revenue target:** $100/day combined across affiliate + adjacent bets (Kalshi, Fiverr, wholesale RE)

## Tech stack

| Layer | Tech |
|---|---|
| Web app | FastAPI + Uvicorn (port 8080) |
| Templating | Jinja2 |
| Database | SQLite (data.db) |
| Scheduler | APScheduler |
| OS scheduling | launchd (macOS) |
| Hosting | Render free tier, Docker, auto-deploy on push to main |
| Tunnel | Cloudflared → aitoolsempire.co |
| CDN | Cloudflare |
| GitHub | https://github.com/boai-maker/ai-tools-empire (public, main branch) |
| Python | 3.9 (local), 3.11-slim (Docker) |

Local path: `/Users/kennethbonnet/ai-tools-empire`

## Content state (2026-04-21)

- **Articles published:** 84
- **Traffic (last 14 days):** 13,000+ pageviews, peaking at 3,755 on Apr 8
- **Recent trend:** ⚠️ Traffic dropped 80% Apr 19–21 (203–353/day, down from ~1,000/day baseline) — investigation pending
- **Subscribers:** 3 total ← funnel is broken; 13K views → 3 subs is dismal
- **Top articles by views:**
  1. "Ultimate AI Content Marketing Guide for 2026" — 5,165 views
  2. "How to Start a Blog With AI Tools: Complete 2026 Guide" — 4,536 views
  3. "AI Tools for Small Business 2026: 7-Tool Stack That Pays" — 3,250 views
  4. "Complete AI Prompt Engineering Guide 2026" — 2,578 views
  5. "10 Best AI Writing Tools for Content Creators in 2026" — 2,343 views

## Affiliate programs

### Active (earning commissions today)
| Program | ID / Link | Commission |
|---|---|---|
| Pictory AI | kenneth46 | 20% recurring |
| ElevenLabs | i3pg30ciu5n8 | ~30% |
| Fireflies AI | kenneth39 | 25% |
| Murf AI | https://get.murf.ai/f5q4vpohhwtq | 20% recurring (activated 2026-04-21) |

### Pending (queued on PartnerStack, network approval pending)
Webflow, Kit/ConvertKit, QuillBot, GetResponse, Descript, Surfer SEO (auto-submit when PartnerStack network flips from Pending → Active)

### Manual-apply required
Semrush, HubSpot, Grammarly, InVideo (Impact.com), Synthesia (Rewardful), Canva

### Dead / unavailable
Copy.ai (terminated), Jasper (discontinued for creators), Runway (no affiliate program)

## Click leak analysis (last 14 days)

**237 total affiliate clicks. Only 31 earning money.**

| Status | Clicks | Notes |
|---|---|---|
| Active affiliates | 31 (ElevenLabs 14, Pictory 11, Fireflies 6, Murf 0 yet) | Earning |
| PartnerStack queued | 71 (kit 16, webflow 9, descript 8, murf 8, quillbot 8, surfer 10, getresponse 12) | Will activate on network approval |
| Manual (Impact/etc.) | 82 (invideo 41, semrush 10, hubspot 8, grammarly 7, synthesia 8, canva manual) | Lost until manual applications |
| Dead programs | 25 (copyai 10, jasper 5, runway 5, others) | Permanently lost |

**~2/3 of traffic earns $0 today.** Biggest unlock: (a) get PartnerStack network approved, (b) complete manual Impact.com/Rewardful applications.

## Architecture — 20 bots across 5 systems

1. **14-bot scheduler** (`com.aitoolsempire.bots`) — website_monitor, content_extractor, blog_seo_bot, analytics_bot, affiliate_revenue_bot, email_sequence, affiliate_gmail_monitor, owner_outreach (wholesale RE), tracerfy_lead_bot, wholesale_lead_hunter, etc.
2. **Dominic** (`com.aitoolsempire.dominic`) — social autopilot; Twitter 3×/day + YouTube noon + weekly routine. Currently being upgraded to 4-subagent Shorts pipeline (see `/automation/dominic/UPGRADES.md`).
3. **Kalshi v4.0** (`com.kenny.kalshi-auto`, `~/.kalshi/`) — prediction market trading bot. Kelly sizing, same-day-only bets, $20/bet, $25 daily stop loss.
4. **Wholesale RE CRM** (`http://localhost:5050`) — 224+ properties, 15 buyers. Pipeline: Redfin scraper → Tracerfy skip trace → outreach. Secondary: Surplus funds recovery ($105K pipeline, 1 signed agreement pending).
5. **FastAPI server** (`com.aitoolsempire.server` + `com.aitoolsempire.tunnel`) — serves aitoolsempire.co.

## Known pain points (honest list)

1. **Traffic down 80%** over Apr 19–21. Root cause unknown (Google algo, tracking bug, Render issue, new articles stopped publishing because SEED_TOPICS ran out of non-duplicates — recently fixed with 20 fresh topics but older stale articles still hurt rankings).
2. **Subscriber funnel broken.** 13K views → 3 subs means either lead magnet opt-in isn't visible, or the value prop doesn't convert. Needs A/B testing.
3. **Most affiliate clicks earn $0.** PartnerStack network pending, Impact.com/Rewardful manual applications blocked.
4. **Article clicks not attributed.** `articles.affiliate_clicks` column shows 0 for every article even though `affiliate_clicks` table has 237 entries. Attribution pipeline is broken.
5. **Content generation was duplicate-locked** until today — SEED_TOPICS had ~50 topics all already used. Fixed 2026-04-21 by adding 20 fresh 2026 trends.
6. **No analytics dashboard on the live site** — internal bots have stats, but nothing public for transparency.
7. **YouTube channel** (UClgQP3jVdCFPHkN-JIOFINA) has community posts blocked (needs 500 subs), shorts uploads fail with `youtubeSignupRequired` until account completes YT setup.

## What I want Cowork help with

Top priorities, in order:
1. **Diagnose the Apr 19–21 traffic drop.** Google Search Console audit + article-level view trend analysis.
2. **Fix the subscriber funnel.** Landing page/lead magnet conversion-rate optimization. Currently sub rate is ~0.02%; should be ≥2%.
3. **Redesign homepage for CTR on active-affiliate tools.** Right now clicks heavily go to Kit/Webflow/InVideo/Semrush which we DON'T earn on. Rebalance featured placements toward Pictory, ElevenLabs, Fireflies, Murf.
4. **Fix affiliate click attribution** so `articles.affiliate_clicks` updates from the `affiliate_clicks` events.
5. **Design A/B testing framework** for hooks, CTAs, lead magnet headlines.
6. **Grow newsletter** — pick a real email platform (beehiiv is already onboarded), set up welcome sequence, pick lead magnet that actually converts.

## Brand voice

- Tone: sharp, concrete, dry. Practical. No corporate filler.
- Pronouns: "you" (second person). Avoid corporate "we".
- Sentence length: short. 8 words beats 18.
- Banned: "delve", "unleash", "game-changer", "revolutionize", "leverage", "empower", "seamlessly", "cutting-edge", "unlock", "let's dive in", "in today's fast-paced world", "at the end of the day"
- Persona: see `/automation/dominic/CLAUDE.md` §2 for 3 target personas (side-hustle solopreneur, aspiring creator, SEO/marketing operator)

## Key files if Cowork needs to read code

- `main.py` — FastAPI entry point
- `config.py` — all env-driven config + AFFILIATE_IDS dict
- `affiliate/links.py` — AFFILIATE_PROGRAMS (active) + PENDING_PROGRAMS (queued)
- `templates/index.html` — homepage (needs the redesign)
- `static/ai-tools-cheatsheet.html` — current lead magnet
- `render.yaml` + `Dockerfile` — deploy config
- `/automation/dominic/CLAUDE.md` — brand/voice spec
- `/automation/dominic/pipeline.py` — 4-subagent Shorts generator (new)

## Hard rules (do not violate)

- Never hardcode Telegram tokens / API keys; read from `.env`
- Never break backward compat on `AFFILIATE_PROGRAMS` dict keys (used by article templates)
- Never use deprecated Claude models (current: `claude-sonnet-4-20250514`)
- Never push to git without syntax-checking Python first
- Always restart the launchd agent after editing bot files
- All cash offer emails to wholesale leads: 5-10K below asking, never mention Proof of Funds
- Never exceed 1 outreach email per property per 48 hours

---

**Updated:** 2026-04-21
