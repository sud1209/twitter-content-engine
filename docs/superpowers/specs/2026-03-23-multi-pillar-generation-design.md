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

**Refactor:** `run()` to expose raw topic list so the pipeline can reuse it for both trend context building and pillar ranking without double-fetching RSS/competitor data.

New signature:
```python
def run(pillar: str, funnel: str) -> str:  # unchanged external interface
def get_all_topics() -> list[dict]:         # new — returns raw RSS + competitor topics
```

`run()` internally calls `get_all_topics()`. The pipeline calls `get_all_topics()` once and passes the result to both `build_trend_context()` and `rank_pillars()`.

---

### 2. `scripts/content_generator.py`

**Change:** Add `num_drafts` parameter to `generate()` and `build_system_prompt()`:

```python
def generate(pillar: str, funnel: str, trend_context: str, num_drafts: int = NUM_DRAFTS) -> list[str]:
def build_system_prompt(pillar: str, funnel: str, num_drafts: int = NUM_DRAFTS) -> str:
```

- `NUM_DRAFTS = 8` constant unchanged — used as default for primary pillar calls
- Non-primary pillar calls pass `num_drafts=3`
- The system prompt already interpolates `NUM_DRAFTS` into the LLM instruction — this just makes it dynamic

No other changes to this module.

---

### 3. `scripts/server.py` — `_run_posts_pipeline()`

**New flow:**

```
1. get today's pillar + funnel from get_todays_pillar()
2. call get_all_topics() once → raw topic list
3. build trend_context for primary pillar via build_trend_context()
4. call rank_pillars(all_topics, exclude_pillar=today_pillar, n=3) → [pillar_a, pillar_b, pillar_c]
5. PRIMARY: generate(today_pillar, funnel, trend_context, num_drafts=8)
           → score all candidates → keep top 5
6. FOR EACH of 3 non-primary pillars:
           build trend_context for that pillar
           → generate(pillar, funnel, trend_context, num_drafts=3)
           → score all candidates → keep top 1
7. assemble all 8 posts → write to queue
```

Each post is tagged with its actual `pillar` value (already the case). Funnel is today's funnel for all 8.

---

## Data Flow

```
cadence.py           → today_pillar, today_funnel
trend_scanner.py     → get_all_topics() [called once]
                     → rank_pillars()   [picks 3 non-primary]
                     → build_trend_context() [called 4x, one per pillar]
content_generator.py → generate() [called 4x]
post_scorer.py       → regenerate_if_below_floor() [called per candidate]
post_queue.py        → add_post() [8 posts written]
```

---

## Error Handling

- If a non-primary pillar generation fails, log the error and continue — the pipeline should not abort because one of the 3 bonus pillars failed
- If `rank_pillars()` returns fewer than 3 pillars (e.g. config has <4 pillars total), use however many are available

---

## Testing

- Unit test `rank_pillars()`: verify it excludes the primary pillar, returns correct top N by score, falls back correctly on zero hits
- Unit test `generate()` with explicit `num_drafts` param: verify the system prompt contains the correct count
- Integration: trigger `/api/posts/generate` and assert 8 posts in queue with 5 from primary pillar and 3 from distinct non-primary pillars

---

## Out of Scope

- Changing which funnel stage non-primary posts use (always today's funnel, per decision)
- Weighted scoring between primary vs non-primary posts
- UI changes to the dashboard (8 posts render in the existing card layout without changes)
