# AI Tools Empire — Project Instructions

## Owner & Identity
- **Operator:** Kenneth Bonnet
- **Primary email:** bosaibot@gmail.com (NEVER use kenneth.bonnet20@gmail.com — except for PayPal payouts)
- **Site:** https://aitoolsempire.co (Render free tier, auto-deploy on git push to main)
- **Local path:** /Users/kennethbonnet/ai-tools-empire
- **Stack:** FastAPI + SQLite (data.db) + Jinja2 + APScheduler + launchd

## Architecture
20 bots across 5 systems coordinated via:
1. **14-bot scheduler** (`com.aitoolsempire.bots`) — content, email, analytics, social
2. **Dominic** (`com.aitoolsempire.dominic`) — Twitter/social autopilot
3. **Kalshi v4.0** (`~/Desktop/telegram_bots/kalshi_auto.py`) — prediction market trading
4. **Wholesale CRM** (`http://localhost:5050`) — real estate deal pipeline
5. **FastAPI server** (`com.aitoolsempire.server`) — public website on port 8080

## Shared Standards (MANDATORY)
**Every bot must import from `bots.shared.standards`:**
```python
from bots.shared.standards import Status, log, tg, BotResult, safe_run, conservative_check
from bots.shared.crm_client import crm
```

### Status Vocabulary (single source of truth)
`new`, `queued`, `researching`, `processing`, `review`, `ready`, `blocked`, `sent`, `follow_up`, `completed`, `dead`, `hot`, `pass`, `under_contract`, `closed`

### Logging
- Use `log = get_logger("my_bot_name")` from standards
- Format: `HH:MM:SS | LEVEL | bot_name | message`
- Levels: INFO (start/done/result), WARNING (recoverable), ERROR (failed but isolated), EXCEPTION (with stack)

### Telegram (Kenny Claude bot — central hub)
- Token: `8620859605:AAFyqpnfFNj-Usgx0J1ZmxLyzQxw8T2s5Pk`
- Chat ID: `6194068092`
- ALL bots use `tg(message, level)` from standards. Do not hardcode tokens.
- Levels: `info`, `success`, `warning`, `error`, `trade`, `deal`, `money`

### Error Handling
- Wrap bot main functions with `@safe_run("bot_name")` decorator
- It catches all errors, logs them, alerts on Telegram, returns BotResult
- Never let one bot's exception crash the scheduler

### Bot Result (handoff format)
```python
return BotResult(
    bot_name="my_bot",
    success=True,
    received={"input": "..."},
    changed={"db_id": 42, "fields": ["status"]},
    produced={"new_record": "..."},
    next_bot="next_bot_name",
    next_action="match_buyers",
    uncertainties=["comp data sparse"],
)
```

## CRM Rules (Phase 7 — single system of record)
- **CRM URL:** http://localhost:5050
- **Always use** `from bots.shared.crm_client import crm`
- **Never** create properties without `crm.find_property(address)` first
- Use `crm.upsert_property(data)` — handles dedup automatically
- Log every material action via `crm.log_activity(...)`
- Create follow-ups via `crm.create_task(...)`
- Falls back to local queue if CRM is down (auto-retried)

## Conservative Decision Rules
**Wholesale RE:**
- 70% rule: `MAO = ARV × 0.70 - Rehab - Assignment Fee`
- Default assignment fee: $10K (was $20K)
- Min spread: $5K
- Reject fire/flood/condemned via `data/lead_filter.py`
- Check exists: `from data.lead_filter import check_lead`

**Kalshi:**
- Max 2 trades/day, $10 each
- Stop after 1 loss
- Min confidence: 0.70 (dynamic, can rise to 0.85)
- 8-component ensemble model

**Email outreach:**
- Rate limit: 3/hour per bot
- Never send without explicit approval flag
- Always log to `crm.log_activity` with type `outreach_drafted` or `outreach_sent`

## Automation Rules (Phase 8)
**Bots should run autonomously through:**
- ingestion, normalization, analysis, scoring, comping, CRM updates, buyer matching, outreach drafting, task creation

**Bots should STOP and alert via Telegram when:**
1. Missing critical data (no address, no price, no comps)
2. Legal/compliance uncertainty
3. External send/commit action (email, contract, payment)
4. Money risk decision (>$100)
5. CRM down for >5 minutes (work queues to fallback)

## Files to Know
- `bots/shared/standards.py` — shared status, log, tg, BotResult, safe_run
- `bots/shared/crm_client.py` — CRM operations (singleton: `crm`)
- `bots/shared/ai_client.py` — Claude API wrapper (model: `claude-sonnet-4-20250514`)
- `bots/shared/notifier.py` — legacy notify() — being phased out, use `tg()` instead
- `bots/run_bots.py` — APScheduler entry point for 14-bot system
- `~/Desktop/wholesale-re/crm/app.py` — Flask CRM server (port 5050)
- `~/Desktop/telegram_bots/kalshi_auto.py` — Kalshi v4.0 (independent)

## Hard Rules
- **Never** hardcode Telegram tokens in bot files (use `tg()` from standards)
- **Never** create duplicate CRM records (use `crm.upsert_property()`)
- **Never** fabricate data, comps, or test results — mark uncertain things clearly
- **Never** use deprecated Claude models — only `claude-sonnet-4-20250514` works
- **Never** push to git without testing the syntax first (`python3 -c "import py_compile..."`)
- **Always** restart launchd agents after editing bot files: `launchctl unload && launchctl load`

## Reload Pattern
```bash
# Restart 14-bot scheduler
launchctl unload ~/Library/LaunchAgents/com.aitoolsempire.bots.plist && \
launchctl load ~/Library/LaunchAgents/com.aitoolsempire.bots.plist
```

## Revenue Targets
- $100/day combined across: affiliate, Kalshi, Fiverr, wholesale RE
- Track in CRM dashboard at http://localhost:5050
- Weekly review every Monday via `/site-health` skill

## Wholesale Email Rules (HARD RULES)
- **NEVER send more than 1 email per property per 48 hours**
- **NEVER send duplicate emails in the same day — to anyone, for any reason**
- **Wait 48 hours minimum before re-sending or following up on ANY email**
- **If an email address is wrong/bounced, wait 48 hours before trying a corrected address**
- **Max 5 FOLLOW-UP emails per day. Initial first-contact emails have no daily cap.**
- **Always contact OWNER directly, not agent (exception: active MLS listings)**
- **Do NOT mention Proof of Funds in emails. If requested by seller/agent, Kenneth will handle manually.**
- **All offers must be 5-10K below asking price**
- **Track every email sent in CRM with timestamp — check before sending**
- **Follow-up cadence: Day 1 → Day 3 (48hr) → Day 7 → Day 14 → Day 30**
