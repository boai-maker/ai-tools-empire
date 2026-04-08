"""
YouTube Shorts Bot
Generates and uploads 30-45 second vertical AI tool tip videos as YouTube Shorts.
No subscriber minimum required — Shorts work on any channel.

Video spec: 1080x1920 (9:16), dark branded style, text animations.
Uploads via YouTube Data API v3 using bosaibot@gmail.com OAuth.
"""
import logging
import os
import sys
import random
import textwrap
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from bots.shared.ai_client import ask_claude
from bots.shared.db_helpers import log_bot_event, upsert_bot_state
from bots.shared.notifier import notify
from config import config

logger = logging.getLogger(__name__)
BOT_NAME = "youtube_shorts_bot"

# ---------------------------------------------------------------------------
# Video dimensions
# ---------------------------------------------------------------------------
SHORT_W = 1080
SHORT_H = 1920
SHORT_FPS = 30

# ---------------------------------------------------------------------------
# Brand colours (match design system)
# ---------------------------------------------------------------------------
BG_TOP    = (15,  23,  42)   # #0f172a slate-900
BG_BOT    = (49,  46, 129)   # #312e81 indigo-900
INDIGO    = (99, 102, 241)   # #6366f1
WHITE     = (248, 250, 252)  # #f8fafc
SLATE_400 = (148, 163, 184)  # #94a3b8
EMERALD   = (16,  185, 129)  # #10b981

# ---------------------------------------------------------------------------
# Tool roster — pick from active affiliate programs
# ---------------------------------------------------------------------------
TOOL_ROSTER = [
    {
        "name": "ElevenLabs",
        "category": "AI Voice",
        "hook": "Clone your voice in 60 seconds",
        "tip": "ElevenLabs lets you create a realistic AI clone of your voice with just 1 minute of audio. Use it to narrate videos, podcasts, or courses — without ever recording again.",
        "cta": "Start free at aitoolsempire.co",
        "url": "https://try.elevenlabs.io/i3pg30ciu5n8",
        "emoji": "🎙️",
    },
    {
        "name": "Pictory AI",
        "category": "AI Video",
        "hook": "Turn blog posts into videos automatically",
        "tip": "Pictory AI converts any article, script, or URL into a polished video in minutes. Perfect for repurposing content across YouTube, Instagram, and TikTok.",
        "cta": "Try free → aitoolsempire.co",
        "url": f"https://pictory.ai?ref={config.AFFILIATE_IDS.get('pictory','kenneth46')}",
        "emoji": "🎬",
    },
    {
        "name": "Fireflies AI",
        "category": "AI Meetings",
        "hook": "Never take meeting notes again",
        "tip": "Fireflies joins your Zoom, Meet, or Teams calls automatically. It records, transcribes, and creates AI summaries so you can stay focused — not furiously typing.",
        "cta": "Free plan available → aitoolsempire.co",
        "url": f"https://fireflies.ai/?fpr={config.AFFILIATE_IDS.get('fireflies','kenneth39')}",
        "emoji": "🤖",
    },
    {
        "name": "Writesonic",
        "category": "AI Writing",
        "hook": "Write SEO articles 10x faster",
        "tip": "Writesonic's Article Writer pulls live Google data, then writes a full SEO-optimised article with headings, FAQs, and meta description — all in under 5 minutes.",
        "cta": "Start free → aitoolsempire.co",
        "url": "https://writesonic.com",
        "emoji": "✍️",
    },
    {
        "name": "Copy.ai",
        "category": "AI Copywriting",
        "hook": "Write 100 social posts in 10 minutes",
        "tip": "Copy.ai's Workflows let you batch-generate social media captions, email sequences, and ad copy. One prompt, unlimited variations — and it never sounds robotic.",
        "cta": "Free forever plan → aitoolsempire.co",
        "url": "https://www.copy.ai",
        "emoji": "💬",
    },
    {
        "name": "Surfer SEO",
        "category": "AI SEO",
        "hook": "Rank on Google with AI content scoring",
        "tip": "Surfer SEO analyses the top 20 Google results and tells you exactly what to write — word count, keywords, headings, and NLP terms — to outrank them.",
        "cta": "See full review → aitoolsempire.co",
        "url": "https://surferseo.com",
        "emoji": "🔍",
    },
    {
        "name": "Murf AI",
        "category": "AI Voiceover",
        "hook": "Studio-quality voiceovers without a microphone",
        "tip": "Murf AI has 120+ ultra-realistic voices in 20 languages. Type your script, pick a voice, adjust pace and pitch — and export broadcast-quality audio in seconds.",
        "cta": "Try free → aitoolsempire.co",
        "url": "https://murf.ai",
        "emoji": "🎤",
    },
    {
        "name": "Semrush",
        "category": "SEO & Marketing",
        "hook": "See exactly what your competitors rank for",
        "tip": "Semrush's competitor analysis shows every keyword your rivals rank for, their traffic, backlinks, and ad spend. Find the gaps — and steal their traffic.",
        "cta": "Free trial → aitoolsempire.co",
        "url": "https://www.semrush.com",
        "emoji": "📊",
    },
]

# ---------------------------------------------------------------------------
# Script generation via Claude
# ---------------------------------------------------------------------------

def generate_short_script(tool: dict) -> dict:
    """
    Ask Claude to sharpen the hook, tip, and CTA into punchy Short-format copy.
    Returns dict with: hook, lines (list), cta.
    """
    prompt = f"""Write a YouTube Shorts script for a 35-second vertical video about {tool['name']} ({tool['category']}).

Base content:
Hook: {tool['hook']}
Core tip: {tool['tip']}
CTA: {tool['cta']}

Rules:
- HOOK: One powerful sentence (max 8 words). Starts with a surprising fact, question, or bold claim.
- LINES: 3-4 short punchy lines that explain the value. Each line max 12 words. No jargon.
- CTA: One line. Ends with "aitoolsempire.co"
- Total spoken words: ~70-85 (fits 35 seconds at speaking pace)

Output EXACTLY this format (no extra text):
HOOK: [hook line]
LINE1: [line]
LINE2: [line]
LINE3: [line]
LINE4: [optional 4th line or leave blank]
CTA: [call to action]"""

    response = ask_claude(prompt, max_tokens=300)
    result = {"hook": tool["hook"], "lines": [], "cta": tool["cta"]}

    if not response:
        result["lines"] = [tool["tip"]]
        return result

    for line in response.strip().split("\n"):
        line = line.strip()
        if line.startswith("HOOK:"):
            result["hook"] = line[5:].strip()
        elif line.startswith("LINE"):
            content = line.split(":", 1)[-1].strip()
            if content:
                result["lines"].append(content)
        elif line.startswith("CTA:"):
            result["cta"] = line[4:].strip()

    if not result["lines"]:
        result["lines"] = [tool["tip"]]

    return result


# ---------------------------------------------------------------------------
# Video rendering with moviepy + pillow
# ---------------------------------------------------------------------------

def _make_gradient_frame(t, total_duration):
    """Returns an RGB numpy array for a gradient background frame."""
    import numpy as np
    frame = np.zeros((SHORT_H, SHORT_W, 3), dtype=np.uint8)
    for y in range(SHORT_H):
        ratio = y / SHORT_H
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * ratio)
        frame[y, :] = [r, g, b]
    return frame


def _wrap(text: str, max_chars: int = 28) -> list[str]:
    """Wrap text into lines of max_chars."""
    return textwrap.wrap(text, width=max_chars)


def _generate_background_audio(duration: float, video_path: str):
    """
    Generate a chill lo-fi background beat for the Short.
    Uses numpy to synthesize a simple ambient pad + soft beat.
    Returns a moviepy AudioClip or None.
    """
    import numpy as np
    import struct
    import wave

    sample_rate = 44100
    total_samples = int(duration * sample_rate)
    t = np.linspace(0, duration, total_samples, endpoint=False)

    # Ambient pad: soft sine chord (C major 7th, low volume)
    pad = (
        0.08 * np.sin(2 * np.pi * 130.81 * t) +  # C3
        0.06 * np.sin(2 * np.pi * 164.81 * t) +  # E3
        0.05 * np.sin(2 * np.pi * 196.00 * t) +  # G3
        0.04 * np.sin(2 * np.pi * 246.94 * t)     # B3
    )

    # Slow LFO tremolo for movement
    lfo = 0.7 + 0.3 * np.sin(2 * np.pi * 0.25 * t)
    pad = pad * lfo

    # Soft kick-like thump every 2 beats (BPM ~75)
    beat_interval = sample_rate * 60 // 75  # samples per beat
    kick = np.zeros(total_samples)
    for i in range(0, total_samples, beat_interval * 2):
        decay_len = min(int(sample_rate * 0.15), total_samples - i)
        decay = np.exp(-np.linspace(0, 8, decay_len))
        freq_sweep = 80 * np.exp(-np.linspace(0, 4, decay_len)) + 40
        phase = np.cumsum(2 * np.pi * freq_sweep / sample_rate)
        kick[i:i + decay_len] += 0.12 * np.sin(phase) * decay

    # Hi-hat on off-beats (very quiet)
    hihat = np.zeros(total_samples)
    for i in range(beat_interval, total_samples, beat_interval * 2):
        noise_len = min(int(sample_rate * 0.03), total_samples - i)
        noise = np.random.randn(noise_len) * 0.02
        decay = np.exp(-np.linspace(0, 15, noise_len))
        hihat[i:i + noise_len] += noise * decay

    # Mix and fade in/out
    mixed = pad + kick + hihat
    fade_samples = int(sample_rate * 1.5)
    mixed[:fade_samples] *= np.linspace(0, 1, fade_samples)
    mixed[-fade_samples:] *= np.linspace(1, 0, fade_samples)

    # Normalize
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak * 0.6  # Keep at 60% volume so it's background

    # Write temp WAV
    audio_path = video_path.replace(".mp4", "_bg.wav")
    mixed_int16 = (mixed * 32767).astype(np.int16)
    with wave.open(audio_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(mixed_int16.tobytes())

    # Load as moviepy audio
    from moviepy import AudioFileClip
    audio_clip = AudioFileClip(audio_path).with_duration(duration)
    logger.info(f"[{BOT_NAME}] Generated background audio: {audio_path}")
    return audio_clip


def render_short(tool: dict, script: dict, output_path: str) -> bool:
    """
    Render a 1080x1920 YouTube Short as an MP4.
    Returns True on success.
    """
    try:
        from moviepy import ImageClip, TextClip, CompositeVideoClip, concatenate_videoclips, ColorClip
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        duration = 35  # seconds

        # ---- Background ----
        bg_array = _make_gradient_frame(0, duration)
        bg_clip = ImageClip(bg_array).with_duration(duration)

        clips = [bg_clip]

        # ---- Helper: PIL text image → moviepy ImageClip ----
        def text_image(text, font_size=72, color=WHITE, bold=False,
                       max_width=900, start=0.0, end=None, y_pos=None,
                       align="center", opacity=1.0):
            """Create a text overlay clip using PIL."""
            try:
                # Try to load a system font
                font_path = None
                for path in [
                    "/System/Library/Fonts/Helvetica.ttc",
                    "/System/Library/Fonts/Arial.ttf",
                    "/Library/Fonts/Arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ]:
                    if os.path.exists(path):
                        font_path = path
                        break

                if font_path:
                    try:
                        font = ImageFont.truetype(font_path, font_size)
                    except Exception:
                        font = ImageFont.load_default()
                else:
                    font = ImageFont.load_default()

                # Wrap text
                lines = _wrap(text, max_chars=max(10, max_width // (font_size // 2)))
                line_h = font_size + 8
                img_h = line_h * len(lines) + 20
                img_w = max_width + 40

                img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                alpha = int(255 * opacity)
                rgba_color = (color[0], color[1], color[2], alpha)

                for i, line in enumerate(lines):
                    bbox = draw.textbbox((0, 0), line, font=font)
                    w = bbox[2] - bbox[0]
                    if align == "center":
                        x = (img_w - w) // 2
                    else:
                        x = 20
                    y = i * line_h + 10
                    draw.text((x, y), line, font=font, fill=rgba_color)

                arr = np.array(img)
                clip = ImageClip(arr, is_mask=False)
                clip_duration = (end or duration) - start
                clip = clip.with_duration(clip_duration).with_start(start)

                if y_pos is not None:
                    clip = clip.with_position(("center", y_pos))
                else:
                    clip = clip.with_position("center")

                return clip

            except Exception as e:
                logger.warning(f"text_image failed: {e}")
                return None

        # ---- Emoji badge top ----
        emoji_clip = text_image(
            f"{tool['emoji']} {tool['category'].upper()}",
            font_size=44,
            color=EMERALD,
            start=0.0, end=duration,
            y_pos=160,
        )
        if emoji_clip:
            clips.append(emoji_clip)

        # ---- HOOK (0-8 sec) — large, centered ----
        hook_lines = _wrap(script["hook"], max_chars=20)
        hook_text = "\n".join(hook_lines)
        hook_clip = text_image(
            hook_text,
            font_size=96,
            color=WHITE,
            start=0.3, end=8.5,
            y_pos=780,
        )
        if hook_clip:
            clips.append(hook_clip)

        # ---- Tool name badge (8-35 sec) ----
        name_clip = text_image(
            tool["name"],
            font_size=64,
            color=INDIGO,
            start=8.5, end=duration,
            y_pos=280,
        )
        if name_clip:
            clips.append(name_clip)

        # ---- Content lines (8-29 sec), staggered ----
        y_positions = [500, 700, 900, 1100]
        for i, line in enumerate(script["lines"][:4]):
            line_start = 8.5 + i * 3.5
            line_end = min(duration - 4, line_start + 20)
            y = y_positions[i] if i < len(y_positions) else 500 + i * 200
            lc = text_image(
                line,
                font_size=62,
                color=WHITE,
                start=line_start, end=line_end,
                y_pos=y,
            )
            if lc:
                clips.append(lc)

        # ---- CTA (last 6 sec) ----
        cta_clip = text_image(
            script["cta"],
            font_size=58,
            color=EMERALD,
            start=duration - 6, end=duration,
            y_pos=1600,
        )
        if cta_clip:
            clips.append(cta_clip)

        # ---- Branding bar bottom ----
        brand_clip = text_image(
            "aitoolsempire.co",
            font_size=42,
            color=SLATE_400,
            start=0.0, end=duration,
            y_pos=1800,
        )
        if brand_clip:
            clips.append(brand_clip)

        # ---- Background music ----
        audio_clip = None
        try:
            audio_clip = _generate_background_audio(duration, output_path)
        except Exception as e:
            logger.warning(f"[{BOT_NAME}] Background audio failed (continuing silent): {e}")

        # ---- Compose and write ----
        final = CompositeVideoClip(clips, size=(SHORT_W, SHORT_H))
        if audio_clip is not None:
            final = final.with_audio(audio_clip)

        final.write_videofile(
            output_path,
            fps=SHORT_FPS,
            codec="libx264",
            audio=True if audio_clip is not None else False,
            audio_codec="aac" if audio_clip is not None else None,
            preset="ultrafast",
            logger=None,
        )
        logger.info(f"[{BOT_NAME}] Rendered Short: {output_path} (audio={'yes' if audio_clip else 'no'})")
        return True

    except Exception as e:
        logger.error(f"[{BOT_NAME}] render_short failed: {e}", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# YouTube upload
# ---------------------------------------------------------------------------

def _get_youtube_service():
    """Build authenticated YouTube service using stored OAuth refresh token."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=config.YOUTUBE_REFRESH_TOKEN,
            client_id=config.YOUTUBE_CLIENT_ID,
            client_secret=config.YOUTUBE_CLIENT_SECRET,
            token_uri="https://oauth2.googleapis.com/token",
        )
        service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        return service
    except Exception as e:
        logger.error(f"[{BOT_NAME}] YouTube auth failed: {e}")
        return None


def upload_short(video_path: str, tool: dict, script: dict) -> dict:
    """
    Upload video to YouTube as a Short.
    Returns {"success": bool, "video_id": str, "url": str}.
    """
    from googleapiclient.http import MediaFileUpload

    service = _get_youtube_service()
    if not service:
        return {"success": False, "video_id": None, "url": None}

    title = f"{script['hook']} | {tool['name']} {tool['emoji']} #Shorts"
    title = title[:100]  # YouTube title limit

    description = (
        f"{tool['tip']}\n\n"
        f"🔗 Full review + free trial: {tool['url']}\n\n"
        f"📋 More AI tool reviews, comparisons & deals:\n"
        f"👉 https://aitoolsempire.co\n\n"
        f"Subscribe for weekly AI tool tips! 🔔\n\n"
        f"#AITools #{tool['name'].replace(' ','')} #AI #Shorts #AITips #{tool['category'].replace(' ','')}"
    )

    tags = [
        "AI tools", tool["name"], tool["category"],
        "AI tips", "artificial intelligence", "productivity",
        "Shorts", "AI tutorial", "aitoolsempire",
    ]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "28",  # Science & Technology
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    try:
        media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
        request = service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )
        response = request.execute()
        video_id = response.get("id")
        url = f"https://www.youtube.com/shorts/{video_id}" if video_id else None
        logger.info(f"[{BOT_NAME}] Uploaded Short: {url}")
        return {"success": True, "video_id": video_id, "url": url}
    except Exception as e:
        logger.error(f"[{BOT_NAME}] Upload failed: {e}", exc_info=True)
        return {"success": False, "video_id": None, "url": None}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_youtube_shorts_bot(tool_key: str = None) -> dict:
    """
    Full pipeline: pick tool → generate script → render video → upload to YouTube.

    Args:
        tool_key: Optional tool name to force (e.g. "ElevenLabs"). Random if None.

    Returns:
        dict with keys: tool, success, video_url, render_path, error.
    """
    logger.info(f"[{BOT_NAME}] Starting YouTube Shorts pipeline")
    result = {"tool": None, "success": False, "video_url": None, "render_path": None, "error": None}

    try:
        # 1. Pick tool (avoid recently used ones if possible)
        if tool_key:
            tool = next((t for t in TOOL_ROSTER if t["name"].lower() == tool_key.lower()), None)
            if not tool:
                tool = random.choice(TOOL_ROSTER)
        else:
            tool = _pick_next_tool()

        result["tool"] = tool["name"]
        logger.info(f"[{BOT_NAME}] Chosen tool: {tool['name']}")

        # 2. Generate punchy script via Claude
        script = generate_short_script(tool)
        logger.info(f"[{BOT_NAME}] Script hook: {script['hook']}")

        # 3. Render video
        with tempfile.TemporaryDirectory() as tmp:
            video_path = os.path.join(tmp, f"short_{tool['name'].replace(' ','_')}.mp4")
            rendered = render_short(tool, script, video_path)

            if not rendered:
                result["error"] = "render_failed"
                log_bot_event(BOT_NAME, "render_failed", tool["name"])
                return result

            result["render_path"] = video_path
            logger.info(f"[{BOT_NAME}] Render complete: {video_path}")

            # 4. Upload to YouTube
            upload_result = upload_short(video_path, tool, script)
            result["success"] = upload_result["success"]
            result["video_url"] = upload_result.get("url")

        # 5. Save state + notify
        now = datetime.now(timezone.utc).isoformat()
        upsert_bot_state(BOT_NAME, "last_run", now)
        upsert_bot_state(BOT_NAME, "last_tool", tool["name"])

        if result["success"]:
            upsert_bot_state(BOT_NAME, "last_video_url", result["video_url"])
            log_bot_event(BOT_NAME, "short_uploaded", f"{tool['name']} → {result['video_url']}")
            notify(
                f"🎬 YouTube Short posted!\n"
                f"<b>{tool['name']}</b> — {tool['emoji']}\n"
                f"Hook: {script['hook']}\n"
                f"🔗 {result['video_url']}",
                level="success",
                use_telegram=True,
                use_email=False,
            )
        else:
            log_bot_event(BOT_NAME, "upload_failed", tool["name"])
            notify(
                f"⚠️ YouTube Short upload failed for <b>{tool['name']}</b>",
                level="warning",
                use_telegram=True,
                use_email=False,
            )

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[{BOT_NAME}] Pipeline error: {e}", exc_info=True)
        log_bot_event(BOT_NAME, "error", str(e))

    logger.info(f"[{BOT_NAME}] Done: {result}")
    return result


def _pick_next_tool() -> dict:
    """Pick the tool least recently used (based on bot_state)."""
    from bots.shared.db_helpers import get_bot_state
    last_tool = get_bot_state(BOT_NAME, "last_tool") or ""
    remaining = [t for t in TOOL_ROSTER if t["name"] != last_tool]
    return random.choice(remaining if remaining else TOOL_ROSTER)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="YouTube Shorts Bot")
    parser.add_argument("--tool", help="Force a specific tool name")
    parser.add_argument("--dry-run", action="store_true", help="Render only, no upload")
    args = parser.parse_args()

    if args.dry_run:
        tool = _pick_next_tool()
        script = generate_short_script(tool)
        print(f"Tool: {tool['name']}")
        print(f"Hook: {script['hook']}")
        print(f"Lines: {script['lines']}")
        print(f"CTA: {script['cta']}")
        out = f"/tmp/short_test_{tool['name'].replace(' ','_')}.mp4"
        ok = render_short(tool, script, out)
        print(f"Render {'OK' if ok else 'FAILED'}: {out}")
    else:
        result = run_youtube_shorts_bot(tool_key=args.tool)
        print(result)
