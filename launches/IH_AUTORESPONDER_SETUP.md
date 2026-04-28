# Indie Hackers DM Autoresponder — Setup

The IH DM autoresponder is wired to handle inbound messages from the Pipeline Hunter post "I cancelled $487/mo of AI tools" without you having to babysit the inbox. It runs as three modules and one set of admin endpoints.

```
ih_dm_monitor.py   →  reads bosaibot@gmail.com IMAP, queues new IH DMs into ih_dms (every 5 min)
ih_dm_drafter.py   →  drafts replies via Claude (haiku-4-5) in your voice (every 5 min, +1 offset)
ih_dm_sender.py    →  sends approved replies via Playwright OR Telegram-tap fallback
main.py /api/ih-dm/*  →  approve / edit / ignore / list / stats endpoints
```

Status lifecycle: `pending → drafted → approved → sent` (or `ignored`).

## 1. Make sure IH email notifications hit bosaibot@gmail.com

1. Log in to indiehackers.com.
2. Settings → Email Notifications → enable "New messages" and "Replies to your posts".
3. Verify the account email is `bosaibot@gmail.com` (not `kenneth.bonnet20@gmail.com`).
4. Send yourself a test DM from a second account to confirm the email arrives.

The monitor recognises these subject patterns:
- `<sender> messaged you on Indie Hackers`
- `New message from <sender>`
- `Your post got a reply: <title>`
- `You have a new message`
- Anything from indiehackers.com containing "message", "reply", or "comment"

## 2. Capture the Playwright session (one-time, ~2 min)

This is the only step that needs your hands. Without this, the sender falls back to Telegram-tap (it pings you the thread URL + reply text and you paste it manually).

```bash
cd /Users/kennethbonnet/ai-tools-empire

# Install Playwright if not already there
pip install playwright
playwright install chromium

# Capture the session
python -m bots.ih_dm_sender --capture-session
```

A Chromium window opens at indiehackers.com/login. Log in, then come back to the terminal and press Enter. The script saves cookies to `~/.config/ih_session.json`. The bots auto-detect this file and switch to full Playwright auto-send.

To re-capture (after IH logs you out): re-run the same command.

## 3. Environment variables

Add to `.env` (defaults shown — only override if you want different behaviour):

```bash
IH_DM_AUTO_SEND_THRESHOLD=0.85    # Drafts >= this AND in safe intent set auto-send
IH_DM_AUTO_SEND_HOURLY_CAP=5      # Hard cap, regardless of confidence
IH_DM_AUTO_SEND_DAILY_CAP=20      # Hard cap per UTC day
```

Already required (already in `.env`):
- `SMTP_USER` / `SMTP_PASSWORD` (for IMAP read of bosaibot@gmail.com)
- `ANTHROPIC_API_KEY`
- `ADMIN_PASSWORD` (gates the `/api/ih-dm/*` endpoints)
- `CLAUDE_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (Telegram alerts via `tg()`)

## 4. Auto-send rules

A draft is auto-sent only if ALL of these are true:
1. `draft_confidence >= IH_DM_AUTO_SEND_THRESHOLD` (default 0.85)
2. `intent ∈ {send_template_pack, send_audit_offer, thank_and_qualify}` — the three "safe" outcomes
3. No banned phrases in the draft (delve, unleash, em-dashes, etc — voice rules)
4. Hourly + daily caps not exceeded

`free_top5` and `unclear` intents always wait for your tap, even at high confidence.

## 5. Reply-pattern map (the drafter's playbook)

| Their message looks like | Intent | Your reply points to |
|---|---|---|
| "what did you replace it with", "share the swap list" | `send_template_pack` | aitoolsempire.co/stack-audit-templates ($19) |
| "can you do mine", "I want a custom audit" | `send_audit_offer` | aitoolsempire.co/stack-audit ($99) |
| "this doesn't add up", "show proof", critical | `free_top5` | Free 5-cut DM (waits for you) |
| "nice post", "cool", vague | `thank_and_qualify` | Thank + ask what they're paying for |
| Other | `unclear` | Asks one clarifying question (waits for you) |

## 6. Where logs land

- IH monitor / drafter / sender: `logs/bots.log` (the same file as the rest of the 14-bot scheduler) under logger names `ih_dm_monitor`, `ih_dm_drafter`, `ih_dm_sender`.
- Telegram review messages: KennyClaude bot (chat 6194068092) — every drafted DM gets a Telegram card with approve/edit/ignore links.
- Per-DM state in SQLite: `data.db` table `ih_dms`. Inspect with `sqlite3 data.db "SELECT id, sender, status, draft_confidence FROM ih_dms ORDER BY id DESC LIMIT 20;"`.

## 7. Admin endpoints

All gated by `?pwd=$ADMIN_PASSWORD`.

```
GET  https://aitoolsempire.co/api/ih-dm/list?pwd=...
GET  https://aitoolsempire.co/api/ih-dm/approve/{id}?pwd=...      # also fires send
POST https://aitoolsempire.co/api/ih-dm/edit/{id}?pwd=...         # body: {"reply": "..."}
POST https://aitoolsempire.co/api/ih-dm/ignore/{id}?pwd=...
GET  https://aitoolsempire.co/api/ih-dm/stats?pwd=...
```

## 8. KILL SWITCH — if anything goes wrong

Single command that stops the whole IH autoresponder by raising the threshold above 1.0 (drafter still drafts but nothing auto-sends; you can still approve manually if you want):

```bash
launchctl unload ~/Library/LaunchAgents/com.aitoolsempire.bots.plist
# Then edit ~/.zshrc or .env to set:
#   IH_DM_AUTO_SEND_THRESHOLD=99
# And reload:
launchctl load ~/Library/LaunchAgents/com.aitoolsempire.bots.plist
```

To kill it harder (no monitor, no drafter at all): keep the unload command and don't reload. Server (`com.aitoolsempire.server`) keeps running so the admin endpoints stay accessible.

To resume: drop the `IH_DM_AUTO_SEND_THRESHOLD` override and reload `com.aitoolsempire.bots`.

## 9. Manual smoke test

```bash
cd /Users/kennethbonnet/ai-tools-empire

# 1. Run monitor once — should find any IH email and queue rows
python -m bots.ih_dm_monitor

# 2. Run drafter once — drafts every pending row, alerts Telegram
python -m bots.ih_dm_drafter

# 3. Inspect queue
sqlite3 data.db "SELECT id, sender, status, draft_confidence FROM ih_dms ORDER BY id DESC LIMIT 10;"

# 4. Send an approved one (or use the Telegram link)
python -m bots.ih_dm_sender --send 1
```
