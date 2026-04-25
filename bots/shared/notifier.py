"""
Notification hub — Telegram + email alerts for all bots.

LEGACY MODULE: This now wraps bots.shared.standards.tg() so all
notifications flow through a single source. Existing bots that import
notify() from here will keep working without changes.

For new code, prefer:
    from bots.shared.standards import tg
    tg("message", level="info")
"""
import os
import logging
import requests
from config import config
from bots.shared.email_sender import send_email
from bots.shared.standards import tg as _tg_unified, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID as _CHAT_ID

logger = logging.getLogger(__name__)

# Backwards-compat — these point at the single source of truth
TELEGRAM_TOKEN = os.getenv("DOMINIC_TELEGRAM_TOKEN", TELEGRAM_BOT_TOKEN)
TELEGRAM_CHAT_ID = os.getenv("DOMINIC_TELEGRAM_CHAT_ID", _CHAT_ID)

LEVEL_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🚨",
    "success": "✅",
}


def _send_telegram(message: str) -> bool:
    """
    Legacy wrapper — routes through unified tg() in standards.
    Kept for backwards compatibility with existing bots.
    """
    return _tg_unified(message, level="info")


def notify(
    message: str,
    level: str = "info",
    use_telegram: bool = True,
    use_email: bool = False
) -> None:
    """
    Send a notification via Telegram and/or email.
    level: "info", "warning", "error", "success"
    """
    emoji = LEVEL_EMOJI.get(level, "ℹ️")
    formatted = f"{emoji} <b>AI Tools Empire Bot</b>\n{message}"

    log_fn = {
        "info": logger.info,
        "warning": logger.warning,
        "error": logger.error,
        "success": logger.info,
    }.get(level, logger.info)
    log_fn(f"[NOTIFY/{level.upper()}] {message}")

    if use_telegram:
        _send_telegram(formatted)

    if use_email and config.SMTP_USER:
        subject = f"[{level.upper()}] AI Tools Empire Bot Alert"
        body_html = f"""
        <html><body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #333;">AI Tools Empire Bot Notification</h2>
        <p><strong>Level:</strong> {level.upper()}</p>
        <p>{message}</p>
        <hr>
        <p style="color: #999; font-size: 12px;">Sent by AI Tools Empire bot system</p>
        </body></html>
        """
        send_email(config.SMTP_USER, subject, body_html, body_text=message)


def notify_admin(subject: str, body: str) -> None:
    """
    Send an admin notification.

    2026-04-25 (Kenneth): EMAIL DISABLED. Inbox was getting jammed by daily
    morning briefings + revenue snapshots. Telegram is now the single channel
    for all admin notifications. To re-enable email per-call, callers should
    use notify(... use_email=True) explicitly.
    """
    _send_telegram(f"📬 <b>{subject}</b>\n\n{body}")
