# Trust Issues Tracker — AI Tools Empire
Last updated: April 2026

## STATUS KEY
- ✅ Fixed
- ⚠️ Needs manual decision
- ❌ Blocked — needs Kenny input
- 🔲 Not started

---

## CRITICAL — Fixed This Session

| # | Issue | File | Fix Applied |
|---|-------|------|-------------|
| 1 | Fake subscriber floor (`max(count, 12000)`) | main.py:103 | ✅ Removed — now shows real count |
| 2 | Fake article floor (`max(count, 50)`) | main.py:104 | ✅ Removed — now shows real count |
| 3 | `{{ tool.reviews }}k+ reviews` (fabricated) | tools.html:130 | ✅ Removed |
| 4 | Commission tags on tool cards (confusing to users) | tools.html:128,138 | ✅ Replaced with "Free trial" |
| 5 | "real user reviews" in tools page header | tools.html:101 | ✅ Removed |
| 6 | No affiliate disclosure on /tools page | tools.html | ✅ Added at top of listings |
| 7 | "We ran 50 test samples" (unverifiable) | index.html:400 | ✅ Removed |
| 8 | "We tested both for 3 months" teaser | index.html:397 | ✅ Removed |
| 9 | "saves 10+ hours per week" unverified claim | index.html:401 | ✅ Removed |
| 10 | "AI is writing these reviews right now" public message | index.html:417 | ✅ Removed |
| 11 | "Hands-on tested" claim vs. AI-generated content | index.html, how-we-test | ✅ Changed to "Research-based reviews" |
| 12 | "100% Independent — No Paid Placement" (misleading) | index.html | ✅ Changed to "No Paid Placements Ever" |
| 13 | Duplicate subscriber count stat | index.html | ✅ Made conditional (only shows if > 100) |

---

## NEEDS KENNY DECISION — Cannot implement without input

### R1 — Hardcoded Star Ratings in links.py
**Severity:** CRITICAL
**Issue:** Every tool has a hardcoded rating (e.g. `"rating": 4.8`) and fabricated review counts. These display on the tools page as star ratings and were previously shown as review counts.

**Options:**
- A) Remove ratings entirely — cleanest, safest
- B) Source them from a real platform (G2, Capterra, Trustpilot) and cite source
- C) Create your own scoring rubric (1–5 across defined criteria) and label it "Our Score"

**What's needed from Kenny:**
- [ ] Decision: A, B, or C above
- [ ] If B: identify which review platform to use as source
- [ ] If C: score each of the 17 tools on the 5 criteria from how-we-test page

**Files affected:** `affiliate/links.py` (17 entries), `templates/tools.html`

---

### R2 — Author / Reviewer Identity
**Severity:** CRITICAL for E-E-A-T
**Issue:** All articles are attributed to "AI Tools Empire" (Organization). Google's E-E-A-T requires demonstrable human expertise. No reviewer name, bio, or credentials exist anywhere.

**What's needed from Kenny:**
- [ ] Your name or a pen name to use as reviewer
- [ ] A 2–3 sentence bio (role, experience, what you've worked on)
- [ ] Optional: LinkedIn URL, Twitter/X handle, photo
- [ ] Decision: one reviewer (you) or multiple named contributors?

**Implementation plan (ready to build once info provided):**
- Add `author_name` and `author_bio` fields to database
- Add byline block to article.html header
- Update Article schema to use `@type: Person` for author
- Add Author page at `/author/[slug]`

---

### R3 — "Editorial Independence" vs. Commission Incentives
**Severity:** HIGH
**Issue:** Tools paying $400/month (HubSpot) appear in same ranked list as tools paying $80/month (Murf) with no disclosure of the financial difference. Ranking by commission income = undisclosed conflict of interest.

**What's needed from Kenny:**
- [ ] Decision: does ranking order reflect your honest opinion or affiliate income?
- [ ] If opinion: add a clear statement of ranking criteria to /how-we-test
- [ ] If income influences ranking: add disclosure ("we may earn more from some tools than others")

---

### R4 — AI-Generated Content Disclosure
**Severity:** MEDIUM (growing regulatory concern)
**Issue:** Content is generated via Claude API. FTC and Google are increasingly flagging undisclosed AI content. The how-we-test page now says "research-based" which is accurate but vague.

**Options:**
- A) Add a footer note: "Content on this site is researched and written with AI assistance"
- B) Add per-article disclosure: "This review was prepared with AI assistance and reviewed for accuracy"
- C) No disclosure (current state — acceptable for now but higher regulatory risk)

**What's needed from Kenny:**
- [ ] Decision: A, B, or C
- [ ] If A or B: approve the exact wording above or provide your own

---

## LOW PRIORITY — Fix Later

| # | Issue | Notes |
|---|-------|-------|
| L1 | Article pages show `created_at` only, not `updated_at` | Add "Last updated" display to article.html |
| L2 | No ethics policy page | Draft ready to write once editorial decisions above are made |
| L3 | Privacy policy doesn't disclose affiliate click tracking | Update /privacy route in main.py |
| L4 | No contact email for privacy requests | Add to /privacy and /contact |
