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


def test_publish_time_read_from_config(monkeypatch):
    """Scheduler reads publish_time_utc from config, not hardcoded 15:00."""
    import scripts.scheduler as sched_mod
    captured = {}

    monkeypatch.setattr(
        "scripts.scheduler.get_config",
        lambda: {"publish_time_utc": "21:00"},
    )

    original_add_job = sched_mod.scheduler.add_job

    def fake_add_job(func, trigger, **kwargs):
        if hasattr(func, "__name__") and func.__name__ == "run_publish_pipeline":
            captured["hour"] = kwargs.get("hour")
            captured["minute"] = kwargs.get("minute")
        return original_add_job(func, trigger, **kwargs)

    monkeypatch.setattr(sched_mod.scheduler, "add_job", fake_add_job)
    sched_mod.schedule_jobs()
    assert captured.get("hour") == 21
    assert captured.get("minute") == 0
