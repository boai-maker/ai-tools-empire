# Affiliate Attribution Bug — 2026-04-21

**Symptom:** `SELECT SUM(affiliate_clicks) FROM articles` returns **0**, even though `SELECT COUNT(*) FROM affiliate_clicks` returns **329**. Per-article click stats are invisible.

## What's broken

Two-table design where the "rollup" side was never wired up.

```
affiliate_clicks (events)         articles (aggregates)
─────────────────────────         ─────────────────────
id                                id, slug, title, ...
tool_key           ─ 329 rows     views                (≈ updated)
source_page TEXT (/articles/..)   affiliate_clicks     ← never written
ip_hash                           ...
clicked_at
```

- **INSERT path:** `database/db.py:log_click()` → called from `main.py:/track/click/{tool_key}` POST handler. Records one row per click. **Works fine** — 329 rows prove it.
- **UPDATE path:** `articles.affiliate_clicks` increment. Grep for `UPDATE articles SET affiliate_clicks` → **zero hits**. No scheduled job, no trigger, no request-time increment. **Missing entirely.**

## Schema details

```sql
CREATE TABLE articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  ...
  views INTEGER DEFAULT 0,
  affiliate_clicks INTEGER DEFAULT 0,   -- ← never updated
  ...
);

CREATE TABLE affiliate_clicks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tool_key TEXT NOT NULL,
  source_page TEXT,       -- ← referrer path, e.g. '/articles/surfer-seo-review-2026'
                          --   NO foreign key, NO index
  ip_hash TEXT,
  clicked_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

- No foreign key to `articles.slug`
- `source_page` is free-form TEXT (can contain `/articles/{slug}`, or `/` for homepage, or anything else)
- Only 13 distinct values of `source_page` across 329 clicks — clicks are concentrating on the popular article paths, good

## Recommended fix — read-time join (low risk)

Replace direct reads of `articles.affiliate_clicks` with a LEFT JOIN on demand.

```sql
SELECT
  a.slug,
  a.title,
  a.views,
  COUNT(ac.id) AS affiliate_clicks
FROM articles a
LEFT JOIN affiliate_clicks ac
       ON ac.source_page LIKE '%' || a.slug || '%'
GROUP BY a.id
ORDER BY affiliate_clicks DESC;
```

**Why this over a scheduled UPDATE job:**

| Dimension | Read-time join (a) | Scheduled UPDATE (b) |
|---|---|---|
| Complexity | 1 query change | New cron job + monitoring |
| Stale data risk | None — always live | High — job failure = silent staleness |
| Write lock risk | None | Requires UPDATE on hot table |
| Race conditions | None | Possible if clicks arrive mid-job |
| Rollback | Revert query | Requires undoing backfill |
| Performance (329 rows) | Instantly acceptable | N/A |
| Performance at 100K clicks | Sub-100ms with a simple index | Faster reads, but...) |

Read-time join is the simpler, safer choice at this scale. Add an index later if query latency crosses ~200ms:

```sql
CREATE INDEX idx_affiliate_clicks_source_page ON affiliate_clicks(source_page);
```

## One more subtle issue

`LIKE '%slug%'` is correct but matches too loosely — if one article's slug is a substring of another (`ai-seo-tools` vs `best-ai-seo-tools-2026`), double-counting happens. Two mitigations:

1. Use a stricter match: `ac.source_page = '/articles/' || a.slug` (requires source_page to always be the canonical path)
2. Or store `article_id` explicitly at click time — proper foreign key.

Option 2 is the right long-term fix. Option 1 is fine for backfill/reads today.

## Changes needed to deploy the fix

1. **Update the aggregation query** wherever `articles.affiliate_clicks` is read today. Grep for `articles.affiliate_clicks`, `a.affiliate_clicks`, and the `analytics_bot.py` analytics query specifically.
2. **Optional: drop the column** on the `articles` table to remove the footgun. Not required, just cosmetic.
3. **Optional: add an index** on `affiliate_clicks(source_page)` if analytics queries get slow.
4. **Future: add `article_id` FK** to `affiliate_clicks` so future clicks link cleanly. Requires capturing article ID at click time in `/track/click/` — which already knows `source_page`, just needs to look up `slug → id`.

## Where the analytics bot is affected

`analytics_bot.py` queries `articles` directly for stats. Its current daily summary shows `affiliate_clicks: 0` for every article — this is the same bug surfacing in the internal daily reports Kenneth sees.

## Quick one-liner diagnostic

```sql
-- Current broken state: clicks table has data, articles column empty
SELECT
  (SELECT COUNT(*) FROM affiliate_clicks) AS clicks_events,     -- 329
  (SELECT SUM(affiliate_clicks) FROM articles) AS articles_col; -- 0
```

When the fix is deployed, the aggregated join query should return per-article counts summing to exactly 329 (minus any click events whose `source_page` doesn't map to a known article — mostly homepage clicks, which are expected).
