"""
Dominic Visual Director sub-agent.

Plans a shot list with cut cadence, B-roll refs, and caption placement —
enforcing 9:16 safe zones per platform.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bots.shared.ai_client import ask_claude

from automation.dominic.logger import log_action, log_error

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(HERE, "prompts", "visual_director.md")
CLAUDE_MD   = os.path.join(HERE, "CLAUDE.md")

# Safe zones in pixels (top, bottom) per platform at 1080x1920
SAFE_ZONES = {
    "tiktok": {"top": 150, "bottom": 350},
    "shorts": {"top": 120, "bottom": 380},
    "reels":  {"top": 220, "bottom": 400},
}

MIN_FONT_PT = 72
TARGET_CUT_CADENCE_MIN_S = 1.0
TARGET_CUT_CADENCE_MAX_S = 2.0


def _load_prompt() -> str:
    with open(PROMPT_PATH) as f:
        return f.read()


def _load_brand_context() -> str:
    try:
        with open(CLAUDE_MD) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _extract_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _validate_shots(shots: List[dict], total_s: float) -> Dict:
    """Check shot coverage, cut cadence, font size."""
    issues = []
    if not shots:
        return {"ok": False, "issues": ["no shots emitted"]}

    # Coverage
    if shots[0].get("start_s", 0) > 0.1:
        issues.append(f"first shot starts at {shots[0].get('start_s')}s, expected 0")
    if abs(shots[-1].get("end_s", 0) - total_s) > 1.0:
        issues.append(f"last shot ends at {shots[-1].get('end_s')}s, expected ~{total_s}")

    # Font size
    for i, s in enumerate(shots):
        if s.get("font_pt", 0) < MIN_FONT_PT:
            issues.append(f"shot {i} font_pt={s.get('font_pt')} < {MIN_FONT_PT}")

    # Cut cadence on payoff+twist only
    payoff_shots = [s for s in shots if s.get("section") in ("payoff", "twist")]
    if payoff_shots:
        durations = [s.get("end_s", 0) - s.get("start_s", 0) for s in payoff_shots]
        avg = sum(durations) / len(durations) if durations else 0
        if not (TARGET_CUT_CADENCE_MIN_S <= avg <= TARGET_CUT_CADENCE_MAX_S):
            issues.append(f"payoff cut cadence avg={avg:.2f}s outside [1.0, 2.0]")

    return {"ok": not issues, "issues": issues}


def direct(
    script_sections: Dict,
    estimated_runtime_s: float,
    platform: str = "tiktok",
) -> Dict:
    """
    Run the Visual Director sub-agent.
    """
    platform = platform.lower() if platform else "tiktok"
    if platform not in SAFE_ZONES:
        platform = "tiktok"

    system = _load_prompt() + "\n\n---\n\n## Brand context\n" + _load_brand_context()

    user_msg = json.dumps({
        "script_sections":     script_sections,
        "estimated_runtime_s": estimated_runtime_s,
        "platform":            platform,
        "safe_zone":           SAFE_ZONES[platform],
    })

    raw = ask_claude(prompt=user_msg, system=system, max_tokens=2000)
    parsed = _extract_json(raw)

    if not parsed:
        log_error("visual_director", f"Failed to parse VD JSON: {raw[:200]}")
        return {
            "shots":                  [],
            "cut_cadence_avg_s":      0.0,
            "captions_in_safe_zone":  False,
            "aspect_ratio":           "9:16",
            "platform":               platform,
            "total_duration_s":       estimated_runtime_s,
            "validation_issues":      ["parse_failed"],
        }

    # Post-validate server-side (model self-reports aren't trustworthy)
    validation = _validate_shots(parsed.get("shots", []), estimated_runtime_s)
    parsed["validation_issues"] = validation["issues"]
    parsed.setdefault("platform", platform)
    parsed.setdefault("aspect_ratio", "9:16")
    parsed.setdefault("total_duration_s", estimated_runtime_s)

    log_action("direct", "visual_director",
               "pass" if validation["ok"] else "fail",
               f"platform={platform} shots={len(parsed.get('shots', []))} issues={validation['issues']}")
    return parsed


if __name__ == "__main__":
    import pprint
    demo = {
        "hook":   "3 AI tools that replaced my entire editor",
        "stake":  "Each one paid for itself in a week.",
        "payoff": "First: Descript. It transcribes video and lets you edit by text. Second: ElevenLabs. Clones your voice for narration. Third: Claude. Rewrites any scene in your style.",
        "twist":  "I fired my editor last month. Revenue is up.",
        "cta":    "Save this — the prompts are in the pinned comment.",
    }
    pprint.pprint(direct(demo, 28.0, "tiktok"))
