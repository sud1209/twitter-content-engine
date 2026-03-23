"""
Tests for scripts/playbook_refresher.py — Feature 5 (Playbook Refresh on Demand)
"""

import os
import threading
import pytest


# ── fetch_own_posts ──────────────────────────────────────────────────────────

def test_fetch_own_posts_returns_list(tmp_path, monkeypatch):
    """fetch_own_posts() should return a list (possibly empty)."""
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    from scripts.playbook_refresher import fetch_own_posts
    result = fetch_own_posts()
    assert isinstance(result, list)


def test_fetch_own_posts_returns_only_published(tmp_path, monkeypatch):
    """fetch_own_posts() should return only published posts, most recent first."""
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    q.save_queue([
        {"id": "1", "text": "published post A", "status": "published", "published_at": "2024-01-01T08:00:00Z"},
        {"id": "2", "text": "pending post", "status": "pending", "published_at": ""},
        {"id": "3", "text": "published post B", "status": "published", "published_at": "2024-01-02T08:00:00Z"},
    ])
    from scripts.playbook_refresher import fetch_own_posts
    result = fetch_own_posts()
    assert "published post A" in result
    assert "published post B" in result
    assert "pending post" not in result


def test_fetch_own_posts_respects_limit(tmp_path, monkeypatch):
    """fetch_own_posts() should return at most NUM_OWN_POSTS items."""
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))
    import scripts.post_queue as q
    posts = [
        {"id": str(i), "text": f"post {i}", "status": "published", "published_at": f"2024-01-{i:02d}T00:00:00Z"}
        for i in range(1, 30)
    ]
    q.save_queue(posts)
    from scripts.playbook_refresher import fetch_own_posts, NUM_OWN_POSTS
    result = fetch_own_posts()
    assert len(result) <= NUM_OWN_POSTS


# ── build_diffs ──────────────────────────────────────────────────────────────

def test_build_diffs_returns_dict_with_expected_keys(tmp_path, monkeypatch):
    """build_diffs() should return a dict with 'voice', 'twitter', 'strategy' keys."""
    # Patch Claude call to avoid real API
    def fake_synthesize(benchmark_posts, own_posts, playbook_key, current_content):
        return f"Fake synthesis for {playbook_key}"

    monkeypatch.setattr("scripts.playbook_refresher.synthesize_with_claude", fake_synthesize)
    # Patch playbook paths to tmp files
    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(tmp_path / "voice.md"),
        "twitter": str(tmp_path / "twitter.md"),
        "strategy": str(tmp_path / "strategy.md"),
    })

    from scripts.playbook_refresher import build_diffs
    result = build_diffs([], [])

    assert isinstance(result, dict)
    assert set(result.keys()) == {"voice", "twitter", "strategy"}


def test_build_diffs_content_contains_trend_update_header(tmp_path, monkeypatch):
    """Each diff value should start with a Trend Update header."""
    def fake_synthesize(benchmark_posts, own_posts, playbook_key, current_content):
        return "1. Some insight"

    monkeypatch.setattr("scripts.playbook_refresher.synthesize_with_claude", fake_synthesize)
    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(tmp_path / "voice.md"),
        "twitter": str(tmp_path / "twitter.md"),
        "strategy": str(tmp_path / "strategy.md"),
    })

    from scripts.playbook_refresher import build_diffs
    result = build_diffs([], [])

    for key, text in result.items():
        assert "## Trend Update —" in text
        assert "1. Some insight" in text


# ── confirm_write ────────────────────────────────────────────────────────────

def test_confirm_write_appends_to_files(tmp_path, monkeypatch):
    """confirm_write() should append diffs to each playbook file."""
    voice_path = tmp_path / "voice.md"
    twitter_path = tmp_path / "twitter.md"
    strategy_path = tmp_path / "strategy.md"

    # Write initial content
    voice_path.write_text("# Voice Playbook\n\nOriginal content.", encoding="utf-8")
    twitter_path.write_text("# Twitter Playbook\n\nOriginal content.", encoding="utf-8")
    strategy_path.write_text("# Strategy Playbook\n\nOriginal content.", encoding="utf-8")

    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(voice_path),
        "twitter": str(twitter_path),
        "strategy": str(strategy_path),
    })

    import scripts.playbook_refresher as pr
    # Inject diffs into status
    test_diffs = {
        "voice": "\n\n## Trend Update — 2026-03-20\n\n1. Voice insight",
        "twitter": "\n\n## Trend Update — 2026-03-20\n\n1. Twitter insight",
        "strategy": "\n\n## Trend Update — 2026-03-20\n\n1. Strategy insight",
    }
    with pr._status_lock:
        pr._refresh_status["diffs"] = test_diffs
        pr._refresh_status["written"] = False

    pr.confirm_write()

    voice_content = voice_path.read_text(encoding="utf-8")
    assert "Original content." in voice_content
    assert "## Trend Update — 2026-03-20" in voice_content
    assert "1. Voice insight" in voice_content

    twitter_content = twitter_path.read_text(encoding="utf-8")
    assert "Original content." in twitter_content
    assert "1. Twitter insight" in twitter_content

    strategy_content = strategy_path.read_text(encoding="utf-8")
    assert "Original content." in strategy_content
    assert "1. Strategy insight" in strategy_content


def test_confirm_write_does_not_overwrite(tmp_path, monkeypatch):
    """confirm_write() must append, not replace — original content must remain."""
    playbook_path = tmp_path / "voice.md"
    original = "# Original Title\n\nThis must not be removed."
    playbook_path.write_text(original, encoding="utf-8")

    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(playbook_path),
        "twitter": str(tmp_path / "twitter.md"),
        "strategy": str(tmp_path / "strategy.md"),
    })
    (tmp_path / "twitter.md").write_text("", encoding="utf-8")
    (tmp_path / "strategy.md").write_text("", encoding="utf-8")

    import scripts.playbook_refresher as pr
    with pr._status_lock:
        pr._refresh_status["diffs"] = {
            "voice": "\n\n## Trend Update — 2026-03-20\n\nNew content",
            "twitter": "\n\n## Trend Update — 2026-03-20\n\nNew content",
            "strategy": "\n\n## Trend Update — 2026-03-20\n\nNew content",
        }
        pr._refresh_status["written"] = False

    pr.confirm_write()

    result = playbook_path.read_text(encoding="utf-8")
    assert original in result


def test_confirm_write_sets_written_flag(tmp_path, monkeypatch):
    """confirm_write() should set written=True in status."""
    for name in ["voice.md", "twitter.md", "strategy.md"]:
        (tmp_path / name).write_text("", encoding="utf-8")

    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(tmp_path / "voice.md"),
        "twitter": str(tmp_path / "twitter.md"),
        "strategy": str(tmp_path / "strategy.md"),
    })

    import scripts.playbook_refresher as pr
    with pr._status_lock:
        pr._refresh_status["diffs"] = {
            "voice": "\n\nNew",
            "twitter": "\n\nNew",
            "strategy": "\n\nNew",
        }
        pr._refresh_status["written"] = False

    pr.confirm_write()

    assert pr.get_status()["written"] is True


# ── get_status ───────────────────────────────────────────────────────────────

def test_get_status_returns_correct_structure():
    """get_status() should return a dict with all expected keys."""
    from scripts.playbook_refresher import get_status
    status = get_status()
    assert isinstance(status, dict)
    assert "running" in status
    assert "done" in status
    assert "error" in status
    assert "diffs" in status
    assert "written" in status


def test_get_status_returns_copy():
    """get_status() should return a copy, not a reference to the internal dict."""
    from scripts.playbook_refresher import get_status, _refresh_status
    status = get_status()
    status["running"] = not status["running"]  # mutate copy
    # internal state should not change
    status2 = get_status()
    assert status2["running"] != status["running"]


# ── run_refresh ──────────────────────────────────────────────────────────────

def test_run_refresh_sets_done_on_completion(tmp_path, monkeypatch):
    """run_refresh() should set done=True when it finishes successfully."""
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))

    def fake_synthesize(benchmark_posts, own_posts, playbook_key, current_content):
        return "Fake synthesis"

    monkeypatch.setattr("scripts.playbook_refresher.synthesize_with_claude", fake_synthesize)
    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(tmp_path / "voice.md"),
        "twitter": str(tmp_path / "twitter.md"),
        "strategy": str(tmp_path / "strategy.md"),
    })

    import scripts.playbook_refresher as pr
    # Reset status
    with pr._status_lock:
        pr._refresh_status.update({"running": False, "done": False, "error": None, "diffs": None, "written": False})

    # Run synchronously (not in thread) to test directly
    pr.run_refresh(client_x=None)

    status = pr.get_status()
    assert status["done"] is True
    assert status["running"] is False
    assert status["error"] is None
    assert isinstance(status["diffs"], dict)


def test_run_refresh_sets_error_on_failure(tmp_path, monkeypatch):
    """run_refresh() should set error and done=True when an exception occurs."""
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))

    def boom(*args, **kwargs):
        raise RuntimeError("Claude API down")

    monkeypatch.setattr("scripts.playbook_refresher.synthesize_with_claude", boom)
    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(tmp_path / "voice.md"),
        "twitter": str(tmp_path / "twitter.md"),
        "strategy": str(tmp_path / "strategy.md"),
    })

    import scripts.playbook_refresher as pr
    with pr._status_lock:
        pr._refresh_status.update({"running": False, "done": False, "error": None, "diffs": None, "written": False})

    pr.run_refresh(client_x=None)

    status = pr.get_status()
    assert status["done"] is True
    assert status["running"] is False
    assert status["error"] is not None
    assert "Claude API down" in status["error"]


def test_run_refresh_running_flag_set_then_cleared(tmp_path, monkeypatch):
    """run_refresh() should set running=True during execution and False after."""
    monkeypatch.setattr("scripts.post_queue.QUEUE_PATH", str(tmp_path / "queue.json"))

    def fake_synthesize(*args, **kwargs):
        return "ok"

    monkeypatch.setattr("scripts.playbook_refresher.synthesize_with_claude", fake_synthesize)
    monkeypatch.setattr("scripts.playbook_refresher.PLAYBOOK_PATHS", {
        "voice": str(tmp_path / "voice.md"),
        "twitter": str(tmp_path / "twitter.md"),
        "strategy": str(tmp_path / "strategy.md"),
    })

    import scripts.playbook_refresher as pr
    with pr._status_lock:
        pr._refresh_status.update({"running": False, "done": False, "error": None, "diffs": None, "written": False})

    pr.run_refresh(client_x=None)

    status = pr.get_status()
    assert status["running"] is False
    assert status["done"] is True


def test_no_nik_references_in_string_literals():
    """No string literal in playbook_refresher contains 'Nik'."""
    import ast, inspect
    from scripts import playbook_refresher
    source = inspect.getsource(playbook_refresher)
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "Nik" in node.value:
                violations.append(f"Line {node.lineno}: {node.value!r}")
    assert not violations, "Found 'Nik' in string literals:\n" + "\n".join(violations)
