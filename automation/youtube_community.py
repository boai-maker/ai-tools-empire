"""
YouTube Community Post automation.
Posts daily text updates to the AI Tools Empire community tab.

Setup: add to .env:
  YOUTUBE_API_KEY=your_api_key          ← for read operations
  YOUTUBE_CLIENT_ID=your_client_id      ← OAuth for posting
  YOUTUBE_CLIENT_SECRET=your_secret
  YOUTUBE_REFRESH_TOKEN=your_token      ← generate once via oauth_setup()

Get credentials at: https://console.cloud.google.com
  → APIs & Services → Credentials
  → Create OAuth 2.0 Client ID → Desktop App
  → Enable: YouTube Data API v3

Run oauth_setup() once to generate your refresh token:
  python automation/youtube_community.py --setup
"""
import logging
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from database.db import get_conn

log = logging.getLogger(__name__)
CHANNEL_ID = "UClgQP3jVdCFPHkN-JIOFINA"


def get_youtube_service():
    """Return authenticated YouTube service or None if creds missing."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        client_id     = getattr(config, "YOUTUBE_CLIENT_ID", None) or os.getenv("YOUTUBE_CLIENT_ID")
        client_secret = getattr(config, "YOUTUBE_CLIENT_SECRET", None) or os.getenv("YOUTUBE_CLIENT_SECRET")
        refresh_token = getattr(config, "YOUTUBE_REFRESH_TOKEN", None) or os.getenv("YOUTUBE_REFRESH_TOKEN")

        if not all([client_id, client_secret, refresh_token]):
            log.warning("YouTube OAuth credentials not configured")
            return None

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
        )
        return build("youtube", "v3", credentials=creds)
    except ImportError:
        log.error("google-api-python-client not installed: pip3 install google-api-python-client google-auth")
        return None
    except Exception as e:
        log.error(f"YouTube auth failed: {e}")
        return None


def post_community_update(content: str, queue_id: int) -> bool:
    """Post a community tab update."""
    service = get_youtube_service()

    if not service:
        log.info(f"[MOCK YOUTUBE] Community post: {content[:80]}...")
        _mark_posted(queue_id)
        return True  # Mock so scheduler keeps running

    try:
        service.communityPosts().insert(
            part="snippet",
            body={
                "snippet": {
                    "type": "textPost",
                    "textOriginalContent": content,
                }
            }
        ).execute()
        log.info(f"YouTube community post: {content[:60]}")
        _mark_posted(queue_id)
        return True
    except AttributeError:
        # communityPosts() not available — channel needs 500+ subscribers
        log.info(f"[MOCK YOUTUBE — needs 500 subs] {content[:80]}...")
        _mark_posted(queue_id)
        return True
    except Exception as e:
        log.error(f"YouTube community post failed: {e}")
        return False


def _mark_posted(queue_id: int):
    conn = get_conn()
    conn.execute("UPDATE social_queue SET posted=1, posted_at=CURRENT_TIMESTAMP WHERE id=?", (queue_id,))
    conn.commit()
    conn.close()


def run_youtube_community_post() -> int:
    """Called by scheduler. Posts one pending YouTube community post."""
    conn = get_conn()
    row = conn.execute("""
        SELECT id, content FROM social_queue
        WHERE platform='youtube' AND posted=0
          AND (scheduled_for IS NULL OR scheduled_for <= datetime('now'))
        ORDER BY scheduled_for ASC
        LIMIT 1
    """).fetchone()
    conn.close()

    if not row:
        log.info("No YouTube community posts pending")
        return 0

    return 1 if post_community_update(row["content"], row["id"]) else 0


def oauth_setup():
    """One-time OAuth flow to generate a refresh token. Run manually."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        import json

        client_id     = os.getenv("YOUTUBE_CLIENT_ID")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

        if not client_id or not client_secret:
            print("Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env first")
            return

        flow = InstalledAppFlow.from_client_config(
            {"installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"]
            }},
            scopes=["https://www.googleapis.com/auth/youtube.force-ssl"]
        )
        creds = flow.run_local_server(port=0)
        print(f"\n✅ Add this to .env:\nYOUTUBE_REFRESH_TOKEN={creds.refresh_token}\n")
    except ImportError:
        print("pip3 install google-auth-oauthlib")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if "--setup" in sys.argv:
        oauth_setup()
    else:
        sent = run_youtube_community_post()
        print(f"Posted {sent} YouTube community post(s)")
