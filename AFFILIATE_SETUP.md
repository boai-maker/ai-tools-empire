# 💰 Affiliate Program Setup Guide

Sign up for each program below, get your affiliate ID, and add it to your .env file.

## Step 1: Sign Up for Programs

| Tool | Signup Link | Commission | Priority |
|------|-------------|------------|----------|
| Jasper AI | https://www.jasper.ai/affiliates | 30% recurring | ⭐⭐⭐ HIGH |
| Copy.ai | https://www.copy.ai/affiliates | 45% recurring | ⭐⭐⭐ HIGH |
| Writesonic | https://writesonic.com/affiliates | 30% recurring | ⭐⭐⭐ HIGH |
| Surfer SEO | https://surferseo.com/affiliate | 25% recurring | ⭐⭐⭐ HIGH |
| Semrush | https://www.semrush.com/news/affiliates/ | $200/sale | ⭐⭐⭐ HIGH |
| ElevenLabs | https://elevenlabs.io/affiliates | 22% recurring | ⭐⭐ MED |
| Murf AI | https://murf.ai/affiliates | 30% recurring | ⭐⭐ MED |
| Descript | https://www.descript.com/affiliates | 15% recurring | ⭐⭐ MED |
| InVideo | https://invideo.io/affiliates | 50% first payment | ⭐⭐ MED |
| Pictory | https://pictory.ai/affiliates | 20% recurring | ⭐ LOW |
| Fireflies | https://fireflies.ai/affiliate | 20% recurring | ⭐ LOW |

## Step 2: Add to .env File

After getting your IDs, add them to /Users/kennethbonnet/ai-tools-empire/.env:

```
JASPER_AFFILIATE_ID=your_actual_id_here
COPYAI_AFFILIATE_ID=your_actual_id_here
WRITESONIC_AFFILIATE_ID=your_actual_id_here
SURFER_AFFILIATE_ID=your_actual_id_here
SEMRUSH_AFFILIATE_ID=your_actual_id_here
ELEVENLABS_AFFILIATE_ID=your_actual_id_here
MURF_AFFILIATE_ID=your_actual_id_here
DESCRIPT_AFFILIATE_ID=your_actual_id_here
INVIDEO_AFFILIATE_ID=your_actual_id_here
```

## Step 3: Restart the Server

```bash
cd /Users/kennethbonnet/ai-tools-empire
pkill -f "uvicorn main:app"
source venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > logs/server.log 2>&1 &
```

## Revenue Projections

With 39 articles and growing traffic:
- Month 1: $50–$200 (traffic building)
- Month 3: $300–$600 (SEO gains)
- Month 6: $600–$1,200 (compounding content)
- Month 12: $1,000–$3,000+ (authority established)

## Priority Actions This Week

1. Sign up for Jasper + Copy.ai + Surfer (highest commission)
2. Add affiliate IDs to .env
3. Add your ANTHROPIC_API_KEY to .env for auto-article generation
4. Post 2-3 articles to relevant Reddit communities (r/ContentMarketing, r/SEO, r/Entrepreneur)
5. Share on LinkedIn with "AI Tools Review" angle
