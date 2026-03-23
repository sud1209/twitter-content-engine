"""
Performance Analyzer — Phase 2 Feature 2
Reads published posts with actual_engagement data.
Computes correlation between predicted score and actual performance.
Outputs data/score_calibration.json for use by scorer and generator.
"""

import json
import os
from datetime import datetime

CALIBRATION_PATH = "data/score_calibration.json"


def fetch_actual_engagement(tweet_id: str) -> dict:
    """Fetch final metrics from X API for a published post."""
    from scripts.x_publisher import build_client
    from scripts.velocity_monitor import get_tweet_metrics
    client = build_client()
    return get_tweet_metrics(client, tweet_id)


def compute_engagement_score(metrics: dict) -> float:
    """Weighted engagement score matching archive formula: likes + (retweets * 20)."""
    return metrics.get("likes", 0) + (metrics.get("retweets", 0) * 20)


def analyze_performance(posts: list) -> dict:
    """
    Given a list of published posts with actual_engagement populated,
    compute per-pillar and per-dimension performance summaries.
    Returns a calibration dict.
    """
    if not posts:
        return {"generated_at": datetime.utcnow().isoformat(), "post_count": 0, "insights": []}

    scored = [p for p in posts if p.get("actual_engagement") and p.get("score")]
    if not scored:
        return {"generated_at": datetime.utcnow().isoformat(), "post_count": 0, "insights": []}

    # Compute engagement scores
    for p in scored:
        p["_eng_score"] = compute_engagement_score(p["actual_engagement"])

    # Overall: avg predicted score vs avg engagement
    avg_predicted = sum(p["score"] for p in scored) / len(scored)
    avg_engagement = sum(p["_eng_score"] for p in scored) / len(scored)

    # Flag posts where high predicted score correlated with low engagement (scorer blind spots)
    blind_spots = [
        {"post_id": p["id"], "text_preview": p["text"][:80], "predicted": p["score"], "actual_engagement": p["_eng_score"]}
        for p in scored
        if p["score"] >= 9.0 and p["_eng_score"] < avg_engagement * 0.5
    ]

    # Flag posts where lower predicted score correlated with high engagement (undervalued signals)
    undervalued = [
        {"post_id": p["id"], "text_preview": p["text"][:80], "predicted": p["score"], "actual_engagement": p["_eng_score"]}
        for p in scored
        if p["score"] < 8.5 and p["_eng_score"] > avg_engagement * 1.5
    ]

    # Per-pillar breakdown
    pillars = {}
    for p in scored:
        pillar = p.get("pillar", "Unknown")
        if pillar not in pillars:
            pillars[pillar] = {"posts": 0, "avg_score": 0, "avg_engagement": 0}
        pillars[pillar]["posts"] += 1
        pillars[pillar]["avg_score"] += p["score"]
        pillars[pillar]["avg_engagement"] += p["_eng_score"]
    for pillar in pillars:
        n = pillars[pillar]["posts"]
        pillars[pillar]["avg_score"] = round(pillars[pillar]["avg_score"] / n, 2)
        pillars[pillar]["avg_engagement"] = round(pillars[pillar]["avg_engagement"] / n, 1)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "post_count": len(scored),
        "avg_predicted_score": round(avg_predicted, 2),
        "avg_engagement_score": round(avg_engagement, 1),
        "blind_spots": blind_spots,
        "undervalued_signals": undervalued,
        "by_pillar": pillars,
        "note": "Calibration is most reliable after 20+ published posts.",
    }


def run_analysis() -> dict:
    """Read queue, fetch metrics for posts missing actual_engagement, run analysis, save calibration."""
    from scripts.post_queue import load_queue, save_queue

    queue = load_queue()
    published = [p for p in queue if p["status"] == "published"]

    # Fetch metrics for published posts that don't have actual_engagement yet
    updated = False
    for post in published:
        if not post.get("actual_engagement") and post.get("tweet_id"):
            try:
                metrics = fetch_actual_engagement(post["tweet_id"])
                post["actual_engagement"] = metrics
                updated = True
                print(f"Fetched engagement for {post['id'][:8]}: {metrics}")
            except Exception as e:
                print(f"Could not fetch metrics for {post['id'][:8]}: {e}")

    if updated:
        save_queue(queue)

    calibration = analyze_performance(published)

    os.makedirs("data", exist_ok=True)
    with open(CALIBRATION_PATH, "w") as f:
        json.dump(calibration, f, indent=2)
    print(f"Calibration saved to {CALIBRATION_PATH} ({calibration['post_count']} posts)")
    return calibration


def load_calibration() -> dict:
    """Load calibration report if it exists and has enough data (>=5 posts)."""
    if not os.path.exists(CALIBRATION_PATH):
        return None
    with open(CALIBRATION_PATH) as f:
        data = json.load(f)
    if data.get("post_count", 0) < 5:
        return None
    return data
