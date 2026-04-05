# SEO Duplicate Content Tracker
Last updated: April 2026

## STATUS KEY
- ✅ Resolved
- ⚠️ Needs decision
- ❌ Blocked — needs Kenny input

---

## CRITICAL: Keyword Cannibalization Groups

These article slug groups all target the same keyword. Google will struggle to
rank any of them. One slug must be kept; the rest should be deleted from the DB
or set to status='draft', then 301-redirected to the canonical URL.

### Group 1 — Surfer SEO vs Semrush (5 duplicates)
Target keyword: `surfer seo vs semrush`

| Slug | Last Modified | Action Needed |
|------|---------------|---------------|
| `surfer-seo-vs-semrush-comparison` | 2026-03-29 | ⚠️ Pick one as canonical |
| `surfer-seo-vs-semrush-full-comparison` | 2026-03-30 | ⚠️ Delete or redirect |
| `surfer-seo-vs-semrush-full-comparison-for-2024` | 2026-03-30 | ❌ Delete (wrong year) |
| `surfer-seo-vs-semrush-complete-comparison-for-2024` | 2026-03-30 | ❌ Delete (wrong year) |
| `surfer-seo-vs-semrush-complete-comparison-2024` | 2026-03-30 | ❌ Delete (wrong year) |
| `surfer-seo-vs-semrush-complete-comparison-best-seo-tool-for-2024` | 2026-03-30 | ❌ Delete (wrong year + over-stuffed slug) |

**Recommended canonical:** `surfer-seo-vs-semrush-comparison`
**Action:** Delete 5 duplicates from DB. Add 301 redirects in main.py.

---

### Group 2 — ElevenLabs vs Murf AI (4 duplicates)
Target keyword: `elevenlabs vs murf ai`

| Slug | Last Modified | Action Needed |
|------|---------------|---------------|
| `elevenlabs-vs-murf-ai-comparison-2026` | 2026-03-29 | ⚠️ Pick one as canonical |
| `elevenlabs-vs-murf-ai-best-ai-voice-generator` | 2026-03-30 | ⚠️ Delete or redirect |
| `elevenlabs-vs-murf-ai-which-ai-voice-generator-wins-in-2026` | 2026-03-30 | ⚠️ Delete or redirect |
| `elevenlabs-vs-murf-ai-which-ai-voice-generator-is-best-in-2026` | 2026-03-30 | ⚠️ Delete or redirect |
| `elevenlabs-vs-murf-ai-which-ai-voice-generator-wins-in-2024` | 2026-03-30 | ❌ Delete (wrong year) |

**Recommended canonical:** `elevenlabs-vs-murf-ai-comparison-2026`
**Action:** Delete 4 duplicates from DB. Add 301 redirects in main.py.

---

### Group 3 — Jasper AI vs Copy.ai (2 duplicates)
Target keyword: `jasper ai vs copy ai`

| Slug | Last Modified | Action Needed |
|------|---------------|---------------|
| `jasper-ai-vs-copyai-2026-comparison` | 2026-03-29 | ⚠️ Pick one as canonical |
| `jasper-ai-vs-copyai-which-is-better-in-2026` | 2026-03-30 | ⚠️ Delete or redirect |
| `jasper-ai-vs-copy-ai-which-is-better-in-2026` | 2026-03-30 | ⚠️ Delete or redirect |

**Recommended canonical:** `jasper-ai-vs-copyai-2026-comparison`
**Action:** Delete 2 duplicates. Add 301 redirects.

---

### Group 4 — ElevenLabs Review (2 duplicates)
Target keyword: `elevenlabs review 2026`

| Slug | Last Modified | Action Needed |
|------|---------------|---------------|
| `elevenlabs-review-2026` | 2026-03-29 | ⚠️ Pick one as canonical |
| `elevenlabs-review-2026-the-best-ai-voice-cloning-tool` | 2026-03-30 | ⚠️ Delete or redirect |

**Recommended canonical:** `elevenlabs-review-2026`
**Action:** Delete 1 duplicate. Add 301 redirect.

---

## IMPLEMENTATION PLAN (ready to execute once Kenny confirms canonical slugs)

### Step 1 — Confirm canonical slugs above
Kenny reviews the list and confirms or changes the recommended canonical for each group.

### Step 2 — Delete duplicates from database
```bash
# Run from project root after confirming slugs
python3 -c "
from database.db import get_conn
conn = get_conn()
slugs_to_delete = [
    'surfer-seo-vs-semrush-full-comparison',
    'surfer-seo-vs-semrush-full-comparison-for-2024',
    # ... add confirmed slugs
]
for slug in slugs_to_delete:
    conn.execute('UPDATE articles SET status=? WHERE slug=?', ('draft', slug))
conn.commit()
print('Done')
"
```

### Step 3 — Add 301 redirects to main.py
```python
ARTICLE_REDIRECTS = {
    "surfer-seo-vs-semrush-full-comparison": "surfer-seo-vs-semrush-comparison",
    # ... add all confirmed slugs
}

@app.get("/articles/{slug}")
async def article_page(slug: str, ...):
    if slug in ARTICLE_REDIRECTS:
        return RedirectResponse(f"/articles/{ARTICLE_REDIRECTS[slug]}", status_code=301)
    # ... existing handler
```

### Step 4 — Update sitemap.xml
Remove duplicate URLs, keep only canonical ones.

---

## OTHER SEO ISSUES

### Dual route risk
Both `/blog/{slug}` and `/articles/{slug}` serve the same content.
- **Fix:** Add canonical `<link>` tag pointing to `/articles/{slug}` from `/blog/{slug}`
- **Status:** ⚠️ Needs implementation after duplicate content resolved

### /newsletter URL in old sitemap
- Removed in this session ✅

### New hub pages added to sitemap
- `/best-ai-writing-tools` ✅
- `/best-ai-seo-tools` ✅
- `/best-ai-video-tools` ✅
- `/best-ai-voice-tools` ✅
- `/best-ai-productivity-tools` ✅
