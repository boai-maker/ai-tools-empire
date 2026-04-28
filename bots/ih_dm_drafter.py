"""
Indie Hackers DM Drafter.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pulls `status='pending'` rows from ih_dms, asks Claude Haiku for a
short reply in Kenneth's voice, stores draft + confidence + intent,
then either:
  • auto-approves + sends (if confidence >= IH_DM_AUTO_SEND_THRESHOLD,
    intent is safe, and rate caps allow), OR
  • Telegrams Kenneth with approve/edit/ignore links.

Brand voice: dry, sharp, short. Banned phrases enforced.
"""
from __future__ import annotations
import os
import re
import sys
import json
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bots.shared.standards import get_logger, tg
from bots.shared.ai_client import ask_claude
from database.db import get_conn

log = get_logger("ih_dm_drafter")

AUTO_SEND_THRESHOLD = float(os.getenv("IH_DM_AUTO_SEND_THRESHOLD", "0.85"))
AUTO_SEND_HOURLY_CAP = int(os.getenv("IH_DM_AUTO_SEND_HOURLY_CAP", "5"))
AUTO_SEND_DAILY_CAP = int(os.getenv("IH_DM_AUTO_SEND_DAILY_CAP", "20"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SITE_URL = os.getenv("SITE_URL", "https://aitoolsempire.co")

SAFE_AUTO_INTENTS = {"send_template_pack", "send_audit_offer", "thank_and_qualify"}

BANNED_PHRASES = [
    "delve", "unleash", "game-changer", "game changer", "dive in",
    "unlock the power of", "in today's fast-paced", "revolutionize",
    "let's explore", "it's important to note", "in conclusion",
    "the power of", "seamlessly", "leverage", "empower",
    "cutting-edge", "at the end of the day",
]

SYSTEM_PROMPT = """You are drafting Indie Hackers DM replies as Kenneth Bonnet, founder of AI Tools Empire (aitoolsempire.co) and author of the Pipeline Hunter post "I cancelled $487/mo of AI tools".

Voice rules (HARD):
- Tone: dry, sharp, slightly self-deprecating. Practical. No corporate filler.
- Pronouns: second person ("you"). First person ("I cancelled X") only when it's proof.
- Sentences: short. 8 words beats 18.
- Length: 1 to 3 sentences max. Never longer.
- No em-dashes. Use commas or full stops.
- Never sound like a bot. Never sound salesy. Never use marketing-speak.

BANNED words/phrases (auto-reject if present):
delve, unleash, game-changer, dive in, unlock the power of, revolutionize, seamlessly, leverage, empower, cutting-edge, in today's fast-paced, let's explore, it's important to note, in conclusion, at the end of the day.

Reply patterns based on what they're asking:
1. They want the substitution map / template / "what did you replace it with" → point them to aitoolsempire.co/stack-audit-templates ($19, one-time).
2. They want a custom audit / "can you do mine" / done-for-you → aitoolsempire.co/stack-audit ($99).
3. They're skeptical or critical ("doesn't add up", "show proof", "this is BS") → acknowledge directly, offer to send the 5 most-impactful cuts free as a DM. Don't get defensive.
4. Vague / friendly ("nice post", "cool", "interesting") → thank them sincerely (one line) and ask what tools they're paying for now.
5. Anything else / unclear → ask one specific clarifying question.

Output STRICT JSON only. No prose. Schema:
{"reply": "<the reply text>", "confidence": <0.0 to 1.0>, "intent": "send_template_pack" | "send_audit_offer" | "free_top5" | "thank_and_qualify" | "unclear"}
"""


def has_banned_phrase(text: str) -> str | None:
    t = (text or "").lower()
    for p in BANNED_PHRASES:
        if p in t:
            return p
    if "—" in (text or ""):
        return "em-dash"
    return None


def parse_json_loose(raw: str) -> dict | None:
    if not raw:
        return None
    # Strip code fences if any
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())
    # Find first {...} block
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def call_claude_for_draft(message_text: str, sender: str) -> dict | None:
    user_prompt = (
        f"Sender's IH username: {sender}\n"
        f"Sender's message:\n\"\"\"\n{message_text or '(no body captured — assume vague friendly comment)'}\n\"\"\"\n\n"
        f"Draft a reply per the rules. Output JSON only."
    )
    raw = ask_claude(
        prompt=user_prompt,
        system=SYSTEM_PROMPT,
        max_tokens=400,
        model="claude-haiku-4-5",
    )
    if not raw:
        # Retry once with a known-good model in case haiku-4-5 isn't available
        log.warning("Empty response from haiku-4-5, retrying with sonnet-4")
        raw = ask_claude(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            max_tokens=400,
            model="claude-sonnet-4-20250514",
        )
    parsed = parse_json_loose(raw)
    if not parsed or "reply" not in parsed:
        log.warning(f"Could not parse draft JSON: {raw[:200]}")
        return None
    return parsed


def fetch_pending(limit: int = 25) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ih_dms WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_draft(dm_id: int, reply: str, confidence: float, intent: str, status: str = "drafted"):
    conn = get_conn()
    conn.execute("""
        UPDATE ih_dms
        SET draft_reply = ?, draft_confidence = ?, status = ?
        WHERE id = ?
    """, (reply, confidence, status, dm_id))
    # Stash intent in send_method temporarily (no dedicated column, keep schema as spec'd)
    # Actually use a separate update — add an "intent" via message_text won't do.
    # We'll piggyback intent in approved_at-adjacent? No — better to store it in
    # send_method only after send. Track intent in the row's send_method column with prefix
    # is wrong. Just keep intent in memory + Telegram message; auto-send needs it now.
    conn.commit()
    conn.close()


def auto_send_counts() -> tuple[int, int]:
    """Return (sent_last_hour, sent_today) using sent_at + send_method ~ 'auto*'."""
    conn = get_conn()
    now = datetime.utcnow()
    one_hour = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    today = now.strftime("%Y-%m-%d")
    hour_n = conn.execute(
        "SELECT COUNT(*) FROM ih_dms WHERE sent_at >= ? AND send_method LIKE 'auto%'",
        (one_hour,),
    ).fetchone()[0]
    day_n = conn.execute(
        "SELECT COUNT(*) FROM ih_dms WHERE DATE(sent_at) = ? AND send_method LIKE 'auto%'",
        (today,),
    ).fetchone()[0]
    conn.close()
    return hour_n, day_n


def telegram_review(dm: dict, draft: str, confidence: float, intent: str, above_threshold: bool):
    msg_preview = (dm.get("message_text") or "")[:200]
    above_str = "above" if above_threshold else "below"
    pwd_q = f"?pwd={ADMIN_PASSWORD}" if ADMIN_PASSWORD else ""
    text = (
        f"📨 IH DM from <b>{dm['sender']}</b>\n"
        f"Their message: \"{msg_preview}\"\n\n"
        f"Draft reply (confidence {confidence:.2f}, intent={intent}):\n"
        f"\"{draft}\"\n\n"
        f"Approve: {SITE_URL}/api/ih-dm/approve/{dm['id']}{pwd_q}\n"
        f"Edit: reply 'edit {dm['id']} &lt;new text&gt;'\n"
        f"Ignore: reply 'ignore {dm['id']}'\n"
        f"Auto-send threshold: {AUTO_SEND_THRESHOLD:.2f} — this draft is {above_str} threshold"
    )
    if dm.get("thread_url"):
        text += f"\nThread: {dm['thread_url']}"
    tg(text, level="info")


def attempt_auto_send(dm_id: int) -> bool:
    """Mark approved + invoke ih_dm_sender for this row. Returns True on send success."""
    conn = get_conn()
    conn.execute(
        "UPDATE ih_dms SET status='approved', approved_at=CURRENT_TIMESTAMP WHERE id=?",
        (dm_id,),
    )
    conn.commit()
    conn.close()
    try:
        from bots.ih_dm_sender import send_one
        result = send_one(dm_id, auto=True)
        return bool(result and result.get("sent"))
    except Exception as e:
        log.exception(f"auto-send failed for dm_id={dm_id}: {e}")
        return False


def run():
    log.info("=== IH DM Drafter ===")
    pending = fetch_pending()
    log.info(f"{len(pending)} pending DMs to draft")
    drafted = 0
    auto_sent = 0
    queued_for_review = 0

    hour_n, day_n = auto_send_counts()
    log.info(f"Auto-send budget: hour={hour_n}/{AUTO_SEND_HOURLY_CAP} day={day_n}/{AUTO_SEND_DAILY_CAP}")

    for dm in pending:
        msg_text = dm.get("message_text") or ""
        draft = call_claude_for_draft(msg_text, dm.get("sender") or "")
        if not draft:
            tg(f"⚠️ IH DM #{dm['id']} from {dm.get('sender')} — drafter failed, please draft manually.", "warning")
            continue

        reply = (draft.get("reply") or "").strip()
        confidence = float(draft.get("confidence") or 0.0)
        intent = (draft.get("intent") or "unclear").strip()

        # Voice safety check — banned phrases force a Telegram review even if confidence is high.
        banned = has_banned_phrase(reply)
        if banned:
            log.warning(f"DM #{dm['id']} draft contained banned phrase '{banned}' — forcing review")
            confidence = min(confidence, 0.5)

        save_draft(dm["id"], reply, confidence, intent, status="drafted")
        drafted += 1

        # Auto-send gate
        eligible = (
            confidence >= AUTO_SEND_THRESHOLD
            and intent in SAFE_AUTO_INTENTS
            and not banned
            and hour_n < AUTO_SEND_HOURLY_CAP
            and day_n < AUTO_SEND_DAILY_CAP
        )
        above_threshold = confidence >= AUTO_SEND_THRESHOLD

        if eligible:
            log.info(f"Auto-sending DM #{dm['id']} (conf={confidence:.2f} intent={intent})")
            ok = attempt_auto_send(dm["id"])
            if ok:
                auto_sent += 1
                hour_n += 1
                day_n += 1
                tg(
                    f"✅ Auto-replied to <b>{dm['sender']}</b> on IH (conf {confidence:.2f}, {intent})\n"
                    f"Sent: \"{reply}\"",
                    level="success",
                )
            else:
                # Fall through to Telegram-tap review
                telegram_review(dm, reply, confidence, intent, above_threshold)
                queued_for_review += 1
        else:
            telegram_review(dm, reply, confidence, intent, above_threshold)
            queued_for_review += 1

    log.info(f"Drafted {drafted}, auto-sent {auto_sent}, queued for review {queued_for_review}")
    return {"drafted": drafted, "auto_sent": auto_sent, "queued_for_review": queued_for_review}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, default=str))
