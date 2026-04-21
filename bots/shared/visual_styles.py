"""
Visual Styles — dramatic backgrounds + UI mockup cards for video rendering.

Replaces the old flat gradient backgrounds with:
  • Marble/fluid textures (numpy noise)
  • Phone-screen mockup cards (PIL) that look like AI chat interfaces
  • Title cards and verdict cards for comparisons
"""
import os
import sys
import math
import textwrap
from typing import Tuple, Optional, List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# ── Font discovery ───────────────────────────────────────────────────────────
_BOLD_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_REGULAR_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _find_font(candidates: list) -> Optional[str]:
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _find_font(_BOLD_FONTS if bold else _REGULAR_FONTS)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ── Color schemes ────────────────────────────────────────────────────────────
COLOR_SCHEMES = {
    "crimson_marble": {
        "bg_dark": (15, 5, 8),
        "bg_accent": (140, 20, 30),
        "bg_mid": (60, 10, 15),
        "card_bg": (25, 25, 30),
        "card_border": (180, 40, 50),
        "text_primary": (255, 255, 255),
        "text_secondary": (180, 180, 190),
        "accent": (255, 60, 80),
        "prompt_bg": (45, 45, 55),
        "response_bg": (30, 30, 38),
    },
    "ocean_deep": {
        "bg_dark": (5, 10, 25),
        "bg_accent": (20, 80, 160),
        "bg_mid": (10, 30, 70),
        "card_bg": (15, 20, 40),
        "card_border": (40, 120, 220),
        "text_primary": (240, 245, 255),
        "text_secondary": (150, 170, 200),
        "accent": (60, 140, 255),
        "prompt_bg": (25, 35, 60),
        "response_bg": (18, 25, 48),
    },
    "emerald_dark": {
        "bg_dark": (5, 15, 10),
        "bg_accent": (16, 120, 80),
        "bg_mid": (8, 50, 35),
        "card_bg": (15, 28, 22),
        "card_border": (16, 185, 129),
        "text_primary": (240, 255, 248),
        "text_secondary": (150, 200, 175),
        "accent": (16, 230, 150),
        "prompt_bg": (20, 42, 35),
        "response_bg": (12, 32, 25),
    },
    "purple_noir": {
        "bg_dark": (12, 5, 20),
        "bg_accent": (100, 30, 150),
        "bg_mid": (40, 15, 65),
        "card_bg": (22, 15, 35),
        "card_border": (140, 60, 200),
        "text_primary": (245, 240, 255),
        "text_secondary": (180, 160, 200),
        "accent": (180, 80, 255),
        "prompt_bg": (35, 25, 55),
        "response_bg": (25, 18, 42),
    },
    "sunset_gold": {
        "bg_dark": (20, 10, 5),
        "bg_accent": (200, 100, 20),
        "bg_mid": (80, 40, 10),
        "card_bg": (30, 22, 15),
        "card_border": (240, 160, 40),
        "text_primary": (255, 250, 240),
        "text_secondary": (200, 180, 150),
        "accent": (255, 180, 40),
        "prompt_bg": (45, 35, 22),
        "response_bg": (35, 28, 18),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Marble / fluid background
# ─────────────────────────────────────────────────────────────────────────────
def _perlin_noise(width: int, height: int, scale: float = 0.01,
                  octaves: int = 4, seed: int = 0) -> np.ndarray:
    """Simple fractal noise using layered sine waves (fast, no deps)."""
    rng = np.random.RandomState(seed)
    result = np.zeros((height, width), dtype=np.float64)
    y_coords = np.arange(height).reshape(-1, 1)
    x_coords = np.arange(width).reshape(1, -1)
    for i in range(octaves):
        freq = scale * (2 ** i)
        amp = 1.0 / (1.5 ** i)
        phase_x = rng.uniform(0, 2 * math.pi)
        phase_y = rng.uniform(0, 2 * math.pi)
        angle = rng.uniform(0, math.pi)
        result += amp * np.sin(
            freq * (x_coords * math.cos(angle) + y_coords * math.sin(angle))
            + phase_x
        )
        result += amp * 0.5 * np.sin(
            freq * 1.7 * (x_coords * math.sin(angle) - y_coords * math.cos(angle))
            + phase_y
        )
    # Normalize to 0-1
    result = (result - result.min()) / max(result.max() - result.min(), 1e-6)
    return result


def generate_marble_bg(width: int, height: int,
                       scheme: str = "crimson_marble",
                       seed: Optional[int] = None) -> np.ndarray:
    """
    Generate a dramatic marble/fluid texture background.
    Returns numpy array (H, W, 3) uint8 suitable for moviepy ImageClip.
    """
    if seed is None:
        seed = np.random.randint(0, 10000)
    colors = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["crimson_marble"])
    dark = np.array(colors["bg_dark"], dtype=np.float64)
    mid = np.array(colors["bg_mid"], dtype=np.float64)
    accent = np.array(colors["bg_accent"], dtype=np.float64)

    # Two noise layers for depth
    noise1 = _perlin_noise(width, height, scale=0.005, octaves=5, seed=seed)
    noise2 = _perlin_noise(width, height, scale=0.012, octaves=3, seed=seed + 42)

    # Vertical gradient bias (darker at top, lighter at bottom)
    v_grad = np.linspace(0, 1, height).reshape(-1, 1)
    v_grad = np.broadcast_to(v_grad, (height, width))

    # Blend: dark base → mid via noise1, accent veins via noise2
    blend1 = noise1 * 0.6 + v_grad * 0.4
    frame = np.zeros((height, width, 3), dtype=np.float64)
    for c in range(3):
        frame[:, :, c] = dark[c] + (mid[c] - dark[c]) * blend1

    # Add accent veins where noise2 is high
    vein_mask = np.clip((noise2 - 0.55) * 4.0, 0, 1)
    for c in range(3):
        frame[:, :, c] += (accent[c] - frame[:, :, c]) * vein_mask * 0.7

    return np.clip(frame, 0, 255).astype(np.uint8)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tool comparison card (chat UI mockup)
# ─────────────────────────────────────────────────────────────────────────────
def render_tool_card(
    tool_name: str,
    prompt_text: str,
    response_text: str,
    card_w: int = 900,
    card_h: int = 1200,
    scheme: str = "crimson_marble",
) -> Image.Image:
    """
    Render a PIL image that looks like a phone chat UI card.
    Dark rounded rectangle with tool name header, user prompt bubble,
    AI response bubble.
    """
    colors = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["crimson_marble"])
    img = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Card background — rounded rectangle
    margin = 20
    draw.rounded_rectangle(
        [margin, margin, card_w - margin, card_h - margin],
        radius=30,
        fill=colors["card_bg"] + (240,),
        outline=colors["card_border"] + (200,),
        width=3,
    )

    font_title = _load_font(52, bold=True)
    font_body = _load_font(36)
    font_label = _load_font(28)

    y = 50

    # Tool name header
    draw.text((card_w // 2, y), tool_name, font=font_title,
              fill=colors["accent"], anchor="mt")
    y += 80

    # Thin separator
    draw.line([(60, y), (card_w - 60, y)], fill=colors["card_border"] + (100,), width=2)
    y += 30

    # "You" label
    draw.text((60, y), "You", font=font_label, fill=colors["text_secondary"])
    y += 35

    # Prompt bubble
    prompt_lines = textwrap.wrap(prompt_text, width=38)
    prompt_h = len(prompt_lines) * 42 + 30
    draw.rounded_rectangle(
        [50, y, card_w - 50, y + prompt_h],
        radius=18,
        fill=colors["prompt_bg"] + (220,),
    )
    for i, line in enumerate(prompt_lines):
        draw.text((70, y + 15 + i * 42), line, font=font_body,
                  fill=colors["text_primary"])
    y += prompt_h + 25

    # AI label
    draw.text((60, y), tool_name, font=font_label, fill=colors["accent"])
    y += 35

    # Response bubble
    response_lines = textwrap.wrap(response_text, width=38)
    response_h = len(response_lines) * 42 + 30
    max_resp_h = card_h - y - 60
    if response_h > max_resp_h:
        response_h = max_resp_h
        response_lines = response_lines[:max(1, max_resp_h // 42)]
    draw.rounded_rectangle(
        [50, y, card_w - 50, y + response_h],
        radius=18,
        fill=colors["response_bg"] + (220,),
    )
    for i, line in enumerate(response_lines):
        draw.text((70, y + 15 + i * 42), line, font=font_body,
                  fill=colors["text_primary"])

    return img


# ─────────────────────────────────────────────────────────────────────────────
# 3. Title card
# ─────────────────────────────────────────────────────────────────────────────
def render_title_card(
    title: str,
    subtitle: str = "",
    width: int = 1080,
    height: int = 1920,
    scheme: str = "crimson_marble",
) -> np.ndarray:
    """Render a full-frame title card with marble background."""
    bg = generate_marble_bg(width, height, scheme)
    img = Image.fromarray(bg)
    draw = ImageDraw.Draw(img)
    colors = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["crimson_marble"])

    font_big = _load_font(88, bold=True)
    font_sub = _load_font(48)

    # Title — centered, multiline
    title_lines = textwrap.wrap(title, width=18)
    total_h = len(title_lines) * 110
    y_start = (height - total_h) // 2 - 50
    for i, line in enumerate(title_lines):
        draw.text(
            (width // 2, y_start + i * 110), line,
            font=font_big, fill=colors["text_primary"],
            anchor="mt", stroke_width=4,
            stroke_fill=(0, 0, 0),
        )

    if subtitle:
        draw.text(
            (width // 2, y_start + total_h + 40), subtitle,
            font=font_sub, fill=colors["accent"],
            anchor="mt",
        )

    return np.array(img)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Verdict card
# ─────────────────────────────────────────────────────────────────────────────
def render_verdict_card(
    winner: str,
    runner_up: str = "",
    verdict_text: str = "",
    width: int = 1080,
    height: int = 1920,
    scheme: str = "crimson_marble",
) -> np.ndarray:
    """Render a verdict/winner announcement frame."""
    bg = generate_marble_bg(width, height, scheme, seed=9999)
    img = Image.fromarray(bg)
    draw = ImageDraw.Draw(img)
    colors = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["crimson_marble"])

    font_label = _load_font(52)
    font_winner = _load_font(96, bold=True)
    font_verdict = _load_font(42)

    cy = height // 2 - 120

    # "WINNER" label
    draw.text(
        (width // 2, cy), "WINNER",
        font=font_label, fill=colors["text_secondary"],
        anchor="mt",
    )

    # Winner name — big and bold
    draw.text(
        (width // 2, cy + 80), winner,
        font=font_winner, fill=colors["accent"],
        anchor="mt", stroke_width=5, stroke_fill=(0, 0, 0),
    )

    # Verdict text
    if verdict_text:
        lines = textwrap.wrap(verdict_text, width=30)
        for i, line in enumerate(lines):
            draw.text(
                (width // 2, cy + 220 + i * 55), line,
                font=font_verdict, fill=colors["text_primary"],
                anchor="mt",
            )

    # Runner up
    if runner_up:
        draw.text(
            (width // 2, cy + 380), f"Runner-up: {runner_up}",
            font=font_label, fill=colors["text_secondary"],
            anchor="mt",
        )

    return np.array(img)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Scene composer — combine marble bg + tool card into one frame
# ─────────────────────────────────────────────────────────────────────────────
def compose_tool_scene(
    tool_name: str,
    prompt_text: str,
    response_text: str,
    width: int = 1080,
    height: int = 1920,
    scheme: str = "crimson_marble",
    seed: Optional[int] = None,
) -> np.ndarray:
    """
    Full scene: marble background + centered tool card.
    Returns numpy array ready for moviepy ImageClip.
    """
    bg = generate_marble_bg(width, height, scheme, seed=seed)
    bg_img = Image.fromarray(bg)

    card_w = int(width * 0.88)
    card_h = int(height * 0.55)
    card = render_tool_card(
        tool_name, prompt_text, response_text,
        card_w, card_h, scheme,
    )

    # Center the card
    x = (width - card_w) // 2
    y = (height - card_h) // 2 - 40
    bg_img.paste(card, (x, y), card)

    return np.array(bg_img)


if __name__ == "__main__":
    # Quick test
    frame = generate_marble_bg(1080, 1920, "crimson_marble")
    print(f"Marble bg: {frame.shape}")
    scene = compose_tool_scene(
        "ChatGPT", "Generate an image of a sunset",
        "Here's a beautiful sunset over the ocean with golden light...",
    )
    print(f"Tool scene: {scene.shape}")
    title = render_title_card("Which AI Makes the Best Images?", "5 AIs Face Off")
    print(f"Title card: {title.shape}")
    verdict = render_verdict_card("ChatGPT", "Grok 3", "Best quality and most creative output")
    print(f"Verdict card: {verdict.shape}")
    # Save test
    Image.fromarray(scene).save("/tmp/test_scene.png")
    print("Saved /tmp/test_scene.png")
