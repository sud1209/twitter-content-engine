import pytest
from unittest.mock import patch, MagicMock
from scripts.trend_scanner import scan_rss_feeds, rank_topics, build_trend_context, RSS_FEEDS


def test_rss_feeds_list_is_not_empty():
    assert len(RSS_FEEDS) >= 4


def test_scan_rss_feeds_returns_list_of_dicts(mocker):
    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(title="AI Replaces Loan Officers at Major Bank", summary="Details...", link="http://example.com/1"),
        MagicMock(title="PropTech Funding Round $50M", summary="Details...", link="http://example.com/2"),
    ]
    mocker.patch("scripts.trend_scanner.feedparser.parse", return_value=mock_feed)

    results = scan_rss_feeds(feeds=["http://fake.com/rss"])
    assert isinstance(results, list)
    assert len(results) == 2
    assert "title" in results[0]
    assert "link" in results[0]


def test_rank_topics_returns_top_n():
    topics = [
        {"title": "AI mortgage automation", "source": "rss"},
        {"title": "Non-QM lending surge", "source": "rss"},
        {"title": "PropTech layoffs", "source": "rss"},
        {"title": "Real estate AI agents", "source": "rss"},
        {"title": "Founder productivity hacks", "source": "rss"},
        {"title": "Unrelated sports news", "source": "rss"},
    ]
    top = rank_topics(topics, pillar="AI for Real Estate", n=3)
    assert len(top) <= 3


def test_build_trend_context_returns_string():
    topics = [
        {"title": "AI replaces loan officers", "source": "rss", "link": "http://example.com"},
    ]
    context = build_trend_context(topics, pillar="AI for Real Estate", funnel="TOFU")
    assert isinstance(context, str)
    assert "AI for Real Estate" in context
    assert "TOFU" in context
