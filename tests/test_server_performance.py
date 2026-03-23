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


def test_get_performance_returns_only_published(client, tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    q.save_queue([
        {"id": "1", "text": "Published", "score": 9.5, "status": "published", "pillar": "AI for Real Estate", "funnel": "TOFU"},
        {"id": "2", "text": "Ready", "score": 9.0, "status": "ready", "pillar": "AI for Real Estate", "funnel": "TOFU"},
    ])
    response = client.get("/api/performance")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data) == 1
    assert data[0]["id"] == "1"
