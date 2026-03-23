import pytest
from unittest.mock import patch, MagicMock, call
from scripts.x_publisher import build_client, post_tweet, post_reply, publish_approved_post


def test_build_client_uses_env_vars(monkeypatch):
    monkeypatch.setenv("X_CONSUMER_KEY", "ck")
    monkeypatch.setenv("X_CONSUMER_SECRET", "cs")
    monkeypatch.setenv("X_ACCESS_TOKEN", "at")
    monkeypatch.setenv("X_ACCESS_TOKEN_SECRET", "ats")
    monkeypatch.setenv("X_BEARER_TOKEN", "bt")
    # Should not raise
    client = build_client()
    assert client is not None


def test_post_tweet_returns_tweet_id(mocker):
    mock_client = MagicMock()
    mock_client.create_tweet.return_value = MagicMock(data={"id": "123456"})
    tweet_id = post_tweet(mock_client, "Test tweet text")
    assert tweet_id == "123456"
    mock_client.create_tweet.assert_called_once_with(text="Test tweet text")


def test_post_reply_uses_in_reply_to_id(mocker):
    mock_client = MagicMock()
    mock_client.create_tweet.return_value = MagicMock(data={"id": "789"})
    post_reply(mock_client, reply_text="https://example.com", in_reply_to_id="123456")
    mock_client.create_tweet.assert_called_once_with(
        text="https://example.com",
        in_reply_to_tweet_id="123456"
    )


def test_publish_approved_post_retries_on_failure(mocker):
    mock_client = MagicMock()
    mock_client.create_tweet.side_effect = Exception("API error")
    mocker.patch("scripts.x_publisher.time.sleep")  # Don't actually sleep in tests
    mocker.patch("scripts.x_publisher.notify_failure")

    result = publish_approved_post(mock_client, post_text="Test", link="http://x.com")
    assert result is False
    assert mock_client.create_tweet.call_count == 3  # 3 retry attempts


def test_publish_approved_post_succeeds_on_first_try(mocker):
    mock_client = MagicMock()
    mock_client.create_tweet.return_value = MagicMock(data={"id": "111"})
    mocker.patch("scripts.x_publisher.time.sleep")

    result = publish_approved_post(mock_client, post_text="Test post", link="http://x.com/tweet/111")
    assert result is True
    assert mock_client.create_tweet.call_count == 2  # main tweet + reply
