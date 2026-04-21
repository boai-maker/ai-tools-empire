"""
Draft Video Generator — renders one comparison video and sends to Telegram.
DOES NOT upload to YouTube. Kenneth reviews first, then /approve to post.
"""
import os
import sys
import json
import re
import random
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import numpy as np
import requests

from bots.shared.standards import (
    get_logger, tg, load_state, save_state, STATE_DIR,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
)
from bots.shared.ai_client import ask_claude
from bots.shared.narration import narrate_smart, NarrationBudget, FFMPEG_BIN
from bots.shared.visual_styles import (
    compose_tool_scene, render_title_card, render_verdict_card,
    COLOR_SCHEMES, generate_marble_bg,
)

log = get_logger("draft_video")

DRAFT_STATE_FILE = os.path.join(STATE_DIR, "draft_video.json")
RENDER_DIR = os.path.join(STATE_DIR, "renders")
os.makedirs(RENDER_DIR, exist_ok=True)

WIDTH = 1080
HEIGHT = 1920
FPS = 30

# ── Color schemes rotation ──────────────────────────────────────────────────
SCHEMES = list(COLOR_SCHEMES.keys())

# ── Script generation ────────────────────────────────────────────────────────

COMPARISON_PROMPT = """You are writing a 35-second YouTube Short comparing AI tools.

Topic: {topic}
Format: Show the same prompt given to {n_tools} different AI tools, then reveal which one wins.

Return ONLY valid JSON:
{{
  "title": "short punchy title under 50 chars (e.g. Which AI writes the best code?)",
  "subtitle": "short subtitle under 30 chars",
  "prompt_shown": "the exact prompt given to each AI (under 80 chars)",
  "tools": [
    {{"name": "...", "response": "what this AI responded/produced (max 60 chars)", "score": "X/10"}},
    {{"name": "...", "response": "...", "score": "X/10"}},
    {{"name": "...", "response": "...", "score": "X/10"}},
    {{"name": "...", "response": "...", "score": "X/10"}},
    {{"name": "...", "response": "...", "score": "X/10"}}
  ],
  "winner": "name of the winning tool",
  "runner_up": "second best",
  "verdict": "one punchy sentence why the winner won (max 60 chars)",
  "narration": [
    "hook line for the opening (max 12 words)",
    "intro line: what we're testing",
    "first tool result narration",
    "second tool result narration",
    "third tool result narration",
    "fourth tool result narration",
    "fifth tool result narration",
    "verdict narration",
    "CTA: try the winner at aitoolsempire.co"
  ]
}}

Rules:
- Use REAL AI tools (ChatGPT, Grok, Gemini, Claude, Perplexity, DeepSeek, Meta AI, Copilot)
- Be honest about strengths/weaknesses
- Scores should vary (not all 8/10)
- Hook must create curiosity or tension
- Narration lines should be short (under 15 words each)
"""

TOPICS = [
    "Best AI for writing code",
    "Best AI for image generation",
    "Best AI for summarizing documents",
    "Best AI for creative writing",
    "Best AI for math and science",
    "Best AI for research",
    "Best AI chatbot for beginners",
    "Best free AI tool overall",
    "Which AI gives the most accurate answers",
    "Best AI for business emails",
]


def generate_comparison_script(topic: str = None) -> dict:
    """Generate a comparison script via Claude."""
    if not topic:
        topic = random.choice(TOPICS)
    prompt = COMPARISON_PROMPT.format(topic=topic, n_tools=5)
    raw = ask_claude(prompt, max_tokens=1500)
    if not raw:
        return {}
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(match.group(0)) if match else {}
    except Exception as e:
        log.warning(f"Script parse failed: {e}")
        return {}


# ── Rendering ────────────────────────────────────────────────────────────────

def _make_energetic_beat(duration: float, work_dir: str) -> str:
    """
    Generate a TikTok-viral style beat — upbeat, bouncy, catchy.
    Inspired by the phonk/trap/EDM-lite beats that trend on short-form.
    140 BPM, heavy 808 sub-bass, crispy hats, snare rolls, rising synth.
    """
    import wave
    sample_rate = 44100
    total = int(duration * sample_rate)
    if total <= 0:
        return ""
    t = np.linspace(0, duration, total, endpoint=False)
    bpm = 140
    beat_samples = sample_rate * 60 // bpm

    # ── 808 sub-bass (the TikTok signature sound) ────────────────────────────
    # Slides down in pitch on every hit for that bouncy phonk feel
    bass808 = np.zeros(total)
    for i in range(0, total, beat_samples * 2):
        d = min(int(sample_rate * 0.35), total - i)
        decay = np.exp(-np.linspace(0, 5, d))
        # Pitch slide from 80Hz down to 40Hz
        freq_slide = 80 * np.exp(-np.linspace(0, 1.5, d)) + 35
        phase = np.cumsum(2 * np.pi * freq_slide / sample_rate)
        bass808[i:i + d] += 0.25 * np.sin(phase) * decay
    # Add sub harmonics for that chest-rattling feel
    bass808 += 0.08 * np.sin(2 * np.pi * 55 * t)

    # ── Hard kick (punchy, short) ────────────────────────────────────────────
    kick = np.zeros(total)
    for i in range(0, total, beat_samples):
        d = min(int(sample_rate * 0.08), total - i)
        decay = np.exp(-np.linspace(0, 15, d))
        sweep = 200 * np.exp(-np.linspace(0, 8, d)) + 50
        phase = np.cumsum(2 * np.pi * sweep / sample_rate)
        kick[i:i + d] += 0.22 * np.sin(phase) * decay

    # ── Snare on beats 2 and 4 (cracking) ────────────────────────────────────
    snare = np.zeros(total)
    for beat_num, i in enumerate(range(0, total, beat_samples)):
        if beat_num % 2 == 1:  # beats 2, 4
            d = min(int(sample_rate * 0.1), total - i)
            noise = np.random.randn(d) * 0.15
            decay = np.exp(-np.linspace(0, 12, d))
            # Add tonal body to the snare
            tone = 0.08 * np.sin(2 * np.pi * 200 * np.linspace(0, d / sample_rate, d))
            snare[i:i + d] += (noise + tone) * decay

    # ── Rapid hi-hats (every 8th note, accent pattern) ───────────────────────
    hihat = np.zeros(total)
    eighth = beat_samples // 2
    for beat_num, i in enumerate(range(0, total, eighth)):
        n_len = min(int(sample_rate * 0.025), total - i)
        noise = np.random.randn(n_len)
        decay = np.exp(-np.linspace(0, 25, n_len))
        # Accent every other hit (louder/softer pattern for groove)
        vol = 0.09 if beat_num % 2 == 0 else 0.05
        hihat[i:i + n_len] += noise * decay * vol

    # ── Open hat on off-beats (longer, airy) ─────────────────────────────────
    open_hat = np.zeros(total)
    for i in range(beat_samples // 2, total, beat_samples * 2):
        d = min(int(sample_rate * 0.12), total - i)
        noise = np.random.randn(d) * 0.06
        decay = np.exp(-np.linspace(0, 8, d))
        open_hat[i:i + d] += noise * decay

    # ── Catchy synth melody (pentatonic, auto-generated) ─────────────────────
    # Pentatonic scale notes that always sound good together
    penta_freqs = [261.6, 293.7, 329.6, 392.0, 440.0,  # C4 D4 E4 G4 A4
                   523.3, 587.3, 659.3]                   # C5 D5 E5
    melody = np.zeros(total)
    note_dur = beat_samples  # one note per beat
    rng = np.random.RandomState(42)
    for i in range(0, total, note_dur):
        freq = penta_freqs[rng.randint(0, len(penta_freqs))]
        d = min(note_dur, total - i)
        note_t = np.linspace(0, d / sample_rate, d, endpoint=False)
        decay = np.exp(-np.linspace(0, 4, d))
        # Square-ish wave (more character than pure sine)
        wave_form = (
            0.06 * np.sin(2 * np.pi * freq * note_t)
            + 0.03 * np.sin(2 * np.pi * freq * 2 * note_t)  # octave
            + 0.015 * np.sin(2 * np.pi * freq * 3 * note_t)  # 5th harmonic
        )
        melody[i:i + d] += wave_form * decay

    # ── Rising tension sweep (builds energy) ─────────────────────────────────
    # White noise sweep that rises every 8 bars
    sweep = np.zeros(total)
    eight_bars = beat_samples * 4 * 8
    for start in range(0, total, eight_bars):
        rise_len = min(eight_bars, total - start)
        noise = np.random.randn(rise_len) * 0.04
        envelope = np.linspace(0, 1, rise_len) ** 2
        # Bandpass rises in frequency
        bp_freq = np.linspace(200, 4000, rise_len)
        bp_t = np.linspace(0, rise_len / sample_rate, rise_len)
        bp_osc = np.sin(np.cumsum(2 * np.pi * bp_freq / sample_rate))
        sweep[start:start + rise_len] += noise * envelope * 0.5 + bp_osc * envelope * 0.03

    # ── Mix everything ───────────────────────────────────────────────────────
    mixed = bass808 + kick + snare + hihat + open_hat + melody + sweep

    # Fade in/out
    fade = int(sample_rate * 0.3)
    mixed[:fade] *= np.linspace(0, 1, fade)
    mixed[-fade:] *= np.linspace(1, 0, fade)

    # Soft-clip for warmth (like analog saturation)
    mixed = np.tanh(mixed * 1.5) * 0.65

    # Normalize loud
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak * 0.85

    path = os.path.join(work_dir, "beat.wav")
    int16 = (mixed * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16.tobytes())
    return path


def render_draft(script: dict, output_path: str,
                 audio_mode: str = "music") -> bool:
    """
    Render a comparison video.
    audio_mode:
      "music" — no narration, energetic beat only, text captions tell the story
      "voice" — Samantha voice narration + quiet lo-fi bed
    """
    try:
        from moviepy import ImageClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
    except Exception as e:
        log.error(f"moviepy import: {e}")
        return False

    scheme = random.choice(SCHEMES)
    tools = script.get("tools", [])
    narration_lines = script.get("narration", [])

    if not tools or not narration_lines:
        log.error("Empty script — can't render")
        return False

    work_dir = os.path.dirname(output_path)

    # ── 1. Audio depends on mode ─────────────────────────────────────────────
    if audio_mode == "voice":
        # Use Samantha voice (more natural than Daniel)
        from bots.shared.narration import narrate_say
        narrated = []
        for i, line in enumerate(narration_lines):
            path = os.path.join(work_dir, f"{i:02d}_voice.mp3")
            result = narrate_say(line, voice="Samantha", output_path=path)
            narrated.append({"text": line, "audio_path": result})
        seg_durations = []
        for seg in narrated:
            p = seg.get("audio_path")
            if p and os.path.exists(p):
                seg_durations.append(max(_probe_duration(p), 1.5))
            else:
                seg_durations.append(2.5)
    else:
        # Music mode — fixed timing, no narration
        narrated = []
        seg_durations = [3.0, 2.5]  # title + intro
        for _ in tools[:5]:
            seg_durations.append(4.0)  # each tool scene
        seg_durations.extend([3.5, 2.5])  # verdict + CTA

    # ── 2. Build visual scenes ───────────────────────────────────────────────
    clips = []
    prompt_shown = script.get("prompt_shown", "")

    # Scene 0: Title card
    title_dur = sum(seg_durations[:2]) if len(seg_durations) >= 2 else 4.0
    title_frame = render_title_card(
        script.get("title", "AI Face Off"),
        script.get("subtitle", ""),
        WIDTH, HEIGHT, scheme,
    )
    clips.append(ImageClip(title_frame).with_duration(title_dur))

    # Scenes 1-5: One per tool (matches narration[2]-narration[6])
    for i, tool in enumerate(tools[:5]):
        idx = i + 2
        dur = seg_durations[idx] if idx < len(seg_durations) else 4.0
        scene_frame = compose_tool_scene(
            tool_name=f"{tool['name']}  {tool.get('score', '')}",
            prompt_text=prompt_shown,
            response_text=tool.get("response", ""),
            width=WIDTH, height=HEIGHT,
            scheme=scheme,
            seed=i * 1000,
        )
        clips.append(ImageClip(scene_frame).with_duration(dur))

    # Scene 6: Verdict card (matches narration[7] + narration[8])
    verdict_dur = sum(seg_durations[7:9]) if len(seg_durations) >= 9 else 5.0
    verdict_frame = render_verdict_card(
        winner=script.get("winner", ""),
        runner_up=script.get("runner_up", ""),
        verdict_text=script.get("verdict", ""),
        width=WIDTH, height=HEIGHT,
        scheme=scheme,
    )
    clips.append(ImageClip(verdict_frame).with_duration(verdict_dur))

    # ── 3. Concatenate visual clips ──────────────────────────────────────────
    video = concatenate_videoclips(clips, method="compose")

    # ── 4. Audio assembly ──────────────────────────────────────────────────────
    total_dur = video.duration
    audio_clips_list = []

    if audio_mode == "voice" and narrated:
        # Concatenate voice narration
        valid_audio = [s for s in narrated
                       if s.get("audio_path") and os.path.exists(s["audio_path"])]
        if valid_audio:
            concat_file = os.path.join(work_dir, "concat.txt")
            with open(concat_file, "w") as f:
                for s in valid_audio:
                    f.write(f"file '{s['audio_path']}'\n")
            combined_audio = os.path.join(work_dir, "narration.mp3")
            try:
                subprocess.run(
                    [FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0",
                     "-i", concat_file, "-c:a", "libmp3lame", "-b:a", "128k",
                     combined_audio],
                    check=True, capture_output=True, timeout=120,
                )
                audio_clips_list.append(AudioFileClip(combined_audio))
            except Exception as e:
                log.warning(f"Audio concat failed: {e}")
        # Quiet lo-fi bed under voice
        try:
            from bots.video_engine import _make_lofi_audio
            bed = _make_lofi_audio(total_dur, work_dir)
            if bed:
                audio_clips_list.append(AudioFileClip(bed).with_duration(total_dur))
        except Exception:
            pass
    else:
        # Music-only mode — energetic beat, no voice
        beat_path = _make_energetic_beat(total_dur, work_dir)
        if beat_path and os.path.exists(beat_path):
            audio_clips_list.append(AudioFileClip(beat_path).with_duration(total_dur))

    if audio_clips_list:
        video = video.with_audio(CompositeAudioClip(audio_clips_list))

    # ── 6. Write mp4 ─────────────────────────────────────────────────────────
    try:
        video.write_videofile(
            output_path, fps=FPS, codec="libx264",
            audio=bool(audio_clips_list),
            audio_codec="aac" if audio_clips_list else None,
            preset="ultrafast", logger=None,
        )
        log.info(f"Draft rendered: {output_path}")
        return True
    except Exception as e:
        log.error(f"Render failed: {e}")
        return False


def _probe_duration(path: str) -> float:
    try:
        import shutil
        ffprobe = shutil.which("ffprobe") or "ffprobe"
        out = subprocess.check_output(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            timeout=10,
        )
        return float(out.strip())
    except Exception:
        return 0.0


# ── Telegram send ────────────────────────────────────────────────────────────

def send_draft_to_telegram(video_path: str, script: dict) -> bool:
    """Send the rendered mp4 to Kenneth via Telegram sendDocument."""
    if not os.path.exists(video_path):
        log.error(f"Video not found: {video_path}")
        return False

    caption = (
        f"🎬 DRAFT — {script.get('title', 'AI Comparison')}\n"
        f"Winner: {script.get('winner', '?')}\n"
        f"Verdict: {script.get('verdict', '')}\n\n"
        f"Reply /approve to post or send feedback."
    )

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        with open(video_path, "rb") as f:
            r = requests.post(
                url,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption[:1024],
                    "parse_mode": "HTML",
                },
                files={"document": (os.path.basename(video_path), f, "video/mp4")},
                timeout=120,
            )
        ok = r.json().get("ok", False)
        if ok:
            log.info("Draft sent to Telegram")
        else:
            log.warning(f"Telegram sendDocument failed: {r.text[:300]}")
        return ok
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def generate_and_send_draft(topic: str = None,
                            audio_mode: str = "music") -> dict:
    """Full pipeline: script → render → send to Telegram.
    audio_mode: "music" (beat only) or "voice" (Samantha narration + bed)
    """
    log.info(f"Generating draft (audio={audio_mode}){' on: ' + topic if topic else ''}...")

    # 1. Script
    script = generate_comparison_script(topic)
    if not script:
        log.error("Script generation failed")
        return {"success": False, "error": "script_failed"}

    log.info(f"Script: {script.get('title')} — winner: {script.get('winner')}")

    # 2. Render
    work_dir = tempfile.mkdtemp(prefix="draft_", dir=RENDER_DIR)
    output_path = os.path.join(work_dir, "draft.mp4")
    ok = render_draft(script, output_path, audio_mode=audio_mode)
    if not ok:
        return {"success": False, "error": "render_failed"}

    # 3. Send to Telegram
    sent = send_draft_to_telegram(output_path, script)

    # 4. Save state for /approve flow
    state = {
        "draft_path": output_path,
        "script": script,
        "rendered_at": __import__("datetime").datetime.utcnow().isoformat(),
        "sent_to_telegram": sent,
        "approved": False,
    }
    save_state(DRAFT_STATE_FILE, state)

    return {
        "success": sent,
        "draft_path": output_path,
        "title": script.get("title"),
        "winner": script.get("winner"),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default=None)
    args = parser.parse_args()
    result = generate_and_send_draft(args.topic)
    print(json.dumps(result, indent=2))
