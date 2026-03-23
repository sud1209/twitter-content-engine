"""
Playbook Refresher — Phase 2 Feature 5
Pulls benchmark posts + user's recent posts, synthesizes with Claude,
appends dated Trend Update sections to playbooks. Append-only, never overwrites.
"""

import os
import json
import threading
from datetime import datetime, timezone
from openai import OpenAI
from dotenv import load_dotenv

from scripts.config_loader import get_config

load_dotenv()

NUM_BENCHMARK_POSTS = 20
NUM_OWN_POSTS = 20

def _playbook_paths():
    return get_config()["playbooks"]

def _benchmark_accounts():
    return get_config().get("benchmark_accounts", [])

MODEL = "gpt-4o-mini"

# In-memory status for the background job
_refresh_status = {
    "running": False,
    "done": False,
    "error": None,
    "diffs": None,  # dict: {playbook_key: proposed_addition_text}
    "written": False,
}
_status_lock = threading.Lock()


def get_status() -> dict:
    with _status_lock:
        return dict(_refresh_status)


def _set_status(**kwargs):
    with _status_lock:
        _refresh_status.update(kwargs)


def fetch_benchmark_posts(client_x) -> list[str]:
    """Fetch recent posts from benchmark accounts via X API. Returns list of post texts."""
    posts = []
    for username in _benchmark_accounts():
        try:
            user_resp = client_x.get_user(username=username, user_auth=False)
            if not user_resp.data:
                continue
            uid = user_resp.data.id
            tweets_resp = client_x.get_users_tweets(
                id=uid,
                max_results=NUM_BENCHMARK_POSTS,
                tweet_fields=["text"],
                exclude=["retweets", "replies"],
                user_auth=False,
            )
            if tweets_resp.data:
                for t in tweets_resp.data:
                    posts.append(f"@{username}: {t.text}")
        except Exception:
            pass  # X API unavailable or rate limited — skip gracefully
    return posts


def fetch_own_posts() -> list[str]:
    """Load the user's last N published posts from queue."""
    from scripts.post_queue import load_queue
    queue = load_queue()
    published = [p for p in queue if p.get("status") == "published"]
    published.sort(key=lambda p: p.get("published_at", ""), reverse=True)
    return [p["text"] for p in published[:NUM_OWN_POSTS]]


def synthesize_with_claude(benchmark_posts: list[str], own_posts: list[str], playbook_key: str, current_content: str) -> str:
    """Call Claude to synthesize a trend update for one playbook. Returns the new section text."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    benchmark_block = "\n".join(benchmark_posts) if benchmark_posts else "(no benchmark posts available)"
    own_block = "\n".join(own_posts) if own_posts else "(no published posts yet)"

    cfg = get_config()
    system = f"""You are a content strategist updating the playbook for @{cfg['handle']}, a {cfg['bio']}.

You will receive:
1. Recent posts from top creators in the space (benchmark)
2. The user's own recent published posts
3. The current {playbook_key} playbook content

Your job: Write a concise "Trend Update" section that identifies 3-5 actionable insights based on what's working in the benchmark posts vs the user's current approach. Focus on patterns, hooks, or formats that are gaining traction.

Rules:
- Output ONLY the section content (no markdown fences, no intro text)
- Start directly with the insights (numbered list)
- Keep it under 300 words
- Be specific: quote formats, hook types, CTA patterns — not vague advice
- Do NOT suggest removing or changing existing playbook content"""

    user_message = f"""## Benchmark posts (top creators, recent):
{benchmark_block}

## Your recent published posts:
{own_block}

## Current {playbook_key} playbook (for context only):
{current_content[:3000]}

Write the Trend Update section now."""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=600,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content.strip()


def build_diffs(benchmark_posts: list[str], own_posts: list[str]) -> dict:
    """Generate proposed additions for all 3 playbooks. Returns {key: proposed_text}."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    diffs = {}
    for key, path in _playbook_paths().items():
        try:
            with open(path, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = ""
        synthesis = synthesize_with_claude(benchmark_posts, own_posts, key, current)
        diffs[key] = f"\n\n## Trend Update — {today}\n\n{synthesis}"
    return diffs


def write_diffs(diffs: dict) -> None:
    """Append the proposed additions to each playbook file."""
    for key, addition in diffs.items():
        path = _playbook_paths()[key]
        with open(path, "a", encoding="utf-8") as f:
            f.write(addition)


def run_refresh(client_x=None) -> None:
    """Background thread entry point. Fetches posts, builds diffs, sets status."""
    _set_status(running=True, done=False, error=None, diffs=None, written=False)
    try:
        benchmark_posts = fetch_benchmark_posts(client_x) if client_x else []
        own_posts = fetch_own_posts()
        diffs = build_diffs(benchmark_posts, own_posts)
        _set_status(running=False, done=True, diffs=diffs)
    except Exception as e:
        _set_status(running=False, done=True, error=str(e))


def confirm_write() -> None:
    """Write the pending diffs to disk (called after user confirms in dashboard)."""
    with _status_lock:
        diffs = _refresh_status.get("diffs")
        if not diffs:
            return
    write_diffs(diffs)
    _set_status(written=True)
