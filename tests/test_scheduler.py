import pytest


def test_run_morning_pipeline_populates_queue(mocker, tmp_path, monkeypatch):
    """run_morning_pipeline generates + scores posts and writes them to queue."""
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))

    mocker.patch("scripts.cadence.get_todays_pillar", return_value={
        "pillar": "AI for Real Estate", "funnel": "TOFU", "day": "Monday"
    })
    mocker.patch("scripts.trend_scanner.run", return_value="AI mortgage news today")
    mocker.patch("scripts.content_generator.generate", return_value=[
        "AI is replacing loan officers. Cost down 40%.",
        "3 things Non-QM lenders get wrong about AI.",
    ])
    mocker.patch("scripts.post_scorer.regenerate_if_below_floor", side_effect=lambda p: {
        **p, "score": 9.6, "status": "ready", "score_breakdown": {}
    })
    mock_notify = mocker.patch("scripts.notifier.notify_posts_ready")

    from scripts.scheduler import run_morning_pipeline
    run_morning_pipeline()

    import scripts.post_queue as q
    queue = q.load_queue()
    assert len(queue) == 2
    assert all(p["status"] == "ready" for p in queue)
    mock_notify.assert_called_once_with(2)


def test_run_morning_pipeline_clears_previous_queue(mocker, tmp_path, monkeypatch):
    """run_morning_pipeline wipes yesterday's posts before generating new ones."""
    import scripts.post_queue as q
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    q.save_queue([{"id": "old", "text": "yesterday", "status": "published"}])

    mocker.patch("scripts.cadence.get_todays_pillar", return_value={"pillar": "AI for Real Estate", "funnel": "TOFU", "day": "Monday"})
    mocker.patch("scripts.trend_scanner.run", return_value="trends")
    mocker.patch("scripts.content_generator.generate", return_value=["New post today"])
    mocker.patch("scripts.post_scorer.regenerate_if_below_floor", side_effect=lambda p: {**p, "score": 9.5, "status": "ready", "score_breakdown": {}})
    mocker.patch("scripts.notifier.notify_posts_ready")

    from scripts.scheduler import run_morning_pipeline
    run_morning_pipeline()

    queue = q.load_queue()
    assert not any(p["id"] == "old" for p in queue)
