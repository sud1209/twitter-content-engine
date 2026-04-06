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


def test_fetch_own_stats_url_contains_config_handle():
    from scripts.benchmark_analyzer import fetch_own_stats
    published_post = {
        "status": "published",
        "id": "123456",
        "text": "A test tweet about something interesting",
        "actual_engagement": {"likes": 10, "retweets": 2, "replies": 1, "quotes": 0},
    }
    with patch("scripts.benchmark_analyzer.load_queue", return_value=[published_post]):
        with patch("scripts.benchmark_analyzer.get_config", return_value={"handle": "testuser"}):
            stats = fetch_own_stats()
    assert len(stats["top_posts"]) > 0
    assert "testuser" in stats["top_posts"][0]["url"]


def test_extract_insights_calls_llm_with_config_model():
    from scripts.benchmark_analyzer import extract_insights
    llm_response = '{"hook_patterns": ["test hook"], "specificity_techniques": [], "cta_patterns": [], "engagement_drivers": []}'
    with patch("scripts.benchmark_analyzer.llm_complete", return_value=llm_response) as mock_llm:
        with patch("scripts.benchmark_analyzer.get_config", return_value={
            "models": {"scoring": "claude-haiku-4-5-20251001"},
            "benchmark_accounts": ["acc1"],
        }):
            result = extract_insights([{"account": "acc1", "score": 100, "text": "test post"}])
    assert "hook_patterns" in result
    mock_llm.assert_called_once()
    _, kwargs = mock_llm.call_args
    assert kwargs.get("model") == "claude-haiku-4-5-20251001"


def test_extract_insights_returns_empty_dict_on_llm_failure():
    from scripts.benchmark_analyzer import extract_insights
    with patch("scripts.benchmark_analyzer.llm_complete", side_effect=Exception("API error")):
        with patch("scripts.benchmark_analyzer.get_config", return_value={
            "models": {"scoring": "claude-haiku-4-5-20251001"},
            "benchmark_accounts": ["acc1"],
        }):
            result = extract_insights([{"account": "acc1", "score": 100, "text": "test"}])
    assert result == {
        "hook_patterns": [],
        "specificity_techniques": [],
        "cta_patterns": [],
        "engagement_drivers": [],
    }
