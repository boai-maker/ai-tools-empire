"""
Dominic QA sub-agent.

Scores an assembled video plan on 6 rubric dimensions. Enforces the rubric
deterministically (server-side) in addition to LLM scoring — so it can't
be gamed by a model being too nice to its own output.
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
from automation.dominic.scriptwriter import BANNED_PHRASES, _word_count

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(HERE, "prompts", "qa_agent.md")
CLAUDE_MD   = os.path.join(HERE, "CLAUDE.md")

MIN_AVG_SCORE = 8.0

PLATFORM_LENGTH_WINDOW = {
    "tiktok": (21.0, 34.0),
    "shorts": (25.0, 45.0),
    "reels":  (15.0, 30.0),
}


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


def _deterministic_checks(
    script_sections: Dict,
    chosen_hook_text: str,
    visual_plan: Dict,
    platform: str,
    recent_frameworks: List[str],
    hook_variants: List[Dict],
) -> Dict:
    """
    Server-side rubric checks. Produces floor scores that override any
    over-generous LLM rating.
    """
    floors: Dict[str, int] = {}
    fix_notes: List[str] = []

    # hook_strength
    hook_wc = _word_count(chosen_hook_text)
    if hook_wc > 9:
        floors["hook_strength"] = min(floors.get("hook_strength", 10), 4)
        fix_notes.append(f"Hook is {hook_wc} words (>9). Cut to ≤9.")
    if hook_wc == 0:
        floors["hook_strength"] = 0
        fix_notes.append("Hook is empty.")
    if chosen_hook_text and not re.search(r"\d|\bAI\b|Claude|GPT|tool|prompt|hour|week|minute|day|\$", chosen_hook_text, re.I):
        floors["hook_strength"] = min(floors.get("hook_strength", 10), 6)
        fix_notes.append("Hook lacks a specific detail (number, tool name, concrete noun).")

    # caption_readability — font floor + safe zone
    shots = (visual_plan or {}).get("shots", [])
    if shots:
        bad_fonts = [i for i, s in enumerate(shots) if s.get("font_pt", 0) < 72]
        if bad_fonts:
            floors["caption_readability"] = min(floors.get("caption_readability", 10), 5)
            fix_notes.append(f"Shots {bad_fonts} have font_pt < 72.")
    if not (visual_plan or {}).get("captions_in_safe_zone", False):
        floors["caption_readability"] = min(floors.get("caption_readability", 10), 3)
        fix_notes.append("captions_in_safe_zone=False — captions would clip on mobile UI.")

    # pacing
    cadence = (visual_plan or {}).get("cut_cadence_avg_s", 0)
    if cadence and not (1.0 <= cadence <= 2.0):
        floors["pacing"] = min(floors.get("pacing", 10), 5)
        fix_notes.append(f"Payoff cut cadence {cadence:.2f}s outside [1.0, 2.0].")

    # length
    total_s = (visual_plan or {}).get("total_duration_s", 0)
    lo, hi = PLATFORM_LENGTH_WINDOW.get(platform, (15.0, 45.0))
    if not (lo <= total_s <= hi):
        floors["length"] = min(floors.get("length", 10), 5)
        fix_notes.append(f"Total duration {total_s}s outside {platform} window [{lo}–{hi}s].")

    # brand_voice — banned phrases
    full_script = " ".join(str(script_sections.get(k, "")) for k in
                           ("hook", "stake", "payoff", "twist", "cta"))
    hits = [p for p in BANNED_PHRASES if p in full_script.lower()]
    if hits:
        floors["brand_voice"] = min(floors.get("brand_voice", 10), 3)
        fix_notes.append(f"Banned phrases present: {hits}")

    # originality — framework not used recently + hook variants diverse
    frameworks_used = [h.get("framework") for h in hook_variants if h.get("framework")]
    if len(set(frameworks_used)) < 4:
        floors["originality"] = min(floors.get("originality", 10), 6)
        fix_notes.append(f"Hook variants lack diversity: {frameworks_used}")

    chosen_framework = None
    if hook_variants:
        try:
            chosen_framework = hook_variants[0].get("framework")
        except (IndexError, AttributeError):
            pass
    if chosen_framework and chosen_framework in (recent_frameworks or []):
        floors["originality"] = min(floors.get("originality", 10), 5)
        fix_notes.append(f"Hook framework '{chosen_framework}' was used in the past 7 days.")

    return {"floors": floors, "fix_notes": fix_notes}


def evaluate(
    script_sections: Dict,
    hook_variants: List[Dict],
    chosen_hook_text: str,
    visual_plan: Dict,
    platform: str = "tiktok",
    recent_frameworks: Optional[List[str]] = None,
) -> Dict:
    """
    Score a Shorts plan. Returns:
      {
        "scores": {...},
        "average": float,
        "passed": bool,
        "fix_notes": [str, ...],
        "deterministic_floors": {...},  # what server-side checks enforced
      }
    """
    recent_frameworks = recent_frameworks or []

    system = _load_prompt() + "\n\n---\n\n## Brand context\n" + _load_brand_context()
    user_msg = json.dumps({
        "script_sections":    script_sections,
        "hook_variants":      hook_variants,
        "chosen_hook_text":   chosen_hook_text,
        "visual_plan":        visual_plan,
        "platform":           platform,
        "recent_frameworks":  recent_frameworks,
    })

    raw = ask_claude(prompt=user_msg, system=system, max_tokens=1200)
    llm_parsed = _extract_json(raw) or {}

    scores = dict(llm_parsed.get("scores", {}))
    llm_fix_notes = list(llm_parsed.get("fix_notes", []))

    # Apply deterministic floors — trust NOTHING the model scored itself if
    # a rule is objectively broken.
    checks = _deterministic_checks(
        script_sections, chosen_hook_text, visual_plan,
        platform, recent_frameworks, hook_variants,
    )
    for k, floor_score in checks["floors"].items():
        scores[k] = min(scores.get(k, 10), floor_score)

    # Ensure all six dimensions present
    for dim in ("hook_strength", "caption_readability", "pacing",
                "length", "brand_voice", "originality"):
        scores.setdefault(dim, 5)  # neutral default if LLM missed

    avg = round(sum(scores.values()) / len(scores), 2)
    passed = avg >= MIN_AVG_SCORE

    # Merge fix notes (dedup)
    all_notes = list(dict.fromkeys(llm_fix_notes + checks["fix_notes"]))
    if passed and all_notes:
        # If we're technically passing but have notes, still surface them — don't hide issues
        passed = avg >= MIN_AVG_SCORE and not checks["fix_notes"]

    result = {
        "scores":                scores,
        "average":               avg,
        "passed":                passed,
        "fix_notes":             all_notes,
        "deterministic_floors":  checks["floors"],
    }

    log_action("evaluate", "qa_agent",
               "pass" if passed else "fail",
               f"avg={avg} scores={scores} floors_hit={list(checks['floors'].keys())}")
    return result


if __name__ == "__main__":
    import pprint
    demo_script = {
        "hook":   "3 AI tools that replaced my entire editor",
        "stake":  "Each one paid for itself in a week.",
        "payoff": "First: Descript. Edit video like a doc. Second: ElevenLabs. Clones your voice. Third: Claude. Rewrites any scene in your voice.",
        "twist":  "I fired my editor last month. Revenue is up.",
        "cta":    "Save this — prompts in the pinned comment.",
    }
    demo_visual = {
        "shots": [{"start_s": 0, "end_s": 2.5, "section": "hook", "font_pt": 96}],
        "cut_cadence_avg_s": 1.6,
        "captions_in_safe_zone": True,
        "total_duration_s": 27.0,
    }
    demo_variants = [
        {"framework": "number", "text": demo_script["hook"]},
        {"framework": "contrarian", "text": "..."},
        {"framework": "curiosity_gap", "text": "..."},
        {"framework": "before_after", "text": "..."},
        {"framework": "pattern_interrupt", "text": "..."},
    ]
    pprint.pprint(evaluate(demo_script, demo_variants, demo_script["hook"], demo_visual, "tiktok"))
