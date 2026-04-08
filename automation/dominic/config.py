"""
Dominic Bot Configuration
Reads all settings from environment variables (.env file in project root).
"""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure project root is on path
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env", override=True)
except ImportError:
    pass  # dotenv not available; rely on OS env


@dataclass
class DominicConfig:
    # --- Dominic operational settings ---
    mode: str = "autonomous"               # "autonomous" | "approval"
    paused: bool = False
    telegram_token: str = ""
    telegram_chat_id: str = ""
    timezone: str = "America/New_York"
    confidence_threshold: float = 0.7

    # --- Site ---
    site_url: str = "https://aitoolsempire.co"
    site_name: str = "AI Tools Empire"

    # --- Anthropic ---
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # --- Twitter ---
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""

    # --- YouTube ---
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""

    # --- Paths ---
    db_path: str = ""
    log_dir: str = ""

    def __post_init__(self):
        if not self.db_path:
            self.db_path = str(_ROOT / "data.db")
        if not self.log_dir:
            self.log_dir = str(_ROOT / "logs")


def get_config() -> DominicConfig:
    """Build and return DominicConfig from environment variables."""
    paused_raw = os.getenv("DOMINIC_PAUSED", "false").lower().strip()
    paused = paused_raw in ("true", "1", "yes")

    threshold_raw = os.getenv("DOMINIC_CONFIDENCE_THRESHOLD", "0.7")
    try:
        threshold = float(threshold_raw)
    except ValueError:
        threshold = 0.7

    return DominicConfig(
        mode=os.getenv("DOMINIC_MODE", "autonomous").lower().strip(),
        paused=paused,
        telegram_token=os.getenv("DOMINIC_TELEGRAM_TOKEN", ""),
        telegram_chat_id=os.getenv("DOMINIC_TELEGRAM_CHAT_ID", ""),
        timezone=os.getenv("DOMINIC_TIMEZONE", "America/New_York"),
        confidence_threshold=threshold,
        site_url=os.getenv("SITE_URL", "https://aitoolsempire.co").rstrip("/"),
        site_name=os.getenv("SITE_NAME", "AI Tools Empire"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        twitter_api_key=os.getenv("TWITTER_API_KEY", ""),
        twitter_api_secret=os.getenv("TWITTER_API_SECRET", ""),
        twitter_access_token=os.getenv("TWITTER_ACCESS_TOKEN", ""),
        twitter_access_secret=os.getenv("TWITTER_ACCESS_SECRET", ""),
        youtube_client_id=os.getenv("YOUTUBE_CLIENT_ID", ""),
        youtube_client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        youtube_refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
    )


# Module-level singleton
_config_instance: DominicConfig = None


def config() -> DominicConfig:
    """Return cached config singleton."""
    global _config_instance
    if _config_instance is None:
        _config_instance = get_config()
    return _config_instance
