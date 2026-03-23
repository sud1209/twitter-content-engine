"""
Trend Scanner — D2
Scans X competitor timelines + RSS feeds for trending topics relevant to configured pillars.
Usage: python scripts/trend_scanner.py
Output: prints trend context to stdout
"""

import os
import feedparser
from dotenv import load_dotenv
from typing import Optional, List

from scripts.config_loader import get_config

load_dotenv()

RSS_FEEDS = [
    # AI / Tech
    "https://techcrunch.com/feed/",
    "https://venturebeat.com/feed/",
    "https://artificialintelligence-news.com/feed/",
    # Real estate / PropTech
    "https://www.inman.com/feed/",
    "https://www.housingwire.com/feed/",
    "https://therealdeal.com/feed/",
    "https://propmodo.com/feed/",
    # Mortgage / Lending
    "https://www.nationalmortgagenews.com/feed",
    "https://www.pymnts.com/feed/",
    # Enterprise automation
    "https://www.zdnet.com/topic/artificial-intelligence/rss.xml",
]

def _competitor_handles():
    return get_config().get("benchmark_accounts", [])

def _pillar_keywords():
    return get_config().get("pillar_keywords", {})


def scan_rss_feeds(feeds: Optional[List[str]] = None) -> list[dict]:
    """Fetch and parse RSS feeds. Returns list of {title, summary, link, source} dicts."""
    feeds = feeds or RSS_FEEDS
    results = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                results.append({
                    "title": getattr(entry, "title", ""),
                    "summary": getattr(entry, "summary", "")[:300],
                    "link": getattr(entry, "link", ""),
                    "source": url,
                })
        except Exception as e:
            print(f"Warning: failed to fetch {url}: {e}")
    return results


def fetch_competitor_posts() -> list[dict]:
    """Fetch recent tweets from benchmark accounts using X Bearer Token."""
    bearer_token = os.getenv("X_BEARER_TOKEN")
    if not bearer_token:
        return []

    try:
        import tweepy
        client = tweepy.Client(bearer_token=bearer_token)
        posts = []
        for handle in _competitor_handles():
            try:
                user_resp = client.get_user(username=handle)
                if not user_resp.data:
                    continue
                tweets_resp = client.get_users_tweets(
                    user_resp.data.id,
                    max_results=10,
                    exclude=["retweets", "replies"],
                )
                for tweet in (tweets_resp.data or []):
                    posts.append({
                        "title": tweet.text[:120],
                        "summary": tweet.text[:300],
                        "link": f"https://x.com/{handle}/status/{tweet.id}",
                        "source": f"@{handle}",
                    })
            except Exception as e:
                print(f"Warning: failed to fetch @{handle}: {e}")
        return posts
    except ImportError:
        return []


def get_all_topics() -> list[dict]:
    """Fetch and combine RSS + competitor posts. Returns raw unfiltered topic list."""
    rss_topics = scan_rss_feeds()
    competitor_topics = fetch_competitor_posts()
    return rss_topics + competitor_topics


def rank_topics(topics: list[dict], pillar: str, n: int = 5) -> list[dict]:
    """Score topics by keyword relevance to the given pillar. Returns top n."""
    keywords = _pillar_keywords().get(pillar, [])
    scored = []
    for topic in topics:
        text = (topic.get("title", "") + " " + topic.get("summary", "")).lower()
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > 0:
            scored.append({**topic, "_relevance": score})
    scored.sort(key=lambda t: t["_relevance"], reverse=True)
    return scored[:n]


def build_trend_context(topics: list[dict], pillar: str, funnel: str) -> str:
    """Format top topics into a context string for the content generator prompt."""
    lines = [
        f"Today's content pillar: {pillar}",
        f"Funnel stage: {funnel}",
        "",
        "Trending topics to draw from (use 1-2 in your post for specificity):",
    ]
    for i, topic in enumerate(topics, 1):
        source_label = f" [{topic.get('source', '')}]" if topic.get("source", "").startswith("@") else ""
        lines.append(f"{i}. {topic['title']}{source_label} — {topic.get('link', '')}")
    return "\n".join(lines)


def run(pillar: str, funnel: str) -> str:
    """Full scan pipeline: RSS + X competitor timelines. Returns trend context string."""
    all_topics = get_all_topics()
    top = rank_topics(all_topics, pillar=pillar, n=7)
    if not top:
        top = all_topics[:7]
    return build_trend_context(top, pillar=pillar, funnel=funnel)


if __name__ == "__main__":
    from cadence import get_todays_pillar
    today = get_todays_pillar()
    context = run(pillar=today["pillar"], funnel=today["funnel"])
    print(context)
