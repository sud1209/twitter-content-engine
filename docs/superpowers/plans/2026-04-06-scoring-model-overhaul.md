# Scoring & Model Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the scoring pipeline, model abstraction, playbook distillation, post validation, and benchmark utility from twitter-bot into twitter-content-engine — adapted for Sud's pillars, TOFU-only scoring, and provider-agnostic LLM calls.

**Architecture:** A new `llm_client.py` provides a single `complete()` function that routes to Anthropic or OpenAI based on model name prefix; `post_scorer.py` is rewritten for batch scoring (max 4 API calls for any N posts); `content_generator.py` adds playbook distillation caching and hard-rule post validation; `benchmark_analyzer.py` is a standalone utility ported from twitter-bot.

**Tech Stack:** Python 3.10+, `anthropic` SDK (new dep), `openai` SDK (kept), `tweepy`, `uv` for dependency management, `pytest` + `pytest-mock` for tests.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/llm_client.py` | Create | Provider-agnostic `complete()` — routes by model prefix |
| `scripts/post_scorer.py` | Overhaul | Batch scoring, upgraded 6-dim TOFU rubric, legacy wrapper |
| `scripts/content_generator.py` | Overhaul | Playbook distillation, `validate_post()`, llm_client, benchmark injection |
| `scripts/benchmark_analyzer.py` | Create | Standalone benchmark fetch + insight extraction utility |
| `config.json` | Modify | Add `"models"` key (already has `"benchmark_accounts"`) |
| `.env.example` | Modify | Replace `OPENAI_API_KEY` with `ANTHROPIC_API_KEY` |
| `pyproject.toml` | Modify | Add `anthropic>=0.40` dependency |
| `tests/test_llm_client.py` | Create | Unit tests for routing and return type |
| `tests/test_post_scorer.py` | Overhaul | Replace old 7-dim tests with 6-dim + batch pipeline tests |
| `tests/test_content_generator.py` | Overhaul | Tests for `validate_post()`, `load_playbooks()` cache logic |
| `tests/test_benchmark_analyzer.py` | Create | Unit tests for score computation and stats functions |

---

## Task 1: Add `anthropic` dependency and `models` config

**Files:**
- Modify: `pyproject.toml`
- Modify: `config.json`
- Modify: `.env.example`

- [ ] **Step 1: Add `anthropic` to pyproject.toml**

Edit `pyproject.toml` dependencies list — add after the `openai` line:

```toml
dependencies = [
    "openai>=1.0",
    "anthropic>=0.40",
    "tweepy>=4.14",
    "feedparser>=6.0",
    "python-dotenv>=1.0",
    "flask>=3.0",
    "apscheduler>=3.10",
    "plyer>=2.1",
]
```

- [ ] **Step 2: Install the new dependency**

```bash
uv sync
```

Expected: `anthropic` package installed, no errors.

- [ ] **Step 3: Add `models` key to config.json**

`config.json` already has `"benchmark_accounts"`. Add `"models"` after `"newsletter_url"`:

```json
"newsletter_url": "",
"models": {
  "generation": "claude-haiku-4-5-20251001",
  "scoring": "claude-haiku-4-5-20251001"
},
```

- [ ] **Step 4: Update `.env.example`**

Replace `OPENAI_API_KEY=` with `ANTHROPIC_API_KEY=`:

```
# X API credentials
X_CONSUMER_KEY=
X_CONSUMER_SECRET=
X_BEARER_TOKEN=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=

# LLM API
ANTHROPIC_API_KEY=

# Config
POST_TIME_UTC=15:30
DASHBOARD_PORT=3000
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock config.json .env.example
git commit -m "chore: add anthropic dep, models config, update env example"
```

---

## Task 2: Create `scripts/llm_client.py`

**Files:**
- Create: `scripts/llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm_client.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


def test_complete_routes_claude_to_anthropic(monkeypatch):
    """Claude model prefix routes to Anthropic SDK."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="anthropic response")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("scripts.llm_client.Anthropic", return_value=mock_client):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from scripts.llm_client import complete
        result = complete(
            model="claude-haiku-4-5-20251001",
            system="You are a helper.",
            user="Say hello.",
        )

    assert result == "anthropic response"
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["system"] == "You are a helper."


def test_complete_routes_gpt_to_openai(monkeypatch):
    """Non-claude model prefix routes to OpenAI SDK."""
    mock_choice = MagicMock()
    mock_choice.message.content = "openai response"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("scripts.llm_client.OpenAI", return_value=mock_client):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from scripts.llm_client import complete
        result = complete(
            model="gpt-4o-mini",
            system="You are a helper.",
            user="Say hello.",
        )

    assert result == "openai response"
    mock_client.chat.completions.create.assert_called_once()


def test_complete_returns_string():
    """complete() always returns a plain string."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="hello")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("scripts.llm_client.Anthropic", return_value=mock_client):
        from scripts.llm_client import complete
        result = complete("claude-haiku-4-5-20251001", "sys", "usr")

    assert isinstance(result, str)


def test_complete_passes_max_tokens():
    """max_tokens parameter is forwarded to the API call."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("scripts.llm_client.Anthropic", return_value=mock_client):
        from scripts.llm_client import complete
        complete("claude-haiku-4-5-20251001", "sys", "usr", max_tokens=500)

    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["max_tokens"] == 500
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_llm_client.py -v
```

Expected: `ImportError` — `scripts.llm_client` doesn't exist yet.

- [ ] **Step 3: Create `scripts/llm_client.py`**

```python
"""
LLM Client — provider-agnostic completion wrapper.
Routes to Anthropic or OpenAI based on model name prefix.
Usage: from scripts.llm_client import complete
"""

import os
from anthropic import Anthropic
from openai import OpenAI


def complete(model: str, system: str, user: str, max_tokens: int = 2000) -> str:
    """
    Call the LLM and return the response text.

    Routes by model name:
    - "claude-*" → Anthropic Messages API (reads ANTHROPIC_API_KEY)
    - anything else → OpenAI Chat Completions API (reads OPENAI_API_KEY)

    Args:
        model: Model identifier string (e.g. "claude-haiku-4-5-20251001")
        system: System prompt string
        user: User message string
        max_tokens: Maximum tokens in response

    Returns:
        Response text as a plain string
    """
    if model.startswith("claude"):
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_llm_client.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run full suite to check no regressions**

```bash
uv run pytest tests/ --ignore=tests/test_content_generator.py --ignore=tests/test_playbook_refresher.py -q
```

Expected: 81 passed (same baseline as before this task).

- [ ] **Step 6: Commit**

```bash
git add scripts/llm_client.py tests/test_llm_client.py
git commit -m "feat: add llm_client.py — provider-agnostic complete() wrapper"
```

---

## Task 3: Overhaul `scripts/post_scorer.py`

**Files:**
- Modify: `scripts/post_scorer.py`
- Modify: `tests/test_post_scorer.py`

This task replaces the entire scorer. The existing tests will break because they reference the old 7-dimension schema and `score_post()` / `parse_score_response()`. We rewrite both file and tests together.

- [ ] **Step 1: Rewrite `tests/test_post_scorer.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
import json


# ── Dimension schema ────────────────────────────────────────────────────────

def test_dimensions_list_has_6_items():
    from scripts.post_scorer import DIMENSIONS
    assert len(DIMENSIONS) == 6


def test_dimensions_weights_sum_to_100():
    from scripts.post_scorer import DIMENSIONS
    assert sum(d["weight"] for d in DIMENSIONS) == 100


def test_dimension_keys():
    from scripts.post_scorer import DIMENSIONS
    keys = {d["key"] for d in DIMENSIONS}
    assert keys == {
        "hook_strength", "tone_compliance", "x_algorithm_optimization",
        "data_specificity", "pillar_alignment", "cta_quality"
    }
    assert "funnel_stage_accuracy" not in keys


# ── compute_composite_score ─────────────────────────────────────────────────

def test_compute_composite_score_all_tens():
    from scripts.post_scorer import compute_composite_score, DIMENSIONS
    scores = {d["key"]: 10 for d in DIMENSIONS}
    result = compute_composite_score(scores)
    # 10 * 1.0 (all weights sum to 100%) + 0.5 offset = 10.5
    assert result == 10.5


def test_compute_composite_score_never_list_violation_returns_zero():
    from scripts.post_scorer import compute_composite_score, DIMENSIONS
    scores = {d["key"]: 9 for d in DIMENSIONS}
    assert compute_composite_score(scores, never_list_violation=True) == 0.0


def test_compute_composite_score_includes_offset():
    from scripts.post_scorer import compute_composite_score, DIMENSIONS
    scores = {d["key"]: 0 for d in DIMENSIONS}
    # All zero + 0.5 offset = 0.5
    assert compute_composite_score(scores) == 0.5


def test_compute_composite_score_weighted():
    from scripts.post_scorer import compute_composite_score
    # Verify weights: hook=25, tone=20, x_algo=20, data=15, pillar=15, cta=5
    scores = {
        "hook_strength": 8,           # 25% * 8 = 2.00
        "tone_compliance": 6,         # 20% * 6 = 1.20
        "x_algorithm_optimization": 7, # 20% * 7 = 1.40
        "data_specificity": 10,       # 15% * 10 = 1.50
        "pillar_alignment": 9,        # 15% * 9 = 1.35
        "cta_quality": 4,             # 5% * 4 = 0.20
    }
    raw = sum([2.00, 1.20, 1.40, 1.50, 1.35, 0.20])  # = 7.65
    expected = round(raw + 0.5, 2)  # = 8.15
    result = compute_composite_score(scores)
    assert abs(result - expected) < 0.01


# ── batch_score_posts ────────────────────────────────────────────────────────

def test_batch_score_posts_returns_posts_with_scores(monkeypatch):
    """batch_score_posts() updates each post with score, score_breakdown, status."""
    from scripts.post_scorer import DIMENSIONS

    score_obj = {d["key"]: 9 for d in DIMENSIONS}
    score_obj["never_list_violation"] = False
    api_response = json.dumps([score_obj])

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    with patch("scripts.post_scorer.llm_complete", return_value=api_response):
        from scripts.post_scorer import batch_score_posts
        posts = [
            {"id": "1", "text": "Post one", "pillar": "AI Innovations",
             "funnel": "TOFU", "score": None, "score_breakdown": None, "status": "pending_score"},
        ]
        result = batch_score_posts(posts)

    assert result[0]["score"] is not None
    assert result[0]["score"] > 0
    assert result[0]["score_breakdown"] is not None
    assert result[0]["status"] in ("ready", "below_target")


def test_batch_score_posts_never_list_gives_zero(monkeypatch):
    """never_list_violation=true in response → score = 0.0."""
    from scripts.post_scorer import DIMENSIONS

    score_obj = {d["key"]: 9 for d in DIMENSIONS}
    score_obj["never_list_violation"] = True
    api_response = json.dumps([score_obj])

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    with patch("scripts.post_scorer.llm_complete", return_value=api_response):
        from scripts.post_scorer import batch_score_posts
        posts = [
            {"id": "1", "text": "Post #hashtag", "pillar": "AI Innovations",
             "funnel": "TOFU", "score": None, "score_breakdown": None, "status": "pending_score"},
        ]
        result = batch_score_posts(posts)

    assert result[0]["score"] == 0.0


# ── score_all_posts ──────────────────────────────────────────────────────────

def test_score_all_posts_returns_all_posts(monkeypatch):
    """score_all_posts() returns same number of posts as input."""
    from scripts.post_scorer import DIMENSIONS

    score_obj = {d["key"]: 9 for d in DIMENSIONS}
    score_obj["never_list_violation"] = False
    api_response = json.dumps([score_obj, score_obj])

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    with patch("scripts.post_scorer.llm_complete", return_value=api_response):
        with patch("scripts.post_scorer.get_todays_pillar", return_value={"pillar": "AI Innovations", "funnel": "TOFU"}):
            with patch("scripts.post_scorer.get_trends", return_value="trend context"):
                from scripts.post_scorer import score_all_posts
                posts = [
                    {"id": "1", "text": "Good post", "pillar": "AI Innovations",
                     "funnel": "TOFU", "score": None, "score_breakdown": None, "status": "pending_score"},
                    {"id": "2", "text": "Another post", "pillar": "AI Innovations",
                     "funnel": "TOFU", "score": None, "score_breakdown": None, "status": "pending_score"},
                ]
                result = score_all_posts(posts)

    assert len(result) == 2


# ── regenerate_if_below_floor (legacy wrapper) ───────────────────────────────

def test_regenerate_if_below_floor_is_single_post_wrapper(monkeypatch):
    """regenerate_if_below_floor() delegates to score_all_posts() and returns one post."""
    from scripts.post_scorer import DIMENSIONS

    score_obj = {d["key"]: 9 for d in DIMENSIONS}
    score_obj["never_list_violation"] = False
    api_response = json.dumps([score_obj])

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    with patch("scripts.post_scorer.llm_complete", return_value=api_response):
        with patch("scripts.post_scorer.get_todays_pillar", return_value={"pillar": "AI Innovations", "funnel": "TOFU"}):
            with patch("scripts.post_scorer.get_trends", return_value="ctx"):
                from scripts.post_scorer import regenerate_if_below_floor
                post = {
                    "id": "1", "text": "Some post", "pillar": "AI Innovations",
                    "funnel": "TOFU", "score": None, "score_breakdown": None, "status": "pending_score"
                }
                result = regenerate_if_below_floor(post)

    assert isinstance(result, dict)
    assert "score" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_post_scorer.py -v
```

Expected: Most tests FAIL — old 7-dim schema, missing `batch_score_posts`, etc.

- [ ] **Step 3: Rewrite `scripts/post_scorer.py`**

```python
"""
Post Scorer — D3
Batch-scores draft posts using Claude as judge. Max 4 API calls for any N posts.
Usage: python -m scripts.post_scorer
"""

import json
import os
import uuid

from dotenv import load_dotenv

from scripts.cadence import get_todays_pillar
from scripts.content_generator import generate
from scripts.llm_client import complete as llm_complete
from scripts.post_queue import load_queue, save_queue
from scripts.trend_scanner import run as get_trends

load_dotenv()

GEN_MODEL_KEY = "scoring"  # reads config["models"]["scoring"]
MAX_REGENERATION_ATTEMPTS = 2
QUALITY_FLOOR = 8.0
TARGET_THRESHOLD = 9.25

DIMENSIONS = [
    {"key": "hook_strength",           "weight": 25,
     "description": "Harry Dry 3 tests: Can I visualize it? Can I falsify it? Can nobody else say this? "
                    "All 3 must pass for 9+. Vague claims or clichés = 5/10 max."},
    {"key": "tone_compliance",         "weight": 20,
     "description": "Six Core Laws (Direct, Data-First, Casual Confidence, Outcome-First, Business Casual, Equal Status). "
                    "ZERO hashtags, ZERO emdashes, ZERO exclamation marks, ZERO hedging ('seems','could','might'). "
                    "Any hashtag = 0/10. Score 9+ only if flawless."},
    {"key": "x_algorithm_optimization","weight": 20,
     "description": "Reply=27x like, Repost=20x like. 9+ requires: ZERO hashtags + specific falsifiable claim "
                    "that makes someone want to publicly argue back. DM CTA alone = 7. "
                    "Bold contestable claim with data = 9+."},
    {"key": "data_specificity",        "weight": 15,
     "description": "Must cite real numbers, named people/products, or concrete outcomes. "
                    "Abstract claims = 6/10 max. Specific data = 9+/10."},
    {"key": "pillar_alignment",        "weight": 15,
     "description": "Reader should know the content pillar in the first sentence. "
                    "Vague or generic opener = 6/10 max. Score 9+ only if pillar is unmistakable immediately."},
    {"key": "cta_quality",             "weight": 5,
     "description": "TOFU only: awareness/follow/debate-bait CTAs score highest. "
                    "No hard sell, no newsletter push, no link drop. "
                    "Soft engagement (reply, follow) or a bold claim with no explicit CTA = 8+. "
                    "DM push = 5."},
]

SCORING_RUBRIC = """Score each post on 6 dimensions (0-10 integers). Use X Algorithm weights: Reply=27x like, Repost=20x like.

hook_strength (25%): Harry Dry 3 tests — visualizable, falsifiable, nobody else can say this. 9+ only if all 3 pass. Generic = 5 max.
tone_compliance (20%): Six Core Laws + ZERO hashtags/emdashes/exclamation marks/hedging. Any hashtag = 0. 9+ if flawless.
x_algorithm_optimization (20%): 9+ = ZERO hashtags + specific falsifiable claim someone argues back at. DM CTA alone = 7. Debate-bait + data = 9+.
data_specificity (15%): Named people/products, concrete numbers, falsifiable outcomes. Abstract claim = 6 max.
pillar_alignment (15%): Pillar clear in first sentence. Vague opener = 6 max. Score 9+ only if pillar is unmistakable.
cta_quality (5%): TOFU. No hard sell, no link drop. Bold claim or follow invite = 8+. DM push = 5.

CRITICAL: If post contains ANY hashtag (#), mark never_list_violation = true."""

REGEN_HARD_RULES = """HARD RULES (NON-NEGOTIABLE):
- ZERO hashtags. EVER.
- ZERO exclamation marks (!)
- ZERO em-dashes (—). Use periods or colons.
- No soft CTAs: "What's your...", "How are you...", "Thoughts?", "Let's discuss"
- No cheesy openers: "Imagine", "Let's dive in", "Let's explore"
- No banned words: streamline, transformative, unlock, ecosystem, landscape, game-changer
- TOFU only: awareness/follow/debate-bait CTAs. No DM asks, no links.

REFRAME WEAK HOOKS using one of:
- COMPETITIVE DISADVANTAGE: "If you're still [old way], your competitors are beating you [specific way]."
- TRUTH NOBODY ADMITS: "The real reason [authority] won't discuss [topic] is [specific truth]."
- TIMESTAMP OBSOLESCENCE: "Anyone still [old way] in 2026 is [consequence]. The ones who shifted to [new way] are [winning how]."
- INVERSE RISK: "People think [common belief] is risky. Real risk is [opposite]. [Data]."
"""


def _get_scoring_model() -> str:
    from scripts.config_loader import get_config
    return get_config()["models"]["scoring"]


def _build_shared_scoring_context() -> str:
    """Build rubric + optional benchmark patterns + optional calibration. Called once per batch."""
    ctx = SCORING_RUBRIC

    try:
        with open("data/benchmark_insights.json", encoding="utf-8") as f:
            insights = json.load(f)
        patterns = insights.get("patterns", {}).get("hook_patterns", [])[:3]
        if patterns:
            ctx += "\nBenchmark hook patterns (top performers):\n"
            ctx += "\n".join(f"- {p}" for p in patterns)
    except Exception:
        pass

    try:
        from scripts.performance_analyzer import load_calibration
        cal = load_calibration()
        if cal:
            ctx += f"\n\nCalibration ({cal['post_count']} live posts): avg engagement {cal['avg_engagement_score']}"
            if cal.get("blind_spots"):
                ctx += "\nOverrated patterns: " + "; ".join(
                    f"\"{b['text_preview']}\"" for b in cal["blind_spots"][:2]
                )
            if cal.get("undervalued_signals"):
                ctx += "\nUnderrated patterns: " + "; ".join(
                    f"\"{u['text_preview']}\"" for u in cal["undervalued_signals"][:2]
                )
    except Exception:
        pass

    return ctx


def compute_composite_score(scores: dict, never_list_violation: bool = False) -> float:
    """Compute weighted composite score with +0.5 calibration offset. Returns 0.0 on violation."""
    if never_list_violation:
        return 0.0
    total = sum(scores.get(d["key"], 0) * (d["weight"] / 100) for d in DIMENSIONS)
    total += 0.5  # calibration offset
    return round(total, 2)


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _weak_dims(score_breakdown: dict) -> str:
    """Return comma-separated dimension names scoring below 8."""
    if not score_breakdown:
        return "all"
    return (
        ", ".join(k for k, v in score_breakdown.items() if isinstance(v, (int, float)) and v < 8)
        or "none"
    )


def batch_score_posts(posts: list[dict]) -> list[dict]:
    """Score all posts in a single API call. Mutates and returns posts with score fields."""
    if not posts:
        return posts

    shared_context = _build_shared_scoring_context()
    posts_block = "\n\n".join(
        f'POST {i + 1}:\n"""{p["text"]}"""\nPillar: {p.get("pillar", "")}'
        for i, p in enumerate(posts)
    )

    prompt = f"""{shared_context}

Score each of the following {len(posts)} posts. Return a JSON array with one object per post in order.
Each object must have exactly these keys: hook_strength, tone_compliance, x_algorithm_optimization, data_specificity, pillar_alignment, cta_quality (all integers 0-10), and never_list_violation (boolean).

{posts_block}

Return ONLY a valid JSON array. No explanation, no markdown fences."""

    raw = llm_complete(
        model=_get_scoring_model(),
        system="You are a Twitter content quality judge. Respond only with valid JSON.",
        user=prompt,
        max_tokens=150 * len(posts),
    )

    results = json.loads(_strip_fences(raw))

    for post, score_obj in zip(posts, results):
        violation = bool(score_obj.pop("never_list_violation", False))
        composite = compute_composite_score(score_obj, never_list_violation=violation)
        post["score"] = composite
        post["score_breakdown"] = score_obj
        post["never_list_violation"] = violation
        post["status"] = "ready" if composite >= TARGET_THRESHOLD else "below_target"

    return posts


def batch_regenerate_posts(failing_posts: list[dict], trend_context: str) -> list[dict]:
    """Regenerate all failing posts in a single API call. Returns new post dicts."""
    if not failing_posts:
        return failing_posts

    posts_block = "\n\n".join(
        f'POST {i + 1} (weak dims: {_weak_dims(p.get("score_breakdown", {}))}, score: {p.get("score", "?")})\n"""{p["text"]}"""'
        for i, p in enumerate(failing_posts)
    )

    prompt = f"""You are a Twitter content coach. Revise each failing post to fix its weak dimensions.

{REGEN_HARD_RULES}

Trend context to leverage: {trend_context[:500]}

{posts_block}

Return a JSON array of {len(failing_posts)} revised post texts in order. Each element is just the post text string.
Return ONLY valid JSON array. No explanation, no markdown fences."""

    raw = llm_complete(
        model=_get_scoring_model(),
        system="You are a Twitter content coach. Respond only with valid JSON.",
        user=prompt,
        max_tokens=350 * len(failing_posts),
    )

    revised_texts = json.loads(_strip_fences(raw))

    return [
        {
            **post,
            "id": str(uuid.uuid4()),
            "text": new_text,
            "score": None,
            "score_breakdown": None,
            "status": "pending_score",
        }
        for post, new_text in zip(failing_posts, revised_texts)
    ]


def score_all_posts(posts: list[dict]) -> list[dict]:
    """
    Batch score → batch regen failing → batch rescore. Max 4 API calls total.
    All posts are returned; below-floor posts get status='below_target'.
    """
    if not posts:
        return posts

    print(f"  Batch scoring {len(posts)} posts...", flush=True)
    scored = batch_score_posts(posts)

    failing = [p for p in scored if (p.get("score") or 0) < TARGET_THRESHOLD]
    passing = [p for p in scored if (p.get("score") or 0) >= TARGET_THRESHOLD]

    print(f"  Scores: {[p['score'] for p in scored]} | Failing: {len(failing)}", flush=True)

    if not failing:
        return scored

    today = get_todays_pillar()
    trend_context = get_trends(pillar=today["pillar"], funnel=today["funnel"])

    for attempt in range(1, MAX_REGENERATION_ATTEMPTS + 1):
        print(
            f"  Batch regenerating {len(failing)} posts (attempt {attempt}/{MAX_REGENERATION_ATTEMPTS})...",
            flush=True,
        )
        revised = batch_regenerate_posts(failing, trend_context)
        rescored = batch_score_posts(revised)

        still_failing = []
        for original, candidate in zip(failing, rescored):
            if (candidate.get("score") or 0) >= TARGET_THRESHOLD:
                passing.append(candidate)
            elif (candidate.get("score") or 0) > (original.get("score") or 0):
                still_failing.append(candidate)
            else:
                still_failing.append(original)

        failing = still_failing
        if not failing:
            break

    for p in failing:
        p["status"] = "below_target"

    return passing + failing


def regenerate_if_below_floor(post: dict) -> dict:
    """Legacy single-post wrapper. Delegates to score_all_posts()."""
    results = score_all_posts([post])
    return results[0] if results else post


if __name__ == "__main__":
    queue = load_queue()
    pending = [p for p in queue if p["status"] == "pending_score"]
    unchanged = [p for p in queue if p["status"] != "pending_score"]

    if not pending:
        print("No posts pending scoring.")
    else:
        print(f"Scoring {len(pending)} posts in batch...")
        scored = score_all_posts(pending)
        save_queue(unchanged + scored)

        ready = [p for p in scored if p["status"] == "ready"]
        below = [p for p in scored if p["status"] == "below_target"]
        print(f"\nScoring complete.")
        print(f"Ready (>={TARGET_THRESHOLD}): {len(ready)} | Below target: {len(below)}")
        for p in scored:
            print(f"  [{p['status'].upper()}] {p['score']} — {p['text'][:60]}...")
```

- [ ] **Step 4: Run new scorer tests**

```bash
uv run pytest tests/test_post_scorer.py -v
```

Expected: All new tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ --ignore=tests/test_content_generator.py --ignore=tests/test_playbook_refresher.py -q
```

Expected: All pass (server.py calls `regenerate_if_below_floor` which is still present as wrapper).

- [ ] **Step 6: Commit**

```bash
git add scripts/post_scorer.py tests/test_post_scorer.py
git commit -m "feat: overhaul post_scorer — 6-dim TOFU rubric, batch scoring, llm_client"
```

---

## Task 4: Overhaul `scripts/content_generator.py`

**Files:**
- Modify: `scripts/content_generator.py`
- Modify: `tests/test_content_generator.py` (currently excluded due to ImportError — we fix it here)

Note: `tests/test_content_generator.py` is currently excluded from collection due to `ImportError: cannot import name 'PLAYBOOK_PATHS'`. After this task it will be collectible and must pass.

- [ ] **Step 1: Write failing tests**

Create/overwrite `tests/test_content_generator.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


# ── validate_post ────────────────────────────────────────────────────────────

def test_validate_post_rejects_hashtag():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("Great AI insight. #AI is changing everything.")
    assert valid is False
    assert reason == "contains_hashtags"


def test_validate_post_rejects_fullwidth_hashtag():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("Great post ＃AI here.")
    assert valid is False
    assert reason == "contains_hashtags"


def test_validate_post_rejects_emdash():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("AI is growing — and fast.")
    assert valid is False
    assert reason == "contains_emdash"


def test_validate_post_rejects_soft_question_at_end():
    from scripts.content_generator import validate_post
    valid, reason = validate_post(
        "Most AI researchers are ignoring the inference cost problem. How do you handle this?"
    )
    assert valid is False
    assert reason == "soft_qa_cta"


def test_validate_post_rejects_weak_cta_phrase():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("IPL 2026 is wild. What do you think about the batting line-ups?")
    assert valid is False
    assert "weak_cta" in reason


def test_validate_post_accepts_clean_post():
    from scripts.content_generator import validate_post
    valid, reason = validate_post(
        "Dota 2's new patch broke every carry hero in the top 1000 MMR bracket. "
        "The ones adapting to support meta are already climbing. Follow for daily breakdowns."
    )
    assert valid is True
    assert reason == ""


def test_validate_post_accepts_post_with_question_in_body_not_end():
    """Soft question in body is OK; only rejected if it's in the final 80 chars."""
    from scripts.content_generator import validate_post
    valid, reason = validate_post(
        "How do top AI labs manage inference cost? Simple: they don't. "
        "They offload it to enterprise contracts. The open-source labs are the ones actually solving it."
    )
    assert valid is True


# ── load_playbooks ────────────────────────────────────────────────────────────

def test_load_playbooks_uses_distilled_when_available(tmp_path, monkeypatch):
    """If distilled file exists and has all 3 keys, use it."""
    distilled = {"voice": "v", "twitter": "t", "strategy": "s"}
    distilled_path = tmp_path / "playbook_distilled.json"
    distilled_path.write_text('{"voice": "v", "twitter": "t", "strategy": "s"}')

    monkeypatch.setattr("scripts.content_generator._DISTILLED_PATH", str(distilled_path))

    from scripts.content_generator import load_playbooks
    result = load_playbooks()
    assert result == distilled


def test_load_playbooks_falls_back_to_full_when_distilled_missing(tmp_path, monkeypatch):
    """Falls back to full playbooks when distilled file does not exist."""
    monkeypatch.setattr(
        "scripts.content_generator._DISTILLED_PATH",
        str(tmp_path / "nonexistent.json"),
    )

    fake_voice = tmp_path / "voice.md"
    fake_voice.write_text("voice content")
    fake_twitter = tmp_path / "twitter.md"
    fake_twitter.write_text("twitter content")
    fake_strategy = tmp_path / "strategy.md"
    fake_strategy.write_text("strategy content")

    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "playbooks": {
                "voice": str(fake_voice),
                "twitter": str(fake_twitter),
                "strategy": str(fake_strategy),
            }
        },
    )

    from scripts.content_generator import load_playbooks
    result = load_playbooks()
    assert result["voice"] == "voice content"
    assert result["twitter"] == "twitter content"
    assert result["strategy"] == "strategy content"


# ── generate ─────────────────────────────────────────────────────────────────

def test_generate_filters_invalid_posts(monkeypatch, tmp_path):
    """generate() drops posts that fail validate_post() before returning."""
    monkeypatch.setattr(
        "scripts.content_generator._DISTILLED_PATH",
        str(tmp_path / "nonexistent.json"),
    )

    fake_playbooks = {"voice": "v", "twitter": "t", "strategy": "s"}
    monkeypatch.setattr("scripts.content_generator.load_playbooks", lambda: fake_playbooks)
    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "handle": "testuser",
            "bio": "test bio",
            "models": {"generation": "claude-haiku-4-5-20251001"},
            "benchmark_accounts": [],
        },
    )

    # One valid, one with hashtag (invalid)
    raw_response = "1. Clean post about Dota 2 patches and meta shifts. Follow for more.\n2. Post with #hashtag inside it."

    monkeypatch.setattr("scripts.content_generator.llm_complete", lambda **kwargs: raw_response)

    from scripts.content_generator import generate
    result = generate(pillar="eSports & Dota 2", funnel="TOFU", trend_context="ctx", num_drafts=2)

    assert len(result) == 1
    assert "#hashtag" not in result[0]


def test_generate_uses_num_drafts_in_prompt(monkeypatch, tmp_path):
    """num_drafts parameter appears in the user message sent to LLM."""
    monkeypatch.setattr(
        "scripts.content_generator._DISTILLED_PATH",
        str(tmp_path / "nonexistent.json"),
    )
    monkeypatch.setattr("scripts.content_generator.load_playbooks", lambda: {"voice": "v", "twitter": "t", "strategy": "s"})
    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "handle": "h", "bio": "b",
            "models": {"generation": "claude-haiku-4-5-20251001"},
            "benchmark_accounts": [],
        },
    )

    captured = {}

    def fake_llm(**kwargs):
        captured["user"] = kwargs.get("user", "")
        return "1. Some post text here without any violations."

    monkeypatch.setattr("scripts.content_generator.llm_complete", fake_llm)

    from scripts.content_generator import generate
    generate(pillar="AI Innovations", funnel="TOFU", trend_context="ctx", num_drafts=3)

    assert "3" in captured["user"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_content_generator.py -v
```

Expected: `ImportError` or test failures — `validate_post`, `load_playbooks` cache, `llm_complete` don't exist yet in this form.

- [ ] **Step 3: Rewrite `scripts/content_generator.py`**

```python
"""
Content Generator — D2
Reads playbooks (distilled if available) + trend context, calls LLM, drafts post variants.
Usage: python -m scripts.content_generator
"""

import json
import os
import re
import uuid

from dotenv import load_dotenv

from scripts.cadence import get_todays_pillar
from scripts.config_loader import get_config
from scripts.llm_client import complete as llm_complete
from scripts.post_queue import add_post
from scripts.trend_scanner import run as get_trends

load_dotenv()

NUM_DRAFTS = 8  # default; pipeline passes explicit num_drafts per pillar
_DISTILLED_PATH = "data/playbook_distilled.json"


# ── Playbook loading ──────────────────────────────────────────────────────────

def load_playbooks() -> dict[str, str]:
    """Load playbooks. Uses distilled version (~1k tokens) if available, else full (~4.5k tokens)."""
    try:
        with open(_DISTILLED_PATH, encoding="utf-8") as f:
            distilled = json.load(f)
        if distilled.get("voice") and distilled.get("twitter") and distilled.get("strategy"):
            return distilled
    except Exception:
        pass

    paths = get_config()["playbooks"]
    result = {}
    for key, path in paths.items():
        with open(path, encoding="utf-8") as f:
            result[key] = f.read()
    return result


def distill_playbooks() -> None:
    """
    Compress full playbooks to ~1k token distilled version. One-time cost via Haiku.
    Caches result to data/playbook_distilled.json.
    Call manually: uv run python -c "from scripts.content_generator import distill_playbooks; distill_playbooks()"
    """
    cfg = get_config()
    paths = cfg["playbooks"]
    full = {}
    for key, path in paths.items():
        with open(path, encoding="utf-8") as f:
            full[key] = f.read()

    prompt = """Distill these three playbooks into compact rules for an AI content generator.
Output a JSON object with keys "voice", "twitter", "strategy".
Each value must be under 350 words. Include only:
- Core laws / rules (one line each)
- Never list (banned words/phrases)
- Hook formulas (one line each)
- CTA rule
- Pillar definitions (one line each)
No examples, no tables, no explanations. Just the rules.

VOICE PLAYBOOK:
""" + full["voice"][:3000] + """

TWITTER PLAYBOOK:
""" + full["twitter"][:3000] + """

STRATEGY PLAYBOOK:
""" + full["strategy"][:3000] + """

Return ONLY valid JSON. No markdown fences."""

    model = cfg["models"]["generation"]
    raw = llm_complete(model=model, system="You are a concise technical writer.", user=prompt, max_tokens=1200)

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    distilled = json.loads(raw.strip())
    os.makedirs("data", exist_ok=True)
    with open(_DISTILLED_PATH, "w", encoding="utf-8") as f:
        json.dump(distilled, f, indent=2)
    print(f"Playbooks distilled and cached to {_DISTILLED_PATH}")


# ── Benchmark insights ────────────────────────────────────────────────────────

def _load_benchmark_insights() -> dict | None:
    """Load benchmark_insights.json. Returns None if absent or malformed."""
    try:
        with open("data/benchmark_insights.json", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("top_posts") or not data.get("patterns"):
            return None
        return data
    except FileNotFoundError:
        return None
    except Exception:
        return None


# ── Post validation ───────────────────────────────────────────────────────────

_WEAK_CTA_PHRASES = [
    "what do you think", "what are your thoughts", "share your thoughts",
    "share your strategies", "share your insights", "share your feedback",
    "let me know your", "comments below", "in the comments", "drop a comment",
    "let's discuss", "let's explore", "reach out to", "feel free to",
    "get in touch", "book a", "schedule a",
]

_SOFT_QUESTION_ENDINGS = [
    "what's your ", "how are you ", "what are you ",
    "how do you ", "are your", "what does your ",
]


def validate_post(text: str) -> tuple[bool, str]:
    """
    Check post against hard rules. Returns (is_valid, reason_if_invalid).
    Reason is "" when valid.
    """
    # Hashtags (regular and fullwidth)
    if "#" in text or "＃" in text:
        return False, "contains_hashtags"

    # Em-dashes
    if "—" in text:
        return False, "contains_emdash"

    # Soft question in final 80 chars
    last_80 = text.lower()[-80:]
    for phrase in _SOFT_QUESTION_ENDINGS:
        if phrase in last_80:
            return False, "soft_qa_cta"

    # Weak CTA phrases anywhere
    text_lower = text.lower()
    for phrase in _WEAK_CTA_PHRASES:
        if phrase in text_lower:
            return False, f"weak_cta:{phrase}"

    return True, ""


# ── Prompt building ───────────────────────────────────────────────────────────

def build_system_prompt(pillar: str, funnel: str, num_drafts: int = NUM_DRAFTS) -> str:
    playbooks = load_playbooks()
    cfg = get_config()

    prompt = f"""You are the content engine for @{cfg['handle']}, a {cfg['bio']}.

## Voice Guide
{playbooks['voice']}

## Twitter Rules
{playbooks['twitter']}

## Content Strategy
{playbooks['strategy']}

## Today's Assignment
- Content pillar: {pillar}
- Funnel stage: {funnel} (TOFU — discovery-oriented, no hard CTAs, no link drops)

Your job is to write {num_drafts} distinct post variants for today's pillar. Each must:

1. **HOOK** — Pass Harry Dry's 3 tests: Can I visualize it? Can I falsify it? Can nobody else say this?
   STRONG: Specific, debatable, falsifiable claim in the first sentence.
   WEAK: "AI is changing everything." / "This matters." / Vague observations.

2. **DATA** — Cite real numbers, named people/products, or concrete outcomes.
   STRONG: "GPT-4o's context window is 128k tokens — 32x the average attention span of a Twitter thread."
   WEAK: "AI models are getting better every month."

3. **ADVERSARIAL FRAME** — Every post must open with ONE of these frames:
   - COMPETITIVE DISADVANTAGE: "If you're still [old way], your peers are already [beating you how]."
   - TRUTH NOBODY ADMITS: "The real reason [authority] won't discuss [topic] is [specific truth]."
   - TIMESTAMP OBSOLESCENCE: "Anyone still [old way] in 2026 is [consequence]. The ones who shifted are [winning how]."
   - INVERSE RISK: "People think [belief] is risky. Real risk is [opposite]. [Data]."

4. **TONE** — Direct, casual confidence. ZERO emdashes, ZERO exclamation marks, ZERO hashtags, ZERO hedging.
   Kill these words: "seems", "appears", "could", "might", "arguably", "transformative", "ecosystem", "landscape", "unlock", "streamline"

5. **CTA (TOFU)** — Awareness or follow invite only. No DMs, no links, no newsletter pushes.
   STRONG: Bold claim, follow invite, or debate-bait statement.
   WEAK: "DM me", "Check the link", "Sign up", "What do you think?"

6. **LENGTH** — Any length is fine. Longer posts score well when they add data, contrast, or step-by-step logic. Do not pad with filler.

## CRITICAL: No AI fingerprints
FORBIDDEN: emdashes (—), exclamation marks (!), hashtags (#), "Let's dive in", "It's worth noting",
"Not just X, not just Y, but Z", parenthetical asides like "(this is key)", "Simply put:", "The truth is:"

Format your response as a numbered list:
1. [post text]
2. [post text]
...{num_drafts}. [post text]

Write only the post text. No labels, no commentary."""

    # Performance calibration (graceful)
    try:
        from scripts.performance_analyzer import load_calibration
        cal = load_calibration()
        if cal:
            prompt += f"\n\n## Performance Calibration (from {cal['post_count']} live posts)\n"
            prompt += f"Average engagement score: {cal['avg_engagement_score']}\n"
            if cal.get("blind_spots"):
                prompt += "Scoring blind spots (high predicted, low actual engagement):\n"
                for bs in cal["blind_spots"][:3]:
                    prompt += f"- Score {bs['predicted']}: \"{bs['text_preview']}\"\n"
            if cal.get("undervalued_signals"):
                prompt += "Undervalued patterns (lower predicted, high actual engagement):\n"
                for uv in cal["undervalued_signals"][:3]:
                    prompt += f"- Score {uv['predicted']}: \"{uv['text_preview']}\"\n"
    except Exception:
        pass

    # Benchmark injection (graceful)
    try:
        insights = _load_benchmark_insights()
        if insights:
            cfg = get_config()
            accounts = cfg.get("benchmark_accounts", [])
            patterns = insights.get("patterns", {})
            top_posts = insights.get("top_posts", [])[:3]

            prompt += f"\n\n## Benchmark Calibration (from {', '.join('@' + a for a in accounts)})\n"

            for label, key in [
                ("Hook patterns", "hook_patterns"),
                ("CTA patterns that drive replies", "cta_patterns"),
                ("Engagement drivers", "engagement_drivers"),
            ]:
                items = patterns.get(key, [])[:3]
                if items:
                    prompt += f"{label}:\n" + "\n".join(f"- {p}" for p in items) + "\n"

            if patterns.get("reply_triggers"):
                prompt += "What drove REPLIES specifically (27x signal):\n"
                for p in patterns["reply_triggers"][:3]:
                    prompt += f"- {p}\n"

            if top_posts:
                prompt += "\nTop benchmark posts by X Algorithm score (27x replies + 20x retweets + 1x likes):\n"
                for post in top_posts:
                    score_note = (
                        f"[{post.get('replies', 0)} replies, {post.get('retweets', 0)} retweets, "
                        f"{post.get('likes', 0)} likes → score {post.get('score', '?')}]"
                    )
                    prompt += f'- [{post["account"]}] {score_note}\n  "{post["text"][:120]}"\n'
    except Exception:
        pass

    return prompt


# ── Draft parsing ─────────────────────────────────────────────────────────────

def parse_drafts(raw: str) -> list[str]:
    """Extract numbered posts from LLM response."""
    lines = raw.strip().split("\n")
    drafts = []
    current = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                drafts.append(" ".join(current).strip())
                current = []
            continue
        if re.match(r"^\d+\.\s", stripped):
            if current:
                drafts.append(" ".join(current).strip())
            current = [re.sub(r"^\d+\.\s*", "", stripped)]
        else:
            current.append(stripped)

    if current:
        drafts.append(" ".join(current).strip())

    return [d for d in drafts if d]


# ── Generation ────────────────────────────────────────────────────────────────

def generate(pillar: str, funnel: str, trend_context: str, num_drafts: int = NUM_DRAFTS) -> list[str]:
    """Generate draft posts via LLM. Filters invalid posts before returning."""
    cfg = get_config()
    model = cfg["models"]["generation"]
    system = build_system_prompt(pillar=pillar, funnel=funnel, num_drafts=num_drafts)
    user_message = (
        f"Trending context for today:\n{trend_context}\n\n"
        f"Write all {num_drafts} posts now."
    )

    raw = llm_complete(model=model, system=system, user=user_message, max_tokens=2000)
    drafts = parse_drafts(raw)
    print(f"[GENERATE] {len(drafts)} raw drafts. Validating...", flush=True)

    valid = []
    for i, draft in enumerate(drafts, 1):
        is_valid, reason = validate_post(draft)
        if is_valid:
            valid.append(draft)
        else:
            print(f"  [DRAFT {i}] REJECTED — {reason}: {draft[:60]}", flush=True)

    print(f"[GENERATE] {len(valid)}/{len(drafts)} passed validation.", flush=True)
    return valid


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    today = get_todays_pillar()
    print(f"Generating posts for: {today['pillar']} ({today['funnel']})")

    trend_context = get_trends(pillar=today["pillar"], funnel=today["funnel"])
    print(f"\nTrend context:\n{trend_context}\n")

    drafts = generate(pillar=today["pillar"], funnel=today["funnel"], trend_context=trend_context)
    print(f"Generated {len(drafts)} drafts")

    for draft in drafts:
        post = {
            "id": str(uuid.uuid4()),
            "text": draft,
            "pillar": today["pillar"],
            "funnel": today["funnel"],
            "score": None,
            "score_breakdown": None,
            "status": "pending_score",
        }
        add_post(post)
        print(f"  Added: {draft[:80]}...")

    print("\nDrafts written to data/queue.json")
```

- [ ] **Step 4: Run content generator tests**

```bash
uv run pytest tests/test_content_generator.py -v
```

Expected: All new tests PASS.

- [ ] **Step 5: Run full suite — content_generator.py is now collectible**

```bash
uv run pytest tests/ --ignore=tests/test_playbook_refresher.py -q
```

Expected: All pass. Note: `test_content_generator.py` is no longer excluded.

- [ ] **Step 6: Commit**

```bash
git add scripts/content_generator.py tests/test_content_generator.py
git commit -m "feat: overhaul content_generator — playbook distillation, validate_post, llm_client"
```

---

## Task 5: Create `scripts/benchmark_analyzer.py`

**Files:**
- Create: `scripts/benchmark_analyzer.py`
- Create: `tests/test_benchmark_analyzer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_benchmark_analyzer.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


def test_compute_weighted_score():
    from scripts.benchmark_analyzer import compute_weighted_score
    # Reply=27x, Repost=20x, Like=1x
    score = compute_weighted_score(likes=10, retweets=5, replies=2)
    assert score == 10 + (5 * 20) + (2 * 27)  # = 10 + 100 + 54 = 164


def test_compute_weighted_score_zero():
    from scripts.benchmark_analyzer import compute_weighted_score
    assert compute_weighted_score(0, 0, 0) == 0


def test_compute_account_stats_empty():
    from scripts.benchmark_analyzer import compute_account_stats
    stats = compute_account_stats([])
    assert stats["post_count"] == 0
    assert stats["top_posts"] == []


def test_compute_account_stats_top_posts():
    from scripts.benchmark_analyzer import compute_account_stats
    posts = [
        {"likes": 10, "retweets": 1, "replies": 0, "score": 30},
        {"likes": 5, "retweets": 2, "replies": 3, "score": 126},
        {"likes": 1, "retweets": 0, "replies": 0, "score": 1},
    ]
    stats = compute_account_stats(posts)
    assert stats["post_count"] == 3
    # Top post should be the one with score=126
    assert stats["top_posts"][0]["score"] == 126


def test_fetch_account_posts_returns_empty_without_client():
    from scripts.benchmark_analyzer import fetch_account_posts
    # client=None → returns []
    result = fetch_account_posts(client=None, handle="testhandle")
    assert result == []


def test_load_report_returns_none_when_missing(tmp_path, monkeypatch):
    from scripts.benchmark_analyzer import BENCHMARK_REPORT_PATH
    monkeypatch.setattr(
        "scripts.benchmark_analyzer.BENCHMARK_REPORT_PATH",
        str(tmp_path / "nonexistent.json"),
    )
    from scripts.benchmark_analyzer import load_report
    assert load_report() is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_benchmark_analyzer.py -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Create `scripts/benchmark_analyzer.py`**

```python
"""
Benchmark Analyzer — standalone utility.
Fetches engagement metrics from benchmark accounts, extracts content patterns via LLM,
writes data/benchmark_report.json and data/benchmark_insights.json.

Usage: uv run python -m scripts.benchmark_analyzer

Requires X_BEARER_TOKEN and ANTHROPIC_API_KEY in .env.
Once run, scorer and generator pick up benchmark_insights.json automatically.
"""

import json
import logging
import os
import statistics
from datetime import datetime

import tweepy
from dotenv import load_dotenv

from scripts.config_loader import get_config
from scripts.llm_client import complete as llm_complete
from scripts.post_queue import load_queue

load_dotenv()

logger = logging.getLogger(__name__)

BENCHMARK_REPORT_PATH = "data/benchmark_report.json"
BENCHMARK_INSIGHTS_PATH = "data/benchmark_insights.json"
MAX_POSTS_PER_ACCOUNT = 50
TOP_N_POSTS = 5
TOP_N_FOR_INSIGHTS = 10

WEIGHT_RETWEET = 20
WEIGHT_REPLY = 27


def compute_weighted_score(likes: int, retweets: int, replies: int) -> int:
    """X Algorithm weighted engagement: Reply=27x like, Repost=20x like."""
    return likes + (retweets * WEIGHT_RETWEET) + (replies * WEIGHT_REPLY)


def _build_x_client() -> tweepy.Client | None:
    bearer_token = os.getenv("X_BEARER_TOKEN")
    if not bearer_token:
        logger.warning("X_BEARER_TOKEN not set — benchmark will skip API calls.")
        return None
    try:
        return tweepy.Client(bearer_token=bearer_token)
    except Exception as e:
        logger.error(f"Failed to build tweepy client: {e}")
        return None


def fetch_account_posts(client: tweepy.Client | None, handle: str, max_results: int = MAX_POSTS_PER_ACCOUNT) -> list[dict]:
    """Fetch up to max_results original tweets from @handle. Returns [] on any error."""
    if not client:
        return []
    try:
        user_id = client.get_user(username=handle).data.id
        tweets = client.get_users_tweets(
            user_id,
            tweet_fields=["public_metrics"],
            exclude=["retweets", "replies"],
            max_results=max_results,
        )
        if not tweets.data:
            return []

        posts = []
        for tweet in tweets.data:
            m = tweet.public_metrics
            posts.append({
                "id": str(tweet.id),
                "text": tweet.text,
                "likes": m["like_count"],
                "retweets": m["retweet_count"],
                "replies": m["reply_count"],
                "quotes": m["quote_count"],
                "url": f"https://x.com/{handle}/status/{tweet.id}",
                "score": compute_weighted_score(m["like_count"], m["retweet_count"], m["reply_count"]),
                "account": handle,
            })
        logger.info(f"Fetched {len(posts)} posts from @{handle}")
        return posts
    except tweepy.TweepyException as e:
        logger.warning(f"API error fetching @{handle}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching @{handle}: {e}")
        return []


def compute_account_stats(posts: list[dict]) -> dict:
    """Compute aggregate stats for one account's posts."""
    if not posts:
        return {
            "post_count": 0,
            "avg_likes": 0.0, "avg_retweets": 0.0, "avg_replies": 0.0,
            "avg_score": 0.0, "median_score": 0.0,
            "top_posts": [],
        }
    likes = [p["likes"] for p in posts]
    retweets = [p["retweets"] for p in posts]
    replies = [p["replies"] for p in posts]
    scores = [p["score"] for p in posts]
    top_posts = sorted(posts, key=lambda p: p["score"], reverse=True)[:TOP_N_POSTS]
    return {
        "post_count": len(posts),
        "avg_likes": round(sum(likes) / len(likes), 1),
        "avg_retweets": round(sum(retweets) / len(retweets), 1),
        "avg_replies": round(sum(replies) / len(replies), 1),
        "avg_score": round(sum(scores) / len(scores), 1),
        "median_score": round(statistics.median(scores), 1),
        "top_posts": top_posts,
    }


def fetch_own_stats() -> dict:
    """Compute stats from published posts in queue with actual_engagement data."""
    cfg = get_config()
    handle = cfg["handle"]
    try:
        queue = load_queue()
    except Exception as e:
        logger.error(f"Failed to load queue: {e}")
        return {"post_count": 0, "avg_likes": 0.0, "avg_retweets": 0.0,
                "avg_replies": 0.0, "avg_score": 0.0, "median_score": 0.0,
                "top_posts": [], "post_count_with_engagement": 0}

    published = [p for p in queue if p.get("status") == "published" and p.get("actual_engagement")]
    if not published:
        return {"post_count": 0, "avg_likes": 0.0, "avg_retweets": 0.0,
                "avg_replies": 0.0, "avg_score": 0.0, "median_score": 0.0,
                "top_posts": [], "post_count_with_engagement": 0}

    posts = []
    for p in published:
        e = p["actual_engagement"]
        posts.append({
            "id": p.get("id", ""),
            "text": p.get("text", "")[:100] + "...",
            "likes": e.get("likes", 0),
            "retweets": e.get("retweets", 0),
            "replies": e.get("replies", 0),
            "quotes": e.get("quotes", 0),
            "url": f"https://x.com/{handle}/status/{p.get('id', '')}",
            "score": compute_weighted_score(e.get("likes", 0), e.get("retweets", 0), e.get("replies", 0)),
        })

    stats = compute_account_stats(posts)
    stats["post_count_with_engagement"] = len(published)
    return stats


def extract_insights(top_posts: list[dict]) -> dict:
    """Send top posts to LLM to extract structured content patterns."""
    if not top_posts:
        return {"hook_patterns": [], "specificity_techniques": [], "cta_patterns": [], "engagement_drivers": []}

    cfg = get_config()
    posts_text = "\n\n".join(
        f"[{p['account']} | score:{p['score']}]\n{p['text']}"
        for p in top_posts
    )
    accounts_str = ", ".join(f"@{a}" for a in cfg.get("benchmark_accounts", []))

    prompt = f"""You are analyzing the top-performing tweets from benchmark accounts to extract actionable content patterns.

Here are the {len(top_posts)} highest-engagement tweets from {accounts_str}:

{posts_text}

Extract exactly the following four categories. For each, give 3-5 concise, actionable observations (one sentence each).
Be specific — name the actual technique, not a vague description.

Respond with valid JSON only, no other text:
{{
  "hook_patterns": ["...", "..."],
  "specificity_techniques": ["...", "..."],
  "cta_patterns": ["...", "..."],
  "engagement_drivers": ["...", "..."]
}}"""

    try:
        raw = llm_complete(
            model=cfg["models"]["scoring"],
            system="You are a content analyst. Respond only with valid JSON.",
            user=prompt,
            max_tokens=800,
        )
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        logger.error(f"Failed to extract insights: {e}")
        return {"hook_patterns": [], "specificity_techniques": [], "cta_patterns": [], "engagement_drivers": []}


def run_benchmark(max_posts: int = MAX_POSTS_PER_ACCOUNT) -> dict:
    """
    Full pipeline: fetch all benchmark accounts + own stats, extract insights.
    Writes data/benchmark_report.json and data/benchmark_insights.json.
    """
    cfg = get_config()
    client = _build_x_client()
    benchmark_accounts = cfg.get("benchmark_accounts", [])

    accounts_data = {}
    all_posts = []
    for handle in benchmark_accounts:
        posts = fetch_account_posts(client, handle, max_posts)
        all_posts.extend(posts)
        accounts_data[handle] = compute_account_stats(posts)

    own_stats = fetch_own_stats()

    gaps = {}
    for handle, account_stats in accounts_data.items():
        gaps[handle] = {
            "avg_likes_gap": round(account_stats["avg_likes"] - own_stats["avg_likes"], 1),
            "avg_retweets_gap": round(account_stats["avg_retweets"] - own_stats["avg_retweets"], 1),
            "avg_replies_gap": round(account_stats["avg_replies"] - own_stats["avg_replies"], 1),
            "score_gap": round(account_stats["avg_score"] - own_stats["avg_score"], 1),
        }

    top_for_insights = sorted(all_posts, key=lambda p: p["score"], reverse=True)[:TOP_N_FOR_INSIGHTS]
    patterns = extract_insights(top_for_insights)

    insights = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_accounts": benchmark_accounts,
        "top_posts": top_for_insights,
        "patterns": patterns,
    }

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "accounts": accounts_data,
        "own": own_stats,
        "gaps": gaps,
        "weights_note": "Reply=27x like, Repost=20x like (X Algorithm weights)",
    }

    os.makedirs("data", exist_ok=True)
    with open(BENCHMARK_INSIGHTS_PATH, "w") as f:
        json.dump(insights, f, indent=2)
    with open(BENCHMARK_REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Benchmark complete. Insights: {BENCHMARK_INSIGHTS_PATH}")
    return report


def load_report() -> dict | None:
    try:
        with open(BENCHMARK_REPORT_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error(f"Failed to load benchmark report: {e}")
        return None


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    report = run_benchmark()
    own = report.get("own", {})
    print(f"Benchmark complete.")
    print(f"Own posts with engagement data: {own.get('post_count_with_engagement', 0)}")
    for handle, gap in report.get("gaps", {}).items():
        print(f"  @{handle} score gap: {gap['score_gap']}")
    print(f"Insights written to {BENCHMARK_INSIGHTS_PATH}")
```

- [ ] **Step 4: Run benchmark tests**

```bash
uv run pytest tests/test_benchmark_analyzer.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
uv run pytest tests/ --ignore=tests/test_playbook_refresher.py -q
```

Expected: All pass with no regressions.

- [ ] **Step 6: Commit**

```bash
git add scripts/benchmark_analyzer.py tests/test_benchmark_analyzer.py
git commit -m "feat: add benchmark_analyzer.py — standalone config-driven benchmark utility"
```

---

## Task 6: Update CLAUDE.md

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update the `.env` section in CLAUDE.md**

Find the Environment variables section and replace:

```
OPENAI_API_KEY=          # NOT ANTHROPIC_API_KEY — this engine uses OpenAI
```

With:

```
ANTHROPIC_API_KEY=       # generation + scoring both use Claude (via llm_client.py)
```

- [ ] **Step 2: Update the Design decisions section**

Find the design decisions bullet about OpenAI:

```
- **OpenAI not Anthropic**: The source repo had `ANTHROPIC_API_KEY` in `.env.example` by mistake. This repo correctly uses `OPENAI_API_KEY` everywhere.
```

Replace with:

```
- **Model-agnostic via `llm_client.py`**: `scripts/llm_client.py` provides a single `complete(model, system, user)` function that routes to Anthropic (`claude-*`) or OpenAI (everything else) based on the model name prefix. Model names live in `config.json["models"]`. Default models are `claude-haiku-4-5-20251001` for both generation and scoring.
```

- [ ] **Step 3: Add `benchmark_analyzer.py` to the Key files table**

Add after the `velocity_monitor.py` row:

```
| `scripts/benchmark_analyzer.py` | Standalone benchmark fetch + LLM insight extraction. Run manually to populate `data/benchmark_insights.json` |
| `scripts/llm_client.py` | Provider-agnostic `complete()` — routes to Anthropic or OpenAI by model name prefix |
```

- [ ] **Step 4: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "docs: update CLAUDE.md — model-agnostic llm_client, benchmark_analyzer, ANTHROPIC_API_KEY"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `llm_client.py` with `complete()` routing by prefix | Task 2 |
| `config.json` `"models"` key | Task 1 |
| `.env.example` `ANTHROPIC_API_KEY` | Task 1 |
| `anthropic` dependency | Task 1 |
| `post_scorer.py` 6-dim TOFU rubric | Task 3 |
| `SCORING_RUBRIC` + `REGEN_HARD_RULES` constants | Task 3 |
| `batch_score_posts()` | Task 3 |
| `batch_regenerate_posts()` | Task 3 |
| `score_all_posts()` max 4 calls | Task 3 |
| `regenerate_if_below_floor()` legacy wrapper | Task 3 |
| +0.5 composite offset | Task 3 |
| `_build_shared_scoring_context()` | Task 3 |
| Benchmark hook injection in scorer (graceful) | Task 3 |
| `content_generator.py` `distill_playbooks()` | Task 4 |
| `load_playbooks()` distilled cache | Task 4 |
| `validate_post()` hard rules | Task 4 |
| `generate()` filters via `validate_post()` | Task 4 |
| `llm_client` in generator | Task 4 |
| Benchmark injection in generator (graceful) | Task 4 |
| Debate-baiting / adversarial frames in system prompt | Task 4 |
| `benchmark_analyzer.py` config-driven handles | Task 5 |
| `fetch_own_stats()` uses `config["handle"]` | Task 5 |
| `extract_insights()` via `llm_client` | Task 5 |
| PII-free outputs | Task 5 |
| `CLAUDE.md` updates | Task 6 |

**Placeholder scan:** None found. All code is complete.

**Type consistency check:**
- `llm_client.complete()` signature: `(model: str, system: str, user: str, max_tokens: int = 2000) -> str` — used consistently in Task 3, 4, 5 via `llm_complete(model=..., system=..., user=..., max_tokens=...)`.
- `batch_score_posts(posts: list[dict]) -> list[dict]` — called in `score_all_posts()` correctly.
- `regenerate_if_below_floor(post: dict) -> dict` — wrapper calls `score_all_posts([post])[0]` — consistent.
- `validate_post(text: str) -> tuple[bool, str]` — called in `generate()` as `is_valid, reason = validate_post(draft)` — consistent.
