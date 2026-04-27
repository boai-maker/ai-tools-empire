"""
Dominic Short Renderer — consumes the 4-sub-agent pipeline output
(script + visual plan) and renders a 9:16 Short that actually honors:

  - cut cadence 1–2s from visual_director.shots
  - 9:16 safe zones (captions never in top 150px or bottom 350px on TikTok)
  - font_pt ≥ 72 with stroke + shadow for legibility on mute
  - 75-word script budget (input is already validated by scriptwriter)
  - ElevenLabs for hook/CTA, macOS `say` for body (budget-aware)

Output: MP4 at a given path. Does NOT upload.

Usage:
    from automation.dominic.render_short import render_from_pipeline
    from automation.dominic.pipeline import generate_short

    result = generate_short("Claude vs ChatGPT for coding", "A", "tiktok")
    mp4 = render_from_pipeline(result, "/tmp/sample.mp4")
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import subprocess
from moviepy import (
    VideoClip, ImageClip, ColorClip, CompositeVideoClip,
    concatenate_videoclips, AudioFileClip, concatenate_audioclips,
    TextClip,
)
from PIL import Image, ImageDraw, ImageFont

from bots.shared.standards import get_logger
from bots.shared.narration import narrate_smart

from automation.dominic.visual_director import SAFE_ZONES
from automation.dominic.logger import log_action, log_error
from automation.dominic.image_gen import generate_image

log = get_logger("dominic_renderer")

# ── Rendering constants ──────────────────────────────────────────────────────
WIDTH, HEIGHT = 1080, 1920
FPS           = 30
MIN_FONT_PT   = 72

# Section → background gradient (top→bottom RGB). Subtle visual pacing cue.
SECTION_COLORS = {
    "hook":    ((15, 23, 42),   (88, 28, 135)),   # slate → deep purple
    "stake":   ((30, 41, 59),   (30, 58, 138)),   # slate → indigo
    "payoff":  ((15, 42, 45),   (15, 118, 110)),  # slate → teal
    "twist":   ((69, 26, 3),    (194, 65, 12)),   # deep amber → orange
    "cta":     ((5, 46, 22),    (20, 83, 45)),    # forest → emerald
}

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _find_font() -> Optional[str]:
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _gradient_background(
    width: int, height: int,
    top_rgb: Tuple[int, int, int], bot_rgb: Tuple[int, int, int],
) -> Image.Image:
    """Vertical gradient as a PIL image."""
    img = Image.new("RGB", (width, height))
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(top_rgb[0] + (bot_rgb[0] - top_rgb[0]) * t)
        g = int(top_rgb[1] + (bot_rgb[1] - top_rgb[1]) * t)
        b = int(top_rgb[2] + (bot_rgb[2] - top_rgb[2]) * t)
        for x in range(width):
            img.putpixel((x, y), (r, g, b))
    return img


def _gradient_background_fast(
    width: int, height: int,
    top_rgb: Tuple[int, int, int], bot_rgb: Tuple[int, int, int],
) -> Image.Image:
    """Fast numpy-based gradient (avoids per-pixel putpixel)."""
    import numpy as np
    top = np.array(top_rgb, dtype=np.float32)
    bot = np.array(bot_rgb, dtype=np.float32)
    t   = np.linspace(0.0, 1.0, height).reshape(height, 1, 1)
    col = top + (bot - top) * t          # shape (H, 1, 3)
    arr = np.broadcast_to(col, (height, width, 3)).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def _unsplash_background(query: str, w: int = WIDTH, h: int = HEIGHT) -> Optional[str]:
    """Real photo fallback. Per CLAUDE.md §8b we want REAL imagery rather than
    synthetic gradients. Tries multiple no-auth sources in order:

      1. LoremFlickr — keyword-matched photo from Flickr Creative Commons
      2. Picsum Photos — random photo (no keyword match, but still real photo)

    Returns a downloaded JPG path on success, None on failure. Cached by
    (query, w, h) hash so repeat shots don't re-download.
    """
    import hashlib
    import requests as _rq
    from urllib.parse import quote
    cache_dir = "/Users/kennethbonnet/ai-tools-empire/bots/state/image_cache"
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha256(f"photo::{query}::{w}::{h}".encode()).hexdigest()[:16]
    cached = os.path.join(cache_dir, f"photo_{key}.jpg")
    if os.path.exists(cached) and os.path.getsize(cached) > 1024:
        return cached

    # LoremFlickr keyword-matched photo (Flickr CC). Use comma for multiple tags.
    candidates = [
        f"https://loremflickr.com/{w}/{h}/{quote(query.replace(' ', ','))}",
        # Last-resort: random Picsum photo (still real photography, satisfies §8b)
        f"https://picsum.photos/seed/{quote(query)[:30]}/{w}/{h}",
    ]
    for url in candidates:
        try:
            r = _rq.get(url, timeout=12, allow_redirects=True)
            if r.ok and len(r.content) > 1024:
                with open(cached, "wb") as f:
                    f.write(r.content)
                return cached
        except Exception as e:
            log.debug(f"photo fetch failed for {url}: {e}")
    return None


def _caption_image(
    text: str, width: int, font_pt: int,
    section: str,
    safe_top: int, safe_bottom: int,
    position: str = "center",
) -> Image.Image:
    """
    Render a caption as a transparent PIL image the size of the full frame,
    positioned inside the safe zone with stroke + shadow for legibility.
    """
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    font_path = _find_font()
    try:
        font = ImageFont.truetype(font_path, font_pt) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)

    # Measure + wrap text to fit within 80% of width (margin for safety)
    max_w = int(WIDTH * 0.85)
    words = (text or "").split()
    lines: List[str] = []
    cur: List[str] = []
    for w in words:
        test = " ".join(cur + [w])
        tw = draw.textlength(test, font=font)
        if tw > max_w and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    if not lines:
        lines = [text or ""]

    line_h = font_pt + 10
    block_h = len(lines) * line_h

    # Vertical position — always inside safe zone
    avail_top = safe_top
    avail_bot = HEIGHT - safe_bottom
    avail_h   = avail_bot - avail_top
    if position == "top":
        y0 = avail_top + int(avail_h * 0.10)
    elif position == "bottom":
        y0 = avail_bot - block_h - int(avail_h * 0.10)
    else:  # center
        y0 = avail_top + (avail_h - block_h) // 2

    # Never allow overflow into safe zones
    if y0 < avail_top:
        y0 = avail_top
    if y0 + block_h > avail_bot:
        y0 = max(avail_top, avail_bot - block_h)

    # Draw each line with stroke + drop shadow
    for i, line in enumerate(lines):
        tw = draw.textlength(line, font=font)
        x = (WIDTH - tw) // 2
        y = y0 + i * line_h
        # Drop shadow
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0, 180))
        # Stroke
        for ox, oy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            draw.text((x + ox, y + oy), line, font=font, fill=(0, 0, 0, 255))
        # Main
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    return img


def _build_shot_clip(
    shot: Dict, platform: str,
    *,
    use_ai_images: bool = True,    # default flipped 2026-04-27 per CLAUDE.md §8b
    character_anchor: str = "",
    base_seed: Optional[int] = None,
) -> VideoClip:
    """
    Compose one shot: (AI image OR Unsplash fallback OR gradient) + caption.

    Background fallback chain (per CLAUDE.md §8b — never solid-color):
      1. Pollinations AI image keyed off shot.b_roll
      2. Unsplash source.unsplash.com (no auth) keyed off the same tag
      3. Gradient (last resort — flagged in log)
    """
    duration = max(0.5, float(shot.get("end_s", 2)) - float(shot.get("start_s", 0)))
    section  = shot.get("section", "payoff")
    top_rgb, bot_rgb = SECTION_COLORS.get(section, SECTION_COLORS["payoff"])

    bg_path: Optional[str] = None
    b_roll_tag = shot.get("b_roll", "") or ""
    base_prompt = b_roll_tag.replace("_", " ").replace("-", " ").strip()

    # 1) Pollinations AI image (fast, no auth, stylised)
    if use_ai_images and base_prompt:
        caption_hint = shot.get("caption", "")
        full = f"{character_anchor}, {base_prompt}" if character_anchor else base_prompt
        if caption_hint:
            full = f"{full} — vibe: {caption_hint[:60]}"
        gen_path = generate_image(
            full,
            seed=base_seed,
            width=WIDTH, height=HEIGHT,
        )
        if gen_path and os.path.exists(gen_path):
            bg_path = gen_path

    # 2) Unsplash source endpoint (no auth) — gives REAL photos when AI fails.
    #    Per CLAUDE.md §8b, real photography beats synthetic when stylised AI
    #    isn't critical. Keyed off the same b_roll tag.
    if not bg_path and base_prompt:
        bg_path = _unsplash_background(base_prompt)

    if not bg_path:
        # Last resort — gradient. Logged so we know §8b was almost violated.
        try:
            log.warning(f"§8b fallback: no AI/Unsplash image for tag={b_roll_tag!r} — using gradient")
        except Exception:
            pass
        bg_img = _gradient_background_fast(WIDTH, HEIGHT, top_rgb, bot_rgb)
        bg_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        bg_img.save(bg_path)

    sz = SAFE_ZONES.get(platform, SAFE_ZONES["tiktok"])
    font_pt = max(MIN_FONT_PT, int(shot.get("font_pt", 96)))

    # Kinetic captions: split shot text into 1–2 word chunks across its
    # duration instead of one static caption (audit 2026-04-27 — single
    # static block is the #1 amateur tell vs pro short-form). Each chunk
    # flashes for ~0.8s. Falls back to single static if the helper fails
    # (e.g. moviepy unavailable in some venv).
    bg = ImageClip(bg_path).with_duration(duration)
    layers: List = [bg]
    caption_text = (shot.get("caption", "") or "").strip()
    used_kinetic = False
    if caption_text:
        try:
            from bots.shared.captions import text_to_captions, render_caption_overlay
            chunks = text_to_captions(caption_text, duration, words_per_chunk=2)
            kinetic_clips = render_caption_overlay(
                chunks, video_size=(WIDTH, HEIGHT),
                font_size=font_pt,
                text_color=(255, 255, 255),
                stroke_color=(0, 0, 0),
                stroke_width=8,
                y_pos=int(HEIGHT * 0.62),  # mid-low, above bottom safe-zone
            )
            if kinetic_clips:
                layers.extend(kinetic_clips)
                used_kinetic = True
        except Exception as e:
            log.debug(f"kinetic captions failed for shot, fallback to static: {e}")

    if not used_kinetic and caption_text:
        # Static-PNG fallback (legacy path)
        cap_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        _caption_image(
            text      = caption_text,
            width     = WIDTH,
            font_pt   = font_pt,
            section   = section,
            safe_top  = sz["top"],
            safe_bottom = sz["bottom"],
            position  = shot.get("caption_position", "center"),
        ).save(cap_path)
        layers.append(ImageClip(cap_path).with_duration(duration))

    return CompositeVideoClip(layers, size=(WIDTH, HEIGHT)).with_duration(duration)


def _narrate_sections(script_sections: Dict, work_dir: str) -> Tuple[str, float]:
    """
    Narrate the 5 sections (hook/stake/payoff/twist/cta). Returns (mp3_path, total_seconds).
    Uses ElevenLabs for hook+cta (budget permitting), macOS `say` for body.
    """
    segments = []
    for i, sec in enumerate(["hook", "stake", "payoff", "twist", "cta"]):
        text = (script_sections.get(sec) or "").strip()
        if not text:
            continue
        segments.append({
            "id":     sec,
            "text":   text,
            "voice":  "elevenlabs" if sec in ("hook", "cta") else "say",
            "index":  i,
        })

    narrated = narrate_smart(segments, output_dir=work_dir) or []
    if not narrated:
        raise RuntimeError("narration produced zero segments")

    # Combine via ffmpeg concat (fast, no loss)
    combined = os.path.join(work_dir, "narration.mp3")
    import shutil
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, dir=work_dir) as f:
        concat_list = f.name
        for seg in narrated:
            path = seg.get("audio_path") or seg.get("path")
            if path and os.path.exists(path):
                f.write(f"file '{path}'\n")
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
         "-c", "copy", combined],
        check=True, capture_output=True,
    )

    # Get duration
    probe = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error",
         "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
         combined],
        check=True, capture_output=True, text=True,
    )
    dur = float(probe.stdout.strip() or 0)
    return combined, dur


def render_from_pipeline(
    pipeline_result: Dict,
    output_path: str,
    *,
    use_ai_images: bool = True,    # default flipped 2026-04-27 per CLAUDE.md §8b
    character_anchor: str = "",
) -> Optional[str]:
    """
    Render a 9:16 Short from a pipeline result. Returns the output MP4 path
    on success, None on failure. Safe zones, cadence, captions all enforced.

    Background fallback chain (per CLAUDE.md §8b — never solid-color):
      1. Pollinations AI image (if use_ai_images=True, default)
      2. Unsplash source.unsplash.com (no auth)
      3. Gradient (last resort, logs §8b warning)

    `character_anchor` is prepended to every Pollinations prompt for
    visual consistency across the whole video.
    """
    script  = pipeline_result.get("script")  or {}
    visual  = pipeline_result.get("visual")  or {}
    platform = pipeline_result.get("platform") or visual.get("platform") or "tiktok"
    sections = script.get("script_sections") or {}
    shots    = visual.get("shots") or []

    # Seed-lock for visual character consistency across the whole video
    topic = pipeline_result.get("topic", "")
    base_seed = abs(hash(topic + character_anchor)) % 2**30 if use_ai_images else None

    if not shots:
        log_error("dominic_renderer", "no shots in pipeline result — cannot render")
        return None
    if not sections:
        log_error("dominic_renderer", "no script_sections in pipeline result — cannot render")
        return None

    work_dir = tempfile.mkdtemp(prefix="dominic_render_")
    log.info(f"render work_dir: {work_dir}")

    # 1. Narrate
    try:
        audio_path, audio_s = _narrate_sections(sections, work_dir)
        log.info(f"narration: {audio_s:.1f}s → {audio_path}")
    except Exception as e:
        log_error("dominic_renderer", f"narration failed: {e}")
        return None

    # 2. Rescale shot durations so visual timeline matches actual audio length
    #    (narration may be shorter/longer than visual_director's estimate)
    visual_total = sum(float(s.get("end_s", 0)) - float(s.get("start_s", 0)) for s in shots)
    scale = (audio_s / visual_total) if visual_total > 0 else 1.0
    log.info(f"visual_total={visual_total:.1f}s audio={audio_s:.1f}s scale={scale:.2f}")

    for s in shots:
        s["start_s"] = float(s.get("start_s", 0)) * scale
        s["end_s"]   = float(s.get("end_s", 0))   * scale

    # 3. Build each shot
    clips = []
    for i, shot in enumerate(shots):
        try:
            clip = _build_shot_clip(
                shot, platform,
                use_ai_images=use_ai_images,
                character_anchor=character_anchor,
                base_seed=base_seed,
            )
            clips.append(clip)
        except Exception as e:
            log_error("dominic_renderer", f"shot {i} build failed: {e}")
            return None

    if not clips:
        return None

    # 4. Concatenate + audio
    video = concatenate_videoclips(clips, method="compose")
    audio = AudioFileClip(audio_path)
    video = video.with_audio(audio)
    # Trim to audio length (avoid trailing silent frames)
    video = video.with_duration(audio.duration)

    # 5. Write MP4
    try:
        video.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger=None,
        )
    except Exception as e:
        log_error("dominic_renderer", f"moviepy write failed: {e}")
        return None
    finally:
        try:
            video.close()
        except Exception:
            pass

    log_action("render", "dominic_renderer", "ok",
               f"shots={len(clips)} duration={audio.duration:.1f}s → {output_path}")
    return output_path


if __name__ == "__main__":
    import argparse
    from automation.dominic.pipeline import generate_short

    parser = argparse.ArgumentParser()
    parser.add_argument("topic", nargs="?",
                        default="Claude vs ChatGPT for coding in 2026")
    parser.add_argument("--persona",  default="A")
    parser.add_argument("--platform", default="tiktok")
    parser.add_argument("--out",      default="/tmp/dominic_sample.mp4")
    parser.add_argument("--ai-images", action="store_true",
                        help="Generate AI backgrounds via Pollinations (faceless-story format)")
    parser.add_argument("--character", default="",
                        help="Character anchor prepended to every image prompt (e.g. 'a fluffy orange tabby cat')")
    args = parser.parse_args()

    result = generate_short(args.topic, persona=args.persona, platform=args.platform)
    result["topic"] = args.topic
    if not result.get("script", {}).get("script_full"):
        print("❌ pipeline failed to produce a script")
        sys.exit(1)

    path = render_from_pipeline(
        result, args.out,
        use_ai_images=args.ai_images,
        character_anchor=args.character,
    )
    if path:
        print(f"✅ rendered: {path}")
    else:
        print("❌ render failed")
        sys.exit(2)
