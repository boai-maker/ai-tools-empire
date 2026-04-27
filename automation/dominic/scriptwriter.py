"""
Dominic Scriptwriter sub-agent.

Generates 5 hook variants + a 75-word Shorts script for a given topic and
persona. Output conforms to the CLAUDE.md §7 schema.
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
PROMPT_PATH = os.path.join(HERE, "prompts", "scriptwriter.md")
CLAUDE_MD   = os.path.join(HERE, "CLAUDE.md")

WORDS_PER_SECOND = 2.6  # typical narration pace

BANNED_PHRASES = [
    "delve", "unleash", "game-changer", "in today's fast-paced world",
    "revolutionize", "dive in", "let's explore", "it's important to note",
    "in conclusion", "the power of", "unlock", "seamlessly", "leverage",
    "empower", "cutting-edge", "at the end of the day",
    "hey guys", "in this video", "today i want to talk about",
    "did you know that", "have you ever wondered", "thanks for watching",
]


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


def _word_count(text: str) -> int:
    return len([w for w in re.findall(r"\b[\w'-]+\b", text or "")])


def _contains_banned(text: str) -> List[str]:
    lowered = (text or "").lower()
    return [p for p in BANNED_PHRASES if p in lowered]


def _post_validate(result: Dict) -> Dict:
    """Recompute word_count + runtime; flag banned-phrase hits."""
    script = result.get("script_full", "")
    wc = _word_count(script)
    result["word_count"] = wc
    result["estimated_runtime_s"] = round(wc / WORDS_PER_SECOND, 1)
    result["banned_hits"] = _contains_banned(script)
    return result


# ─── Hook scoring (ported from bots/video_engine.py 2026-04-27) ──────
#
# Audit found scriptwriter generated 5 hook variants but trusted the LLM
# to self-pick `chosen_hook_index`. Models pick lazily — often the first
# variant or one with a question mark. This deterministic post-LLM rerank
# applies the same rubric MrBeast/TikTok hook-research repos converge on:
# specific detail + tight word count + first-person proof + tool name.

def _score_hook(text: str) -> float:
    """0.0–1.0 score. Higher = better hook for short-form."""
    if not text:
        return 0.0
    s = 0.0
    wc = _word_count(text)
    if wc <= 8:                              s += 0.25  # speakable in <3s
    elif wc <= 11:                           s += 0.10
    if any(c.isdigit() for c in text):       s += 0.20  # specific number
    if re.search(r"\b(I|me|my)\b", text):    s += 0.10  # first-person proof
    pattern_words = ("actually", "stop", "wrong", "catch", "one", "secret",
                     "nobody", "everyone", "before")
    if any(w in text.lower() for w in pattern_words): s += 0.10
    if not _contains_banned(text):           s += 0.20  # no banned phrases
    if "?" not in text[:20]:                 s += 0.05  # avoid lazy questions
    tool_names = ("claude", "chatgpt", "gpt", "cursor", "midjourney",
                  "elevenlabs", "pictory", "fliki", "rytr", "gemini", "fireflies")
    if any(t in text.lower() for t in tool_names): s += 0.10
    return round(s, 3)


def _rerank_hooks(parsed: Dict) -> Dict:
    """Override the LLM's chosen_hook_index with the highest-scored variant."""
    variants = parsed.get("hook_variants") or []
    if len(variants) < 2:
        return parsed
    scores = [_score_hook((v or {}).get("text", "")) for v in variants]
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    parsed["hook_scores"] = scores
    if parsed.get("chosen_hook_index") != best_idx:
        parsed["chosen_hook_reasoning"] = (
            f"Reranked: variant #{best_idx} scored {scores[best_idx]:.2f} "
            f"(was variant #{parsed.get('chosen_hook_index', 0)} at "
            f"{scores[parsed.get('chosen_hook_index', 0)]:.2f})"
        )
        parsed["chosen_hook_index"] = best_idx
        # Update script_sections.hook to match the new winner
        if isinstance(parsed.get("script_sections"), dict):
            parsed["script_sections"]["hook"] = variants[best_idx].get("text", "")
    return parsed


def write(
    topic: str,
    persona: str = "A",
    references: Optional[List[dict]] = None,
    framework_hint: Optional[str] = None,
) -> Dict:
    """
    Run the Scriptwriter sub-agent.

    Returns the schema in CLAUDE.md §7 — plus a `banned_hits` field added
    by post-validation so the QA agent can see our own tripwire.
    """
    system = _load_prompt() + "\n\n---\n\n## Brand context\n" + _load_brand_context()

    user_msg = json.dumps({
        "topic":          topic,
        "persona":        persona,
        "references":     references or [],
        "framework_hint": framework_hint,
    })

    raw = ask_claude(prompt=user_msg, system=system, max_tokens=2000)
    parsed = _extract_json(raw)

    if not parsed:
        log_error("scriptwriter", f"Failed to parse Scriptwriter JSON: {raw[:200]}")
        return {
            "hook_variants":        [],
            "chosen_hook_index":    0,
            "chosen_hook_reasoning": "",
            "script_sections":      {},
            "script_full":          "",
            "word_count":           0,
            "estimated_runtime_s":  0.0,
            "banned_hits":          [],
            "error":                "parse_failed",
        }

    parsed = _rerank_hooks(parsed)
    result = _post_validate(parsed)

    if result.get("banned_hits"):
        log_error("scriptwriter",
                  f"Banned phrases in script: {result['banned_hits']} — topic={topic}")
    log_action("write", "scriptwriter", "ok",
               f"topic={topic} wc={result.get('word_count')} runtime={result.get('estimated_runtime_s')}s")
    return result


if __name__ == "__main__":
    import pprint
    pprint.pprint(write("Claude vs ChatGPT for coding", "A"))
