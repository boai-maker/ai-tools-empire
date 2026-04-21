"""
Dominic Researcher sub-agent.

Surfaces trending hook patterns + hashtags in the AI-tools / solopreneur
niche so the Scriptwriter has context for generation.

Strict contract — returns a JSON dict matching the schema in CLAUDE.md §7.
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
PROMPT_PATH = os.path.join(HERE, "prompts", "researcher.md")
CLAUDE_MD   = os.path.join(HERE, "CLAUDE.md")


def _load_prompt() -> str:
    with open(PROMPT_PATH) as f:
        return f.read()


def _load_brand_context() -> str:
    """Load Dominic's CLAUDE.md so system prompt has brand voice."""
    try:
        with open(CLAUDE_MD) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _extract_json(raw: str) -> Optional[dict]:
    """Pull the first {...} JSON object out of the model output."""
    if not raw:
        return None
    # Strip ``` fences if present
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


def research(
    topic: str,
    persona: str = "A",
    recent_hooks_seen: Optional[List[str]] = None,
) -> Dict:
    """
    Run the Researcher sub-agent.

    Returns:
        {
          "references": [...],
          "hooks_seen": [...],
          "trending_sounds": [...],
          "trending_hashtags": [...]
        }
    On failure returns the same schema with empty lists (never raises).
    """
    recent_hooks_seen = recent_hooks_seen or []

    system = _load_prompt() + "\n\n---\n\n## Brand context\n" + _load_brand_context()

    user_msg = json.dumps({
        "topic":             topic,
        "persona":           persona,
        "recent_hooks_seen": recent_hooks_seen,
    })

    raw = ask_claude(prompt=user_msg, system=system, max_tokens=1500)
    parsed = _extract_json(raw)

    if not parsed:
        log_error("researcher", f"Failed to parse Researcher JSON: {raw[:200]}")
        return {
            "references":        [],
            "hooks_seen":        [],
            "trending_sounds":   [],
            "trending_hashtags": [],
        }

    # Shape-check — coerce to the contract schema
    result = {
        "references":        list(parsed.get("references",        [])),
        "hooks_seen":        list(parsed.get("hooks_seen",        [])),
        "trending_sounds":   list(parsed.get("trending_sounds",   [])),
        "trending_hashtags": list(parsed.get("trending_hashtags", [])),
    }
    log_action("research", "researcher", "ok",
               f"topic={topic} refs={len(result['references'])} hashtags={len(result['trending_hashtags'])}")
    return result


if __name__ == "__main__":
    import pprint
    pprint.pprint(research("Claude vs ChatGPT for coding", "A"))
