# Architecture — twitter-content-engine

## System Overview

Data moves in one direction: external signals (RSS feeds and competitor X timelines) flow into the trend scanner, which feeds the content generator, which produces drafts that are scored, queued, reviewed in the dashboard, and finally published to X.

```
RSS feeds + competitor X timelines
        |
        v
   trend_scanner.py
   (get_all_topics, rank_pillars, rank_topics, build_trend_context)
        |
        v
  content_generator.py
  (build_system_prompt + generate — primary pillar x8, non-primary x3 each)
        |
        v
    post_scorer.py
    (score_all_posts — batch score, batch regen, batch rescore, max 5 API calls)
        |
        v
    post_queue.py
    (data/queue.json)
        |
        v
  Dashboard — server.py (localhost:3000)
  Manual approve / reject / edit / regen
        |
        v
   x_publisher.py
   (publish one approved post per day at publish_time_utc)
```

---

## Component Map

### `config_loader.py`

Exposes a single function `get_config()` that reads `config.json` and returns the parsed dict. The result is cached as a module-level singleton — subsequent calls return the same object without re-reading disk. All other scripts import from here; nothing reads `config.json` directly.

---

### `cadence.py`

Single exported function: `get_todays_pillar() -> dict`.

Reads the UTC weekday, looks up the matching entry in `config["cadence"]`, and returns `{"pillar": ..., "funnel": ..., "day": ...}` after applying two resolution rules:

- **Flex Sunday**: if `pillar == "flex"`, resolves to the lowest-engagement pillar by calling `get_lowest_engagement_pillar()` from `performance_analyzer`. This import is deferred — it happens inside the `if pillar == "flex":` branch, not at module top — to prevent a potential circular import on the default (non-flex) path.
- **BOFU dormancy**: if `funnel == "BOFU"` and `config["newsletter_url"]` is empty, the funnel silently falls back to `"TOFU"`. Activates automatically when the newsletter URL is filled in.

---

### `llm_client.py`

Provider-agnostic completion wrapper. Single exported function:

```python
complete(model: str, system: str, user: str, max_tokens: int = 2000) -> str
```

Routes by model name prefix:
- `"claude-*"` → Anthropic Messages API (`ANTHROPIC_API_KEY`)
- anything else → OpenAI Chat Completions API (`OPENAI_API_KEY`)

No SDK client objects are exposed outside this module. All other scripts call `llm_complete(...)` and receive a plain string.

---

### `content_generator.py`

Responsible for producing validated draft posts.

**`load_playbooks() -> dict`**
Attempts to load the distilled playbook cache at `data/playbook_distilled.json` (approximately 1 000 tokens). Falls back to reading the full markdown playbook files from `config["playbooks"]` (approximately 4 500 tokens) if the cache is absent or incomplete.

**`distill_playbooks()`**
One-time manual step. Compresses the three full playbooks into the distilled JSON cache. Run via:
```
uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"
```
Not auto-triggered by any pipeline step.

**`validate_post(text: str) -> tuple[bool, str]`**
Hard-rejects posts containing:
- any `#` character (hashtags, including fullwidth `\uff03`)
- em-dashes (`\u2014`)
- soft question endings in the final 80 characters (e.g. "what's your ", "how do you ")
- weak CTA phrases anywhere in the text (e.g. "what do you think", "share your thoughts", "let me know your")

Returns `(True, "")` on pass, `(False, reason_string)` on fail.

**`build_system_prompt(pillar, funnel, num_drafts) -> str`**
Assembles the full system prompt from playbook content, today's pillar/funnel assignment, adversarial frame templates, and two optional injections (both fail gracefully if files are absent):
- Performance calibration from `data/score_calibration.json` via `load_calibration()`
- Benchmark patterns from `data/benchmark_insights.json`

**`generate(pillar, funnel, trend_context, num_drafts) -> list[str]`**
Calls the LLM, parses the numbered list response via `parse_drafts()`, runs each draft through `validate_post()`, and returns only the passing drafts. Logs rejection reasons for any that fail.

---

### `post_scorer.py`

Scores and iteratively improves posts using the LLM as judge.

**`batch_score_posts(posts) -> list[dict]`**
Sends all posts in a single API call. Returns posts mutated with `score`, `score_breakdown`, `never_list_violation`, and `status` fields.

**`batch_regenerate_posts(failing_posts, trend_context) -> list[dict]`**
Sends all below-threshold posts in a single API call for revision. Each revised post gets a new UUID. Weak dimensions are passed to the LLM for targeted fixes.

**`score_all_posts(posts) -> list[dict]`**
Main entry point. Runs: batch score → batch regen failing → batch rescore. Repeats regen up to `MAX_REGENERATION_ATTEMPTS = 2` times. Maximum 5 API calls regardless of post count. Posts that remain below threshold after all attempts get `status = "below_target"` (they are still returned, not dropped).

**`regenerate_if_below_floor(post) -> dict`**
Legacy single-post wrapper. Delegates to `score_all_posts([post])` and returns the first result. Used by `_rescore_post()` in `server.py`.

---

### `post_queue.py`

Thin persistence layer over `data/queue.json`.

| Function | Behaviour |
|---|---|
| `load_queue()` | Returns `[]` if file does not exist |
| `save_queue(posts)` | Writes with `indent=2`, creates `data/` directory if needed |
| `add_post(post)` | Load → append → save |
| `update_post_status(post_id, status)` | Raises `ValueError` if post ID not found |

---

### `trend_scanner.py`

**`get_all_topics() -> list[dict]`**
Calls `scan_rss_feeds()` (10 hardcoded RSS feeds, up to 8 entries each) and `fetch_competitor_posts()` (reads `config["benchmark_accounts"]`, requires `X_BEARER_TOKEN`). Returns the combined list of `{title, summary, link, source}` dicts.

**`rank_pillars(all_topics, exclude_pillar, n) -> list[str]`**
Scores every pillar (except the primary) by counting keyword hits across all topics using `config["pillar_keywords"]`. Returns the top `n` pillar names. Falls back to config-order if no keyword hits are found.

**`rank_topics(topics, pillar, n) -> list[dict]`**
Scores topics against a single pillar's keywords. Returns the top `n` most relevant topics.

**`build_trend_context(topics, pillar, funnel) -> str`**
Formats the ranked topic list into the context string passed to the content generator prompt.

**`run(pillar, funnel) -> str`**
Full pipeline convenience wrapper: `get_all_topics()` → `rank_topics()` → `build_trend_context()`. Used by the scheduler's morning job.

---

### `performance_analyzer.py`

**`analyze_performance(posts) -> dict`**
Given published posts with `actual_engagement` data, computes average predicted vs. actual engagement, flags scorer blind spots (high predicted / low actual), flags undervalued signals (low predicted / high actual), and produces per-pillar breakdowns.

**`run_analysis()`**
Reads the queue, fetches missing `actual_engagement` data from the X API for any published post that has a `tweet_id` but no metrics yet, runs `analyze_performance()`, and writes `data/score_calibration.json`.

**`load_calibration() -> dict | None`**
Returns `None` if the file is absent or has fewer than 5 posts. The 5-post minimum prevents noisy calibration from distorting generation and scoring on a fresh account.

**`get_lowest_engagement_pillar(pillars) -> str`**
Used by `cadence.py` for flex Sunday. Falls back to `pillars[0]` if calibration is unavailable or none of the requested pillars have data yet.

---

### `server.py`

Flask application on `localhost:3000` (configurable via `DASHBOARD_PORT`). Serves the static dashboard from `dashboard/` and exposes the REST API described in `docs/API.md`.

**`_run_posts_pipeline()`**
The 8-post daily generation pipeline, run in a background thread:

1. Clears all non-published posts from the queue.
2. Calls `get_all_topics()` once — the result is reused for both pillar ranking and topic ranking.
3. Primary pillar: generates 8 candidates, scores all 8, keeps the top 5 by score.
4. Non-primary pillars (top 3 trending, via `rank_pillars()`): generates 3 candidates per pillar, scores each set, keeps the top 1 per pillar.
5. All surviving posts (up to 8 total: 5 primary + 3 non-primary) are written to the queue.

**`_rescore_post(post_id)`**
Called after a manual edit. Loads the edited post from the queue, runs `regenerate_if_below_floor()` in a background thread, and writes the result back.

---

### `scheduler.py`

Registers 4 APScheduler jobs via `schedule_jobs()`. Always call this function at startup — never add `scheduler.add_job()` calls at module level.

| Job | Schedule | Action |
|---|---|---|
| `run_morning_pipeline` | 07:00 UTC daily | Generate + score posts, send desktop notification |
| `run_analysis_job` | 09:00 UTC daily | Fetch engagement metrics, update `score_calibration.json` |
| `run_publish_pipeline` | `publish_time_utc` from config (default 15:30) | Publish one approved post to X |
| `run_spike_check` | Every 2 hours | RSS scan → spike detection → desktop alert if new spike |

---

### `benchmark_analyzer.py`

Standalone utility. Run manually with `uv run python -m scripts.benchmark_analyzer`.

1. Fetches up to 50 original tweets per benchmark account via Tweepy (requires `X_BEARER_TOKEN`).
2. Computes weighted engagement scores: `likes + (retweets * 20) + (replies * 27)`.
3. Computes per-account stats and gap analysis against own published posts.
4. Sends the top 10 posts by score to the LLM to extract structured content patterns.
5. Writes two files:
   - `data/benchmark_report.json`: per-account stats and gap tables.
   - `data/benchmark_insights.json`: top posts + extracted patterns (hook patterns, specificity techniques, CTA patterns, engagement drivers).

Once `benchmark_insights.json` exists, both `post_scorer.py` and `content_generator.py` pick it up automatically on their next run.

---

### `playbook_refresher.py`

Fetches recent posts from benchmark accounts and the user's own account, synthesises a trend update via LLM, and appends a timestamped section to each of the three playbook files. Triggered via `POST /api/playbooks/refresh` or run directly. A two-step flow: the first call generates and previews the update; `{"confirm": true}` writes it.

---

## Scoring Rubric

Posts are scored on 6 dimensions. The composite score is the weighted sum plus a `+0.5` calibration offset.

| Dimension | Weight | Notes |
|---|---|---|
| `hook_strength` | 25% | Harry Dry 3 tests: visualizable, falsifiable, nobody else can say it. All 3 must pass for 9+. |
| `tone_compliance` | 20% | Six Core Laws. Zero hashtags, zero em-dashes, zero exclamation marks, zero hedging. Any hashtag = 0/10. |
| `x_algorithm_optimization` | 20% | Reply=27x like, Repost=20x like. Debate-bait + data = 9+. DM CTA alone = 7. |
| `data_specificity` | 15% | Named people/products, concrete numbers, falsifiable outcomes. Abstract claim = 6 max. |
| `pillar_alignment` | 15% | Pillar must be unmistakable in the first sentence. Vague opener = 6 max. |
| `cta_quality` | 5% | TOFU only: awareness, follow invite, or debate-bait. No hard sell, no link drop, no DM push. |

**Score thresholds:**
- `ready`: composite >= 9.25
- `below_target`: composite >= 8.0 and < 9.25
- `failed_floor`: composite < 8.0 (triggers regeneration)

A `never_list_violation` (any `#` character detected by the scorer) forces the composite to `0.0` regardless of dimension scores.

---

## Daily Pipeline Data Flow

```
[07:00 UTC — morning job]
        |
        v
 get_all_topics()           <- RSS (10 feeds) + competitor X timelines
        |
        +---> rank_pillars()      <- find top 3 trending non-primary pillars
        |
        +---> rank_topics()       <- filter topics for primary pillar
                |
                v
         build_trend_context()
                |
                v
         generate(primary, num_drafts=8)    <- 8 candidates
                |
                v
         score_all_posts(8 candidates)      <- batch score + regen, max 5 API calls
                |
                v
         keep top 5 by score
                |
                +--- (repeat for each of 3 trending non-primary pillars)
                |    generate(pillar, num_drafts=3) -> score_all_posts -> keep top 1
                |
                v
         add_post() x8          <- write to data/queue.json
                |
                v
[Dashboard — manual review]
   approve / reject / edit / regen
                |
                v
[publish_time_utc — publish job]
   x_publisher: publish one approved post to X
```

---

## Data Directory

| File | Written by | Read by |
|---|---|---|
| `data/queue.json` | `post_queue.py` (all writes) | `server.py`, `scheduler.py`, `post_scorer.py`, `x_publisher.py` |
| `data/playbook_distilled.json` | `distill_playbooks()` (manual) | `content_generator.load_playbooks()` |
| `data/benchmark_report.json` | `benchmark_analyzer.run_benchmark()` | Read directly by humans; no script dependency |
| `data/benchmark_insights.json` | `benchmark_analyzer.run_benchmark()` | `content_generator.build_system_prompt()`, `post_scorer._build_shared_scoring_context()` |
| `data/score_calibration.json` | `performance_analyzer.run_analysis()` | `content_generator.build_system_prompt()`, `post_scorer._build_shared_scoring_context()`, `cadence.get_todays_pillar()` (via `get_lowest_engagement_pillar`) |

---

## Key Design Decisions

**Deferred import in `cadence.py`**
`get_lowest_engagement_pillar` is imported inside the `if pillar == "flex":` branch. On the default path (non-flex weekdays), this import never runs. Placing it at module top would create a circular dependency because `performance_analyzer` imports `post_queue`, which is also imported early in the pipeline.

**BOFU dormancy**
The newsletter check lives in `cadence.py`, not in `content_generator.py`, because cadence is the single source of truth for pillar and funnel. The generator consumes whatever `get_todays_pillar()` returns without needing to know about the newsletter state.

**Relative paths assume CWD = project root**
All file paths (`data/queue.json`, `data/benchmark_insights.json`, etc.) are relative. Always run scripts from the project root using `uv run`. Never `cd` into `scripts/` before running.

**`score_all_posts()` maximum 5 API calls**
With `MAX_REGENERATION_ATTEMPTS = 2`, the worst-case call sequence is: 1 score + 1 regen + 1 rescore + 1 regen + 1 rescore = 5 calls. This cap holds regardless of how many posts are in the batch, because all posts in each step are batched into a single API call.

**Playbook distillation is a one-time manual step**
`distill_playbooks()` is not wired into any pipeline or scheduler job. Run it once after the playbooks are stable. The distilled cache reduces prompt token cost by roughly 75% on every generation call.
