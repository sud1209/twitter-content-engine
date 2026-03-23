# Multi-Pillar Content Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate 8 posts per day — 5 from today's scheduled pillar and 1 each from the 3 most trending non-primary pillars.

**Architecture:** Add `get_all_topics()` and `rank_pillars()` to `trend_scanner.py` for single-fetch topic data and pillar ranking. Parameterise `num_drafts` in `content_generator.py` (3 occurrences). Update `_run_posts_pipeline()` in `server.py` to orchestrate 4 generate calls (1 primary + 3 non-primary).

**Tech Stack:** Python 3.10+, uv, OpenAI gpt-4o-mini, feedparser, pytest, pytest-mock

**Spec:** `docs/superpowers/specs/2026-03-23-multi-pillar-generation-design.md`

---

## File Map

| File | Change |
|------|--------|
| `scripts/trend_scanner.py` | Add `get_all_topics()`, add `rank_pillars()`, refactor `run()` to delegate to `get_all_topics()` |
| `scripts/content_generator.py` | Add `num_drafts` param to `generate()` and `build_system_prompt()`; update all 3 `NUM_DRAFTS` hardcoding sites (2 in `build_system_prompt`, 1 in `generate` user message) |
| `scripts/server.py` | Rewrite body of `_run_posts_pipeline()` for multi-pillar flow; remove trailing no-op `save_queue(load_queue())` |
| `tests/test_trend_scanner.py` | Add tests for `get_all_topics()`, `rank_pillars()`, and refactored `run()` |
| `tests/test_server.py` | Add synchronous integration test for 8-post pipeline |

---

## Task 1: `get_all_topics()` in trend_scanner.py

**Files:**
- Modify: `scripts/trend_scanner.py`
- Test: `tests/test_trend_scanner.py`

- [ ] **Step 1: Write the failing tests**

`MagicMock` is already imported in `tests/test_trend_scanner.py`. Add these tests at the end of the file:

```python
from scripts.trend_scanner import get_all_topics, run


def test_get_all_topics_returns_combined_list(mocker):
    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(title="AI news", summary="detail", link="http://example.com/1"),
    ]
    mocker.patch("scripts.trend_scanner.feedparser.parse", return_value=mock_feed)
    mocker.patch("scripts.trend_scanner.fetch_competitor_posts", return_value=[
        {"title": "competitor post", "summary": "text", "link": "http://x.com/1", "source": "@handle"}
    ])
    topics = get_all_topics()
    assert isinstance(topics, list)
    assert len(topics) >= 2  # 1 RSS + 1 competitor
    assert "title" in topics[0]


def test_get_all_topics_returns_empty_list_on_failure(mocker):
    mocker.patch("scripts.trend_scanner.feedparser.parse", side_effect=Exception("network error"))
    mocker.patch("scripts.trend_scanner.fetch_competitor_posts", return_value=[])
    topics = get_all_topics()
    assert isinstance(topics, list)


def test_run_still_returns_string_after_refactor(mocker):
    mocker.patch("scripts.trend_scanner.get_all_topics", return_value=[
        {"title": "AI mortgage automation", "summary": "", "link": "http://example.com", "source": "rss"},
    ])
    result = run(pillar="AI Innovations", funnel="TOFU")
    assert isinstance(result, str)
    assert "AI Innovations" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:\Users\sudar\OneDrive\Desktop\twitter-content-engine
uv run pytest tests/test_trend_scanner.py::test_get_all_topics_returns_combined_list tests/test_trend_scanner.py::test_get_all_topics_returns_empty_list_on_failure tests/test_trend_scanner.py::test_run_still_returns_string_after_refactor -v
```

Expected: `ImportError` or `FAILED` — `get_all_topics` does not exist yet.

- [ ] **Step 3: Implement `get_all_topics()` and refactor `run()`**

In `scripts/trend_scanner.py`, add `get_all_topics()` after `fetch_competitor_posts()`:

```python
def get_all_topics() -> list[dict]:
    """Fetch and combine RSS + competitor posts. Returns raw unfiltered topic list."""
    rss_topics = scan_rss_feeds()
    competitor_topics = fetch_competitor_posts()
    return rss_topics + competitor_topics
```

Then replace the body of `run()`:

```python
def run(pillar: str, funnel: str) -> str:
    """Full scan pipeline: RSS + X competitor timelines. Returns trend context string."""
    all_topics = get_all_topics()
    top = rank_topics(all_topics, pillar=pillar, n=7)
    if not top:
        top = all_topics[:7]
    return build_trend_context(top, pillar=pillar, funnel=funnel)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_trend_scanner.py -v
```

Expected: all existing tests + 3 new ones pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/trend_scanner.py tests/test_trend_scanner.py
git commit -m "feat: add get_all_topics() to trend_scanner, refactor run()"
```

---

## Task 2: `rank_pillars()` in trend_scanner.py

**Files:**
- Modify: `scripts/trend_scanner.py`
- Test: `tests/test_trend_scanner.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_trend_scanner.py`:

```python
from scripts.trend_scanner import rank_pillars

MOCK_CONFIG = {
    "pillars": ["AI Innovations", "Sports & Cricket", "eSports & Dota 2", "Literature", "Gaming & Experimental Cooking"],
    "pillar_keywords": {
        "AI Innovations": ["AI", "LLM"],
        "Sports & Cricket": ["cricket", "IPL", "BCCI"],
        "eSports & Dota 2": ["Dota", "eSports"],
        "Literature": ["book", "novel"],
        "Gaming & Experimental Cooking": ["game", "cooking"],
    }
}


def test_rank_pillars_excludes_primary(mocker):
    mocker.patch("scripts.trend_scanner.get_config", return_value=MOCK_CONFIG)
    topics = [{"title": "cricket IPL match", "summary": ""}]
    result = rank_pillars(topics, exclude_pillar="AI Innovations", n=3)
    assert "AI Innovations" not in result
    assert len(result) == 3


def test_rank_pillars_orders_by_score(mocker):
    mocker.patch("scripts.trend_scanner.get_config", return_value=MOCK_CONFIG)
    topics = [
        {"title": "cricket IPL BCCI match", "summary": ""},  # 3 keyword hits for Sports & Cricket
        {"title": "cricket strategy", "summary": ""},         # 1 more hit
        {"title": "Dota 2 patch", "summary": ""},             # 1 hit for eSports
        {"title": "book recommendation", "summary": ""},      # 1 hit for Literature
    ]
    result = rank_pillars(topics, exclude_pillar="AI Innovations", n=3)
    assert result[0] == "Sports & Cricket"


def test_rank_pillars_fallback_on_zero_hits(mocker):
    mocker.patch("scripts.trend_scanner.get_config", return_value=MOCK_CONFIG)
    topics = [{"title": "completely unrelated news", "summary": ""}]
    result = rank_pillars(topics, exclude_pillar="AI Innovations", n=3)
    assert len(result) == 3
    assert "AI Innovations" not in result
    # Fallback should return pillars in config order (excluding primary)
    expected_order = ["Sports & Cricket", "eSports & Dota 2", "Literature"]
    assert result == expected_order
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_trend_scanner.py::test_rank_pillars_excludes_primary tests/test_trend_scanner.py::test_rank_pillars_orders_by_score tests/test_trend_scanner.py::test_rank_pillars_fallback_on_zero_hits -v
```

Expected: `ImportError` or `FAILED` — `rank_pillars` does not exist yet.

- [ ] **Step 3: Implement `rank_pillars()`**

Add after `rank_topics()` in `scripts/trend_scanner.py`:

```python
def rank_pillars(all_topics: list[dict], exclude_pillar: str, n: int = 3) -> list[str]:
    """Rank pillars by trending relevance. Returns top n pillar names, excluding exclude_pillar."""
    cfg = get_config()
    pillars = [p for p in cfg.get("pillars", []) if p != exclude_pillar]
    keywords = cfg.get("pillar_keywords", {})

    scores = []
    for pillar in pillars:
        kws = [kw.lower() for kw in keywords.get(pillar, [])]
        score = 0
        for topic in all_topics:
            text = (topic.get("title", "") + " " + topic.get("summary", "")).lower()
            score += sum(1 for kw in kws if kw in text)
        scores.append((pillar, score))

    scores.sort(key=lambda x: x[1], reverse=True)

    # If no keyword hits at all, fall back to config order
    if all(s == 0 for _, s in scores):
        return pillars[:n]

    return [pillar for pillar, _ in scores[:n]]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_trend_scanner.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/trend_scanner.py tests/test_trend_scanner.py
git commit -m "feat: add rank_pillars() to trend_scanner"
```

---

## Task 3: `num_drafts` param in content_generator.py

**Files:**
- Modify: `scripts/content_generator.py`

Note: `tests/test_content_generator.py` is excluded from pytest collection due to a pre-existing `PLAYBOOK_PATHS` ImportError — do not touch it. Instead, verify correctness with a smoke test in Step 3.

- [ ] **Step 1: Update `build_system_prompt()`**

Change signature:
```python
# Before
def build_system_prompt(pillar: str, funnel: str) -> str:

# After
def build_system_prompt(pillar: str, funnel: str, num_drafts: int = NUM_DRAFTS) -> str:
```

Inside the `prompt = f"""..."""` block, replace **both** occurrences of `{NUM_DRAFTS}`:
1. `"Your job is to write {NUM_DRAFTS} distinct post variants"` → `{num_drafts}`
2. `"...{NUM_DRAFTS}. [post text]"` (the format tail) → `{num_drafts}`

- [ ] **Step 2: Update `generate()`**

Change signature:
```python
# Before
def generate(pillar: str, funnel: str, trend_context: str) -> list[str]:

# After
def generate(pillar: str, funnel: str, trend_context: str, num_drafts: int = NUM_DRAFTS) -> list[str]:
```

Inside `generate()`, make two changes:

1. Pass `num_drafts` to `build_system_prompt`:
```python
system = build_system_prompt(pillar=pillar, funnel=funnel, num_drafts=num_drafts)
```

2. Update the user message (third `NUM_DRAFTS` occurrence):
```python
# Before
user_message = f"Trending context for today:\n\n{trend_context}\n\nWrite the {NUM_DRAFTS} post variants now."

# After
user_message = f"Trending context for today:\n\n{trend_context}\n\nWrite the {num_drafts} post variants now."
```

- [ ] **Step 3: Smoke test — verify module imports and param is wired correctly**

```bash
uv run python -c "
from scripts.content_generator import build_system_prompt
prompt = build_system_prompt('AI Innovations', 'TOFU', num_drafts=3)
assert '3 distinct post variants' in prompt, 'num_drafts not wired in system prompt'
assert '3. [post text]' in prompt, 'num_drafts not wired in format tail'
print('OK — num_drafts=3 correctly wired into build_system_prompt')
"
```

Expected: `OK — num_drafts=3 correctly wired into build_system_prompt`

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
uv run pytest tests/ --ignore=tests/test_content_generator.py --ignore=tests/test_playbook_refresher.py -q
```

Expected: all 80 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/content_generator.py
git commit -m "feat: add num_drafts param to generate() and build_system_prompt()"
```

---

## Task 4: Multi-pillar pipeline in server.py

**Files:**
- Modify: `scripts/server.py`
- Test: `tests/test_server.py`

**Note on lock pattern:** `_run_posts_pipeline()` acquires `_posts_refresh_lock` twice — once at the top (set `running=True`) and once at the bottom (set `running=False`). The `/api/posts/generate` endpoint also sets `running=True` before starting the thread. This double-set is pre-existing intentional behaviour — it ensures the status is set before the thread starts. Do not consolidate or remove either lock acquisition.

- [ ] **Step 1: Write the failing integration test**

Add to `tests/test_server.py`:

```python
def test_generate_pipeline_produces_eight_posts(tmp_path, monkeypatch):
    """Call _run_posts_pipeline() directly (synchronously) to test multi-pillar output.

    NOTE: _run_posts_pipeline() uses deferred imports, so patches must target the
    source modules (scripts.cadence, scripts.trend_scanner, etc.) not scripts.server.
    """
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))

    monkeypatch.setattr("scripts.cadence.get_todays_pillar", lambda: {"pillar": "AI Innovations", "funnel": "TOFU"})
    monkeypatch.setattr("scripts.trend_scanner.get_all_topics", lambda: [
        {"title": "cricket IPL match", "summary": "", "link": "", "source": "rss"},
        {"title": "Dota 2 patch notes", "summary": "", "link": "", "source": "rss"},
        {"title": "book recommendation 2026", "summary": "", "link": "", "source": "rss"},
    ])
    monkeypatch.setattr("scripts.trend_scanner.rank_pillars", lambda topics, exclude_pillar, n: [
        "Sports & Cricket", "eSports & Dota 2", "Literature"
    ])
    monkeypatch.setattr("scripts.trend_scanner.rank_topics", lambda topics, pillar, n: topics)
    monkeypatch.setattr("scripts.trend_scanner.build_trend_context", lambda topics, pillar, funnel: f"context for {pillar}")

    def fake_generate(pillar, funnel, trend_context, num_drafts=8):
        return [f"post {i} for {pillar}" for i in range(num_drafts)]

    monkeypatch.setattr("scripts.content_generator.generate", fake_generate)
    monkeypatch.setattr("scripts.post_scorer.regenerate_if_below_floor",
                        lambda post: {**post, "score": 8.0, "status": "scored"})

    from scripts.server import _run_posts_pipeline
    _run_posts_pipeline()

    from scripts.post_queue import load_queue
    queue = load_queue()

    assert len(queue) == 8
    pillars = [p["pillar"] for p in queue]
    assert pillars.count("AI Innovations") == 5
    non_primary = [p for p in pillars if p != "AI Innovations"]
    assert len(non_primary) == 3
    assert len(set(non_primary)) == 3  # all 3 are distinct pillars
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_server.py::test_generate_pipeline_produces_eight_posts -v
```

Expected: `FAILED` — pipeline currently generates 5 posts, all same pillar. May also fail with `ImportError` for `get_all_topics` / `rank_pillars` which don't exist yet in the server imports.

- [ ] **Step 3: Rewrite `_run_posts_pipeline()` in server.py**

Replace the entire `_run_posts_pipeline()` function (lines 16–59) with:

```python
def _run_posts_pipeline():
    with _posts_refresh_lock:
        _posts_refresh_status.update({"running": True, "done": False, "error": None})
    try:
        import uuid
        from scripts.cadence import get_todays_pillar
        from scripts.trend_scanner import get_all_topics, rank_pillars, rank_topics, build_trend_context
        from scripts.content_generator import generate
        from scripts.post_scorer import regenerate_if_below_floor
        from scripts.post_queue import add_post

        # Clear non-published posts before generating fresh batch
        queue = load_queue()
        queue = [p for p in queue if p["status"] == "published"]
        save_queue(queue)

        today = get_todays_pillar()
        pillar = today["pillar"]
        funnel = today["funnel"]

        # Fetch all topics once — reused for trend context and pillar ranking
        all_topics = get_all_topics()

        # Pick 3 trending non-primary pillars
        trending_pillars = rank_pillars(all_topics, exclude_pillar=pillar, n=3)

        all_posts = []

        # PRIMARY PILLAR: generate 8 candidates, keep top 5
        primary_topics = rank_topics(all_topics, pillar=pillar, n=7)
        if not primary_topics:
            primary_topics = all_topics[:7]
        primary_context = build_trend_context(primary_topics, pillar, funnel)
        primary_drafts = generate(pillar, funnel, primary_context, num_drafts=8)

        primary_candidates = []
        for draft in primary_drafts:
            post = {
                "id": str(uuid.uuid4()),
                "text": draft,
                "pillar": pillar,
                "funnel": funnel,
                "score": None,
                "score_breakdown": None,
                "status": "pending_score",
            }
            primary_candidates.append(regenerate_if_below_floor(post))

        primary_candidates.sort(key=lambda p: p.get("score") or 0, reverse=True)
        all_posts.extend(primary_candidates[:5])

        # NON-PRIMARY PILLARS: generate 3 candidates each, keep top 1
        for np_pillar in trending_pillars:
            try:
                np_topics = rank_topics(all_topics, pillar=np_pillar, n=7)
                if not np_topics:
                    np_topics = all_topics[:7]
                np_context = build_trend_context(np_topics, np_pillar, funnel)
                np_drafts = generate(np_pillar, funnel, np_context, num_drafts=3)

                np_candidates = []
                for draft in np_drafts:
                    post = {
                        "id": str(uuid.uuid4()),
                        "text": draft,
                        "pillar": np_pillar,
                        "funnel": funnel,
                        "score": None,
                        "score_breakdown": None,
                        "status": "pending_score",
                    }
                    np_candidates.append(regenerate_if_below_floor(post))

                np_candidates.sort(key=lambda p: p.get("score") or 0, reverse=True)
                all_posts.append(np_candidates[0])
            except Exception as e:
                print(f"Warning: failed to generate post for pillar '{np_pillar}': {e}")

        for post in all_posts:
            add_post(post)

        with _posts_refresh_lock:
            _posts_refresh_status.update({"running": False, "done": True})
    except Exception as e:
        with _posts_refresh_lock:
            _posts_refresh_status.update({"running": False, "done": True, "error": str(e)})
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/ --ignore=tests/test_content_generator.py --ignore=tests/test_playbook_refresher.py -q
```

Expected: all 80 existing tests + new integration test = 81 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/server.py tests/test_server.py
git commit -m "feat: multi-pillar pipeline — 5 primary + 3 trending non-primary posts"
```

---

## Task 5: End-to-end smoke test via live server

- [ ] **Step 1: Ensure server is running**

Open a separate terminal and run:
```bash
cd c:\Users\sudar\OneDrive\Desktop\twitter-content-engine
uv run python -m scripts.server
```

Or if already running from a previous session, verify it's up:
```bash
curl -s http://localhost:3000/api/config
```

Expected: JSON with `handle`, `display_name`, etc.

- [ ] **Step 2: Trigger generation**

```bash
curl -s -X POST http://localhost:3000/api/posts/generate
```

Expected: `{"ok": true, "started": true}`

- [ ] **Step 3: Poll until done (generation takes ~30s for 4 LLM calls)**

```bash
curl -s http://localhost:3000/api/posts/generate/status
```

Repeat until `"done": true`. If `"error"` is non-null, check server logs.

- [ ] **Step 4: Verify 8 posts with correct pillar distribution**

```bash
curl -s http://localhost:3000/api/posts/today | uv run python -c "
import json, sys
from collections import Counter
posts = json.load(sys.stdin)
print(f'Total posts: {len(posts)}')
for k, v in Counter(p['pillar'] for p in posts).items():
    print(f'  {k}: {v}')
"
```

Expected:
```
Total posts: 8
  AI Innovations: 5
  <trending_pillar_1>: 1
  <trending_pillar_2>: 1
  <trending_pillar_3>: 1
```

- [ ] **Step 5: Open dashboard and verify visually**

Open `http://localhost:3000` — confirm 8 cards visible, each labelled with its pillar.
