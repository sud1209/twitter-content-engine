import pytest
from pathlib import Path
from scripts.archive_analyzer import load_tweets, parse_tweet, compute_engagement_score

FIXTURE_PATH = str(Path(__file__).parent / "fixtures" / "sample_tweets.js")


def test_load_tweets_strips_js_wrapper():
    tweets = load_tweets(FIXTURE_PATH)
    assert isinstance(tweets, list)
    assert len(tweets) == 5


def test_load_tweets_returns_tweet_dicts():
    tweets = load_tweets(FIXTURE_PATH)
    assert "id_str" in tweets[0]
    assert "full_text" in tweets[0]


def test_parse_tweet_casts_counts_to_int():
    tweets = load_tweets(FIXTURE_PATH)
    parsed = parse_tweet(tweets[0])
    assert isinstance(parsed["favorite_count"], int)
    assert isinstance(parsed["retweet_count"], int)
    assert parsed["favorite_count"] == 142
    assert parsed["retweet_count"] == 28


def test_parse_tweet_extracts_hour_and_weekday():
    tweets = load_tweets(FIXTURE_PATH)
    parsed = parse_tweet(tweets[0])
    assert parsed["hour"] == 15  # 15:00 UTC
    assert parsed["weekday"] == "Tuesday"


def test_parse_tweet_counts_hashtags():
    tweets = load_tweets(FIXTURE_PATH)
    parsed = parse_tweet(tweets[2])
    assert parsed["hashtag_count"] == 1


def test_parse_tweet_flags_retweets_via_retweeted_field():
    """Tweet with retweeted=True (but no RT @ prefix) is flagged as retweet."""
    tweets = load_tweets(FIXTURE_PATH)
    # tweets[3] has retweeted=True but text does not start with "RT @"
    parsed = parse_tweet(tweets[3])
    assert parsed["is_retweet"] is True


def test_parse_tweet_flags_retweets_via_rt_prefix():
    """Tweet with RT @ prefix (but retweeted=False) is flagged as retweet."""
    tweets = load_tweets(FIXTURE_PATH)
    # tweets[4] has retweeted=False but text starts with "RT @"
    parsed = parse_tweet(tweets[4])
    assert parsed["is_retweet"] is True


def test_compute_engagement_score():
    # Engagement = favorites + (retweets * 20)
    # No reply_count in archive export
    score = compute_engagement_score(favorites=142, retweets=28)
    assert score == 142 + (28 * 20)  # == 702


# ---------------------------------------------------------------------------
# Analysis tests
# ---------------------------------------------------------------------------

from scripts.archive_analyzer import filter_original_tweets, get_top_performers, get_zero_traction, analyze_patterns


def test_filter_original_tweets_removes_retweets():
    tweets = load_tweets(FIXTURE_PATH)
    parsed = [parse_tweet(t) for t in tweets]
    originals = filter_original_tweets(parsed)
    assert len(originals) == 2  # IDs 1001, 1003 — 1002, 1004, 1005 are retweets
    assert all(not t["is_retweet"] for t in originals)


def test_get_top_performers_sorted_by_engagement():
    tweets = load_tweets(FIXTURE_PATH)
    parsed = [parse_tweet(t) for t in tweets]
    originals = filter_original_tweets(parsed)
    top = get_top_performers(originals, n=1)
    assert len(top) == 1
    assert top[0]["id"] == "1001"  # 142 + 28*20 = 702, highest score


def test_get_zero_traction_returns_low_engagement():
    tweets = load_tweets(FIXTURE_PATH)
    parsed = [parse_tweet(t) for t in tweets]
    originals = filter_original_tweets(parsed)
    zero = get_zero_traction(originals, threshold=10)
    assert any(t["id"] == "1003" for t in zero)  # 2 + 0*20 = 2


def test_analyze_patterns_returns_expected_keys():
    tweets = load_tweets(FIXTURE_PATH)
    parsed = [parse_tweet(t) for t in tweets]
    originals = filter_original_tweets(parsed)
    patterns = analyze_patterns(originals)
    assert "best_hour" in patterns
    assert "best_weekday" in patterns
    assert "avg_char_count" in patterns
    assert "total_original_tweets" in patterns
