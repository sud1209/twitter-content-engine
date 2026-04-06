"""
Benchmark Analyzer — standalone utility.
Fetches engagement metrics from benchmark accounts, extracts content patterns via LLM,
writes data/benchmark_report.json and data/benchmark_insights.json.

Usage: uv run python -m scripts.benchmark_analyzer

Requires X_BEARER_TOKEN and ANTHROPIC_API_KEY in .env.
Once run, scorer and generator pick up benchmark_insights.json automatically.
"""

import json
import logging
import os
import statistics
from datetime import datetime

import tweepy
from dotenv import load_dotenv

from scripts.config_loader import get_config
from scripts.llm_client import complete as llm_complete
from scripts.post_queue import load_queue

load_dotenv()

logger = logging.getLogger(__name__)

BENCHMARK_REPORT_PATH = "data/benchmark_report.json"
BENCHMARK_INSIGHTS_PATH = "data/benchmark_insights.json"
MAX_POSTS_PER_ACCOUNT = 50
TOP_N_POSTS = 5
TOP_N_FOR_INSIGHTS = 10

WEIGHT_RETWEET = 20
WEIGHT_REPLY = 27


def compute_weighted_score(likes: int, retweets: int, replies: int) -> int:
    """X Algorithm weighted engagement: Reply=27x like, Repost=20x like."""
    return likes + (retweets * WEIGHT_RETWEET) + (replies * WEIGHT_REPLY)


def _build_x_client() -> tweepy.Client | None:
    bearer_token = os.getenv("X_BEARER_TOKEN")
    if not bearer_token:
        logger.warning("X_BEARER_TOKEN not set — benchmark will skip API calls.")
        return None
    try:
        return tweepy.Client(bearer_token=bearer_token)
    except Exception as e:
        logger.error(f"Failed to build tweepy client: {e}")
        return None


def fetch_account_posts(client: tweepy.Client | None, handle: str, max_results: int = MAX_POSTS_PER_ACCOUNT) -> list[dict]:
    """Fetch up to max_results original tweets from @handle. Returns [] on any error."""
    if not client:
        return []
    try:
        user_id = client.get_user(username=handle).data.id
        tweets = client.get_users_tweets(
            user_id,
            tweet_fields=["public_metrics"],
            exclude=["retweets", "replies"],
            max_results=max_results,
        )
        if not tweets.data:
            return []

        posts = []
        for tweet in tweets.data:
            m = tweet.public_metrics
            posts.append({
                "id": str(tweet.id),
                "text": tweet.text,
                "likes": m["like_count"],
                "retweets": m["retweet_count"],
                "replies": m["reply_count"],
                "quotes": m["quote_count"],
                "url": f"https://x.com/{handle}/status/{tweet.id}",
                "score": compute_weighted_score(m["like_count"], m["retweet_count"], m["reply_count"]),
                "account": handle,
            })
        logger.info(f"Fetched {len(posts)} posts from @{handle}")
        return posts
    except tweepy.TweepyException as e:
        logger.warning(f"API error fetching @{handle}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching @{handle}: {e}")
        return []


def compute_account_stats(posts: list[dict]) -> dict:
    """Compute aggregate stats for one account's posts."""
    if not posts:
        return {
            "post_count": 0,
            "avg_likes": 0.0, "avg_retweets": 0.0, "avg_replies": 0.0,
            "avg_score": 0.0, "median_score": 0.0,
            "top_posts": [],
        }
    likes = [p["likes"] for p in posts]
    retweets = [p["retweets"] for p in posts]
    replies = [p["replies"] for p in posts]
    scores = [p["score"] for p in posts]
    top_posts = sorted(posts, key=lambda p: p["score"], reverse=True)[:TOP_N_POSTS]
    return {
        "post_count": len(posts),
        "avg_likes": round(sum(likes) / len(likes), 1),
        "avg_retweets": round(sum(retweets) / len(retweets), 1),
        "avg_replies": round(sum(replies) / len(replies), 1),
        "avg_score": round(sum(scores) / len(scores), 1),
        "median_score": round(statistics.median(scores), 1),
        "top_posts": top_posts,
    }


def fetch_own_stats() -> dict:
    """Compute stats from published posts in queue with actual_engagement data."""
    cfg = get_config()
    handle = cfg["handle"]
    try:
        queue = load_queue()
    except Exception as e:
        logger.error(f"Failed to load queue: {e}")
        return {"post_count": 0, "avg_likes": 0.0, "avg_retweets": 0.0,
                "avg_replies": 0.0, "avg_score": 0.0, "median_score": 0.0,
                "top_posts": [], "post_count_with_engagement": 0}

    published = [p for p in queue if p.get("status") == "published" and p.get("actual_engagement")]
    if not published:
        return {"post_count": 0, "avg_likes": 0.0, "avg_retweets": 0.0,
                "avg_replies": 0.0, "avg_score": 0.0, "median_score": 0.0,
                "top_posts": [], "post_count_with_engagement": 0}

    posts = []
    for p in published:
        e = p["actual_engagement"]
        posts.append({
            "id": p.get("id", ""),
            "text": p.get("text", "")[:100] + "...",
            "likes": e.get("likes", 0),
            "retweets": e.get("retweets", 0),
            "replies": e.get("replies", 0),
            "quotes": e.get("quotes", 0),
            "url": f"https://x.com/{handle}/status/{p.get('id', '')}",
            "score": compute_weighted_score(e.get("likes", 0), e.get("retweets", 0), e.get("replies", 0)),
        })

    stats = compute_account_stats(posts)
    stats["post_count_with_engagement"] = len(published)
    return stats


def extract_insights(top_posts: list[dict]) -> dict:
    """Send top posts to LLM to extract structured content patterns."""
    if not top_posts:
        return {"hook_patterns": [], "specificity_techniques": [], "cta_patterns": [], "engagement_drivers": []}

    cfg = get_config()
    posts_text = "\n\n".join(
        f"[{p['account']} | score:{p['score']}]\n{p['text']}"
        for p in top_posts
    )
    accounts_str = ", ".join(f"@{a}" for a in cfg.get("benchmark_accounts", []))

    prompt = f"""You are analyzing the top-performing tweets from benchmark accounts to extract actionable content patterns.

Here are the {len(top_posts)} highest-engagement tweets from {accounts_str}:

{posts_text}

Extract exactly the following four categories. For each, give 3-5 concise, actionable observations (one sentence each).
Be specific — name the actual technique, not a vague description.

Respond with valid JSON only, no other text:
{{
  "hook_patterns": ["...", "..."],
  "specificity_techniques": ["...", "..."],
  "cta_patterns": ["...", "..."],
  "engagement_drivers": ["...", "..."]
}}"""

    try:
        raw = llm_complete(
            model=cfg["models"]["scoring"],
            system="You are a content analyst. Respond only with valid JSON.",
            user=prompt,
            max_tokens=800,
        )
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        logger.error(f"Failed to extract insights: {e}")
        return {"hook_patterns": [], "specificity_techniques": [], "cta_patterns": [], "engagement_drivers": []}


def run_benchmark(max_posts: int = MAX_POSTS_PER_ACCOUNT) -> dict:
    """
    Full pipeline: fetch all benchmark accounts + own stats, extract insights.
    Writes data/benchmark_report.json and data/benchmark_insights.json.
    """
    cfg = get_config()
    client = _build_x_client()
    benchmark_accounts = cfg.get("benchmark_accounts", [])

    accounts_data = {}
    all_posts = []
    for handle in benchmark_accounts:
        posts = fetch_account_posts(client, handle, max_posts)
        all_posts.extend(posts)
        accounts_data[handle] = compute_account_stats(posts)

    own_stats = fetch_own_stats()

    gaps = {}
    for handle, account_stats in accounts_data.items():
        gaps[handle] = {
            "avg_likes_gap": round(account_stats["avg_likes"] - own_stats["avg_likes"], 1),
            "avg_retweets_gap": round(account_stats["avg_retweets"] - own_stats["avg_retweets"], 1),
            "avg_replies_gap": round(account_stats["avg_replies"] - own_stats["avg_replies"], 1),
            "score_gap": round(account_stats["avg_score"] - own_stats["avg_score"], 1),
        }

    top_for_insights = sorted(all_posts, key=lambda p: p["score"], reverse=True)[:TOP_N_FOR_INSIGHTS]
    patterns = extract_insights(top_for_insights)

    insights = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_accounts": benchmark_accounts,
        "top_posts": top_for_insights,
        "patterns": patterns,
    }

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "accounts": accounts_data,
        "own": own_stats,
        "gaps": gaps,
        "weights_note": "Reply=27x like, Repost=20x like (X Algorithm weights)",
    }

    os.makedirs("data", exist_ok=True)
    with open(BENCHMARK_INSIGHTS_PATH, "w") as f:
        json.dump(insights, f, indent=2)
    with open(BENCHMARK_REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Benchmark complete. Insights: {BENCHMARK_INSIGHTS_PATH}")
    return report


def load_report() -> dict | None:
    try:
        with open(BENCHMARK_REPORT_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error(f"Failed to load benchmark report: {e}")
        return None


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    report = run_benchmark()
    own = report.get("own", {})
    print(f"Benchmark complete.")
    print(f"Own posts with engagement data: {own.get('post_count_with_engagement', 0)}")
    for handle, gap in report.get("gaps", {}).items():
        print(f"  @{handle} score gap: {gap['score_gap']}")
    print(f"Insights written to {BENCHMARK_INSIGHTS_PATH}")
