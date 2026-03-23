import pytest
import json
from datetime import datetime, timedelta
from scripts.spike_detector import record_headlines, detect_spike, get_cooldown_active, mark_alerted, SPIKE_LOG_PATH


@pytest.fixture(autouse=True)
def clean_spike_log(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.spike_detector.SPIKE_LOG_PATH", str(tmp_path / "spike_log.json"))


def make_topics(keyword, count=3):
    return [{"title": f"{keyword} headline {i}", "summary": "", "link": "", "source": "test"} for i in range(count)]


def test_record_headlines_creates_log(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.spike_detector.SPIKE_LOG_PATH", str(tmp_path / "spike_log.json"))
    topics = make_topics("mortgage AI", 2)
    record_headlines(topics)
    with open(tmp_path / "spike_log.json") as f:
        data = json.load(f)
    assert "headlines" in data
    assert len(data["headlines"]) == 2


def test_detect_spike_returns_spike_above_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.spike_detector.SPIKE_LOG_PATH", str(tmp_path / "spike_log.json"))
    topics = make_topics("Fed rate decision", 4)
    record_headlines(topics)
    spikes = detect_spike(topics, window_hours=2, threshold=3)
    assert len(spikes) >= 1


def test_detect_spike_no_spike_below_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.spike_detector.SPIKE_LOG_PATH", str(tmp_path / "spike_log.json"))
    topics = make_topics("random topic", 2)
    record_headlines(topics)
    spikes = detect_spike(topics, window_hours=2, threshold=3)
    assert len(spikes) == 0


def test_cooldown_prevents_duplicate_alerts(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.spike_detector.SPIKE_LOG_PATH", str(tmp_path / "spike_log.json"))
    record_headlines([])
    mark_alerted("mortgage AI")
    assert get_cooldown_active("mortgage AI", cooldown_hours=6) is True


def test_cooldown_expired_allows_alert(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.spike_detector.SPIKE_LOG_PATH", str(tmp_path / "spike_log.json"))
    # Write an alert that happened 7 hours ago
    old_time = (datetime.utcnow() - timedelta(hours=7)).isoformat()
    with open(tmp_path / "spike_log.json", "w") as f:
        json.dump({"headlines": [], "alerts": {"mortgage AI": old_time}}, f)
    assert get_cooldown_active("mortgage AI", cooldown_hours=6) is False
