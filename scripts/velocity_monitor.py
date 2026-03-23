"""
Velocity Monitor — Phase 2 Feature 1
Polls X API at T+30 and T+60 after publishing.
Notifies the user if a post is gaining above-average traction.
"""

import os
from datetime import datetime
from dotenv import load_dotenv

from scripts.config_loader import get_config

load_dotenv()

TRACTION_MULTIPLIER = 1.5  # alert if metrics exceed 1.5x archive median

# Baseline medians — will be overridden by live calibration data over time
ARCHIVE_MEDIANS = {
    "default": {"likes": 8, "retweets": 2, "replies": 1},
}


def get_tweet_metrics(client, tweet_id: str) -> dict:
    """Fetch public metrics for a tweet. Returns dict with likes, retweets, replies, impressions."""
    response = client.get_tweet(tweet_id, tweet_fields=["public_metrics"])
    metrics = response.data.public_metrics
    return {
        "likes": metrics.get("like_count", 0),
        "retweets": metrics.get("retweet_count", 0),
        "replies": metrics.get("reply_count", 0),
        "impressions": metrics.get("impression_count", 0),
    }


def is_above_threshold(metrics: dict, pillar: str) -> bool:
    """Return True if any key metric exceeds 1.5x the archive median for this pillar."""
    baseline = ARCHIVE_MEDIANS.get(pillar, ARCHIVE_MEDIANS["default"])
    return (
        metrics["likes"] >= baseline["likes"] * TRACTION_MULTIPLIER or
        metrics["retweets"] >= baseline["retweets"] * TRACTION_MULTIPLIER or
        metrics["replies"] >= baseline["replies"] * TRACTION_MULTIPLIER
    )


def store_velocity_metrics(post_id: str, checkpoint: str, metrics: dict) -> None:
    """Store velocity snapshot in the post's queue record."""
    from scripts.post_queue import load_queue, save_queue
    queue = load_queue()
    for post in queue:
        if post["id"] == post_id:
            if "velocity_metrics" not in post:
                post["velocity_metrics"] = {}
            post["velocity_metrics"][checkpoint] = {**metrics, "timestamp": datetime.utcnow().isoformat()}
            save_queue(queue)
            return


def check_velocity(tweet_id: str, post_id: str, pillar: str, checkpoint: str) -> None:
    """
    Poll metrics for tweet_id, store snapshot, notify if gaining traction.
    checkpoint: "T+30" or "T+60"
    """
    from scripts.x_publisher import build_client
    from scripts.notifier import notify

    try:
        client = build_client()
        metrics = get_tweet_metrics(client, tweet_id)
        store_velocity_metrics(post_id, checkpoint, metrics)

        if is_above_threshold(metrics, pillar):
            notify(
                title=f"@{get_config()['handle']} — Post Gaining Traction",
                message=f"{checkpoint}: {metrics['likes']} likes, {metrics['retweets']} RTs, {metrics['replies']} replies. Reply now to keep it going.",
            )
            print(f"[velocity] {checkpoint} alert fired for post {post_id[:8]}: {metrics}")
        else:
            print(f"[velocity] {checkpoint} check for {post_id[:8]}: below threshold {metrics}")
    except Exception as e:
        print(f"[velocity] {checkpoint} check failed: {e}")
