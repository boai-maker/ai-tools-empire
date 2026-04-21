"""
Caption generation — turn narration text into timed, animated word chunks.

Used by the video engine to bake big bold captions onto videos for the
captions-on-mobile retention boost. Renders via PIL into transparent PNGs
that moviepy can composite as ImageClips.
"""
import os
import sys
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.standards import get_logger

log = get_logger("captions")

# Try common system font paths
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
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


def text_to_captions(text: str, audio_duration: float,
                     words_per_chunk: int = 2) -> List[Dict]:
    """
    Split text into short impact chunks (1-4 words) evenly distributed
    across audio_duration. Short-form videos need FAST captions — each
    chunk should hit emotionally or intellectually.
    Returns [{"text": "...", "start": 0.0, "end": 0.4}, ...]
    """
    if not text or audio_duration <= 0:
        return []
    words = text.split()
    if not words:
        return []
    # Adaptive chunk size: shorter for short text, longer for paragraphs
    wpc = min(words_per_chunk, max(1, len(words) // 3))
    chunks = []
    for i in range(0, len(words), wpc):
        chunk = " ".join(words[i:i + wpc])
        if chunk:
            chunks.append(chunk.upper())  # uppercase for visual impact

    per = audio_duration / max(1, len(chunks))
    return [
        {"text": c, "start": round(i * per, 3), "end": round((i + 1) * per, 3)}
        for i, c in enumerate(chunks)
    ]


def impact_captions_to_clips(
    captions: List[str],
    duration: float,
    video_size: Tuple[int, int],
    font_size: int = 60,
    text_color: Tuple[int, int, int] = (16, 185, 129),  # Emerald green
    stroke_color: Tuple[int, int, int] = (0, 0, 0),
    stroke_width: int = 5,
) -> List:
    """
    Render standalone impact caption overlays (the ones from the script
    generator, NOT word-for-word narration). These are short punchy phrases
    like "Game changer", "Wait for it", "Free forever" that flash on screen
    at evenly-spaced intervals.

    Args:
        captions: list of short impact strings (1-6 words each)
        duration: total video duration
        video_size: (width, height)

    Returns:
        list of moviepy ImageClips ready to composite
    """
    if not captions or duration <= 0:
        return []
    # Space them evenly across the middle portion of the video
    start_at = duration * 0.15  # skip the hook section
    end_at = duration * 0.85
    span = end_at - start_at
    n = len(captions)
    interval = span / max(1, n)
    show_dur = min(1.5, interval * 0.7)  # each shows for 1.5s max

    vw, vh = video_size
    y_pos = int(vh * 0.55)  # mid-screen — above the narration captions

    clips = []
    for i, txt in enumerate(captions):
        if not txt:
            continue
        cap = {
            "text": txt.upper(),
            "start": round(start_at + i * interval, 3),
            "end": round(start_at + i * interval + show_dur, 3),
        }
        c = render_caption_clip(
            cap, video_size,
            font_size=font_size, text_color=text_color,
            stroke_color=stroke_color, stroke_width=stroke_width,
            y_pos=y_pos,
        )
        if c is not None:
            clips.append(c)
    return clips


def render_caption_clip(caption: Dict, video_size: Tuple[int, int],
                        font_size: int = 80,
                        text_color: Tuple[int, int, int] = (255, 255, 255),
                        stroke_color: Tuple[int, int, int] = (0, 0, 0),
                        stroke_width: int = 6,
                        y_pos: Optional[int] = None):
    """
    Render a single caption dict into a moviepy ImageClip.
    Returns the clip ready to composite, or None on failure.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np
        from moviepy import ImageClip
    except Exception as e:
        log.warning(f"Caption deps missing: {e}")
        return None

    text = caption.get("text", "").strip()
    if not text:
        return None

    font_path = _find_font()
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    # Measure
    tmp_img = Image.new("RGBA", (10, 10))
    draw = ImageDraw.Draw(tmp_img)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw = bbox[2] - bbox[0] + stroke_width * 2
    th = bbox[3] - bbox[1] + stroke_width * 2 + 20
    img_w = max(tw + 40, 200)
    img_h = max(th + 40, 80)

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = (img_w - tw) // 2 + stroke_width
    y = 20
    draw.text(
        (x, y), text, font=font, fill=text_color,
        stroke_width=stroke_width, stroke_fill=stroke_color,
    )

    arr = np.array(img)
    clip = ImageClip(arr, is_mask=False)
    duration = max(0.05, caption["end"] - caption["start"])
    clip = clip.with_duration(duration).with_start(caption["start"])

    vw, vh = video_size
    if y_pos is None:
        # Place captions in lower-third for vertical, lower for landscape
        y_pos = int(vh * 0.72) if vh > vw else int(vh * 0.82)
    clip = clip.with_position(("center", y_pos))
    return clip


def render_caption_overlay(captions: List[Dict], video_size: Tuple[int, int],
                           **kwargs) -> List:
    """Render a full list of captions to a list of moviepy clips."""
    clips = []
    for cap in captions:
        c = render_caption_clip(cap, video_size, **kwargs)
        if c is not None:
            clips.append(c)
    return clips


if __name__ == "__main__":
    sample = "I tested five AI voice cloning tools so you don't have to"
    chunks = text_to_captions(sample, audio_duration=6.0)
    for c in chunks:
        print(c)
