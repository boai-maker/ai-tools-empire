"""
Activity logger for Dominic.
Writes structured logs to logs/dominic.log with rotation.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path
from typing import List

_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# File handler setup
# ---------------------------------------------------------------------------
LOG_DIR = _ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "dominic.log"

_logger = logging.getLogger("dominic")
_logger.setLevel(logging.DEBUG)

if not _logger.handlers:
    # File handler — 10 MB, 5 backups
    fh = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fmt)
    _logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    _logger.addHandler(ch)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _safe_db(key: str, value: str) -> None:
    """Write to dom_config silently, ignoring errors."""
    try:
        from automation.dominic.db import set_dom_config
        set_dom_config(key, value)
    except Exception:
        pass


def log_action(action: str, platform: str = "", status: str = "", detail: str = "") -> None:
    """Log a generic Dominic action to file and DB."""
    msg = f"ACTION | {action} | platform={platform} | status={status} | {detail}"
    _logger.info(msg)
    ts = datetime.utcnow().isoformat()
    _safe_db("last_action", f"{ts} | {action} | {platform} | {status}")


def log_post(platform: str, content_summary: str, status: str, url: str = "") -> None:
    """Log a post attempt."""
    summary = (content_summary or "")[:120]
    msg = f"POST | platform={platform} | status={status} | url={url} | summary={summary}"
    if status == "success":
        _logger.info(msg)
    else:
        _logger.warning(msg)
    _safe_db("last_post", f"{datetime.utcnow().isoformat()} | {platform} | {status}")


def log_error(module: str, error: str, context: str = "") -> None:
    """Log an error."""
    msg = f"ERROR | module={module} | error={error} | context={context}"
    _logger.error(msg)


def log_telegram(message: str, success: bool) -> None:
    """Log a Telegram notification attempt."""
    status = "sent" if success else "failed"
    preview = (message or "")[:80].replace("\n", " ")
    _logger.debug(f"TELEGRAM | status={status} | msg={preview}")


def get_recent_logs(n: int = 20) -> List[str]:
    """Return last N lines from dominic.log."""
    try:
        with open(str(LOG_FILE), "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [line.rstrip() for line in lines[-n:]]
    except FileNotFoundError:
        return []
    except Exception as e:
        _logger.debug(f"get_recent_logs error: {e}")
        return []


def get_logger() -> logging.Logger:
    """Return the Dominic logger."""
    return _logger
