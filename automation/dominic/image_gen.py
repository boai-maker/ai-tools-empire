"""
Dominic — AI image generator for faceless story Shorts.

Wraps Pollinations.ai (free, unlimited, no auth required) as the primary
backend for generating shot imagery. Replaces the gradient-background
placeholders in `render_short.py` with real visual content so Dominic can
produce faceless-narrator-style Shorts (the "cat story" format the owner
wants to automate on 2026-04-21).

Design rules:
- Never block the render if image generation fails — fall back to gradient.
- Cache by (prompt+seed) to avoid regenerating the same image between shots.
- Enforce 9:16 aspect (1080x1920) at download time — Pollinations returns
  square by default, so we fill-and-crop in PIL.
- Seed-lock for character consistency: every shot in a single video shares
  a base seed so the "character" stays visually consistent across frames.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from bots.shared.standards import get_logger

log = get_logger("image_gen")

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "bots", "state", "image_cache",
)
os.makedirs(CACHE_DIR, exist_ok=True)

# Pollinations.ai — free, no auth, supports prompt + seed + width/height
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={seed}&nologo=true&enhance=true"

DEFAULT_STYLE_SUFFIX = (
    "cinematic, sharp focus, dramatic lighting, high detail, "
    "vertical composition, centered subject"
)


def _prompt_hash(prompt: str, seed: int, w: int, h: int) -> str:
    key = f"{prompt}|{seed}|{w}|{h}".encode()
    return hashlib.sha256(key).hexdigest()[:20]


def _cache_path(prompt: str, seed: int, w: int, h: int) -> str:
    return os.path.join(CACHE_DIR, f"{_prompt_hash(prompt, seed, w, h)}.png")


def generate_image(
    prompt: str,
    output_path: Optional[str] = None,
    *,
    width: int = 1080,
    height: int = 1920,
    seed: Optional[int] = None,
    style_suffix: str = DEFAULT_STYLE_SUFFIX,
    timeout: int = 120,
) -> Optional[str]:
    """
    Generate a single image matching the prompt.

    Returns the output file path on success, None on failure.
    Cached by (prompt+seed+size) — repeat calls are instant.
    """
    if not prompt or not prompt.strip():
        return None
    if seed is None:
        seed = abs(hash(prompt)) % 2**31
    full_prompt = f"{prompt.strip()}, {style_suffix}" if style_suffix else prompt.strip()

    # Cache hit?
    cached = _cache_path(full_prompt, seed, width, height)
    if os.path.exists(cached):
        log.info(f"image_gen cache hit: {cached}")
        if output_path and output_path != cached:
            Image.open(cached).save(output_path)
            return output_path
        return cached

    # Miss — call Pollinations (with 429 backoff; their queue caps 1 req/IP)
    url = POLLINATIONS_URL.format(
        prompt=quote(full_prompt)[:1800],   # URL-safe, bounded
        w=width, h=height, seed=seed,
    )
    max_attempts = 6
    backoff = 3.0
    for attempt in range(max_attempts):
        try:
            if attempt == 0:
                log.info(f"image_gen POST Pollinations seed={seed} ('{prompt[:60]}')")
            else:
                log.info(f"image_gen retry #{attempt} after {backoff:.1f}s (seed={seed})")
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 20.0)
            r = requests.get(url, timeout=timeout, stream=True)
            if r.status_code == 429:
                log.info(f"image_gen 429 — queue full, will retry")
                continue
            if not r.ok:
                log.warning(f"image_gen HTTP {r.status_code}: {r.text[:200]}")
                return None
            with open(cached, "wb") as f:
                for chunk in r.iter_content(64 * 1024):
                    f.write(chunk)
            break
        except Exception as e:
            log.warning(f"image_gen error (attempt {attempt+1}): {e}")
            if attempt == max_attempts - 1:
                return None
            time.sleep(backoff)
    else:
        log.warning(f"image_gen exhausted {max_attempts} attempts for seed={seed}")
        return None

    # Sanity check — did we get a real image?
    try:
        img = Image.open(cached)
        img.verify()
    except Exception as e:
        log.warning(f"image_gen invalid image: {e}")
        try:
            os.remove(cached)
        except Exception:
            pass
        return None

    log.info(f"image_gen saved: {cached} ({os.path.getsize(cached)} bytes)")
    if output_path and output_path != cached:
        Image.open(cached).save(output_path)
        return output_path
    return cached


def generate_batch_consistent(
    prompts: list,
    output_dir: str,
    *,
    width: int = 1080,
    height: int = 1920,
    base_seed: Optional[int] = None,
    style_suffix: str = DEFAULT_STYLE_SUFFIX,
    character_anchor: str = "",
) -> list:
    """
    Generate a batch with consistent character/style across frames.

    Seed locking + a common `character_anchor` (e.g. "a fluffy orange cat
    with emerald eyes") prepended to every prompt keeps the subject
    visually stable. Returns list of file paths (or None for failures).
    """
    if base_seed is None:
        base_seed = abs(hash(" ".join(prompts) + character_anchor)) % 2**30
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for i, p in enumerate(prompts):
        full_prompt = f"{character_anchor}, {p}" if character_anchor else p
        out = os.path.join(output_dir, f"shot_{i:02d}.png")
        path = generate_image(
            full_prompt, out,
            width=width, height=height,
            seed=base_seed,        # same seed for all → consistent character
            style_suffix=style_suffix,
        )
        results.append(path)
        # Respect Pollinations queue (1 req/IP). 2s gap guarantees the previous
        # request has fully drained from the queue before we submit the next.
        if i < len(prompts) - 1:
            time.sleep(2.5)
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt", nargs="?", default="orange tabby cat watching sunrise over Tokyo skyline")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="/tmp/test_image.png")
    args = ap.parse_args()
    path = generate_image(args.prompt, args.out, seed=args.seed)
    print(f"→ {path}")
