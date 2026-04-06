"""
Notification hub — Telegram + email alerts for all bots.
"""
import os
import logging
import requests
from config import config
from bots.shared.email_sender import send_email

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("DOMINIC_TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("DOMINIC_TELEGRAM_CHAT_ID", "")

LEVEL_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🚨",
    "success": "✅",
}


def _send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured — skipping Telegram notification")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.debug("Telegram notification sent")
            return True
        else:
            logger.warning(f"Telegram API returned {response.status_code}: {response.text[:200]}")
            return False
    except requests.RequestException as e:
        logger.error(f"Telegram notification error: {e}")
        return False


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
    Send an admin notification via both Telegram and email.
    """
    _send_telegram(f"📬 <b>{subject}</b>\n\n{body}")

    if config.SMTP_USER:
        body_html = f"""
        <html><body style="font-family: Arial, sans-serif; padding: 20px; max-width: 600px;">
        <h2 style="color: #1a1a2e;">{subject}</h2>
        <div style="background: #f9f9f9; padding: 15px; border-radius: 8px; margin: 10px 0;">
        <pre style="white-space: pre-wrap; font-family: Arial, sans-serif; color: #333;">{body}</pre>
        </div>
        <hr>
        <p style="color: #999; font-size: 12px;">
        AI Tools Empire — Autonomous Bot System<br>
        <a href="{config.SITE_URL}">{config.SITE_URL}</a>
        </p>
        </body></html>
        """
        send_email(config.SMTP_USER, subject, body_html, body_text=body)
