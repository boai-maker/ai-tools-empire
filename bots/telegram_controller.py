"""
Telegram Controller — Kenny Claude command-and-control layer
═════════════════════════════════════════════════════════════
Persistent long-poll listener for the KennyClaude Telegram bot. Turns
Telegram into a live remote control panel for the AI Tools Empire stack.

Architecture
────────────
  Telegram API ──getUpdates(long-poll)──▶ poll_loop()
                                               │
                                               ▼
                                       handle_message()
                                               │
                            ┌──────────────────┼──────────────────┐
                            ▼                  ▼                  ▼
                       slash command      plain text         rate limit /
                       (COMMANDS)         (classifier)       admin gate
                            │                  │
                            └────────┬─────────┘
                                     ▼
                              _spawn_task() (thread)
                                     │
                                     ▼
                       agent / video / CRM / Claude

Health & monitoring
───────────────────
  • heartbeat_loop writes bots/state/telegram_heartbeat.json every 30s
  • LAST_ERROR / TASKS_DONE / TASKS_FAILED counters
  • exponential backoff on getUpdates failures
  • automatic Telegram alert on 5+ consecutive poll failures
  • /health command surfaces all of the above

Security
────────
  • TELEGRAM_ADMIN_IDS env var (comma-sep) gates admin commands
  • per-user rate limiter (RATE_LIMIT_PER_MIN)
  • token only ever read from bots.shared.standards (env-driven)
  • subprocess.run for launchctl uses absolute paths, no shell
  • no eval / no exec on user input

Run
───
  python3 bots/telegram_controller.py
  (or via launchd: com.aitoolsempire.telegram.plist — KeepAlive)
"""
import os
import sys
import time
import json
import html
import threading
import subprocess
import sqlite3
from collections import defaultdict, deque
from datetime import datetime
from typing import Callable, Dict, Optional, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import requests

from bots.shared.standards import (
    get_logger, tg, load_state, save_state, STATE_DIR, PROJECT_ROOT,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)

log = get_logger("telegram_controller")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
STATE_FILE = os.path.join(STATE_DIR, "telegram_controller.json")
HEARTBEAT_FILE = os.path.join(STATE_DIR, "telegram_heartbeat.json")
DB_PATH = os.path.join(PROJECT_ROOT, "data.db")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
POLL_TIMEOUT = 30  # long-poll seconds

# Admins: env var TELEGRAM_ADMIN_IDS (comma-separated). Defaults to the
# main chat ID from standards so Kenneth is always admin out of the box.
ADMIN_USER_IDS: set = set()
for uid in os.getenv("TELEGRAM_ADMIN_IDS", str(TELEGRAM_CHAT_ID)).split(","):
    uid = uid.strip()
    if uid:
        try:
            ADMIN_USER_IDS.add(int(uid))
        except ValueError:
            pass

RATE_LIMIT_PER_MIN = 30  # per user

# ─────────────────────────────────────────────────────────────────────────────
# Runtime metrics (in-memory; mirrored to heartbeat file)
# ─────────────────────────────────────────────────────────────────────────────
START_TIME = time.time()
TASKS_DONE = 0
TASKS_FAILED = 0
LAST_MESSAGE_AT: Optional[str] = None
LAST_ERROR: Optional[str] = None
ACTIVE_TASKS: Dict[str, Dict] = {}  # task_id -> {name, user, start}
POLL_OFFSET = 0


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter (per user, sliding 60s window)
# ─────────────────────────────────────────────────────────────────────────────
_rate_buckets: Dict[int, deque] = defaultdict(deque)


def _rate_limited(user_id: int) -> bool:
    now = time.time()
    bucket = _rate_buckets[user_id]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        return True
    bucket.append(now)
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Telegram API helpers
# ─────────────────────────────────────────────────────────────────────────────
def api(method: str, timeout: int = 60, **params) -> dict:
    """POST to Telegram bot API. Never raises."""
    global LAST_ERROR
    try:
        r = requests.post(f"{API_BASE}/{method}", json=params, timeout=timeout)
        return r.json()
    except Exception as e:
        LAST_ERROR = f"api({method}): {e}"
        log.warning(LAST_ERROR)
        return {"ok": False, "error": str(e)}


def send(chat_id: int, text: str, parse_mode: str = "HTML") -> bool:
    """Send a message. Auto-truncates to Telegram's 4096 char limit."""
    if not text:
        return False
    if len(text) > 4000:
        text = text[:3990] + "\n…(truncated)"
    res = api(
        "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
    return bool(res.get("ok"))


def typing(chat_id: int) -> None:
    api("sendChatAction", chat_id=chat_id, action="typing")


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat
# ─────────────────────────────────────────────────────────────────────────────
def write_heartbeat() -> None:
    save_state(HEARTBEAT_FILE, {
        "alive_at": datetime.utcnow().isoformat(),
        "uptime_sec": int(time.time() - START_TIME),
        "tasks_done": TASKS_DONE,
        "tasks_failed": TASKS_FAILED,
        "last_message_at": LAST_MESSAGE_AT,
        "active_tasks": list(ACTIVE_TASKS.keys()),
        "last_error": LAST_ERROR,
        "pid": os.getpid(),
    })


def heartbeat_loop() -> None:
    while True:
        try:
            write_heartbeat()
        except Exception as e:
            log.warning(f"heartbeat error: {e}")
        time.sleep(30)


# ─────────────────────────────────────────────────────────────────────────────
# Command registry
# ─────────────────────────────────────────────────────────────────────────────
COMMANDS: Dict[str, Dict] = {}


def command(name: str, help_text: str = "", admin_only: bool = False):
    def deco(fn):
        COMMANDS[name] = {"fn": fn, "help": help_text, "admin": admin_only}
        return fn
    return deco


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS


# ─────────────────────────────────────────────────────────────────────────────
# Task spawning (thread-per-task with metric updates)
# ─────────────────────────────────────────────────────────────────────────────
def _spawn_task(name: str, fn: Callable, user_id: int) -> str:
    task_id = f"{name}_{int(time.time() * 1000)}"

    def _wrap():
        global TASKS_DONE, TASKS_FAILED, LAST_ERROR
        ACTIVE_TASKS[task_id] = {
            "name": name, "user": user_id, "start": time.time(),
        }
        try:
            fn()
            TASKS_DONE += 1
        except Exception as e:
            TASKS_FAILED += 1
            LAST_ERROR = f"{name}: {e}"
            log.exception(f"task {name} failed")
            tg(
                f"<b>🚨 Task failed</b>\n<code>{name}</code>\n"
                f"{html.escape(str(e))[:300]}",
                level="error",
            )
        finally:
            ACTIVE_TASKS.pop(task_id, None)

    threading.Thread(target=_wrap, daemon=True, name=task_id).start()
    return task_id


# ─────────────────────────────────────────────────────────────────────────────
# Command implementations
# ─────────────────────────────────────────────────────────────────────────────
@command("start", "Welcome message")
def cmd_start(ctx):
    ctx["reply"](
        "<b>👋 Kenny Claude controller is online</b>\n\n"
        "I'm your remote command link to the AI Tools Empire stack.\n"
        "Send /help to see commands, or just type a normal message and I'll route it.\n\n"
        "Examples:\n"
        "• <code>/video ElevenLabs voice cloning</code>\n"
        "• <code>/run wholesale</code>\n"
        "• <code>/health</code>\n"
        "• <i>How many subscribers do I have?</i>"
    )


@command("help", "List all commands")
def cmd_help(ctx):
    lines = ["<b>📖 Commands</b>"]
    for name, meta in sorted(COMMANDS.items()):
        tag = " 🔒" if meta["admin"] else ""
        lines.append(f"/{name}{tag} — {meta['help']}")
    lines.append("")
    lines.append("🔒 = admin only. Plain messages are auto-routed.")
    ctx["reply"]("\n".join(lines))


@command("status", "Quick system status")
def cmd_status(ctx):
    up = int(time.time() - START_TIME)
    h, m = divmod(up // 60, 60)
    ctx["reply"](
        f"<b>📊 Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Bot:</b> ✅ online\n"
        f"<b>Uptime:</b> {h}h {m}m\n"
        f"<b>Tasks done:</b> {TASKS_DONE}\n"
        f"<b>Tasks failed:</b> {TASKS_FAILED}\n"
        f"<b>Active tasks:</b> {len(ACTIVE_TASKS)}\n"
        f"<b>Last msg:</b> {LAST_MESSAGE_AT or 'never'}"
    )


@command("health", "Full health report (services + uptime + errors)")
def cmd_health(ctx):
    services = {}

    # CRM
    try:
        from bots.shared.crm_client import crm
        services["CRM (5050)"] = "✅" if crm.is_healthy() else "🔴 down"
    except Exception:
        services["CRM (5050)"] = "⚠️ import"

    # YouTube
    try:
        from bots.video_engine import _get_youtube_service
        services["YouTube API"] = "✅" if _get_youtube_service() else "🔴"
    except Exception:
        services["YouTube API"] = "⚠️ import"

    # Anthropic
    services["Anthropic"] = "✅" if os.getenv("ANTHROPIC_API_KEY") else "🔴 no key"
    # Gmail IMAP
    services["Gmail IMAP"] = "✅" if os.getenv("SMTP_PASSWORD") else "🔴 no pass"
    # ElevenLabs (optional)
    services["ElevenLabs"] = "✅" if os.getenv("ELEVENLABS_API_KEY") else "⚠️ fallback"

    # launchd agents
    try:
        out = subprocess.check_output(
            ["launchctl", "list"], timeout=5,
        ).decode("utf-8", errors="replace")
        for label in [
            "com.aitoolsempire.bots",
            "com.aitoolsempire.dominic",
            "com.aitoolsempire.server",
            "com.aitoolsempire.telegram",
        ]:
            services[label] = "✅" if label in out else "🔴 not loaded"
    except Exception:
        pass

    services_block = "\n".join(f"  {k}: {v}" for k, v in services.items())
    up = int(time.time() - START_TIME)
    h, m = divmod(up // 60, 60)

    ctx["reply"](
        f"<b>🩺 Health Report</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Controller:</b> ✅ alive (PID {os.getpid()})\n"
        f"<b>Uptime:</b> {h}h {m}m\n"
        f"<b>Last msg processed:</b> {LAST_MESSAGE_AT or 'never'}\n"
        f"<b>Tasks done:</b> {TASKS_DONE}\n"
        f"<b>Tasks failed:</b> {TASKS_FAILED}\n"
        f"<b>Active tasks:</b> {len(ACTIVE_TASKS)}\n"
        f"<b>Poll offset:</b> {POLL_OFFSET}\n\n"
        f"<b>Services:</b>\n{services_block}\n\n"
        f"<b>Last error:</b> {(LAST_ERROR or 'none')[:200]}"
    )


@command("agents", "List registered agents")
def cmd_agents(ctx):
    agents = [
        ("video", "Video engine (Shorts + long-form)"),
        ("wholesale", "Wholesale RE deal monitor"),
        ("fiverr", "Fiverr message responder"),
        ("linkedin", "LinkedIn message monitor"),
        ("affiliate", "Affiliate Gmail approval monitor"),
        ("dominic", "Social autopilot (separate launchd)"),
        ("kalshi", "Kalshi prediction-market trader (separate)"),
    ]
    lines = ["<b>🤖 Registered agents</b>"]
    for short, desc in agents:
        lines.append(f"• <code>{short}</code> — {desc}")
    lines.append("")
    lines.append("Run with <code>/run &lt;name&gt;</code>")
    ctx["reply"]("\n".join(lines))


_RUN_HANDLERS = {
    "video": ("bots.video_engine", "run_video_engine"),
    "short": ("bots.video_engine", "run_video_engine"),
    "wholesale": ("bots.wholesale_monitor", "run_wholesale_monitor"),
    "fiverr": ("bots.fiverr_responder", "run_fiverr_responder"),
    "linkedin": ("bots.linkedin_monitor", "run_linkedin_monitor"),
    "affiliate": ("bots.affiliate_gmail_monitor", "run_affiliate_gmail_monitor"),
}


@command("run", "Run an agent: /run video|wholesale|fiverr|linkedin|affiliate", admin_only=True)
def cmd_run(ctx):
    state = load_state(STATE_FILE)
    if state.get("paused"):
        ctx["reply"]("⏸ Agents are paused. /resume first.")
        return
    args = ctx["args"]
    if not args:
        ctx["reply"](
            "Usage: <code>/run &lt;agent&gt;</code>\n"
            f"Available: {', '.join(_RUN_HANDLERS)}"
        )
        return
    name = args[0].lower()
    if name not in _RUN_HANDLERS:
        ctx["reply"](f"Unknown: {name}\nAvailable: {', '.join(_RUN_HANDLERS)}")
        return

    mod_name, fn_name = _RUN_HANDLERS[name]
    ctx["reply"](f"⏳ Running <b>{name}</b>...")

    def _go():
        import importlib
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, fn_name)
        result = fn()
        text = str(result.to_dict() if hasattr(result, "to_dict") else result)
        ctx["reply"](
            f"✅ <b>{name}</b> done\n<pre>{html.escape(text[:1500])}</pre>"
        )

    _spawn_task(f"run_{name}", _go, ctx["user_id"])


@command("video", "Produce a video: /video [format] [topic]")
def cmd_video(ctx):
    args = ctx["args"]
    # Check if first arg is a known format
    known_fmts = ["short", "listicle", "versus", "moneysaver", "pov", "demo", "long", "rotate"]
    fmt = "rotate"
    topic_parts = args
    if args and args[0].lower() in known_fmts:
        fmt = args[0].lower()
        topic_parts = args[1:]
    topic = " ".join(topic_parts).strip()

    ctx["reply"](
        f"🎬 Producing <b>{fmt}</b>{(' on ' + topic) if topic else ''}...\n"
        f"<i>~60-90 seconds for render + upload + tweet.</i>"
    )

    def _produce():
        from bots.video_engine import run_video_engine, VideoSpec, produce, FORMAT_PRESETS
        if topic and fmt in FORMAT_PRESETS:
            spec = VideoSpec(
                format_type=fmt,
                topic=topic,
                tool=topic.split()[0] if topic else "",
                angle=topic,
                pain="you've been doing this manually for too long",
            )
            result = produce(spec)
        else:
            result = run_video_engine(fmt)
        if result.success:
            url = (result.produced or {}).get("video_url", "(none)")
            script = (result.produced or {}).get("script") or {}
            hook = script.get("hook", "")
            ctx["reply"](
                f"✅ <b>Video published</b>\n"
                f"<b>Hook:</b> {html.escape(hook)}\n"
                f"🔗 {url}"
            )
        else:
            ctx["reply"](f"🚨 Video failed: {html.escape(str(result.error))}")

    _spawn_task("video", _produce, ctx["user_id"])


@command("draft", "Generate a draft: /draft [music|voice] [topic]")
def cmd_draft(ctx):
    args = ctx["args"]
    audio_mode = "music"
    if args and args[0].lower() in ("music", "voice"):
        audio_mode = args[0].lower()
        args = args[1:]
    topic = " ".join(args).strip() or None
    ctx["reply"](
        f"🎬 Generating draft ({audio_mode}){(' on ' + topic) if topic else ''}...\n"
        f"<i>~90 seconds. I'll send the mp4 when ready.</i>"
    )

    def _go():
        from bots.draft_video import generate_and_send_draft
        result = generate_and_send_draft(topic, audio_mode=audio_mode)
        if result.get("success"):
            ctx["reply"](
                f"✅ Draft sent above.\n"
                f"<b>{html.escape(result.get('title', ''))}</b>\n"
                f"Winner: {html.escape(result.get('winner', ''))}\n\n"
                f"Reply /approve to post, or send feedback."
            )
        else:
            ctx["reply"](f"🚨 Draft failed: {result.get('error', 'unknown')}")

    _spawn_task("draft", _go, ctx["user_id"])


@command("approve", "Upload the last draft to YouTube + tweet it", admin_only=True)
def cmd_approve(ctx):
    from bots.shared.standards import load_state, save_state
    draft_state_file = os.path.join(STATE_DIR, "draft_video.json")
    state = load_state(draft_state_file)
    draft_path = state.get("draft_path")
    script = state.get("script", {})

    if not draft_path or not os.path.exists(draft_path):
        ctx["reply"]("⚠️ No draft to approve. Use /draft first.")
        return
    if state.get("approved"):
        ctx["reply"]("⚠️ This draft was already approved and posted.")
        return

    ctx["reply"]("⏳ Uploading to YouTube + tweeting...")

    def _go():
        from bots.video_engine import (
            VideoSpec, VideoScript, upload_video, _build_metadata,
        )
        from bots.shared.distributor import distribute
        from dataclasses import asdict

        spec = VideoSpec(
            format_type="short",
            topic=script.get("title", "AI Comparison"),
            tool=script.get("winner", "AI"),
        )
        vs = VideoScript(
            hook=script.get("title", ""),
            value=[t.get("name", "") + ": " + t.get("response", "")
                   for t in script.get("tools", [])],
            cta="Try the winner at aitoolsempire.co",
        )

        upload = upload_video(draft_path, spec, vs)
        if upload.get("success"):
            state["approved"] = True
            state["youtube_url"] = upload["url"]
            save_state(draft_state_file, state)

            # Distribute (tweet + TikTok/IG export)
            try:
                distribute(
                    video_path=draft_path,
                    format_type="short",
                    hook=script.get("title", ""),
                    tool=script.get("winner", ""),
                    youtube_url=upload["url"],
                    script_dict=script,
                )
            except Exception as e:
                log.warning(f"Distribution failed: {e}")

            # Send TikTok-ready copy to Telegram for easy phone upload
            try:
                _send_tiktok_file(draft_path, script)
            except Exception as e:
                log.warning(f"TikTok file send failed: {e}")

            ctx["reply"](
                f"✅ <b>Posted!</b>\n"
                f"🔗 {upload['url']}\n"
                f"Tweet sent. TikTok file sent below — save and upload from your phone."
            )
        else:
            ctx["reply"]("🚨 YouTube upload failed. Draft saved — try /approve again.")

    _spawn_task("approve", _go, ctx["user_id"])


def _send_tiktok_file(video_path: str, script: dict) -> bool:
    """Send video + TikTok caption to Telegram so Kenneth can upload from phone."""
    import requests as req
    caption = (
        f"📲 <b>TikTok Upload Ready</b>\n\n"
        f"<b>Caption to paste:</b>\n"
        f"{script.get('title', '')} 🤯 "
        f"#ai #aitools #techtok #fyp #foryou "
        f"#artificialintelligence #tech #productivity #free"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    with open(video_path, "rb") as f:
        r = req.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption[:1024],
            "parse_mode": "HTML",
        }, files={"document": ("tiktok_upload.mp4", f, "video/mp4")}, timeout=120)
    return r.json().get("ok", False)


@command("tiktok", "Send latest video for TikTok upload from phone")
def cmd_tiktok(ctx):
    draft_state_file = os.path.join(STATE_DIR, "draft_video.json")
    state = load_state(draft_state_file)
    draft_path = state.get("draft_path")
    script = state.get("script", {})

    if not draft_path or not os.path.exists(draft_path):
        ctx["reply"]("⚠️ No video available. Use /draft first.")
        return

    ctx["reply"]("📲 Sending TikTok-ready file...")

    def _go():
        ok = _send_tiktok_file(draft_path, script)
        if ok:
            ctx["reply"]("✅ TikTok file sent above. Save it and upload from your TikTok app.")
        else:
            ctx["reply"]("🚨 Failed to send file.")

    _spawn_task("tiktok_send", _go, ctx["user_id"])


@command("surplus", "Surplus funds pipeline stats")
def cmd_surplus(ctx):
    try:
        from bots.surplus_funds.scraper import get_stats, DB_PATH
        stats = get_stats()
        ctx["reply"](
            f"<b>💰 Surplus Funds Pipeline</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>Total leads:</b> {stats['total_leads']}\n"
            f"<b>New:</b> {stats['new']}\n"
            f"<b>Contacted:</b> {stats['contacted']}\n"
            f"<b>Agreements signed:</b> {stats['signed']}\n"
            f"<b>Claims filed:</b> {stats['filed']}\n"
            f"<b>Paid:</b> {stats['paid']}\n"
            f"<b>Total value:</b> ${stats['total_surplus_value']:,.2f}\n\n"
            f"Dashboard: localhost:5050/surplus"
        )
    except Exception as e:
        ctx["reply"](f"⚠️ Surplus stats error: {html.escape(str(e))}")


@command("scrape", "Run surplus scraper now", admin_only=True)
def cmd_scrape(ctx):
    ctx["reply"]("⏳ Running surplus scraper across 44 counties...")

    def _go():
        from bots.surplus_funds.scraper import run_scraper, init_db
        init_db()
        result = run_scraper()
        ctx["reply"](
            f"✅ <b>Scrape complete</b>\n"
            f"Counties: {result['counties_scraped']}\n"
            f"Leads found: {result['leads_found']}\n"
            f"New added: {result['leads_added']}\n"
            f"Total value: ${result['stats']['total_surplus_value']:,.2f}"
        )

    _spawn_task("scrape", _go, ctx["user_id"])


@command("crm", "CRM stats")
def cmd_crm(ctx):
    try:
        from bots.shared.crm_client import crm
        if not crm.is_healthy():
            ctx["reply"]("🔴 CRM is down at localhost:5050")
            return
        stats = crm.get_stats() or {}
        ctx["reply"](
            f"<b>🏠 CRM Snapshot</b>\n"
            f"<pre>{html.escape(json.dumps(stats, indent=2)[:1500])}</pre>"
        )
    except Exception as e:
        ctx["reply"](f"⚠️ CRM error: {html.escape(str(e))}")


@command("leads", "Recent newsletter subscribers")
def cmd_leads(ctx):
    try:
        if not os.path.exists(DB_PATH):
            ctx["reply"](f"⚠️ data.db not found at {DB_PATH}")
            return
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM subscribers")
        total = c.fetchone()[0]
        c.execute(
            "SELECT email, created_at FROM subscribers "
            "ORDER BY created_at DESC LIMIT 10"
        )
        rows = c.fetchall()
        conn.close()
        lines = [f"<b>📬 Subscribers — {total} total</b>", "Recent 10:"]
        for email, ts in rows:
            lines.append(f"• {html.escape(email)} <i>({(ts or '')[:10]})</i>")
        ctx["reply"]("\n".join(lines))
    except Exception as e:
        ctx["reply"](f"⚠️ Leads query failed: {html.escape(str(e))}")


@command("logs", "Recent logs: /logs [bot_name] [n]")
def cmd_logs(ctx):
    args = ctx["args"]
    n = 30
    bot_name = None
    for a in args:
        if a.isdigit():
            n = min(int(a), 100)
        else:
            bot_name = a
    if not os.path.isdir(LOG_DIR):
        ctx["reply"]("No logs directory")
        return
    files = sorted(
        [f for f in os.listdir(LOG_DIR) if f.endswith((".log", ".txt"))]
    )
    if bot_name:
        files = [f for f in files if bot_name in f]
    if not files:
        ctx["reply"]("No log files found")
        return
    target = os.path.join(LOG_DIR, files[-1])
    try:
        with open(target, errors="replace") as f:
            lines = f.readlines()[-n:]
        body = "".join(lines)
        ctx["reply"](
            f"<b>📜 {os.path.basename(target)}</b> (last {len(lines)})\n"
            f"<pre>{html.escape(body[:3500])}</pre>"
        )
    except Exception as e:
        ctx["reply"](f"⚠️ {html.escape(str(e))}")


_PLIST_MAP = {
    "bots": "com.aitoolsempire.bots",
    "dominic": "com.aitoolsempire.dominic",
    "server": "com.aitoolsempire.server",
    "tunnel": "com.aitoolsempire.tunnel",
    "telegram": "com.aitoolsempire.telegram",
}


@command("restart", "Restart launchd agent: /restart bots|dominic|server|telegram", admin_only=True)
def cmd_restart(ctx):
    args = ctx["args"]
    if not args:
        ctx["reply"](
            "Usage: <code>/restart &lt;name&gt;</code>\n"
            f"Available: {', '.join(_PLIST_MAP)}"
        )
        return
    name = args[0].lower()
    if name not in _PLIST_MAP:
        ctx["reply"](f"Unknown: {name}")
        return
    label = _PLIST_MAP[name]
    plist = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
    if not os.path.exists(plist):
        ctx["reply"](f"⚠️ {plist} not found")
        return
    try:
        subprocess.run(
            ["/bin/launchctl", "unload", plist],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["/bin/launchctl", "load", plist],
            capture_output=True, timeout=10,
        )
        ctx["reply"](f"✅ Restarted <code>{label}</code>")
    except Exception as e:
        ctx["reply"](f"🚨 Restart failed: {html.escape(str(e))}")


@command("pause", "Pause /run dispatch", admin_only=True)
def cmd_pause(ctx):
    state = load_state(STATE_FILE)
    state["paused"] = True
    save_state(STATE_FILE, state)
    ctx["reply"]("⏸ /run is paused. (Scheduled launchd jobs still run.)")


@command("resume", "Resume /run dispatch", admin_only=True)
def cmd_resume(ctx):
    state = load_state(STATE_FILE)
    state["paused"] = False
    save_state(STATE_FILE, state)
    ctx["reply"]("▶️ /run is enabled.")


# ─────────────────────────────────────────────────────────────────────────────
# Plain-text classifier + router
# ─────────────────────────────────────────────────────────────────────────────
def classify_intent(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["video", "youtube", "short", "render", "narration"]):
        return "video"
    if any(w in t for w in ["lead", "subscriber", "newsletter", "signup"]):
        return "leads"
    if any(w in t for w in ["wholesale", "deal", "property", "house", "comp", "arv"]):
        return "wholesale"
    if any(w in t for w in ["fiverr"]):
        return "fiverr"
    if any(w in t for w in ["linkedin"]):
        return "linkedin"
    if any(w in t for w in ["crm"]):
        return "crm"
    if any(w in t for w in ["health", "alive", "uptime"]):
        return "health"
    if any(w in t for w in ["status"]):
        return "status"
    if any(w in t for w in ["log", "logs"]):
        return "logs"
    return "general"


def route_plain_text(ctx) -> None:
    text = ctx["text"].strip()
    intent = classify_intent(text)
    log.info(f"intent={intent} text={text[:80]}")

    # Map intent → command handler
    quick_map = {
        "video": cmd_video,
        "leads": cmd_leads,
        "crm": cmd_crm,
        "health": cmd_health,
        "status": cmd_status,
        "logs": cmd_logs,
    }
    if intent in quick_map:
        # Strip the trigger word so /video can take topic args
        if intent == "video":
            ctx["args"] = [w for w in text.split() if w.lower() not in
                           ("video", "youtube", "short", "make", "produce", "a")]
        quick_map[intent](ctx)
        return

    if intent == "wholesale":
        if not is_admin(ctx["user_id"]):
            ctx["reply"]("🔒 Wholesale ops are admin only.")
            return
        ctx["reply"]("⏳ Running wholesale monitor...")

        def _w():
            from bots.wholesale_monitor import run_wholesale_monitor
            r = run_wholesale_monitor()
            text_out = str(r.to_dict() if hasattr(r, "to_dict") else r)
            ctx["reply"](
                f"✅ wholesale done\n<pre>{html.escape(text_out[:1200])}</pre>"
            )

        _spawn_task("wholesale", _w, ctx["user_id"])
        return

    if intent in ("fiverr", "linkedin"):
        if not is_admin(ctx["user_id"]):
            ctx["reply"]("🔒 Outreach ops are admin only.")
            return
        target = intent
        ctx["reply"](f"⏳ Running {target} monitor...")

        def _x():
            mod_name = f"bots.{target}_responder" if target == "fiverr" \
                else f"bots.linkedin_monitor"
            fn_name = f"run_{target}_responder" if target == "fiverr" \
                else "run_linkedin_monitor"
            import importlib
            r = getattr(importlib.import_module(mod_name), fn_name)()
            text_out = str(r.to_dict() if hasattr(r, "to_dict") else r)
            ctx["reply"](
                f"✅ {target} done\n<pre>{html.escape(text_out[:1200])}</pre>"
            )

        _spawn_task(target, _x, ctx["user_id"])
        return

    # Fallback: general assistant via Claude
    ctx["reply"]("🤔 Thinking...")

    def _think():
        from bots.shared.ai_client import ask_claude
        sys_prompt = (
            "You are Kenny Claude, the embedded ops assistant for Kenneth's "
            "AI Tools Empire stack (FastAPI site, 14-bot scheduler, Dominic "
            "social autopilot, video engine, Wholesale RE CRM, Kalshi trader). "
            "Be concise (under 200 words), action-oriented, and suggest the "
            "exact slash command when the user wants to trigger something. "
            "Available commands: /status /health /agents /run /video /crm "
            "/leads /logs /restart /pause /resume."
        )
        answer = ask_claude(text, system=sys_prompt, max_tokens=600)
        ctx["reply"](html.escape(answer or "(no response from Claude)"))

    _spawn_task("think", _think, ctx["user_id"])


# ─────────────────────────────────────────────────────────────────────────────
# Message handler
# ─────────────────────────────────────────────────────────────────────────────
def handle_message(msg: dict) -> None:
    global LAST_MESSAGE_AT
    LAST_MESSAGE_AT = datetime.utcnow().isoformat()

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    user = msg.get("from") or {}
    user_id = user.get("id", 0)
    text = msg.get("text") or msg.get("caption") or ""
    if not text or not chat_id:
        return

    if _rate_limited(user_id):
        send(chat_id, "⚠️ Rate limit (30/min). Slow down.")
        return

    log.info(f"msg from {user_id}: {text[:80]}")

    def reply(text_out: str) -> None:
        send(chat_id, text_out)

    ctx = {
        "chat_id": chat_id,
        "user_id": user_id,
        "text": text,
        "args": [],
        "reply": reply,
        "is_admin": is_admin(user_id),
    }

    typing(chat_id)

    # Slash command branch
    if text.startswith("/"):
        parts = text[1:].split()
        if not parts:
            reply("Empty command. Try /help")
            return
        cmd = parts[0].split("@")[0].lower()
        ctx["args"] = parts[1:]
        meta = COMMANDS.get(cmd)
        if not meta:
            reply(f"Unknown command: /{cmd}\nTry /help")
            return
        if meta["admin"] and not ctx["is_admin"]:
            reply("🔒 Admin only")
            return
        try:
            meta["fn"](ctx)
        except Exception as e:
            log.exception(f"command /{cmd} crashed")
            reply(
                f"🚨 /{cmd} crashed\n"
                f"<code>{html.escape(str(e))[:300]}</code>"
            )
        return

    # Plain text branch
    try:
        route_plain_text(ctx)
    except Exception as e:
        log.exception("route_plain_text crashed")
        reply(f"🚨 Routing crashed: {html.escape(str(e))[:300]}")


# ─────────────────────────────────────────────────────────────────────────────
# Main poll loop
# ─────────────────────────────────────────────────────────────────────────────
def poll_loop() -> None:
    global POLL_OFFSET, LAST_ERROR

    # Resume offset from last shutdown
    state = load_state(STATE_FILE)
    POLL_OFFSET = state.get("offset", 0)

    # Make sure no webhook is hijacking updates
    api("deleteWebhook", drop_pending_updates=False)

    log.info(
        f"Polling start (offset={POLL_OFFSET}, "
        f"admins={sorted(ADMIN_USER_IDS)})"
    )
    tg(
        f"<b>🤖 Kenny Claude controller online</b>\n"
        f"PID {os.getpid()} — send /help",
        level="success",
    )

    fail_streak = 0
    while True:
        try:
            res = api(
                "getUpdates",
                offset=POLL_OFFSET,
                timeout=POLL_TIMEOUT,
                allowed_updates=["message"],
            )
            if not res.get("ok"):
                fail_streak += 1
                LAST_ERROR = f"getUpdates not ok: {str(res)[:200]}"
                log.warning(LAST_ERROR)
                if fail_streak >= 5:
                    tg(
                        f"<b>⚠️ Telegram poll failing</b>\n"
                        f"{html.escape(str(res))[:300]}",
                        level="error",
                    )
                    fail_streak = 0
                time.sleep(min(2 ** min(fail_streak, 6), 60))
                continue

            fail_streak = 0
            updates = res.get("result", [])
            for update in updates:
                POLL_OFFSET = update["update_id"] + 1
                msg = update.get("message")
                if msg:
                    try:
                        handle_message(msg)
                    except Exception as e:
                        log.exception(f"handle_message: {e}")
                        LAST_ERROR = f"handle_message: {e}"

            if updates:
                state = load_state(STATE_FILE)
                state["offset"] = POLL_OFFSET
                state["last_update_at"] = datetime.utcnow().isoformat()
                save_state(STATE_FILE, state)

        except KeyboardInterrupt:
            log.info("KeyboardInterrupt — exiting")
            break
        except Exception as e:
            fail_streak += 1
            LAST_ERROR = f"poll loop: {e}"
            log.exception(LAST_ERROR)
            time.sleep(min(2 ** min(fail_streak, 6), 60))


def main():
    log.info(
        f"Telegram controller starting. "
        f"Admins: {sorted(ADMIN_USER_IDS)} | DB: {DB_PATH}"
    )
    threading.Thread(
        target=heartbeat_loop, daemon=True, name="heartbeat"
    ).start()
    poll_loop()


if __name__ == "__main__":
    main()
