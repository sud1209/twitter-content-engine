"""
Queue — read/write the local JSON post queue at data/queue.json.
"""

import json
import os

QUEUE_PATH = "data/queue.json"


def load_queue() -> list[dict]:
    if not os.path.exists(QUEUE_PATH):
        return []
    with open(QUEUE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_queue(posts: list[dict]) -> None:
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)


def add_post(post: dict) -> None:
    queue = load_queue()
    queue.append(post)
    save_queue(queue)


def update_post_status(post_id: str, status: str) -> None:
    queue = load_queue()
    for post in queue:
        if post["id"] == post_id:
            post["status"] = status
            save_queue(queue)
            return
    raise ValueError(f"Post with id '{post_id}' not found in queue")
