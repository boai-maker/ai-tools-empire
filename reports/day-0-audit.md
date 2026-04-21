# Day 0 Audit — 2026-04-21

This is the mission kickoff report. Full diagnostics already landed earlier
in the day (see `/diagnostics/`) — this doc consolidates the state going
into the $1,000 mission.

## Dollars today
**$0** — first day, attribution was broken until today so no prior earnings
are verifiable yet. Baseline reset.

## Dollars total this mission
**$0**

## What's already shipped (before the mission clock started but in-session)

| Priority | Status | File |
|---|---|---|
| P4 — attribution fix | ✅ | `bots/analytics_bot.py` fuzzy JOIN |
| P2 — /stack-audit lead magnet page | ✅ | `templates/stack-audit.html` + routes |
| P2 — beehiiv integration | ✅ | `integrations/beehiiv.py` |
| P2 — Welcome automation | ✅ | beehiiv Automations, Live, test send verified |
| P3 — `is_active` flag | ✅ | `affiliate/links.py` — pictory/murf/elevenlabs/fireflies |
| P3 — homepage featured re-order | ✅ | `main.py` homepage handler |
| P5 — A/B framework | ✅ | `ab_testing.py` + Jinja `ab()` global + admin endpoint |
| P5 — 2 experiments live | ✅ | `hero-cta-v1`, `stack-audit-h1-v1` |
| P4 — daily revenue report | ✅ | Scheduled 9 AM ET → Telegram |
| `/newsletter` 404 fix | ✅ | 301 redirect to `/stack-audit` |

## Current funnel numbers (baseline)

- 329 affiliate clicks to date
- 14-day: 244 clicks, **16% going to earning affiliates** / 84% leaking
- Top attributed article: `runway-ml-vs-capcut-ai` (21 clicks, 7 from ChatGPT citations)
- 3 subscribers total; 1 tested the beehiiv welcome flow today
- Est monthly revenue at current earning pace: **$44.60**

## Blockers that need owner action

Written to `decisions.md`. Short list:
- GSC OAuth creds — required for impression/ranking diagnosis
- Impact.com, Rewardful, Canva affiliate applications — require human login
- Legacy program replacement for Copy.ai (terminated) in featured surfaces

## Tomorrow's plan (in priority order)

1. **Build comparison-page generator** (Hour 24-48 of mission brief). Generate 5 high-priority `[active-earner]-vs-[competitor]` pages. Comparison pages rank for "vs" intent and convert 5-10× informational content. Direct path to affiliate revenue on existing traffic.

2. **PDF lead magnet with affiliate links inside**. Current `/static/ai-tools-cheatsheet.html` is HTML only. A PDF with affiliate links embedded earns revenue even from non-visiting subscribers.

3. **Featured-tools card redesign** on homepage. Currently the 4 active earners are in slots 1-4 but visually look the same as the 2 non-earners. Add "Editor's Pick" badge + color discipline (emerald CTA button) to active earners only.

Budget: all 3 stay within $0. Full autonomous execution.
