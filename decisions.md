# Decisions Log — Items needing owner action

Format: YYYY-MM-DD HH:MM — Title
Then Context / Options / I chose / Why / If wrong.

---

## 2026-04-21 15:00 — GSC OAuth credentials not in .env

**Context:** Traffic drop Apr 19–21 (~1000/day → 266/day). Local evidence
ranks Google algo action as #1 hypothesis but can't confirm without GSC
impressions/position data. Per-page ranking trends needed to know if this
is site-wide, topic-specific, or a single-page deindex.

**Options:**
A. Add GSC service-account OAuth JSON to `.env`, impact: confirm/kill algo hypothesis in 10 min, cost: $0, risk: none.
B. Ignore, assume algo, wait 7 days for organic recovery. Risk: if it's a technical bug, we miss revenue for a week.

**I chose:** waiting on owner.
**Why:** creating a service account requires owner to click in Google Cloud Console + GSC property settings. Out of scope for this mission.
**If wrong:** zero downside to waiting — the other work items are higher ROI than the diagnosis itself.

---

## 2026-04-21 15:00 — PartnerStack network approval still Pending

**Context:** 6 affiliate programs (Webflow, Kit, QuillBot, GetResponse, Descript, Surfer SEO) auto-submit on PartnerStack network approval. Currently Pending. These represent 71 clicks / 14 days going to $0-earning destinations.

**Options:**
A. Wait for PartnerStack to flip status automatically (no action).
B. Owner emails PartnerStack support asking for expedited review with the active Murf affiliation as proof of program fit.

**I chose:** waiting on owner.
**Why:** I can't email PartnerStack from their account.
**If wrong:** opportunity cost only — if network never approves, the 71 clicks stay at $0. Route traffic elsewhere in meantime (done via `is_active` homepage rebalance).

---

## 2026-04-21 15:00 — Beehiiv trial expiring 2026-04-27 (6 days)

**Context:** Max trial gives Scale-plan features for 14 days. After trial, site auto-downgrades to free tier. Free tier KEEPS welcome emails but loses automations/advanced features. The welcome email automation we built may or may not survive downgrade.

**Options:**
A. Do nothing — let trial expire, accept downgrade.
B. Upgrade to Scale ($84/mo) now.
C. Upgrade to Max ($249/mo) for full send API access.

**I chose:** A (waiting, don't spend).
**Why:** Mission budget is $0. Welcome email is the only automation we need for $1K goal; it lives on free tier.
**If wrong:** automation stops firing post-expiry → verify this on 2026-04-28. If broken, owner decides whether to upgrade or rewire welcome via local SMTP.

---

## 2026-04-21 15:00 — Affiliate programs requiring manual human application

**Context:** Per SITE_CONTEXT.md, these affiliate programs require owner to log in personally + complete application (Cloudflare anti-bot, reCAPTCHA, or dashboard-gated):
- Semrush, HubSpot, Grammarly, InVideo (Impact.com)
- Synthesia (Rewardful)
- Canva (public form)

**Options:**
A. Leave as-is — 82 clicks/14 days going to $0.
B. Owner does 6 manual applications in 30 minutes.

**I chose:** waiting on owner.
**Why:** Each requires login to the owner's personal account. Out of scope.
**If wrong:** 82 clicks × $10-30 avg commission × 1% conversion × 12 mo = $100-300/yr recurring left on the table. Flag to owner as Tier-1 priority when they next touch decisions.md.

---

## 2026-04-21 15:00 — Copy.ai terminated; still listed in AFFILIATE_PROGRAMS

**Context:** Copy.ai shut down their affiliate program. Currently still in `AFFILIATE_PROGRAMS` dict, gets 10 clicks/14 days that earn $0.

**Options:**
A. Remove from dict → breaks backward-compat (hard rule violation: "Never break the AFFILIATE_PROGRAMS dict keys").
B. Keep key, replace `signup_url` with a non-affiliate landing (e.g., a comparison page "Copy.ai is dead → try [ElevenLabs/Pictory] instead").
C. Leave as-is → bleed clicks.

**I chose:** B (swap to internal comparison page, preserve key).
**Why:** Respects the hard rule. Recovers the 10 clicks into ELEVEN or a suitable active earner via the comparison page.
**If wrong:** one pass through the /go/ redirect will show Copy.ai's dead link error; user will bounce. Monitor affiliate_clicks WHERE tool_key='copyai' for zero conversions — which is already the state.
