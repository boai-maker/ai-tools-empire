"""
Cross-platform distribution — auto-tweet + export for TikTok/IG.

Called from video_engine.produce() after a successful YouTube upload.
Never fatal — all errors are caught and logged.
"""
import os
import sys
import shutil
import json
import time
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.standards import get_logger, tg, STATE_DIR

log = get_logger("distributor")

DISTRIBUTE_DIR = os.path.join(STATE_DIR, "distribute")
os.makedirs(DISTRIBUTE_DIR, exist_ok=True)

CLEANUP_DAYS = 7


# ─────────────────────────────────────────────────────────────────────────────
# 1. Auto-tweet announcing the video
# ─────────────────────────────────────────────────────────────────────────────
def _tweet_video(hook: str, tool: str, youtube_url: str,
                 emoji: str = "🎬") -> Dict:
    """Tweet a video announcement. Returns {"success": bool, "tweet_url": str}."""
    try:
        import tweepy
        from config import config
        if not all([
            config.TWITTER_API_KEY, config.TWITTER_API_SECRET,
            config.TWITTER_ACCESS_TOKEN, config.TWITTER_ACCESS_SECRET,
        ]):
            log.info("Twitter creds missing — skipping tweet")
            return {"success": False, "error": "no creds"}

        client = tweepy.Client(
            consumer_key=config.TWITTER_API_KEY,
            consumer_secret=config.TWITTER_API_SECRET,
            access_token=config.TWITTER_ACCESS_TOKEN,
            access_token_secret=config.TWITTER_ACCESS_SECRET,
        )

        # Build tweet text: hook + link + hashtags, under 280 chars
        hashtags = "#AITools #AI #Shorts"
        hook_clean = hook[:150].rstrip(".")
        tweet = f"{emoji} {hook_clean}\n\n🔗 {youtube_url}\n\n{hashtags}"
        if len(tweet) > 280:
            tweet = f"{emoji} {hook_clean[:80]}...\n\n🔗 {youtube_url}\n\n{hashtags}"

        response = client.create_tweet(text=tweet)
        tweet_id = str(response.data["id"])
        try:
            me = client.get_me()
            username = me.data.username
        except Exception:
            username = "AIToolsEmpire"
        tweet_url = f"https://twitter.com/{username}/status/{tweet_id}"
        log.info(f"Tweeted: {tweet_url}")
        return {"success": True, "tweet_url": tweet_url}
    except Exception as e:
        log.warning(f"Tweet failed: {e}")
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Copy mp4 + metadata to distribute folder for manual TikTok/IG
# ─────────────────────────────────────────────────────────────────────────────
def _copy_to_distribute(video_path: str, format_type: str,
                        tool: str, metadata: Dict) -> str:
    """Copy rendered mp4 + sidecar JSON to distribute/. Returns dest path."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_tool = (tool or "ai").replace(" ", "_").lower()[:20]
    basename = f"{format_type}_{safe_tool}_{ts}"

    dest_mp4 = os.path.join(DISTRIBUTE_DIR, f"{basename}.mp4")
    dest_json = os.path.join(DISTRIBUTE_DIR, f"{basename}.json")

    shutil.copy2(video_path, dest_mp4)
    with open(dest_json, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    log.info(f"Copied to distribute: {dest_mp4}")
    return dest_mp4


# ─────────────────────────────────────────────────────────────────────────────
# 3. Generate platform-specific captions
# ─────────────────────────────────────────────────────────────────────────────
def _generate_platform_captions(basename: str, hook: str, tool: str,
                                youtube_url: str, format_type: str) -> None:
    """Write _twitter.txt, _tiktok.txt, _instagram.txt alongside the mp4."""
    base_path = os.path.join(DISTRIBUTE_DIR, basename)

    # Twitter
    tw = (
        f"🎬 {hook[:120]}\n\n"
        f"🔗 Full video: {youtube_url}\n\n"
        f"#AITools #{(tool or 'AI').replace(' ','')} #AI #Shorts"
    )
    with open(f"{base_path}_twitter.txt", "w") as f:
        f.write(tw)

    # TikTok
    tk = (
        f"{hook[:150]}\n\n"
        f"👉 Link in bio for the full review\n\n"
        f"#ai #aitools #techtok #fyp #foryou "
        f"#{(tool or 'AI').replace(' ','').lower()} "
        f"#artificialintelligence #productivity #free"
    )
    with open(f"{base_path}_tiktok.txt", "w") as f:
        f.write(tk)

    # Instagram
    ig = (
        f"🔥 {hook[:200]}\n\n"
        f"{'🎯 Full breakdown and free trial link in bio!' if tool else 'Link in bio!'}\n\n"
        f"💾 Save this for later — you'll thank yourself.\n\n"
        f"📱 Follow @aitoolsempire for daily AI tool tips\n\n"
        f".\n.\n.\n"
        f"#aitools #ai #artificialintelligence #productivity "
        f"#{(tool or 'AI').replace(' ','').lower()} "
        f"#techtips #automation #fretools #reels #explore"
    )
    with open(f"{base_path}_instagram.txt", "w") as f:
        f.write(ig)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Cleanup old distribute files
# ─────────────────────────────────────────────────────────────────────────────
def _cleanup_old() -> int:
    """Remove files older than CLEANUP_DAYS from distribute/."""
    cutoff = time.time() - (CLEANUP_DAYS * 86400)
    removed = 0
    for fn in os.listdir(DISTRIBUTE_DIR):
        fp = os.path.join(DISTRIBUTE_DIR, fn)
        if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
            os.unlink(fp)
            removed += 1
    if removed:
        log.info(f"Cleaned {removed} old distribute files")
    return removed


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def distribute(video_path: str, format_type: str, hook: str,
               tool: str, youtube_url: str, script_dict: Dict) -> Dict:
    """
    Full distribution pipeline. Called from video_engine.produce() after
    a successful YouTube upload. Non-fatal — all errors logged.

    Returns {"twitter": {...}, "distribute_path": str}.
    """
    results = {}

    # 1. Auto-tweet
    try:
        results["twitter"] = _tweet_video(hook, tool, youtube_url)
    except Exception as e:
        results["twitter"] = {"success": False, "error": str(e)}
        log.warning(f"Tweet distribution failed: {e}")

    # 2. Copy to distribute folder
    try:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_tool = (tool or "ai").replace(" ", "_").lower()[:20]
        basename = f"{format_type}_{safe_tool}_{ts}"

        metadata = {
            "format": format_type,
            "tool": tool,
            "hook": hook,
            "youtube_url": youtube_url,
            "script": script_dict,
            "distributed_at": datetime.utcnow().isoformat(),
        }
        dest = _copy_to_distribute(video_path, format_type, tool, metadata)
        results["distribute_path"] = dest

        # 3. Platform-specific captions
        _generate_platform_captions(basename, hook, tool, youtube_url, format_type)
    except Exception as e:
        results["distribute_path"] = None
        log.warning(f"Copy-to-distribute failed: {e}")

    # 4. Cleanup old files
    try:
        _cleanup_old()
    except Exception:
        pass

    # 5. Telegram summary
    tw = results.get("twitter", {})
    tw_status = f"✅ {tw.get('tweet_url', '')}" if tw.get("success") else "⚠️ skipped"
    tg(
        f"<b>📢 Distribution complete</b>\n"
        f"<b>Format:</b> {format_type}\n"
        f"<b>Twitter:</b> {tw_status}\n"
        f"<b>TikTok/IG:</b> ready in distribute/",
        level="info",
    )

    return results
