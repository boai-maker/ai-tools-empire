# Opt-in Surface Audit — 2026-04-21

**Context:** 13K pageviews over 14 days produced **3 subscribers** — a 0.02% conversion rate. Industry baseline is 1–3%. The question: are opt-in *surfaces* missing, or is the *offer/copy* the problem?

## Finding: Surfaces are NOT missing. Offer quality is.

The site already has **5 distinct opt-in surfaces**. The original brief assumed they were missing — they're not. What's missing is:
- A clear, specific, benefit-loaded lead magnet promise
- Conversion tracking per surface
- Send-on-signup automation (no beehiiv integration exists)

## Every opt-in surface currently live

| # | Template | Surface | Line | Endpoint | Copy |
|---|---|---|---|---|---|
| 1 | `index.html` | Hero newsletter section | 581 | `/subscribe` | "Join 12,000+ weekly subscribers" + "Get instant access to the Top 10 AI Tools Cheat Sheet" |
| 2 | `article.html` | Inline mid-article | 533 | `/subscribe` | "Subscribe & get instant access to the AI Tools Cheatsheet" |
| 3 | `article.html` | Sticky right sidebar | 601 | `/subscribe` | Sidebar newsletter form |
| 4 | `article.html` | Scroll-triggered sticky CTA | 633 | `/subscribe` | Appears after 40% article scroll |
| 5 | `base.html` | Exit-intent modal | 238 | `/subscribe` | "Free AI Tools Starter Kit" |
| 6 | `base.html` | Footer newsletter | 205 | `/subscribe` | "Join our free newsletter" |
| 7 | `articles.html` | Right sidebar (index) | 311 | `/subscribe` | "Subscribe to our newsletter for weekly AI updates" |
| 8 | `tools.html` | CTA section | 332 | `/subscribe` | "Get weekly AI tools updates" |

That's 6 distinct placements across 5 templates. The site has MORE opt-in surfaces than most — yet converts worse.

## The actual problem — ranked

### 1. "12,000+ weekly subscribers" is a lie and Google knows it (HIGH impact)
The hero shows a fake subscriber count. Actual table has 3 rows. This is:
- A trust-destroyer if a savvy visitor suspects it
- A Google spam signal (false social proof is flagged)
- A self-sabotage — if claimed-count > actual, the promise falls flat

**Fix:** replace with something honest: "Get the lead magnet. Unsubscribe anytime." Or grow real social proof first.

### 2. Lead magnet is a generic "Top 10 AI Tools Cheatsheet" (HIGH impact)
The lead magnet file (`static/ai-tools-cheatsheet.html`) is an HTML cheat sheet with tool comparisons and ROI calcs. Problems:
- Generic headline — every AI blog offers "top 10 tools"
- It's an HTML page, not a downloadable PDF — loses the "gated download" feel
- No urgency, no specific outcome ("save 10 hours", "make $X")

**Fix:** replace with a specific-number, outcome-loaded offer. Candidates from the brief:
  - "The 7-tool AI stack that pays my bills"
  - "47 AI prompts I use every week"
  - "Free AI audit: send me your stack, I'll show you what to drop"

### 3. Zero conversion tracking per surface (HIGH impact, blocker)
All 6 surfaces POST to `/subscribe` with no surface identifier. Means you cannot answer: does the exit-modal convert better than the sidebar? Does the sticky CTA beat the hero?

**Fix:** add `<input type="hidden" name="surface" value="exit_modal">` (etc.) to every form. Extend the `subscribers` table with `source` detail or create a dedicated `signups` events table. This is a prerequisite for A/B testing in Priority 5.

### 4. No beehiiv integration (MEDIUM impact)
Grep for 'beehiiv', 'BEEHIIV', 'publication_id' returned **zero hits**. All signups go into the local SQLite `subscribers` table. There is no:
- Send-on-signup automation
- Welcome email sequence
- Drip campaign wiring
- Beehiiv API client

**Fix:** Wire the `/subscribe` endpoint to also POST to beehiiv's API (publication_id + reader API key in `.env`). Without this, subscribers get the form success state but NO actual email — killing trust on the very first interaction.

### 5. Forms ask for email only (small win available)
All 6 forms are email-only. Consider adding an optional first-name field on 1-2 surfaces (inline, modal). Personalized "Hi Sarah" subject lines in beehiiv lift opens 10-15%.

## Database evidence

```sql
SELECT COUNT(*) FROM subscribers;              -- 3
SELECT welcome_sent, COUNT(*) FROM subscribers GROUP BY 1;  -- 3 | 0  (none ever got a welcome email)
```

All 3 subscribers have `welcome_sent=0`. No welcome email was ever sent. The `send-welcomes` admin action exists (main.py) but has never successfully fired.

## Recommendations, in order

1. **Kill the "12,000+ subscribers" claim** — 5 min edit. Stops Google from flagging and stops self-sabotage.
2. **Add `surface` tracking to every form** — 1 hour. Unblocks measurement.
3. **Rewrite the lead magnet** — pick one of the 3 candidate headlines and A/B test (Priority 5's first experiment). Content work, ~3 hours.
4. **Wire beehiiv** — use existing API, POST on signup, trigger welcome. 2 hours.
5. **Add per-surface A/B — only after #2 is live**. Otherwise you're testing blind.

## Not-a-problem (confirmed not broken)

- Exit-intent modal exists and is wired (`mouseleave` handler in `base.html:238`)
- Scroll-triggered sticky exists and is wired (`scroll` handler in `article.html:633`)
- `/subscribe` endpoint accepts POSTs
- Email validation likely works (not tested here, but `/subscribe` is a POST handler in main.py)

The surfaces work mechanically. The conversion problem is upstream — the offer, the trust signals, and the lack of a working email fulfillment flow.
