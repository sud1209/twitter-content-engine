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


def test_generate_pipeline_produces_eight_posts(tmp_path, monkeypatch):
    """Call _run_posts_pipeline() directly (synchronously) to test multi-pillar output.

    NOTE: _run_posts_pipeline() uses deferred imports, so patches must target the
    source modules (scripts.cadence, scripts.trend_scanner, etc.) not scripts.server.
    """
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))

    monkeypatch.setattr("scripts.cadence.get_todays_pillar", lambda: {"pillar": "AI Innovations", "funnel": "TOFU"})
    monkeypatch.setattr("scripts.trend_scanner.get_all_topics", lambda: [
        {"title": "cricket IPL match", "summary": "", "link": "", "source": "rss"},
        {"title": "Dota 2 patch notes", "summary": "", "link": "", "source": "rss"},
        {"title": "book recommendation 2026", "summary": "", "link": "", "source": "rss"},
    ])
    monkeypatch.setattr("scripts.trend_scanner.rank_pillars", lambda topics, exclude_pillar, n: [
        "Sports & Cricket", "eSports & Dota 2", "Literature"
    ])
    monkeypatch.setattr("scripts.trend_scanner.rank_topics", lambda topics, pillar, n: topics)
    monkeypatch.setattr("scripts.trend_scanner.build_trend_context", lambda topics, pillar, funnel: f"context for {pillar}")

    def fake_generate(pillar, funnel, trend_context, num_drafts=8):
        return [f"post {i} for {pillar}" for i in range(num_drafts)]

    monkeypatch.setattr("scripts.content_generator.generate", fake_generate)
    monkeypatch.setattr("scripts.post_scorer.score_all_posts",
                        lambda posts: [{**post, "score": 8.0, "status": "scored"} for post in posts])

    from scripts.server import _run_posts_pipeline
    _run_posts_pipeline()

    from scripts.post_queue import load_queue
    queue = load_queue()

    assert len(queue) == 8
    pillars = [p["pillar"] for p in queue]
    assert pillars.count("AI Innovations") == 5
    non_primary = [p for p in pillars if p != "AI Innovations"]
    assert len(non_primary) == 3
    assert len(set(non_primary)) == 3  # all 3 are distinct pillars
