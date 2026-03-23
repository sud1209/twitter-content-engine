"""
X Publisher — D4
Posts approved tweets to @NikhaarShah via Tweepy.
Main post at 15:00 UTC, link reply at 15:02 UTC.
"""

import os
import time
import tweepy
from dotenv import load_dotenv
from scripts.post_queue import load_queue, update_post_status

from scripts.config_loader import get_config

load_dotenv()

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 60
REPLY_DELAY_SECONDS = 120  # 2 minutes


def build_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=os.getenv("X_BEARER_TOKEN"),
        consumer_key=os.getenv("X_CONSUMER_KEY"),
        consumer_secret=os.getenv("X_CONSUMER_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
    )


def post_tweet(client: tweepy.Client, text: str) -> str:
    """Post a tweet. Returns the tweet ID."""
    response = client.create_tweet(text=text)
    return response.data["id"]


def post_reply(client: tweepy.Client, reply_text: str, in_reply_to_id: str) -> str:
    """Post a reply to an existing tweet. Returns the reply tweet ID."""
    response = client.create_tweet(
        text=reply_text,
        in_reply_to_tweet_id=in_reply_to_id,
    )
    return response.data["id"]


def notify_failure(post_text: str) -> None:
    """Send a system notification if posting fails after all retries."""
    try:
        from plyer import notification
        notification.notify(
            title=f"@{get_config()['handle']} Post Failed",
            message=f"Post failed to publish after {MAX_RETRIES} attempts. Manual action required.\n{post_text[:80]}",
            timeout=30,
        )
    except Exception:
        print(f"ALERT: Post failed to publish — manual action required: {post_text[:80]}")


def schedule_velocity_checks(tweet_id: str, post_id: str, pillar: str) -> None:
    """Schedule T+30 and T+60 velocity checks via APScheduler one-off jobs."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from datetime import datetime, timedelta
        from scripts.velocity_monitor import check_velocity

        bg = BackgroundScheduler(timezone="UTC")
        bg.add_job(
            check_velocity,
            "date",
            run_date=datetime.utcnow() + timedelta(minutes=30),
            args=[tweet_id, post_id, pillar, "T+30"],
        )
        bg.add_job(
            check_velocity,
            "date",
            run_date=datetime.utcnow() + timedelta(minutes=60),
            args=[tweet_id, post_id, pillar, "T+60"],
        )
        bg.start()
        print(f"[velocity] Scheduled T+30 and T+60 checks for tweet {tweet_id}")
    except Exception as e:
        print(f"[velocity] Failed to schedule checks: {e}")


def publish_approved_post(client: tweepy.Client, post_text: str, link: str, post_id: str = "", pillar: str = "") -> bool:
    """
    Post tweet + reply. Retries on failure.
    Returns True on success, False after all retries exhausted.
    """
    tweet_id = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            tweet_id = post_tweet(client, post_text)
            print(f"Tweet posted: {tweet_id}")
            schedule_velocity_checks(tweet_id, post_id, pillar)
            break
        except Exception as e:
            print(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS)
            else:
                notify_failure(post_text)
                return False

    # Wait 2 minutes then post link as reply
    time.sleep(REPLY_DELAY_SECONDS)
    try:
        reply_id = post_reply(client, reply_text=link, in_reply_to_id=tweet_id)
        print(f"Reply posted: {reply_id}")
        return True
    except Exception as e:
        print(f"Warning: link reply failed: {e}")
        # Main tweet succeeded — don't count this as total failure
        return True


if __name__ == "__main__":
    queue = load_queue()
    approved = [p for p in queue if p["status"] == "approved"]

    if not approved:
        print("No approved posts in queue. Nothing to publish.")
        exit(0)

    client = build_client()
    # Post only the first approved post (one post per day)
    post = approved[0]
    link = post.get("link", get_config()["profile_url"])

    print(f"Publishing: {post['text'][:80]}...")
    success = publish_approved_post(client, post_text=post["text"], link=link, post_id=post["id"], pillar=post.get("pillar", ""))

    if success:
        update_post_status(post["id"], "published")
        print("Done. Post marked as published.")
    else:
        print("Publishing failed. Check notifications.")
