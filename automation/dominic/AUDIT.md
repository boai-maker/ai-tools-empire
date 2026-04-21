# Dominic Audit — 2026-04-21

Read-only architecture audit ahead of targeted upgrade. Scope is the
`/automation/dominic/` pipeline plus the video-render handoff in
`/bots/video_engine.py`. No code changed by this audit.

## TL;DR

Dominic is two systems loosely glued together: a **concept/metadata generator**
(Dominic proper) and a separate **video renderer** (`bots/video_engine.py`).
The handoff is `enqueue_for_video_engine()` at `automation/dominic/youtube_gen.py:369`.

Concept quality is OK but mid. Video quality (hook, pacing, captions, safe
zones, brand voice) is largely unenforced — the prompts *ask* the model to
do the right thing, nothing *verifies* it did.

Zero tests exist. No eval harness. Brand-voice, anti-slop, and hook-timing
gates are the most impactful missing pieces.

---

## 1. Pipeline map

```
crawl ─► ideas ─► generate (tweet | youtube concept) ─► score/audit
                                                             │
                                                             ▼
                                              plan (scheduler) ─► publish
                                                                      │
                                     ┌────────────────────────────────┤
                                     ▼                                ▼
                               Twitter API                 hand-off to video_engine
                                                                 (rendering)
```

### Stage-by-stage

| Stage | File | Key fn | LLM? | External API | Notes |
|---|---|---|---|---|---|
| Crawl | `crawler.py` | `run_crawl` | — | aitoolsempire.co (HTTP) | 4h cron, BeautifulSoup |
| Idea extract | `idea_engine.py` | `extract_ideas_from_article`, `batch_extract_ideas`, `generate_evergreen_ideas` | Claude Sonnet 4, 1200 tok | Anthropic | Inline prompt at L182-200; 15 hardcoded evergreen topics |
| Tweet gen | `tweet_gen.py` | `generate_tweet`, `generate_thread` | Claude Sonnet 4, 200/800 tok | Anthropic | Inline prompt L127-145; 30 hardcoded templates |
| YouTube concept | `youtube_gen.py` | `generate_full_package` | Claude Sonnet 4 ×5 (title, tags, outline, script, description) | Anthropic | max_tokens up to 3000; 10 thumbnail templates |
| Audit/score | `compliance.py` | `audit_content`, `is_duplicate_content` | — | — | Fuzzy dedup via SequenceMatcher, threshold 0.85 |
| Plan/schedule | `planner.py` | `plan_week`, `find_next_slot` | — | — | 2 tweets/day (9am,6pm ET); 1 YT draft/2d at noon |
| Publish | `publisher.py` | `publish_tweet`, `publish_youtube_draft` | — | Twitter v2, YouTube Data API | 3× retry; Telegram notifies |
| Render (downstream) | `bots/video_engine.py` | `produce`, `run_video_engine` | Claude + ElevenLabs + macOS `say` | YouTube upload | Reads `dom_content.body`; uses moviepy |
| Analytics | `analytics.py` | — | — | — | Exists but not exposed in API; reports to Telegram |
| Orchestration | `brain.py` | `morning_routine`, `posting_routine`, `evening_routine`, `weekly_routine` | — | Telegram | Pausable via `dom_config`; modes: autonomous / approval |

### LLM call budget (per full cycle)
- 1 idea extraction call per crawled article (~5-10/cycle)
- 1 evergreen idea batch
- 1 tweet call per scheduled tweet (~2)
- 5 calls per YouTube concept (title, tags, outline, script, description)
- **Total: ~15-25 Claude calls/cycle, ~$0.10-0.30/cycle**
- No prompt caching, no embedding-based dedup of similar ideas

### Inline prompts (problem: not versioned, hard to eval)
Every LLM call uses an inline f-string prompt. No `/prompts/` directory.
Notable prompts:
- `idea_engine.py:182-200` — idea extraction (Claude)
- `tweet_gen.py:127-145` — single tweet
- `youtube_gen.py:116-154` — title (generates 5, scores by heuristic)
- `youtube_gen.py:251-285` — script (max_tokens=3000, `[B-ROLL: …]` markers embedded)

---

## 2. Top 10 weaknesses vs. 2026 short-form best practices

| # | Gap | Where it lives | Impact |
|---|---|---|---|
| 1 | **No hook-length gate.** Script generator doesn't enforce hook to ≤3s or ≤10 words. | `bots/video_engine.py:169` — hook is a segment with no duration check | Viewers bounce in first 2s → poor retention |
| 2 | **Video length not enforced.** Shorts target 38s (`video_engine.py:66`) but no word-count cap on script. YT concept says "10-15 min" aspirationally. | `youtube_gen.py:237`, `video_engine.py:66-70` | Actual output length drifts |
| 3 | **Cut cadence is fixed 3.5s/scene.** Retention research says 1-2s cuts on Shorts. No B-roll-to-narration sync. | `video_engine.py:69` | Sluggish pacing reads as AI-generated |
| 4 | **No 9:16 safe zones.** Captions/graphics can overlap TikTok UI (bottom 200px, top 200px). | `bots/shared/captions` (import only) | Critical text cut off on mobile |
| 5 | **Caption legibility not validated.** No contrast ratio, no font-size floor for muted viewing. Imported but config not exposed. | `bots/shared/captions` | 85% of TikTok is watched muted — unreadable captions = bounce |
| 6 | **Brand voice is aspirational.** Prompts say "sound like a knowledgeable friend" but no banned-phrase filter, no banned-cliché list, no post-generation tone check. | `tweet_gen.py:143`, `youtube_gen.py:265` | Generates generic AI-speak |
| 7 | **No anti-slop filter.** Nothing rejects "in today's fast-paced world", "game-changer", "level up your", "here's the thing nobody talks about". | — | Dead giveaway of AI content |
| 8 | **No originality system.** Dedup is fuzzy match against past 500 own posts. Doesn't check against competitor content or online trending phrases. | `compliance.py:47-93` | Redundant content, no differentiation |
| 9 | **No test/eval harness.** Zero unit tests. No golden-input regression. No quality rubric scored programmatically. | — | Any refactor is blind |
| 10 | **No analytics loop.** `analytics.py` exists but doesn't feed back into generation (no "top-performing hook framework" memory). | `analytics.py` | Bot can't learn from what worked |

### Honorable-mention weaknesses
- 5 separate Claude calls per YT concept — could be 1-2 with structured output
- Telegram tightly coupled — silent-fails don't surface operationally
- LLM calls are not cached; same topic generated twice costs 2×
- Concurrent cycles could race on `dom_config` (no lock)

---

## 3. External dependencies

| Service | Env var | Criticality | Est. cost |
|---|---|---|---|
| Anthropic Claude (claude-sonnet-4-20250514) | ANTHROPIC_API_KEY | Hard blocker | ~$0.05-0.15/cycle |
| Twitter/X v2 | TWITTER_API_KEY + 3 more | Hard | Free tier |
| YouTube Data API | YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN | Hard | Free quotas |
| ElevenLabs (narration, hook/CTA only) | ELEVENLABS_API_KEY | Optional | ~$0.10-0.30/video |
| macOS `say` (narration body fallback) | — | Bundled | Free |
| Telegram (KennyClaude) | DOMINIC_TELEGRAM_TOKEN / CHAT_ID | Notify only | Free |
| SQLite (data.db, shared with other bots) | — | Hard | — |

Last successful run: **2026-04-21 12:39 UTC** — crashed on Anthropic credit
exhaustion (credits restored 13:56 UTC).

---

## 4. Existing tests/evals

**None.** Confirmed:
- No `tests/`, no `evals/`, no pytest.ini/tox.ini
- No eval harness, no golden inputs, no quality rubric
- Only `dominic.log` for operational visibility
- `analytics.py` exists but is Telegram-only reporting, doesn't score content

---

## 5. Recent activity (last 72h)

- 2026-04-21 12:21: 89 ideas extracted from 38 articles; dedup → 78 unique
- 2026-04-21 12:27: ~10 tweet drafts generated before credits ran out
- 2026-04-19/20: Many missed APScheduler jobs during Mac sleep (since patched)
- No rendered videos produced in this window — only metadata/drafts

Current state:
- Scheduler running (com.aitoolsempire.dominic, PID varies)
- Mode: autonomous (not approval)
- Paused: false

---

## 6. Key observations for refactor

1. Dominic is fundamentally a **metadata/script generator**. The "video"
   quality levers (hook timing, cut cadence, captions, safe zones) live in
   `bots/video_engine.py`, not here. A sub-agent refactor has to touch both.

2. The 5-call YT concept generator is the highest-leverage surface for
   prompt engineering improvements (centralized in one file).

3. Compliance module is the natural home for a QA rubric; currently it's
   just dedup + platform-rule-check. Expanding to a scoring rubric is a
   minimal-disruption addition.

4. No `/prompts/` directory exists yet — standing up one is effectively
   greenfield and doesn't risk the running bot.

5. The most dangerous refactors:
   - Touching `brain.py` (orchestration) — silent failures likely
   - Touching `publisher.py` (Twitter/YouTube posting live)
   - Touching video_engine rendering loop (long feedback cycle)

   Safer: add new modules (researcher, scriptwriter, visual_director,
   qa_agent) and call them from brain.py at clear integration points.

---

## Proposed upgrade scope (for approval before Phase 2)

Targeted additions, NOT a rewrite:

- `automation/dominic/prompts/` — extract all inline prompts to versioned files
- `automation/dominic/researcher.py` — trend/hook scraper (wrapper around existing crawler + new public-trend sources)
- `automation/dominic/scriptwriter.py` — hook-framework-aware generator; outputs 5 hook variants + word count + est. runtime
- `automation/dominic/visual_director.py` — cadence, caption style, safe-zone enforcement (hooks into `bots/video_engine.py` config)
- `automation/dominic/qa_agent.py` — rubric scorer; reject below threshold with fix notes
- `automation/dominic/CLAUDE.md` — brand voice, banned phrases, hook frameworks library
- `automation/dominic/evals/` — 10 golden inputs + Python eval runner
- `brain.py` — minimal edits to call the new sub-agents at existing seams

Existing files stay. Backward compat preserved. If anything breaks, we
revert the brain.py seams and the old pipeline continues working.
