"""
Dominic Shorts Pipeline — chains the four sub-agents end-to-end.

Call sites:
  - New `generate_short()` entry point for brain.py.
  - Eval harness (automation/dominic/evals/run_eval.py) uses this directly.

The existing `tweet_gen.py` / `youtube_gen.py` generators remain untouched
for backward compat. This pipeline is specifically for Shorts (15–45s 9:16).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from automation.dominic.logger import log_action, log_error
from automation.dominic.researcher       import research
from automation.dominic.scriptwriter     import write    as write_script
from automation.dominic.visual_director  import direct   as direct_visuals
from automation.dominic.qa_agent         import evaluate as qa_evaluate


def generate_short(
    topic: str,
    persona: str = "A",
    platform: str = "tiktok",
    recent_frameworks: Optional[List[str]] = None,
    recent_hooks_seen: Optional[List[str]] = None,
    skip_research: bool = False,
) -> Dict:
    """
    Run the full Shorts pipeline for one topic.

    Returns a payload with every sub-agent's output plus an overall
    `qa_passed` flag the caller can use as a gate before publishing.
    """
    pipeline_id = f"{topic[:30]}::{persona}::{platform}"
    log_action("start", "pipeline", "start", pipeline_id)

    # 1. Researcher
    if skip_research:
        research_out = {
            "references": [], "hooks_seen": recent_hooks_seen or [],
            "trending_sounds": [], "trending_hashtags": [],
        }
    else:
        research_out = research(topic, persona, recent_hooks_seen)

    # 2. Scriptwriter
    script_out = write_script(
        topic=topic,
        persona=persona,
        references=research_out.get("references", []),
    )
    if script_out.get("error") == "parse_failed" or not script_out.get("script_full"):
        log_error("pipeline", f"Scriptwriter failed for {pipeline_id}")
        return {
            "topic": topic, "persona": persona, "platform": platform,
            "research":   research_out,
            "script":     script_out,
            "visual":     None,
            "qa":         None,
            "qa_passed":  False,
            "fix_notes":  ["script_generation_failed"],
        }

    # 3. Visual Director
    visual_out = direct_visuals(
        script_sections=script_out["script_sections"],
        estimated_runtime_s=script_out["estimated_runtime_s"],
        platform=platform,
    )

    # 4. QA
    chosen_idx  = script_out.get("chosen_hook_index", 0)
    chosen_hook = ""
    hook_variants = script_out.get("hook_variants", [])
    if hook_variants and 0 <= chosen_idx < len(hook_variants):
        chosen_hook = hook_variants[chosen_idx].get("text", "")

    qa_out = qa_evaluate(
        script_sections=script_out["script_sections"],
        hook_variants=hook_variants,
        chosen_hook_text=chosen_hook,
        visual_plan=visual_out,
        platform=platform,
        recent_frameworks=recent_frameworks,
    )

    log_action("complete", "pipeline",
               "pass" if qa_out["passed"] else "fail",
               f"{pipeline_id} avg={qa_out['average']}")

    return {
        "topic":      topic,
        "persona":    persona,
        "platform":   platform,
        "research":   research_out,
        "script":     script_out,
        "visual":     visual_out,
        "qa":         qa_out,
        "qa_passed":  qa_out["passed"],
        "fix_notes":  qa_out["fix_notes"],
    }


if __name__ == "__main__":
    import pprint
    result = generate_short("Claude vs ChatGPT for coding", "A", "tiktok")
    pprint.pprint(result)
