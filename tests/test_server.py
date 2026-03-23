import json
import pytest
from scripts.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_posts_today_returns_empty_list(client):
    response = client.get("/api/posts/today")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data == []


def test_get_posts_today_returns_queue(client, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    q.save_queue([{"id": "1", "text": "Test post", "score": 9.5, "status": "ready"}])
    response = client.get("/api/posts/today")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 1


def test_approve_post(client, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    q.save_queue([{"id": "abc", "text": "Test", "score": 9.5, "status": "ready"}])
    response = client.post("/api/posts/abc/approve")
    assert response.status_code == 200
    queue = q.load_queue()
    assert queue[0]["status"] == "approved"


def test_reject_post(client, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    q.save_queue([{"id": "xyz", "text": "Test", "score": 8.0, "status": "ready"}])
    response = client.post("/api/posts/xyz/reject")
    assert response.status_code == 200
    queue = q.load_queue()
    assert queue[0]["status"] == "rejected"


def test_skip_today(client, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    q.save_queue([{"id": "1", "text": "Post", "score": 9.5, "status": "ready"}])
    response = client.post("/api/skip-today")
    assert response.status_code == 200
    queue = q.load_queue()
    assert all(p["status"] == "skipped" for p in queue)
