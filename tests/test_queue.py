import json
import os
import pytest
from scripts.post_queue import load_queue, save_queue, add_post, update_post_status, QUEUE_PATH


@pytest.fixture(autouse=True)
def clean_queue(tmp_path, monkeypatch):
    """Use a temp path for queue during tests."""
    test_queue = str(tmp_path / "queue.json")
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", test_queue)
    yield test_queue
    if os.path.exists(test_queue):
        os.remove(test_queue)


def test_load_queue_returns_empty_list_when_file_missing():
    result = load_queue()
    assert result == []


def test_save_and_load_queue():
    posts = [{"id": "1", "text": "Hello", "score": 9.5, "status": "pending"}]
    save_queue(posts)
    result = load_queue()
    assert result == posts


def test_add_post_appends_to_queue():
    add_post({"id": "1", "text": "Post one", "score": 8.0, "status": "pending"})
    add_post({"id": "2", "text": "Post two", "score": 9.5, "status": "pending"})
    queue = load_queue()
    assert len(queue) == 2
    assert queue[1]["id"] == "2"


def test_update_post_status_changes_status():
    add_post({"id": "abc", "text": "Test post", "score": 9.5, "status": "pending"})
    update_post_status("abc", "approved")
    queue = load_queue()
    assert queue[0]["status"] == "approved"


def test_update_post_status_raises_if_id_not_found():
    with pytest.raises(ValueError, match="Post with id 'missing' not found"):
        update_post_status("missing", "approved")
