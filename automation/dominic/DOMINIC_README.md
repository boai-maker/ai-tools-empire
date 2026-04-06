# Dominic — Autonomous Social Media Bot
## AI Tools Empire

Dominic is a fully autonomous social media bot that crawls aitoolsempire.co, generates tweet and YouTube content using Claude AI, schedules posts, publishes to Twitter and YouTube, and sends you Telegram notifications — all on autopilot.

---

## Architecture Overview

```
run.py (APScheduler entry point)
  └─ brain.py (Orchestrator)
       ├─ crawler.py       — Crawls aitoolsempire.co for new articles
       ├─ idea_engine.py   — Extracts content ideas using Claude AI
       ├─ tweet_gen.py     — Generates tweets using Claude AI
       ├─ youtube_gen.py   — Generates YouTube concepts and scripts
       ├─ compliance.py    — Scores content, deduplicates, validates
       ├─ planner.py       — Manages content calendar and scheduling
       ├─ publisher.py     — Posts to Twitter and YouTube with retry
       ├─ analytics.py     — Tracks engagement and generates reports
       ├─ telegram_notifier.py — Sends Telegram alerts and reports
       ├─ admin.py         — Control interface (CLI + Telegram commands)
       ├─ db.py            — All database operations (dom_* tables)
       ├─ config.py        — Configuration from environment variables
       └─ logger.py        — Rotating file logger
```

**Data flow:**
1. Every morning: crawl site for new articles
2. Use Claude to extract content ideas from articles + evergreen topics
3. Generate tweets and YouTube concepts for each idea
4. Score content for quality, uniqueness, and relevance
5. Schedule high-confidence content into posting slots
6. At posting times: publish to Twitter/YouTube
7. Track engagement, send Telegram reports

---

## Setup

### 1. Install dependencies

```bash
cd /Users/kennethbonnet/ai-tools-empire
pip install -r requirements_dominic.txt
```

### 2. Configure environment variables

All required variables are in your `.env` file. Dominic-specific vars:

```env
DOMINIC_TELEGRAM_TOKEN=your_telegram_bot_token
DOMINIC_TELEGRAM_CHAT_ID=your_telegram_chat_id
DOMINIC_MODE=autonomous
DOMINIC_PAUSED=false
DOMINIC_TIMEZONE=America/New_York
DOMINIC_CONFIDENCE_THRESHOLD=0.70
```

The following are already in your `.env` and Dominic uses them automatically:
- `ANTHROPIC_API_KEY` — for Claude AI
- `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_SECRET`
- `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
- `SITE_URL` — https://aitoolsempire.co

### 3. Set up Telegram Bot

**Get your bot token:**
1. Open Telegram and message `@BotFather`
2. Send `/newbot`
3. Follow prompts — give it a name like "Dominic AI Tools"
4. Copy the token (looks like `1234567890:ABCdef...`)
5. Set `DOMINIC_TELEGRAM_TOKEN=<your_token>` in `.env`

**Get your chat ID:**
1. Message your new bot in Telegram
2. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":XXXXXXXXX}` — that's your chat ID
4. Set `DOMINIC_TELEGRAM_CHAT_ID=<your_chat_id>` in `.env`

### 4. Initialize the database

```bash
python -c "from automation.dominic.db import init_dominic_db; init_dominic_db(); print('DB ready')"
```

### 5. Test the setup

```bash
# Check status
python -m automation.dominic.run --status

# Run one full cycle to verify everything works
python -m automation.dominic.run --once

# Test crawl
python -m automation.dominic.run --crawl
```

### 6. Start Dominic

```bash
python -m automation.dominic.run
```

For production, run with a process manager like `supervisor` or `systemd`:

```bash
# With nohup
nohup python -m automation.dominic.run > logs/dominic_run.log 2>&1 &

# Check it's running
ps aux | grep dominic
```

---

## Posting Schedule

All times are Eastern (America/New_York).

| Time | Platform | Frequency |
|------|----------|-----------|
| 8:00 AM | System | Morning routine (crawl, plan, briefing) |
| 9:00 AM | Twitter | Daily |
| 12:00 PM | YouTube | Every 2 days |
| 6:00 PM | Twitter | Daily |
| 8:00 PM | System | Evening routine (analytics, summary) |
| Monday 9 AM | System | Weekly report and plan |
| Every 4 hours | System | Crawl check for new articles |

---

## Operating Modes

### Autonomous Mode (`DOMINIC_MODE=autonomous`)
Dominic generates, schedules, and posts automatically without any human review. You receive Telegram notifications after each post. Best when you trust the content quality (confidence threshold >= 0.70 filters out weak content).

### Approval Mode (`DOMINIC_MODE=approval`)
Dominic generates content and sends drafts to Telegram for your review before posting. You approve or reject each piece with `/approve_<id>` or `/reject_<id>`. Best when starting out or when you want full control.

---

## Telegram Commands

Send these to your Dominic bot:

| Command | Description |
|---------|-------------|
| `/pause` | Pause all posting immediately |
| `/resume` | Resume posting |
| `/status` | Full system status report |
| `/queue` | Content queue counts |
| `/mode autonomous` | Switch to autonomous mode |
| `/mode approval` | Switch to approval mode |
| `/approve_<id>` | Approve content #ID for posting |
| `/reject_<id>` | Reject content #ID |
| `/force_<id>` | Force-post content #ID immediately |
| `/reset_failed` | Reset failed posts back to queued |
| `/logs` | Show last 20 log lines |
| `/help` | Show all commands |

---

## CLI Commands

From the project root:

```bash
# Start scheduler
python -m automation.dominic.run

# Run one full cycle (crawl → generate → schedule → publish)
python -m automation.dominic.run --once

# Crawl site for new articles
python -m automation.dominic.run --crawl

# Print status
python -m automation.dominic.run --status

# Run morning routine now
python -m automation.dominic.run --morning

# Run posting routine now
python -m automation.dominic.run --posting

# Admin CLI
python -m automation.dominic.admin pause
python -m automation.dominic.admin resume
python -m automation.dominic.admin status
python -m automation.dominic.admin approve <content_id>
python -m automation.dominic.admin reject <content_id>
python -m automation.dominic.admin force <content_id>
python -m automation.dominic.admin logs
python -m automation.dominic.admin reset_failed
```

---

## Database Tables

Dominic adds these tables to your existing `data.db`:

- `dom_content` — All generated content (drafts, queued, published)
- `dom_history` — Published post history with engagement metrics
- `dom_config` — Runtime configuration and state
- `dom_crawl_log` — Website crawl history
- `dom_schedule` — Content calendar and posting schedule

---

## Logs

Logs are written to `logs/dominic.log` with rotation (10 MB, 5 backups).

```bash
# Watch logs in real-time
tail -f logs/dominic.log

# Last 50 lines
tail -n 50 logs/dominic.log
```

---

## Confidence Threshold

Set `DOMINIC_CONFIDENCE_THRESHOLD=0.70` (default). Content is scored 0.0–1.0 based on:
- Freshness (how recently created)
- Uniqueness (not similar to previously posted content)
- Relevance (AI tools keywords and topics)
- Quality (engagement signals, specific hooks)
- Platform compliance (length, hashtag count)

Only content scoring above the threshold gets scheduled and published.

Raise to `0.80` for stricter filtering. Lower to `0.60` for more volume.

---

## Troubleshooting

**Dominic isn't posting:**
1. Check if paused: `python -m automation.dominic.run --status`
2. Check queue: `python -m automation.dominic.admin queue`
3. Check logs: `tail -n 50 logs/dominic.log`
4. Verify Twitter credentials: check `.env` values are correct
5. Try force-posting: `python -m automation.dominic.admin force <id>`

**No content being generated:**
1. Check Anthropic API key is valid and has credits
2. Check confidence threshold isn't set too high
3. Run manually: `python -m automation.dominic.run --once`

**Telegram notifications not working:**
1. Verify bot token and chat ID in `.env`
2. Make sure you've messaged the bot at least once
3. Test: `python -c "from automation.dominic.telegram_notifier import notify_urgent; notify_urgent('Test from Dominic')"`

**Duplicate content being posted:**
1. Check `dom_history` table is being populated correctly
2. Verify `is_duplicate_content()` threshold in `compliance.py`
3. The default threshold of 0.85 should catch most duplicates

**APScheduler not installed:**
```bash
pip install apscheduler>=3.10.0
```

**BeautifulSoup not installed (crawler fails):**
```bash
pip install beautifulsoup4 lxml
```

---

## File Structure

```
automation/dominic/
├── __init__.py
├── admin.py           — Admin control (CLI + Telegram commands)
├── analytics.py       — Engagement tracking and reports
├── brain.py           — Main orchestrator
├── compliance.py      — Content scoring and validation
├── config.py          — Configuration dataclass
├── crawler.py         — Website scraper
├── db.py              — Database operations
├── idea_engine.py     — AI-powered idea extraction
├── logger.py          — Rotating file logger
├── planner.py         — Content calendar
├── publisher.py       — Post to Twitter/YouTube
├── run.py             — Entry point with APScheduler
├── telegram_notifier.py — Telegram notifications
├── tweet_gen.py       — Tweet generator
├── youtube_gen.py     — YouTube content generator
└── DOMINIC_README.md  — This file
```

---

Built for AI Tools Empire by Kenny. Powered by Claude AI.
