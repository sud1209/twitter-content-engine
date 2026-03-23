"""
Scheduler — D4
Runs the daily content pipeline on a schedule.
Keep this process running in the background (started by setup wizard).

Schedule:
- 07:00 UTC (midnight PDT): Generate + score posts, notify user
- 15:00 UTC (08:00 PDT): Publish approved posts
"""

import os
import json
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv
from scripts.config_loader import get_config

load_dotenv()

scheduler = BlockingScheduler(timezone="UTC")


def run_morning_pipeline() -> None:
    """Generate + score posts and notify user they're ready."""
    print(f"[{datetime.utcnow()}] Starting morning pipeline...")

    # Clear yesterday's queue
    import scripts.post_queue as q
    q.save_queue([])

    # Generate drafts
    from scripts.cadence import get_todays_pillar
    from scripts.trend_scanner import run as get_trends
    from scripts.content_generator import generate
    from scripts.post_scorer import regenerate_if_below_floor
    import uuid

    today = get_todays_pillar()
    trend_context = get_trends(pillar=today["pillar"], funnel=today["funnel"])
    drafts = generate(pillar=today["pillar"], funnel=today["funnel"], trend_context=trend_context)

    for draft in drafts:
        post = {
            "id": str(uuid.uuid4()),
            "text": draft,
            "pillar": today["pillar"],
            "funnel": today["funnel"],
            "score": None,
            "score_breakdown": None,
            "status": "pending_score",
        }
        q.add_post(post)

    # Score all drafts
    queue = q.load_queue()
    updated = []
    for post in queue:
        if post["status"] == "pending_score":
            scored = regenerate_if_below_floor(post)
            updated.append(scored)
        else:
            updated.append(post)
    q.save_queue(updated)

    # notify user
    ready = [p for p in updated if p["status"] in ("ready", "below_target")]
    from scripts.notifier import notify_posts_ready
    notify_posts_ready(len(ready))
    print(f"[{datetime.utcnow()}] Morning pipeline complete. {len(ready)} posts ready.")


def run_publish_pipeline() -> None:
    """Publish approved posts at 15:00 UTC."""
    print(f"[{datetime.utcnow()}] Starting publish pipeline...")

    from scripts.post_queue import load_queue, update_post_status
    from scripts.x_publisher import build_client, publish_approved_post
    from scripts.notifier import notify_posts_published, notify_no_approved_posts

    queue = load_queue()
    approved = [p for p in queue if p["status"] == "approved"]

    if not approved:
        notify_no_approved_posts()
        print("No approved posts. Nothing published.")
        return

    client = build_client()
    published = 0
    for post in approved[:1]:  # Publish one post per day
        from scripts.config_loader import get_config
        link = post.get("link", get_config()["profile_url"])
        success = publish_approved_post(client, post_text=post["text"], link=link, post_id=post["id"], pillar=post.get("pillar", ""))
        if success:
            update_post_status(post["id"], "published")
            published += 1

    notify_posts_published(published)
    print(f"[{datetime.utcnow()}] Published {published} post(s).")


def run_analysis_job() -> None:
    """Run performance analysis daily to update score_calibration.json."""
    from scripts.performance_analyzer import run_analysis
    print(f"[{datetime.utcnow()}] Running performance analysis...")
    result = run_analysis()
    print(f"[{datetime.utcnow()}] Analysis complete. {result.get('post_count', 0)} posts analyzed.")


def run_spike_check() -> None:
    """Scan RSS feeds every 2 hours and alert if a topic spike is detected."""
    from scripts.trend_scanner import scan_rss_feeds
    from scripts.spike_detector import record_headlines, detect_spike, get_cooldown_active, mark_alerted
    from scripts.notifier import notify_spike
    from scripts.cadence import get_todays_pillar

    topics = scan_rss_feeds()
    record_headlines(topics)
    spikes = detect_spike(topics)

    today = get_todays_pillar()
    for spike in spikes:
        keyword = spike["keyword"]
        if not get_cooldown_active(keyword):
            notify_spike(
                topic=keyword,
                suggested_pillar=spike.get("suggested_pillar", today["pillar"]),
                headline_count=spike["count"],
            )
            mark_alerted(keyword)
            print(f"Spike alert fired: {keyword} ({spike['count']} headlines)")


def schedule_jobs():
    cfg = get_config()
    publish_time = cfg.get("publish_time_utc", "15:00")
    pub_hour, pub_minute = map(int, publish_time.split(":"))

    scheduler.add_job(run_morning_pipeline,  "cron",     hour=7, minute=0)
    scheduler.add_job(run_analysis_job,      "cron",     hour=9, minute=0)
    scheduler.add_job(run_publish_pipeline,  "cron",     hour=pub_hour, minute=pub_minute)
    scheduler.add_job(run_spike_check,       "interval", hours=2)


if __name__ == "__main__":
    schedule_jobs()
    print("Scheduler started. Waiting for scheduled jobs...")
    print("  07:00 UTC — generate + score posts")
    print("  09:00 UTC — performance analysis")
    print("  15:00 UTC — publish approved posts")
    print("  every 2h  — trend spike check")
    scheduler.start()
