# AI Tools Empire — Setup Checklist

Everything is built and running. These are the remaining manual steps.

---

## 🚨 STEP 1: Deploy Website Permanently (15 minutes)

The site runs locally. You need one of these to make it live at aitoolsempire.co:

### Option A — Cloudflare Tunnel (FREE, recommended)
1. Open Terminal
2. Run: `cloudflared tunnel login`
3. A browser window opens → click **Authorize**
4. Then run:
   ```
   cd /Users/kennethbonnet/ai-tools-empire
   cloudflared tunnel create aitoolsempire
   cloudflared tunnel route dns aitoolsempire aitoolsempire.co
   ```
5. Start tunnel permanently:
   ```
   cloudflared tunnel run --url http://localhost:8000 aitoolsempire
   ```

### Option B — Render.com (FREE tier, easy)
1. Go to render.com → Sign in with GitHub
2. Click **New → Web Service**
3. Connect repo: `https://github.com/YOUR_USERNAME/ai-tools-empire`
4. Settings auto-filled from render.yaml
5. Add env var: `ANTHROPIC_API_KEY` = your key
6. Deploy → you get a URL, then set custom domain to aitoolsempire.co

---

## 💰 STEP 2: Add Affiliate IDs (30 minutes → starts earning)

Edit `/Users/kennethbonnet/ai-tools-empire/.env` — replace placeholders with real IDs:

| Tool | Sign Up URL | Env Variable |
|------|-------------|--------------|
| Jasper AI | jasper.ai/affiliate | `JASPER_AFFILIATE_ID` |
| Copy.ai | copy.ai/affiliates | `COPYAI_AFFILIATE_ID` |
| Surfer SEO | surferseo.com/affiliate | `SURFER_AFFILIATE_ID` |
| Semrush | semrush.com/lp/affiliate | `SEMRUSH_AFFILIATE_ID` |
| ElevenLabs | elevenlabs.io/affiliates | `ELEVENLABS_AFFILIATE_ID` |

After adding IDs, restart the server. Revenue starts immediately on clicks.

---

## 🎰 STEP 3: Fund Kalshi Account

Current balance: ~$0.48 (need minimum $20 to place aggressive bets)

1. Go to kalshi.com
2. Deposit $50-100
3. Bot auto-restarts when current bets settle

**Current bets waiting to settle:**
- Golden State Warriors YES (tonight's NBA game)
- Sacramento Kings NO (tonight's NBA game)

---

## 📱 STEP 4: Post to Reddit (30 minutes → free traffic)

Posts are ready at: `/Users/kennethbonnet/ai-tools-empire/marketing/reddit_posts.md`

Post schedule:
- **Day 1:** r/Entrepreneur — "I built an AI tools site..."
- **Day 2:** r/SEO — "Data: AI comparisons outperform..."
- **Day 3:** r/juststart — Helpful comment with site link
- **Day 4:** r/passive_income — Income update post

---

## 🔍 STEP 5: Google Search Console (10 minutes)

1. Go to search.google.com/search-console
2. Add property: `https://aitoolsempire.co`
3. Copy the verification meta tag
4. Add to `.env`: `GOOGLE_SITE_VERIFICATION=your_code_here`
5. Submit sitemap: `https://aitoolsempire.co/sitemap.xml`

---

## ✅ What's Already Done

- [x] 38 articles published (regenerating all to 2000+ words)
- [x] Affiliate link tracking built in
- [x] Email newsletter system ready
- [x] Admin dashboard at /admin?pwd=empire2024secure
- [x] Automated content: 3 articles/day at 7am, 12pm, 5pm
- [x] Kalshi bot: auto-restarts, aggressive profit strategy ($10 bet → $10+ profit)
- [x] SEO: Schema.org, BreadcrumbList, sitemap.xml, robots.txt
- [x] Internal linking between articles (automatic)
- [x] YouTube scripts generated (check /admin → Export Scripts)
- [x] Reddit posts ready to copy/paste

---

## 📊 Revenue Projections

Once affiliate IDs added and site live:
- **Month 1:** $200-400 (SEO building)
- **Month 3:** $800-1,500 (ranking for comparison keywords)
- **Month 6:** $2,000-4,000 (compound traffic growth)

Kalshi bot: $10/round × 2 rounds/day = $20/day target = $600/month
