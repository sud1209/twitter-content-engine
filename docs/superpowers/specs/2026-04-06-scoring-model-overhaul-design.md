# Scoring & Model Overhaul — Design Spec

**Date:** 2026-04-06
**Status:** Approved

---

## Goal

Port the scoring pipeline, model abstraction, and benchmark utility from `twitter-bot` into `twitter-content-engine`, adapted for Sud's content pillars and voice. Reduces token cost, improves post quality signal, and makes the system model-agnostic.

---

## Scope

Sub-projects covered:
1. Model abstraction (`llm_client.py`)
2. Scoring overhaul (`post_scorer.py`) — batch scoring, upgraded rubric, TOFU-only
3. Generation overhaul (`content_generator.py`) — playbook distillation, `validate_post()`, benchmark injection
4. Benchmark utility (`benchmark_analyzer.py`) — standalone, config-driven, PII-free

---

## Files Changed

| File | Change |
|---|---|
| `scripts/llm_client.py` | **New** — provider-agnostic `complete()` wrapper |
| `scripts/post_scorer.py` | Overhaul — batch scoring, upgraded rubric, Anthropic via llm_client |
| `scripts/content_generator.py` | Overhaul — playbook distillation, validate_post, llm_client, benchmark injection |
| `scripts/benchmark_analyzer.py` | **New** — ported from twitter-bot, config-driven, standalone utility |
| `config.json` | Add `"models"` and `"benchmark_accounts"` keys |
| `.env.example` | `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` |
| `CLAUDE.md` | Update model references and `.env` section |

---

## Component Design

### 1. `scripts/llm_client.py` (new)

Single public function:

```python
def complete(model: str, system: str, user: str, max_tokens: int = 2000) -> str:
```

- Routes by model name prefix: `model.startswith("claude")` → `anthropic.Anthropic`, reads `ANTHROPIC_API_KEY`
- Otherwise → `openai.OpenAI`, reads `OPENAI_API_KEY`
- Returns plain string (response text)
- No SDK objects exposed to callers
- Both SDKs remain in `pyproject.toml`; only the active provider's key needs to be set in `.env`

**Config changes (`config.json`):**
```json
"models": {
  "generation": "claude-haiku-4-5-20251001",
  "scoring": "claude-haiku-4-5-20251001"
}
```

Callers read `get_config()["models"]["generation"]` / `["scoring"]` and pass to `llm_client.complete()`.

---

### 2. `scripts/post_scorer.py` (overhaul)

#### Thresholds
```python
QUALITY_FLOOR = 8.0
TARGET_THRESHOLD = 9.25
MAX_REGENERATION_ATTEMPTS = 2
```

Status labels: `ready` (≥9.25), `below_target` (<9.25 but ≥8.0), `failed_floor` (<8.0, only surfaced as `below_target` after exhaustion)

#### Dimensions (6, TOFU-only, weights sum to 100)

| Dimension | Weight | Description |
|---|---|---|
| `hook_strength` | 25 | Harry Dry 3 tests: visualizable, falsifiable, nobody else can say this. 9+ requires all 3. |
| `tone_compliance` | 20 | Six Core Laws + ZERO hashtags, emdashes, exclamation marks, hedging. Any hashtag = 0. |
| `x_algorithm_optimization` | 20 | Reply=27x like. 9+ = ZERO hashtags + specific falsifiable claim someone argues back at. |
| `data_specificity` | 15 | Named companies, concrete numbers, falsifiable outcomes. Abstract = 6/10 max. |
| `pillar_alignment` | 15 | Pillar clear in first sentence. Vague = 6/10 max. |
| `cta_quality` | 5 | TOFU: no hard sell, no link push. Soft engagement (reply, follow) or none scores highest. DM push = low. |

No `funnel_stage_accuracy` dimension — all posts are TOFU.

#### Scoring rubric prompt (constant `SCORING_RUBRIC`)
Compact single string injected once per batch. Includes:
- Dimension descriptions with score anchors
- `CRITICAL: If post contains ANY hashtag (#), mark never_list_violation = true`
- X algorithm weights (Reply=27x, Repost=20x)

#### Regen hard rules (constant `REGEN_HARD_RULES`)
Injected into batch regeneration prompt:
- ZERO hashtags, emdashes, exclamation marks
- No soft CTAs
- Four reframe techniques: COMPETITIVE DISADVANTAGE, TRUTH NOBODY ADMITS, TIMESTAMP OBSOLESCENCE, INVERSE RISK (adapted to Sud's voice/pillars — no Nik-specific data points)

#### Batch pipeline

```python
def _build_shared_scoring_context() -> str:
    # rubric + benchmark hook_patterns (graceful) + calibration (graceful)

def batch_score_posts(posts: list[dict]) -> list[dict]:
    # single API call, returns JSON array, applies +0.5 calibration offset

def batch_regenerate_posts(failing_posts: list[dict], trend_context: str) -> list[dict]:
    # single API call with REGEN_HARD_RULES, returns revised texts

def score_all_posts(posts: list[dict]) -> list[dict]:
    # orchestrates: batch score → batch regen failing → batch rescore
    # max 4 API calls total regardless of post count

def regenerate_if_below_floor(post: dict) -> dict:
    # legacy single-post wrapper → calls score_all_posts([post])[0]
    # kept for backwards compatibility with server.py
```

#### Composite score
```python
total = sum(scores[dim] * weight/100 for dim in DIMENSIONS)
total += 0.5  # calibration offset
```
Returns 0.0 on `never_list_violation = true`.

---

### 3. `scripts/content_generator.py` (overhaul)

#### Playbook distillation (major token saving)

```python
_DISTILLED_PATH = "data/playbook_distilled.json"

def distill_playbooks() -> None:
    # One-time Haiku call. Compresses ~4,500 token playbooks to ~1,000 tokens.
    # Caches to data/playbook_distilled.json.
    # Call manually once, or on first run if distilled file absent.

def load_playbooks() -> dict[str, str]:
    # Loads distilled version if available, falls back to full playbooks.
    # Keys: "voice", "twitter", "strategy"
```

#### Post validation

```python
def validate_post(text: str) -> tuple[bool, str]:
```

Hard rejects (return `False, reason`):
- Any `#` or `＃` character → `"contains_hashtags"`
- Em-dash `—` → `"contains_emdash"`
- Soft question in final 80 chars: `"what's your "`, `"how are you "`, `"what are you "`, `"how do you "`, `"are your"` → `"soft_qa_cta"`
- Known weak CTA phrases anywhere: `"what do you think"`, `"share your thoughts"`, `"let's discuss"`, etc. → `"weak_cta:{phrase}"`

`generate()` filters all drafts through `validate_post()` before returning. Filtered posts are logged.

#### LLM switch
- `from openai import OpenAI` removed
- `from scripts.llm_client import complete as llm_complete`
- Model: `get_config()["models"]["generation"]`
- `generate()` uses `llm_complete(model, system, user_message, max_tokens=2000)`

#### Benchmark injection (graceful)
```python
def _load_benchmark_insights() -> dict | None:
    # Returns None if data/benchmark_insights.json absent or malformed
```

Injected into `build_system_prompt()` if available:
- `hook_patterns[:3]`
- `cta_patterns[:3]`
- `engagement_drivers[:3]`
- `reply_triggers[:3]` (if present)
- Top 3 posts by weighted score with reply/retweet/like breakdown

Benchmark accounts in injection text use `config["benchmark_accounts"]` values (not hardcoded).

#### System prompt
- Debate-baiting section adapted from twitter-bot with **Sud's pillar-agnostic framing** (no Nik-specific data points like `$2k → $80`, CMBS, Non-QM)
- Four adversarial frames retained: COMPETITIVE DISADVANTAGE, TRUTH NOBODY ADMITS, TIMESTAMP OBSOLESCENCE, INVERSE RISK
- Length note: posts can be any length; longer is better when it adds data, context, or before/after contrast
- TOFU CTA rule: awareness/follow/debate-bait only. No DM pushes, no link drops.

---

### 4. `scripts/benchmark_analyzer.py` (new, standalone)

Ported from twitter-bot with these adaptations:
- No hardcoded handles; reads `config["benchmark_accounts"]` (already `["Iyervval", "ruchirsharma_1", "mujifren"]`)
- `fetch_own_stats()` replaces `fetch_nik_stats()` — uses `config["handle"]` in URL construction, no PII
- `benchmark_insights.json` — `"source_accounts"` field uses config values; `top_posts[].url` uses `config["handle"]`; no account-specific PII in pattern strings
- Insight extraction uses `llm_client.complete()` with `config["models"]["scoring"]`
- **Not wired to scheduler or pipeline** — run manually: `uv run python -m scripts.benchmark_analyzer`
- When `benchmark_insights.json` is present, scorer and generator pick it up automatically on next run

#### Output files
- `data/benchmark_report.json` — per-account stats + gaps vs Sud's published posts
- `data/benchmark_insights.json` — patterns extracted by Haiku; consumed by scorer and generator

#### PII scrub checklist
- No `NikhaarShah` anywhere
- No `businessbarista`, `gregisenberg`, `thedankoe` (those are Nik's benchmarks)
- `top_posts[].url` uses `https://x.com/{config["handle"]}/status/{id}` for own posts
- Benchmark post URLs: `https://x.com/{handle}/status/{id}` (handle from config list, no hardcoding)

---

## Config Changes

**`config.json`** — add two new top-level keys:
```json
"models": {
  "generation": "claude-haiku-4-5-20251001",
  "scoring": "claude-haiku-4-5-20251001"
},
"benchmark_accounts": ["Iyervval", "ruchirsharma_1", "mujifren"]
```

**`.env.example`** — replace:
```
ANTHROPIC_API_KEY=        # replaces OPENAI_API_KEY
```

---

## Data Flow

```
config.json              → models, benchmark_accounts
scripts/llm_client.py    → complete(model, system, user) [routes by prefix]
scripts/content_generator.py
  load_playbooks()       → distilled (~1k tokens) or full (~4.5k tokens)
  validate_post()        → hard reject filter before scoring
  generate()             → llm_complete → parse_drafts → validate_post filter
scripts/post_scorer.py
  _build_shared_scoring_context() → rubric + benchmark + calibration [once per batch]
  batch_score_posts()    → 1 API call for N posts
  batch_regenerate_posts() → 1 API call for failing posts
  score_all_posts()      → max 4 API calls total
scripts/benchmark_analyzer.py (standalone)
  run_benchmark()        → X API fetch → extract_insights → write benchmark_insights.json
```

---

## Error Handling

- `llm_client.complete()` raises on API error — callers handle as before
- `benchmark_insights.json` absent: graceful skip in both scorer and generator (existing `try/except`)
- `playbook_distilled.json` absent: `load_playbooks()` falls back to full playbooks silently
- `validate_post()` rejection: logged, post dropped; pipeline continues with remaining valid drafts
- `batch_score_posts()` JSON parse failure: raises, caught by `score_all_posts()` → surfaces as pipeline error

---

## Out of Scope

- Lex chat interface (sub-project 4)
- Auto-post toggle (sub-project 5)
- FastAPI migration (sub-project 5)
- Wiring `benchmark_analyzer.py` to the scheduler
- Any dashboard UI changes
- `openai` package removal from `pyproject.toml` (keep until confirmed unused)
