# Multi-Pillar Content Generation — Design Spec

**Date:** 2026-03-23
**Status:** Approved

---

## Problem

The current pipeline generates all posts from a single pillar (today's scheduled cadence pillar). This means the dashboard shows 5 posts on the same topic every day, missing opportunities to capitalise on trending topics across the other pillars.

---

## Goal

Produce **8 posts per day**:
- **5 posts** from today's scheduled pillar (unchanged quality/scoring logic)
- **1 post each** from the **3 most trending non-primary pillars**, selected by RSS keyword signal

All 8 posts use today's funnel stage.

---

## Approach

Option B: extend `trend_scanner.py` with pillar ranking, add `num_drafts` param to `content_generator.py`, update `_run_posts_pipeline()` in `server.py`.

---

## Component Changes

### 1. `scripts/trend_scanner.py`

**Add:** `rank_pillars(all_topics, exclude_pillar, n=3) -> list[str]`

- Iterates all pillars from config, excluding `exclude_pillar`
- For each pillar, sums keyword relevance scores across `all_topics` using existing keyword matching logic (same as `rank_topics`)
- Returns top N pillar names sorted by aggregate score descending
- Fallback: if no keyword hits found, returns first N remaining pillars in config order

**Add:** `get_all_topics() -> list[dict]`

- Extracts the `scan_rss_feeds() + fetch_competitor_posts()` concatenation from `run()` into a standalone function
- Returns the raw combined topic list with no filtering or ranking applied
- `run()` is refactored to call `get_all_topics()` internally — its external interface (`run(pillar, funnel) -> str`) is unchanged
- The `if not top: top = all_topics[:7]` fallback inside `run()` stays inside `run()` and does not move into `get_all_topics()`
- The pipeline calls `get_all_topics()` once and passes the result to both `build_trend_context()` and `rank_pillars()` to avoid double-fetching RSS/competitor data

---

### 2. `scripts/content_generator.py`

**Change:** Add `num_drafts` parameter to both `generate()` and `build_system_prompt()`:

```python
def generate(pillar: str, funnel: str, trend_context: str, num_drafts: int = NUM_DRAFTS) -> list[str]:
def build_system_prompt(pillar: str, funnel: str, num_drafts: int = NUM_DRAFTS) -> str:
```

- `NUM_DRAFTS = 8` constant unchanged — it is the default value for both parameters
- Non-primary pillar calls pass `num_drafts=3` explicitly
- **Two places** in the current code hardcode `NUM_DRAFTS` and both must become dynamic:
  1. `build_system_prompt()` line: `"Your job is to write {NUM_DRAFTS} distinct post variants"` → replace with `num_drafts`
  2. `generate()` user message line: `"Write the {NUM_DRAFTS} post variants now."` → replace with `num_drafts`
- Primary pillar calls may rely on the default (`num_drafts=8`) or pass it explicitly — either is correct

No other changes to this module.

---

### 3. `scripts/server.py` — `_run_posts_pipeline()`

**Preserve:** The existing `_posts_refresh_lock` / status management at the top and bottom of the function must be kept exactly as-is. Only the body between the lock acquisitions changes.

**New flow:**

```
[status lock: set running=True]

1. get today's pillar + funnel from get_todays_pillar()
2. clear non-published posts from queue (existing behaviour — keep)
3. call get_all_topics() once → raw topic list
4. call rank_pillars(all_topics, exclude_pillar=today_pillar, n=3) → [pillar_a, pillar_b, pillar_c]

5. PRIMARY (today's pillar):
   a. rank_topics(all_topics, pillar=today_pillar, n=7) → filtered topics
   b. build_trend_context(filtered_topics, pillar, funnel) → trend_context
   c. generate(today_pillar, funnel, trend_context, num_drafts=8) → candidates
   d. score each candidate via regenerate_if_below_floor()
   e. sort by score descending, keep top 5 → add to posts list

6. FOR EACH non_primary_pillar of 3 non-primary pillars:
   a. rank_topics(all_topics, pillar=non_primary_pillar, n=7) → filtered topics
   b. build_trend_context(filtered_topics, non_primary_pillar, funnel) → trend_context
   c. generate(non_primary_pillar, funnel, trend_context, num_drafts=3) → candidates
   d. score each candidate via regenerate_if_below_floor()
   e. keep top 1 → add to posts list
   (if generation or scoring fails: log error and continue — do not abort pipeline)

7. write all accumulated posts to queue via add_post()
   (if a non-primary pillar's scoring floor was never met after retries:
    add the best available candidate anyway rather than dropping to <8 posts)

[status lock: set running=False, done=True]
```

Each post is tagged with its actual `pillar` value (already the case since `post["pillar"]` is set per generate call). Funnel is today's funnel for all 8.

Note: `post_scorer.py → regenerate_if_below_floor()` is already imported in `server.py` — no new import needed.

---

## Data Flow

```
cadence.py           → today_pillar, today_funnel
trend_scanner.py     → get_all_topics() [called once, raw topics]
                     → rank_topics()    [called 4x, one per pillar, for trend context]
                     → rank_pillars()   [called once, picks 3 non-primary pillars]
                     → build_trend_context() [called 4x, one per pillar]
content_generator.py → generate() [called 4x]
post_scorer.py       → regenerate_if_below_floor() [called per candidate, already imported]
post_queue.py        → add_post() [8 posts written]
```

---

## Error Handling

- If a non-primary pillar **generation** fails: log error, skip that pillar, continue. Queue may have fewer than 8 posts.
- If a non-primary pillar's scoring floor is **never met** after retries: add best available candidate anyway (do not drop to <8 posts).
- If `rank_pillars()` returns fewer than 3 pillars (e.g. config has <4 pillars total): use however many are available.
- If `get_all_topics()` returns `[]` (both RSS and competitor fetch empty): `rank_pillars()` uses its config-order fallback, `build_trend_context()` produces a header-only context string, and `generate()` receives thin context. The pipeline degrades gracefully — it does not abort.

---

## Testing

- Unit test `rank_pillars()`: verify it excludes the primary pillar, returns correct top N by score, falls back correctly on zero hits
- Unit test `get_all_topics()`: verify it returns combined RSS + competitor results
- Unit test `generate()` with explicit `num_drafts` param: verify both the system prompt and user message contain the correct count
- Integration: trigger `/api/posts/generate` and assert 8 posts in queue with 5 from primary pillar and 3 from distinct non-primary pillars

---

## Out of Scope

- Changing which funnel stage non-primary posts use (always today's funnel, per decision)
- Weighted scoring between primary vs non-primary posts
- UI changes to the dashboard (8 posts render in the existing card layout without changes)
