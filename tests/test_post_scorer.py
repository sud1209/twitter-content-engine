import pytest
from scripts.post_scorer import compute_composite_score, parse_score_response, DIMENSIONS


def test_dimensions_list_has_7_items():
    assert len(DIMENSIONS) == 7


def test_dimensions_weights_sum_to_100():
    total = sum(d["weight"] for d in DIMENSIONS)
    assert total == 100


def test_compute_composite_score_weighted_average():
    scores = {
        "hook_strength": 10,
        "tone_compliance": 10,
        "data_specificity": 10,
        "pillar_alignment": 10,
        "funnel_stage_accuracy": 10,
        "cta_quality": 10,
        "x_algorithm_optimization": 10,
    }
    result = compute_composite_score(scores)
    assert result == 10.0


def test_compute_composite_score_never_list_violation_returns_zero():
    scores = {
        "hook_strength": 9,
        "tone_compliance": 0,
        "data_specificity": 8,
        "pillar_alignment": 9,
        "funnel_stage_accuracy": 8,
        "cta_quality": 7,
        "x_algorithm_optimization": 8,
    }
    result = compute_composite_score(scores, never_list_violation=True)
    assert result == 0.0


def test_compute_composite_score_partial():
    scores = {
        "hook_strength": 8,           # 20% * 8 = 1.6
        "tone_compliance": 9,         # 20% * 9 = 1.8
        "data_specificity": 7,        # 15% * 7 = 1.05
        "pillar_alignment": 10,       # 15% * 10 = 1.5
        "funnel_stage_accuracy": 8,   # 10% * 8 = 0.8
        "cta_quality": 7,             # 10% * 7 = 0.7
        "x_algorithm_optimization": 9,  # 10% * 9 = 0.9
    }
    result = compute_composite_score(scores)
    assert abs(result - 8.35) < 0.01


def test_parse_score_response_extracts_scores():
    raw = """
hook_strength: 8
tone_compliance: 9
data_specificity: 7
pillar_alignment: 10
funnel_stage_accuracy: 8
cta_quality: 7
x_algorithm_optimization: 9
never_list_violation: false
"""
    scores, violation = parse_score_response(raw)
    assert scores["hook_strength"] == 8
    assert scores["tone_compliance"] == 9
    assert violation is False


def test_parse_score_response_detects_never_list_violation():
    raw = """
hook_strength: 6
tone_compliance: 2
data_specificity: 5
pillar_alignment: 8
funnel_stage_accuracy: 7
cta_quality: 6
x_algorithm_optimization: 7
never_list_violation: true
"""
    _, violation = parse_score_response(raw)
    assert violation is True


def test_regenerate_if_below_floor_surfaces_best_after_max_attempts(mocker):
    """If all regeneration attempts score below floor, best draft is returned with warning."""
    from scripts.post_scorer import regenerate_if_below_floor, QUALITY_FLOOR

    low_score_post = {
        "id": "1", "text": "Vague post", "pillar": "AI for Real Estate",
        "funnel": "TOFU", "score": None, "score_breakdown": None, "status": "pending_score"
    }

    mocker.patch("scripts.post_scorer.score_post", return_value={
        **low_score_post, "score": 5.0, "status": "failed_floor", "score_breakdown": {}
    })
    mocker.patch("scripts.post_scorer.get_todays_pillar", return_value={"pillar": "AI for Real Estate", "funnel": "TOFU"})
    mocker.patch("scripts.post_scorer.get_trends", return_value="trend context")
    mocker.patch("scripts.post_scorer.generate", return_value=["New draft post text"])

    result = regenerate_if_below_floor(low_score_post)
    assert result["status"] == "below_target"
    assert "quality_warning" in result


def test_regenerate_if_below_floor_stops_when_floor_met(mocker):
    """Stops regenerating as soon as a post meets the quality floor."""
    from scripts.post_scorer import regenerate_if_below_floor

    post = {
        "id": "2", "text": "Good post", "pillar": "AI for Real Estate",
        "funnel": "TOFU", "score": None, "score_breakdown": None, "status": "pending_score"
    }

    mocker.patch("scripts.post_scorer.score_post", return_value={
        **post, "score": 9.5, "status": "ready", "score_breakdown": {}
    })

    result = regenerate_if_below_floor(post)
    assert result["status"] == "ready"
    assert result["score"] == 9.5
