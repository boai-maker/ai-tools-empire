# Phase 0 — Codebase Audit

Summary of the aitoolsempire.co codebase before making any changes.

## Routes (main.py — 28 total)

**Public (21):**
```
GET  /                                    GET  /how-we-test
GET  /tools                               GET  /free-ai-kit
GET  /articles                            POST /contact
GET  /articles/{slug}                     POST /subscribe
GET  /blog/{slug}                         GET  /go/{tool_key}
GET  /about                               POST /track/click/{tool_key}
GET  /privacy                             GET  /unsubscribe
GET  /disclaimer                          GET  /best-ai-{writing,seo,video,voice,productivity}-tools
GET  /contact                             GET  /sitemap.xml
GET  /services                            GET  /robots.txt
GET  /resume                              GET  /rss.xml
GET  /health
HEAD /
```

**Admin (7, password-protected via `ADMIN_PASSWORD` env):**
```
GET  /admin                               POST /admin/post-tweet
POST /admin/login                         POST /admin/save-affiliate-ids
POST /admin/generate-content              POST /admin/add-topic
POST /admin/send-welcomes                 POST /admin/export-youtube-scripts
POST /admin/send-newsletter               GET  /admin/service-summary
                                           GET  /admin/reddit-guide
```

## Tech snapshot

- **FastAPI 0.111**, **uvicorn[standard] 0.29**, **jinja2 3.1**
- **anthropic 0.28** (outdated — current is 0.40+, but irrelevant unless we need new API features)
- **moviepy 2.2+, numpy 1.26+, google-api-python-client 2.190+** — for YouTube bot rendering path
- SQLite via `aiosqlite` + raw `sqlite3`
- Twitter via **tweepy 4.14**, Reddit via `praw` (not in requirements — may be missing or installed system-wide)
- Email via **Resend** AND **SMTP** (both clients imported — unclear which is active)
- **No beehiiv SDK, no pandas, no scipy, no plausible/posthog client**

## Database — 16 tables, 4 matter for Priority 1-4

- **articles** — id, slug (UNIQUE), title, content, views, `affiliate_clicks` (always 0 — see attribution bug report)
- **affiliate_clicks** — id, tool_key, source_page TEXT, ip_hash, clicked_at. 329 rows.
- **page_views** — id, path, referrer, user_agent, ip_hash, viewed_at. Used for site analytics; has the Apr 19 traffic drop evidence.
- **subscribers** — 3 rows, all `welcome_sent=0` (no welcome email ever actually sent)

Other tables (not central to current priorities): content_queue, email_campaigns, sequence_queue, social_queue, dom_content, dom_history, dom_config, dom_crawl_log, dom_schedule, bot_state, bot_events.

## Affiliate config surfaces

- `config.AFFILIATE_IDS` — 40 keys. 14 have real IDs; 26 are empty strings.
- `affiliate/links.AFFILIATE_PROGRAMS` — 40 entries with display metadata (name, description, commission, rating, logo, badge, category, signup_url).
- `PENDING_PROGRAMS` dict exists but appears empty/unpopulated in the current excerpt.
- **No `is_active` flag on any program dict** — Priority 3's homepage rebalance requires adding this.

## Cookie / client-state infrastructure

None. Grep for `set_cookie`, `sessionStorage`, `localStorage` — zero hits. Admin auth is POST-body password check, not cookie-based. This matters for Priority 5 (A/B testing framework needs a `visitor_id` cookie) — infrastructure needs to be built from scratch.

## Deploy

- **Dockerfile:** Python 3.11-slim, port 8080, `uvicorn main:app`
- **render.yaml:** Oregon, free tier, auto-deploys from `main` branch
- **Cloudflared tunnel** → aitoolsempire.co (managed via launchd agent `com.aitoolsempire.tunnel`)

## What's in good shape

- Route coverage is complete — nothing obviously missing
- Admin surface exists and is password-gated
- Lead magnet file (`static/ai-tools-cheatsheet.html`) exists and is substantive
- RSS + sitemap + robots.txt are dynamic routes, not static files (correct)
- Health check endpoint works
- Separate `/go/{tool_key}` and `/track/click/{tool_key}` paths suggest thoughtful attribution design — just missing the rollup

## What needs attention before Priority 2-5 work starts

1. **Add `is_active: bool` to each entry in `AFFILIATE_PROGRAMS`** — required for homepage rebalance. Low risk; templates read via `.get('is_active', False)`.
2. **Add beehiiv client + env var (`BEEHIIV_API_KEY`, `BEEHIIV_PUBLICATION_ID`)** — required for Priority 2 & 6.
3. **Decide on a single email-send path**. Currently both Resend and SMTP are imported. Pick one for welcome + drip; keep the other (if any) for admin notifications only.
4. **Add `visitor_id` cookie middleware** — required before Priority 5 A/B framework can run.
5. **Add GSC OAuth credentials** — required to close out Hypothesis 1 in the traffic-drop report.

None of these are breaking changes. All can be added incrementally without disrupting the live site.
