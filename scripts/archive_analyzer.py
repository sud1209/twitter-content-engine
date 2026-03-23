"""
Archive Analyzer — D5
Parses resources/X Archive/data/tweets.js and extracts performance patterns.
Usage: python scripts/archive_analyzer.py
Output: docs/archive-analysis.md
"""

import re
import json
from datetime import datetime


# ---------------------------------------------------------------------------
# Loading and parsing
# ---------------------------------------------------------------------------

def load_tweets(path: str) -> list[dict]:
    """Load tweets.js, strip the JS wrapper, return list of raw tweet dicts."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    # Strip: window.YTD.tweets.part0 = [...];
    json_str = re.sub(r"^window\.YTD\.tweets\.part\d+\s*=\s*", "", raw.strip()).rstrip(";")
    records = json.loads(json_str)
    return [record["tweet"] for record in records]


def parse_tweet(raw: dict) -> dict:
    """Normalize a raw tweet dict into a clean analysis record."""
    full_text = raw.get("full_text", "")
    retweeted = raw.get("retweeted", False)
    is_retweet = retweeted or full_text.startswith("RT @")

    created_str = raw.get("created_at", "")
    try:
        created_at = datetime.strptime(created_str, "%a %b %d %H:%M:%S +0000 %Y")
    except ValueError:
        created_at = None

    hashtags = raw.get("entities", {}).get("hashtags", [])

    return {
        "id": raw.get("id_str", ""),
        "full_text": full_text,
        "favorite_count": int(raw.get("favorite_count", 0)),
        "retweet_count": int(raw.get("retweet_count", 0)),
        "created_at": created_at,
        "hour": created_at.hour if created_at else None,
        "weekday": created_at.strftime("%A") if created_at else None,
        "char_count": len(full_text),
        "hashtag_count": len(hashtags),
        "is_retweet": is_retweet,
        "lang": raw.get("lang", ""),
    }


def compute_engagement_score(favorites: int, retweets: int) -> int:
    """
    Weighted engagement score using X algorithm weights.
    Retweets = 20x a like. Reply count not available in archive export.
    """
    return favorites + (retweets * 20)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def filter_original_tweets(tweets: list[dict]) -> list[dict]:
    """Remove retweets. Keep only original content."""
    return [t for t in tweets if not t["is_retweet"]]


def get_top_performers(tweets: list[dict], n: int = 20) -> list[dict]:
    """Return top N tweets by weighted engagement score."""
    scored = sorted(
        tweets,
        key=lambda t: compute_engagement_score(t["favorite_count"], t["retweet_count"]),
        reverse=True,
    )
    return scored[:n]


def get_zero_traction(tweets: list[dict], threshold: int = 5) -> list[dict]:
    """Return tweets where engagement score is at or below threshold."""
    return [
        t for t in tweets
        if compute_engagement_score(t["favorite_count"], t["retweet_count"]) <= threshold
    ]


def analyze_patterns(tweets: list[dict]) -> dict:
    """Compute aggregate patterns across all original tweets."""
    if not tweets:
        return {}

    hour_scores: dict[int, list[int]] = {}
    weekday_scores: dict[str, list[int]] = {}

    for t in tweets:
        score = compute_engagement_score(t["favorite_count"], t["retweet_count"])
        if t["hour"] is not None:
            hour_scores.setdefault(t["hour"], []).append(score)
        if t["weekday"]:
            weekday_scores.setdefault(t["weekday"], []).append(score)

    best_hour = max(hour_scores, key=lambda h: sum(hour_scores[h]) / len(hour_scores[h])) if hour_scores else None
    best_weekday = max(weekday_scores, key=lambda d: sum(weekday_scores[d]) / len(weekday_scores[d])) if weekday_scores else None

    char_counts = [t["char_count"] for t in tweets]
    avg_chars = sum(char_counts) / len(char_counts) if char_counts else 0

    return {
        "total_original_tweets": len(tweets),
        "best_hour": best_hour,
        "best_weekday": best_weekday,
        "avg_char_count": round(avg_chars, 1),
        "avg_hashtags": round(sum(t["hashtag_count"] for t in tweets) / len(tweets), 2),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def format_tweet_block(tweet: dict, rank: int) -> str:
    score = compute_engagement_score(tweet["favorite_count"], tweet["retweet_count"])
    text = tweet["full_text"][:200].replace("\n", " ")
    return (
        f"**#{rank}** (score: {score} | {tweet['favorite_count']} likes, {tweet['retweet_count']} RTs)\n"
        f"> {text}\n"
        f"- Posted: {tweet['weekday']} {tweet['hour']}:00 UTC | {tweet['char_count']} chars | {tweet['hashtag_count']} hashtags\n"
    )


def write_report(output_path: str, tweets_path: str) -> None:
    raw_tweets = load_tweets(tweets_path)
    parsed = [parse_tweet(t) for t in raw_tweets]
    originals = filter_original_tweets(parsed)
    top = get_top_performers(originals, n=20)
    zero = get_zero_traction(originals, threshold=5)
    patterns = analyze_patterns(originals)

    sections = []
    from scripts.config_loader import get_config
    sections.append(f"# X Archive Analysis — @{get_config()['handle']}")
    sections.append(f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d')}")
    sections.append(
        f"**Total tweets in archive:** {len(raw_tweets):,}  \n"
        f"**Original tweets (excl. RTs):** {patterns.get('total_original_tweets', 0):,}"
    )
    sections.append("---")
    sections.append("## Key Patterns")
    sections.append(
        f"- **Best posting hour (UTC):** {patterns.get('best_hour')}:00\n"
        f"- **Best day of week:** {patterns.get('best_weekday')}\n"
        f"- **Average tweet length:** {patterns.get('avg_char_count')} chars\n"
        f"- **Average hashtags per tweet:** {patterns.get('avg_hashtags')}"
    )
    sections.append("---")
    sections.append("## Top 20 Performing Tweets\n_Ranked by weighted engagement score (likes + retweets × 20)_")
    for i, tweet in enumerate(top, 1):
        sections.append(format_tweet_block(tweet, i))

    sections.append("---")
    sections.append(
        f"## Zero-Traction Tweets (score ≤ 5)\n"
        f"_{len(zero)} tweets got virtually no engagement._\n\n"
        f"**Patterns in low-performing content:**"
    )
    for tweet in zero[:10]:
        text = tweet["full_text"][:120].replace("\n", " ")
        sections.append(f"- {text}")

    sections.append("---")
    sections.append(
        "## Recommendations\n_Fill this section after reviewing the data above._\n\n"
        "- Double down on: [topics/formats from top performers]\n"
        "- Kill: [topics/formats from zero-traction tweets]\n"
        "- Optimal posting time: [best_hour] UTC"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(sections))

    print(f"Report written to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    TWEETS_PATH = "resources/X Archive/data/tweets.js"
    OUTPUT_PATH = "docs/archive-analysis.md"
    write_report(OUTPUT_PATH, TWEETS_PATH)
