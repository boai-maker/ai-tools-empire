# Dominic Upgrades — 2026-04-21

## What changed

### Phase 1 — Audit
- [AUDIT.md](./AUDIT.md) — full pipeline map + top 10 gaps. No code touched.

### Phase 2 — Architecture (4 sub-agents)
New modules (all additive — legacy `tweet_gen.py` / `youtube_gen.py` untouched):

- [researcher.py](./researcher.py) — surfaces trending hooks + hashtags in the niche
- [scriptwriter.py](./scriptwriter.py) — generates 5 hook variants, picks best, writes 75-word script; post-validates word count + banned-phrase hits
- [visual_director.py](./visual_director.py) — plans shot list, enforces 9:16 safe zones, checks cut cadence 1–2s
- [qa_agent.py](./qa_agent.py) — rubric scorer with **deterministic server-side floors** that override any over-generous LLM self-scoring
- [pipeline.py](./pipeline.py) — chains the four, returns `qa_passed` gate

Each sub-agent returns strict JSON matching the schema in CLAUDE.md §7.

### Phase 3 — Memory & Voice
- [CLAUDE.md](./CLAUDE.md) — brand voice rules, 22 banned phrases, 3 target personas (Side-Hustle Solopreneur / Aspiring Creator / SEO-Marketing Operator), 8 hook frameworks, platform-specific safe zones and length windows, 6-dimension QA rubric with hard pass threshold (avg ≥8.0).

### Phase 4 — Evals
- [evals/samples.json](./evals/samples.json) — 10 golden inputs
- [evals/run_eval.py](./evals/run_eval.py) — runner; exits non-zero if avg QA < 8.0
- [evals/README.md](./evals/README.md) — usage docs

Run: `python3 -m automation.dominic.evals.run_eval`

### Phase 5 — Prompts extracted
[prompts/](./prompts/) — one Markdown file per sub-agent. No inline prompts in code.

## Live smoke test (claude-vs-chatgpt-coding)
```
hook = 6 words (≤9 ✅)
length = 28.5s (21–34s ✅)
QA scores: hook=9, caption=8, pacing=9, length=10, voice=9, originality=8
avg = 8.83 (threshold 8.0 ✅)
PASSED end-to-end.
```

## Still risky / not done

1. **Not wired into brain.py yet.** The live scheduled routines (`morning_routine`, `posting_routine`) still call the legacy `tweet_gen` + `youtube_gen` paths. The new pipeline works standalone but is not autonomously producing videos yet. Wiring it into brain.py is a ~10-line change but could break the live bot — needs a scheduled blue-green cutover (see follow-ups).

2. **Researcher is stub-ish.** It currently asks Claude to synthesize trending references from training data. For real trend signals we need to wire a scraper (TikTok Creative Center, SocialBlade, or RapidAPI). Honest output: it does NOT fabricate view counts — returns `null` when unknown.

3. **No B-roll asset library.** Visual Director emits descriptive tags like `"tool_logo_montage"` but there's no mapping from tag → actual clip path yet. The downstream `bots/video_engine.py` renderer will need to resolve these.

4. **Video rendering still in `bots/video_engine.py`.** This refactor only covers the creative-decision layer. Cut cadence, caption placement, and safe zones are emitted as plans — the renderer must be updated to consume them. Right now video_engine uses its own hardcoded `scene_interval=3.5s`.

5. **Eval runs cost real $.** One full run of 10 samples ≈ $0.60 in Claude calls. Don't run in a tight loop.

## 3 follow-up experiments I'd run

1. **A/B two hook frameworks.** Generate 2 versions of the same video using different frameworks (e.g. `contrarian` vs `before_after`), post one to TikTok and one to Shorts, compare 24h watch-through. After 10 paired tests you'll know which framework performs best for your audience.

2. **Caption style split.** Same script, two renders: one with 1-word-per-frame staccato style, one with full-phrase captions. Compare completion rate. Industry lore says staccato wins; verify for your niche.

3. **Voice model shootout.** Current bot mixes ElevenLabs (hook/CTA) + macOS `say` (body). Run an eval cycle with ElevenLabs for everything (~$0.30/video) vs a cheaper TTS like Google Cloud or OpenAI. Measure drop-off at 4–6 seconds — cheap TTS usually loses viewers there.

## Recommended cutover plan (for when you want to go live)

1. Add a `generate_short_v2()` function to `brain.py` that calls `pipeline.generate_short()`.
2. In `planner.py`, gate a feature flag `cfg.use_v2_shorts_pipeline` (default False).
3. For 2 days, run both pipelines side-by-side and log QA scores.
4. When v2 has beaten v1 on ≥10 generations, flip the flag.
5. Leave the legacy modules in place for 30 days as fallback.

This keeps the running bot running and gives a rollback path.
