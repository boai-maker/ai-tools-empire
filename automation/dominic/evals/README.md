# Dominic Evals

Regression harness for Dominic's Shorts pipeline. Runs the full
Researcher → Scriptwriter → Visual Director → QA flow against 10 sample
inputs and scores each on hook-in-3s, length-in-window, and QA rubric
average.

## Run

```bash
# All 10 samples (costs ~$0.50-1.50 in Claude API calls)
python3 -m automation.dominic.evals.run_eval

# One sample, faster
python3 -m automation.dominic.evals.run_eval --sample claude-vs-chatgpt-coding

# Relaxed threshold (e.g. during iteration)
python3 -m automation.dominic.evals.run_eval --threshold 7.0

# Dump full results to disk
python3 -m automation.dominic.evals.run_eval --out /tmp/dominic_eval_$(date +%Y%m%d).json
```

Exits **non-zero** if average QA score across all samples < threshold
(default 8.0). Wire this into CI/pre-commit to prevent regression.

## Samples

Stored in `samples.json`. Each sample is `{id, topic, persona, platform}`.
Adding a sample? Make sure it exercises a real content axis:
comparisons, reviews, how-to, contrarian takes, money-related hooks.

## What's scored

| Metric | Definition | Target |
|---|---|---|
| `hook_in_3s` | Chosen hook ≤9 words (≈3s spoken) | 100% pass |
| `length_in_window` | Total duration in platform sweet spot | 100% pass |
| `qa_average` | QA agent's 6-dim rubric average | ≥8.0 |

## Cost note

Each sample fires 4 Claude calls (researcher skipped by default with
`skip_research=True` to save cost + avoid hallucinated references).
At ~$0.015/call that's ~$0.06/sample = ~$0.60 for a full run.

Run the full eval weekly. Run single-sample after prompt edits.
