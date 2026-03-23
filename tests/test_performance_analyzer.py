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


# --- get_lowest_engagement_pillar ---

def test_get_lowest_engagement_pillar_returns_lowest(tmp_path, monkeypatch):
    """Returns the pillar with the lowest avg_engagement when calibration exists."""
    import json
    calibration = {
        "post_count": 10,
        "by_pillar": {
            "AI Innovations":               {"posts": 3, "avg_score": 8.5, "avg_engagement": 120.0},
            "Sports & Cricket":             {"posts": 2, "avg_score": 7.0, "avg_engagement": 45.0},
            "eSports & Dota 2":             {"posts": 2, "avg_score": 8.0, "avg_engagement": 80.0},
            "Literature":                   {"posts": 2, "avg_score": 7.5, "avg_engagement": 30.0},
            "Gaming & Experimental Cooking":{"posts": 1, "avg_score": 7.0, "avg_engagement": 60.0},
        },
    }
    cal_path = tmp_path / "score_calibration.json"
    cal_path.write_text(json.dumps(calibration))
    monkeypatch.setattr(
        "scripts.performance_analyzer.CALIBRATION_PATH", str(cal_path)
    )
    from scripts.performance_analyzer import get_lowest_engagement_pillar
    pillars = list(calibration["by_pillar"].keys())
    result = get_lowest_engagement_pillar(pillars)
    assert result == "Literature"  # avg_engagement 30.0 is lowest


def test_get_lowest_engagement_pillar_falls_back_when_no_calibration(tmp_path, monkeypatch):
    """Returns first pillar in list when calibration file does not exist."""
    monkeypatch.setattr(
        "scripts.performance_analyzer.CALIBRATION_PATH",
        str(tmp_path / "nonexistent.json"),
    )
    from scripts.performance_analyzer import get_lowest_engagement_pillar
    pillars = ["AI Innovations", "Sports & Cricket", "Literature"]
    result = get_lowest_engagement_pillar(pillars)
    assert result == "AI Innovations"


def test_get_lowest_engagement_pillar_falls_back_when_no_known_pillars(tmp_path, monkeypatch):
    """Falls back to first pillar when none of the requested pillars appear in calibration data."""
    import json
    calibration = {
        "post_count": 5,
        "by_pillar": {
            "Some Other Pillar": {"posts": 5, "avg_score": 8.0, "avg_engagement": 100.0},
        },
    }
    cal_path = tmp_path / "score_calibration.json"
    cal_path.write_text(json.dumps(calibration))
    monkeypatch.setattr(
        "scripts.performance_analyzer.CALIBRATION_PATH", str(cal_path)
    )
    from scripts.performance_analyzer import get_lowest_engagement_pillar
    pillars = ["AI Innovations", "Literature", "Sports & Cricket"]
    # None of the pillars appear in calibration → known dict is empty → fall back
    result = get_lowest_engagement_pillar(pillars)
    assert result == "AI Innovations"  # pillars[0]
