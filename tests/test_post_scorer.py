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
