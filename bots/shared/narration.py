"""
Narration utility — ElevenLabs (with hard budget cap) + macOS `say` fallback.

Free-tier ElevenLabs gives you 10,000 characters/month. We track usage in
`bots/state/narration_budget.json` and reset on the 1st of each month.

When the budget is exhausted (or no API key is set), we fall back to macOS
`say` which is free, fast, and offline. `narrate_smart()` is the recommended
entry point — it uses ElevenLabs for short, high-impact lines (hook + CTA)
and `say` for the longer body to stretch the budget.
"""
import os
import sys
import shutil
import subprocess
import tempfile
from datetime import datetime
from typing import Optional, List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.standards import get_logger, load_state, save_state, STATE_DIR

log = get_logger("narration")

BUDGET_FILE = os.path.join(STATE_DIR, "narration_budget.json")
MONTHLY_CHAR_CAP = 10_000
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel

SAY_BIN = "/usr/bin/say"
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"


# ─────────────────────────────────────────────────────────────────────────────
# Budget tracking
# ─────────────────────────────────────────────────────────────────────────────

class NarrationBudget:
    """Tracks ElevenLabs character usage with a monthly hard cap."""

    def __init__(self, cap: int = MONTHLY_CHAR_CAP):
        self.cap = cap
        self._load()

    def _load(self) -> None:
        state = load_state(BUDGET_FILE)
        now = datetime.utcnow()
        period = f"{now.year}-{now.month:02d}"
        if state.get("period") != period:
            state = {"period": period, "used": 0, "history": state.get("history", [])[-12:]}
            save_state(BUDGET_FILE, state)
        self._state = state

    @property
    def used(self) -> int:
        return int(self._state.get("used", 0))

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.used)

    def can_afford(self, chars: int) -> bool:
        return chars <= self.remaining

    def spend(self, chars: int) -> None:
        self._state["used"] = self.used + chars
        save_state(BUDGET_FILE, self._state)

    def status(self) -> Dict:
        return {
            "period": self._state.get("period"),
            "used": self.used,
            "cap": self.cap,
            "remaining": self.remaining,
            "pct_used": round(100 * self.used / self.cap, 1) if self.cap else 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ElevenLabs (high quality)
# ─────────────────────────────────────────────────────────────────────────────

def narrate_elevenlabs(text: str, voice_id: Optional[str] = None,
                       output_path: Optional[str] = None) -> Optional[str]:
    """
    Synthesize text via ElevenLabs. Returns path to mp3 or None on failure.
    Decrements the monthly budget. Skips silently when no API key is set.
    """
    if not ELEVENLABS_API_KEY:
        log.debug("No ELEVENLABS_API_KEY — skipping EL narration")
        return None
    if not text:
        return None

    budget = NarrationBudget()
    chars = len(text)
    if not budget.can_afford(chars):
        log.warning(f"EL budget exhausted: needed {chars}, remaining {budget.remaining}")
        return None

    voice = voice_id or DEFAULT_VOICE_ID
    if not output_path:
        output_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name

    try:
        import requests
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        body = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        r = requests.post(url, headers=headers, json=body, timeout=60)
        if r.status_code != 200:
            log.warning(f"EL API {r.status_code}: {r.text[:200]}")
            return None
        with open(output_path, "wb") as f:
            f.write(r.content)
        budget.spend(chars)
        log.info(f"EL narrated {chars} chars → {output_path} ({budget.remaining} remaining)")
        return output_path
    except Exception as e:
        log.warning(f"EL narration failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# macOS say fallback (free, offline, unlimited)
# ─────────────────────────────────────────────────────────────────────────────

def narrate_say(text: str, voice: str = "Daniel",
                output_path: Optional[str] = None) -> Optional[str]:
    """
    Use macOS `say` to synthesize text. Outputs AIFF, then converts to mp3
    via ffmpeg. Returns path or None.
    """
    if not text:
        return None
    if not os.path.exists(SAY_BIN):
        log.warning("/usr/bin/say not available — narration disabled")
        return None

    aiff_path = tempfile.NamedTemporaryFile(suffix=".aiff", delete=False).name
    if not output_path:
        output_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name

    try:
        subprocess.run(
            [SAY_BIN, "-v", voice, "-r", "180", "-o", aiff_path, text],
            check=True, capture_output=True, timeout=120,
        )
    except Exception as e:
        log.warning(f"`say` failed: {e}")
        return None

    # Convert AIFF → MP3 via ffmpeg
    try:
        subprocess.run(
            [FFMPEG_BIN, "-y", "-i", aiff_path, "-codec:a", "libmp3lame",
             "-b:a", "128k", output_path],
            check=True, capture_output=True, timeout=120,
        )
        os.unlink(aiff_path)
        log.info(f"say narrated {len(text)} chars → {output_path}")
        return output_path
    except Exception as e:
        log.warning(f"ffmpeg conversion failed: {e}")
        # Fall back to returning the AIFF directly
        return aiff_path


# ─────────────────────────────────────────────────────────────────────────────
# Smart hybrid
# ─────────────────────────────────────────────────────────────────────────────

def narrate_smart(segments: List[Dict], output_dir: Optional[str] = None,
                  prefer_quality_for: Optional[List[str]] = None) -> List[Dict]:
    """
    Narrate a list of script segments with cost-aware quality selection.

    Args:
        segments: list of {"role": "hook|problem|tease|value|callback|payoff|cta",
                           "text": "..."}
        output_dir: where to write audio files (temp dir if None)
        prefer_quality_for: roles that should use ElevenLabs if budget allows.
                            Default: ["hook", "cta"] (small chars, big retention impact)

    Returns:
        Same list with each segment annotated with "audio_path" and "engine".
    """
    if prefer_quality_for is None:
        prefer_quality_for = ["hook", "cta"]
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="narration_")
    os.makedirs(output_dir, exist_ok=True)

    budget = NarrationBudget()
    out = []
    for i, seg in enumerate(segments):
        role = seg.get("role", "body")
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        path = os.path.join(output_dir, f"{i:02d}_{role}.mp3")

        engine = "say"
        audio_path = None
        if role in prefer_quality_for and budget.can_afford(len(text)) and ELEVENLABS_API_KEY:
            audio_path = narrate_elevenlabs(text, output_path=path)
            if audio_path:
                engine = "elevenlabs"
                budget = NarrationBudget()  # refresh after spend
        if not audio_path:
            audio_path = narrate_say(text, output_path=path)
            engine = "say"

        out.append({**seg, "audio_path": audio_path, "engine": engine})

    log.info(f"Narrated {len(out)} segments. Budget: {NarrationBudget().status()}")
    return out


if __name__ == "__main__":
    print("Budget:", NarrationBudget().status())
    sample = [
        {"role": "hook", "text": "I tested 5 AI voice tools so you don't have to."},
        {"role": "value", "text": "ElevenLabs cloned my voice in under a minute. The result was eerie."},
        {"role": "cta", "text": "Get the full review at aitoolsempire.co."},
    ]
    results = narrate_smart(sample)
    for r in results:
        print(f"  [{r['engine']}] {r['role']}: {r['audio_path']}")
