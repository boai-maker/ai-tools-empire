# Traffic Drop — Part 2: Referrer & Technical Audit

Follow-up to the Part 1 report. No GSC data (still need OAuth creds).
This pass focuses on local evidence only.

## Referrer breakdown (Apr 15–21)

| Day | (direct) | internal | google | chatgpt | other | Total |
|---|---|---|---|---|---|---|
| Apr 15 | **1,096** | 53 | 1 | 2 | 2 | 1,154 |
| Apr 16 | 1,058 | 9 | 3 | — | 1 | 1,071 |
| Apr 17 | 1,002 | 30 | 4 | 1 | 4 | 1,041 |
| Apr 18 | 957 | 86 | 1 | 2 | 3 | 1,049 |
| **Apr 19** | **318** | 31 | 2 | 2 | — | **353** |
| Apr 20 | 251 | 14 | 1 | — | — | 266 |
| Apr 21 | 412 | 37 | — | — | 1 | 450 |

### What this tells us
- **(direct) dropped 957 → 318 overnight** — that's a 67% cliff
- **internal ALSO dropped 86 → 31** (64% cliff on the same day) — people who WERE on the site also stopped clicking through to other pages
- **google referrer is useless** as a signal — 1-4/day consistently, because Google strips referrers on HTTPS→HTTPS transitions. The SEO traffic is hiding inside `(direct)`.
- **chatgpt** shows up consistently — confirms what we saw in click attribution. Users finding articles via ChatGPT citations. Low volume but sticky signal.

### Verdict
Site-wide event, not a single-page deindex. The fact that internal clicks dropped on the SAME DAY means even the users who DID land stopped browsing deeper. Patterns that match:
- Site was slow / broken on Apr 19 (no server errors logged but could be Cloudflare edge)
- Google algo update that pushed all articles ~1-2 positions lower simultaneously
- A core navigation element broke (header/menu) that stopped internal clickthrough

## `/newsletter` — confirmed bleeding traffic

HTTP 404 live. Pageview hits by day:

| Day | /newsletter hits |
|---|---|
| Apr 18 | 46 |
| Apr 19 | 24 |
| Apr 20 | 20 |
| Apr 21 | 25 |

**~25-46 visitors/day are hitting /newsletter and getting a 404.** This has been happening the whole time — it's not a new issue driving the Apr 19 drop, but it IS an ongoing leak worth fixing. Fix: add a redirect `/newsletter` → `/stack-audit` (better offer) or `/#newsletter` (the existing opt-in on homepage).

Referrer data for /newsletter hits shows blank — users typing the URL or old email links/internal site links pointing to the nonexistent route.

## Sitemap — HEALTHY (false alarm)

First look suggested only 1 URL. That was a grep artifact: the sitemap is emitted as one giant single-line XML without newlines, so `grep -c '<loc>'` returns 1. Full content contains **~80 URLs** including all published articles with correct `lastmod` values.

Verdict: sitemap is fine. Not the cause of the drop.

## robots.txt — CLEAN but with an oddity

```
# Content-Signal content/ai-input=yes
# Content-Signal content/search=yes
# Content-Signal content/ai-train=no
User-agent: *
Disallow:
Sitemap: https://aitoolsempire.co/sitemap.xml
```

Allows all crawlers. Content-Signal block is a 2026 proposal for controlling AI crawlers (OpenAI, Anthropic, etc.) — you're letting ChatGPT/Claude cite your content (`ai-input=yes`) but blocking them from training (`ai-train=no`). Reasonable choice. Google should still see everything.

## Top referrer buckets I suspect but can't confirm

The `(direct)` bucket of 1,000/day is mostly:
- Google organic (Google strips referrer)
- Bing (minor)
- Social media apps that strip referrer (Twitter mobile, Instagram)
- Direct type-ins (small)
- Scraper bots (?)

Without GSC I can't break this down. **Add GSC API credentials to `.env` to resolve this.** Setup guide:
1. Google Cloud Console → enable Search Console API
2. Create service account → download JSON key
3. Add service account email to your GSC property as "Owner"
4. Save JSON to `.env` as `GSC_SERVICE_ACCOUNT_JSON` (base64)

## Recommended actions

### Fix now (low cost)
1. **Add `/newsletter` redirect** — 5 min code change. Reclaim 25-46 visitors/day.
2. **Check Cloudflare edge analytics** for Apr 19 — cross-check whether the drop originated at edge or origin
3. **Manually test 10 article URLs** for HTTP 200 + `<meta name="robots">` absence

### Evidence still missing
- GSC impressions/clicks by page for Apr 15-21 (confirms/kills Hypothesis 1)
- Cloudflare edge requests vs origin requests around Apr 19

### Pattern watch
- Traffic partially recovered Apr 21 (266 → 450, +70% single day). If that trend continues, this may resolve organically. Monitor for 7 days.
