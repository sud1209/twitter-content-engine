import pytest
import json
from scripts.performance_analyzer import compute_engagement_score, analyze_performance, load_calibration, CALIBRATION_PATH


def test_compute_engagement_score():
    metrics = {"likes": 10, "retweets": 3, "replies": 1}
    assert compute_engagement_score(metrics) == 10 + (3 * 20)  # 70


def test_analyze_performance_empty_returns_zero_count():
    result = analyze_performance([])
    assert result["post_count"] == 0


def test_analyze_performance_identifies_blind_spots():
    posts = [
        {"id": "1", "text": "High score low engagement post", "score": 9.5, "pillar": "AI for Real Estate",
         "actual_engagement": {"likes": 1, "retweets": 0, "replies": 0}},
        {"id": "2", "text": "High score high engagement post", "score": 9.5, "pillar": "AI for Real Estate",
         "actual_engagement": {"likes": 50, "retweets": 5, "replies": 3}},
    ]
    result = analyze_performance(posts)
    assert result["post_count"] == 2
    assert "blind_spots" in result


def test_analyze_performance_by_pillar():
    posts = [
        {"id": "1", "text": "Post A", "score": 9.0, "pillar": "Non-QM Lending Optimization",
         "actual_engagement": {"likes": 20, "retweets": 5, "replies": 2}},
        {"id": "2", "text": "Post B", "score": 8.5, "pillar": "Non-QM Lending Optimization",
         "actual_engagement": {"likes": 10, "retweets": 2, "replies": 1}},
    ]
    result = analyze_performance(posts)
    assert "Non-QM Lending Optimization" in result["by_pillar"]
    assert result["by_pillar"]["Non-QM Lending Optimization"]["posts"] == 2


def test_load_calibration_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.performance_analyzer.CALIBRATION_PATH", str(tmp_path / "none.json"))
    assert load_calibration() is None


def test_load_calibration_returns_none_when_too_few_posts(tmp_path, monkeypatch):
    path = tmp_path / "cal.json"
    path.write_text(json.dumps({"post_count": 3, "insights": []}))
    monkeypatch.setattr("scripts.performance_analyzer.CALIBRATION_PATH", str(path))
    assert load_calibration() is None
