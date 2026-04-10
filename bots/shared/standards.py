"""
SHARED BOT STANDARDS — Single source of truth for all bots
═══════════════════════════════════════════════════════════
Master Bot Upgrade Directive — Phase 5 implementation.

Every bot in this project should import from here:
  from bots.shared.standards import (
      Status, log, tg, BotResult, conservative_check
  )

Provides:
  • Unified status vocabulary (Status enum)
  • Standardized logging format
  • Single Telegram notification function
  • Structured bot result type for handoffs
  • Conservative decision rules
  • Error handling decorator
"""
import os
import json
import logging
import functools
import requests
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


# ── Single Telegram source of truth ─────────────────────────────────────────
# Per CLAUDE.md: KennyClaude bot is the central notification hub
TELEGRAM_BOT_TOKEN = os.getenv(
    "CLAUDE_BOT_TOKEN",
    "8620859605:AAFyqpnfFNj-Usgx0J1ZmxLyzQxw8T2s5Pk"
)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6194068092")


# ── Unified Status Vocabulary (Phase 5) ─────────────────────────────────────
class Status(str, Enum):
    """Single status vocabulary used across ALL bots and the CRM."""
    NEW = "new"
    QUEUED = "queued"
    RESEARCHING = "researching"
    PROCESSING = "processing"
    REVIEW = "review"
    READY = "ready"
    BLOCKED = "blocked"
    SENT = "sent"
    FOLLOW_UP = "follow_up"
    COMPLETED = "completed"
    DEAD = "dead"
    # Wholesale-specific (subset)
    HOT = "hot"
    PASS = "pass"
    UNDER_CONTRACT = "under_contract"
    CLOSED = "closed"


# ── Standardized Logging ─────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
LOG_DATE = "%H:%M:%S"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE)


def get_logger(bot_name: str) -> logging.Logger:
    """Return a logger named for the bot. Standard format."""
    logger = logging.getLogger(bot_name)
    logger.setLevel(logging.INFO)
    return logger


# Module-level fast access
log = get_logger("bot")


# ── Single Telegram Notifier ─────────────────────────────────────────────────
LEVEL_EMOJI = {
    "info":    "ℹ️",
    "success": "✅",
    "warning": "⚠️",
    "error":   "🚨",
    "trade":   "💹",
    "deal":    "🏠",
    "money":   "💰",
}


def tg(message: str, level: str = "info", parse_mode: str = "HTML") -> bool:
    """
    Send Telegram message via Kenny Claude bot.
    Single source of truth for all bot notifications.

    Args:
        message: Text content
        level: info | success | warning | error | trade | deal | money
        parse_mode: HTML or Markdown

    Returns:
        True on success, False on failure (silent — never raises)
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.debug("Telegram not configured")
        return False

    emoji = LEVEL_EMOJI.get(level, "ℹ️")
    if not message.startswith(emoji):
        message = f"{emoji} {message}"

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message[:4000],  # Telegram limit
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.ok
    except Exception as e:
        log.warning(f"Telegram failed: {e}")
        return False


# ── Structured Bot Result (Phase 5 handoff format) ──────────────────────────
class BotResult:
    """
    Standard return type for every bot.
    Enables clean handoffs between bots.
    """
    def __init__(
        self,
        bot_name: str,
        success: bool = True,
        received: Any = None,
        changed: Any = None,
        produced: Any = None,
        next_bot: Optional[str] = None,
        next_action: Optional[str] = None,
        uncertainties: Optional[list] = None,
        error: Optional[str] = None,
        data: Optional[dict] = None,
    ):
        self.bot_name = bot_name
        self.success = success
        self.received = received
        self.changed = changed
        self.produced = produced
        self.next_bot = next_bot
        self.next_action = next_action
        self.uncertainties = uncertainties or []
        self.error = error
        self.data = data or {}
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "bot": self.bot_name,
            "success": self.success,
            "received": self.received,
            "changed": self.changed,
            "produced": self.produced,
            "next_bot": self.next_bot,
            "next_action": self.next_action,
            "uncertainties": self.uncertainties,
            "error": self.error,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def __repr__(self) -> str:
        icon = "✅" if self.success else "❌"
        return f"{icon} {self.bot_name}: {self.next_action or 'done'}"


# ── Standardized Error Handler ───────────────────────────────────────────────
def safe_run(bot_name: str, alert_on_error: bool = True):
    """
    Decorator for bot main functions. Catches all errors, logs them,
    optionally alerts via Telegram, returns BotResult.

    Usage:
        @safe_run("my_bot")
        def run_my_bot():
            ...
            return BotResult(...)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger(bot_name)
            try:
                logger.info(f"START")
                result = func(*args, **kwargs)
                if isinstance(result, BotResult):
                    logger.info(f"DONE: {result}")
                    return result
                else:
                    logger.info(f"DONE")
                    return BotResult(bot_name, success=True, data={"raw": result})
            except Exception as e:
                logger.exception(f"FAILED: {e}")
                if alert_on_error:
                    tg(f"<b>Bot {bot_name} failed</b>\n{type(e).__name__}: {str(e)[:300]}", level="error")
                return BotResult(bot_name, success=False, error=str(e))
        return wrapper
    return decorator


# ── Conservative Decision Rules (Phase 4) ────────────────────────────────────
def conservative_check(
    confidence: float,
    spread_dollars: int = 0,
    min_confidence: float = 0.70,
    min_spread: int = 5000,
) -> tuple[bool, str]:
    """
    Conservative gate for any decision (trades, deals, sends).
    Returns (proceed: bool, reason: str)
    """
    if confidence < min_confidence:
        return False, f"confidence {confidence:.2f} < {min_confidence}"
    if spread_dollars > 0 and spread_dollars < min_spread:
        return False, f"spread ${spread_dollars} < ${min_spread}"
    return True, "passed conservative checks"


# ── State / Memory Helpers ───────────────────────────────────────────────────
def load_state(state_file: str) -> dict:
    """Load JSON state file with safe defaults."""
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state_file: str, state: dict) -> None:
    """Save JSON state file atomically."""
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    tmp = f"{state_file}.tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, state_file)


# ── Project paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
STATE_DIR = os.path.join(PROJECT_ROOT, "bots", "state")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(STATE_DIR, exist_ok=True)


__all__ = [
    "Status",
    "BotResult",
    "log",
    "tg",
    "get_logger",
    "safe_run",
    "conservative_check",
    "load_state",
    "save_state",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PROJECT_ROOT",
    "LOG_DIR",
    "STATE_DIR",
]
