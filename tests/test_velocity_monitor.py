import pytest
from unittest.mock import MagicMock, patch


def test_get_tweet_metrics_returns_dict(mocker):
    from scripts.velocity_monitor import get_tweet_metrics
    mock_client = MagicMock()
    mock_client.get_tweet.return_value = MagicMock(
        data=MagicMock(public_metrics={
            "like_count": 15, "retweet_count": 5, "reply_count": 3, "impression_count": 200
        })
    )
    metrics = get_tweet_metrics(mock_client, "123")
    assert metrics["likes"] == 15
    assert metrics["retweets"] == 5
    assert metrics["replies"] == 3


def test_is_above_threshold_returns_true_when_exceeds_median(mocker):
    from scripts.velocity_monitor import is_above_threshold
    # 1.5x median for Non-QM is likes>=15, retweets>=4.5, replies>=1.5
    metrics = {"likes": 20, "retweets": 2, "replies": 1, "impressions": 100}
    assert is_above_threshold(metrics, "Non-QM Lending Optimization") is True


def test_is_above_threshold_returns_false_when_below_median(mocker):
    from scripts.velocity_monitor import is_above_threshold
    metrics = {"likes": 2, "retweets": 1, "replies": 0, "impressions": 50}
    assert is_above_threshold(metrics, "AI for Real Estate") is False


def test_store_velocity_metrics_writes_to_queue(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    q.save_queue([{"id": "post-001", "text": "test", "status": "published", "pillar": "AI for Real Estate"}])

    from scripts.velocity_monitor import store_velocity_metrics
    store_velocity_metrics("post-001", "T+30", {"likes": 10, "retweets": 3, "replies": 1, "impressions": 100})

    queue = q.load_queue()
    assert "velocity_metrics" in queue[0]
    assert "T+30" in queue[0]["velocity_metrics"]
    assert queue[0]["velocity_metrics"]["T+30"]["likes"] == 10


def test_publish_approved_post_passes_post_id_and_pillar(mocker):
    from scripts.x_publisher import publish_approved_post
    mock_client = MagicMock()
    mock_client.create_tweet.return_value = MagicMock(data={"id": "tweet-123"})
    mocker.patch("scripts.x_publisher.time.sleep")
    mocker.patch("scripts.x_publisher.schedule_velocity_checks")

    result = publish_approved_post(
        mock_client,
        post_text="Test post",
        link="https://x.com",
        post_id="post-001",
        pillar="AI for Real Estate"
    )
    assert result is True
