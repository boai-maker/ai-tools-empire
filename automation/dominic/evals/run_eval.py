"""
Dominic eval harness.

Runs the full Shorts pipeline against 10 sample inputs and scores each on:
  - hook_in_3s: hook is ≤3s spoken (≤9 words)
  - length_in_window: total duration in platform sweet spot
  - qa_average: QA agent's rubric average (target ≥8.0)

Usage:
    python3 -m automation.dominic.evals.run_eval           # all samples
    python3 -m automation.dominic.evals.run_eval --sample claude-vs-chatgpt-coding
    python3 -m automation.dominic.evals.run_eval --threshold 7.5

Exits non-zero if avg QA score < threshold (default 8.0), so CI fails the build.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import statistics
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from automation.dominic.pipeline      import generate_short
from automation.dominic.qa_agent      import PLATFORM_LENGTH_WINDOW
from automation.dominic.scriptwriter  import _word_count

HERE         = os.path.dirname(os.path.abspath(__file__))
SAMPLES_PATH = os.path.join(HERE, "samples.json")
DEFAULT_THRESHOLD = 8.0


def score_sample(result: Dict) -> Dict:
    """Extract pass/fail metrics from one pipeline result."""
    script = result.get("script") or {}
    visual = result.get("visual") or {}
    qa     = result.get("qa") or {}

    hook_text = ""
    variants = script.get("hook_variants", [])
    idx = script.get("chosen_hook_index", 0)
    if variants and 0 <= idx < len(variants):
        hook_text = variants[idx].get("text", "")

    hook_wc   = _word_count(hook_text)
    hook_ok   = 0 < hook_wc <= 9

    duration  = visual.get("total_duration_s", 0)
    platform  = result.get("platform", "tiktok")
    lo, hi    = PLATFORM_LENGTH_WINDOW.get(platform, (15.0, 45.0))
    length_ok = lo <= duration <= hi

    qa_avg    = qa.get("average", 0) if qa else 0
    qa_passed = bool(qa.get("passed", False)) if qa else False

    return {
        "hook_text":    hook_text,
        "hook_words":   hook_wc,
        "hook_in_3s":   hook_ok,
        "duration_s":   duration,
        "length_in_window": length_ok,
        "qa_average":   qa_avg,
        "qa_passed":    qa_passed,
        "fix_notes":    result.get("fix_notes", []),
    }


def run(samples: List[Dict], threshold: float) -> Dict:
    results = []
    for sample in samples:
        print(f"▶ {sample['id']}: {sample['topic'][:60]}")
        pipeline_result = generate_short(
            topic    = sample["topic"],
            persona  = sample.get("persona",  "A"),
            platform = sample.get("platform", "tiktok"),
            skip_research = True,  # eval harness: skip real research for speed/cost
        )
        score = score_sample(pipeline_result)
        score["id"]       = sample["id"]
        score["platform"] = sample.get("platform", "tiktok")
        results.append(score)

        marker = "✅" if score["qa_passed"] else "❌"
        print(f"  {marker} hook={score['hook_words']}w in3s={score['hook_in_3s']} "
              f"len={score['duration_s']}s ok={score['length_in_window']} "
              f"qa={score['qa_average']} pass={score['qa_passed']}")

    # Aggregate
    qa_scores = [r["qa_average"] for r in results if r["qa_average"] is not None]
    avg_qa    = round(statistics.mean(qa_scores), 2) if qa_scores else 0.0
    hook_pass = sum(1 for r in results if r["hook_in_3s"])
    len_pass  = sum(1 for r in results if r["length_in_window"])
    qa_pass   = sum(1 for r in results if r["qa_passed"])
    n         = len(results)

    summary = {
        "n_samples":         n,
        "hook_in_3s_pass":   hook_pass,
        "hook_in_3s_rate":   round(hook_pass / n, 2) if n else 0.0,
        "length_pass":       len_pass,
        "length_rate":       round(len_pass / n, 2) if n else 0.0,
        "qa_pass":           qa_pass,
        "qa_pass_rate":      round(qa_pass / n, 2) if n else 0.0,
        "avg_qa_score":      avg_qa,
        "threshold":         threshold,
        "build_passes":      avg_qa >= threshold,
    }

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    return {"samples": results, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample",    help="Run only one sample id")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="Min avg QA score to pass (default 8.0)")
    parser.add_argument("--out",       help="Write full results JSON to this path")
    args = parser.parse_args()

    with open(SAMPLES_PATH) as f:
        samples = json.load(f)

    if args.sample:
        samples = [s for s in samples if s["id"] == args.sample]
        if not samples:
            print(f"No sample with id {args.sample}")
            return 2

    output = run(samples, args.threshold)

    if args.out:
        with open(args.out, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nFull results → {args.out}")

    return 0 if output["summary"]["build_passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
