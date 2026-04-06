import pytest
from unittest.mock import patch, MagicMock


# ── validate_post ────────────────────────────────────────────────────────────

def test_validate_post_rejects_hashtag():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("Great AI insight. #AI is changing everything.")
    assert valid is False
    assert reason == "contains_hashtags"


def test_validate_post_rejects_fullwidth_hashtag():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("Great post ＃AI here.")
    assert valid is False
    assert reason == "contains_hashtags"


def test_validate_post_rejects_emdash():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("AI is growing — and fast.")
    assert valid is False
    assert reason == "contains_emdash"


def test_validate_post_rejects_soft_question_at_end():
    from scripts.content_generator import validate_post
    valid, reason = validate_post(
        "Most AI researchers are ignoring the inference cost problem. How do you handle this?"
    )
    assert valid is False
    assert reason == "soft_qa_cta"


def test_validate_post_rejects_weak_cta_phrase():
    from scripts.content_generator import validate_post
    valid, reason = validate_post("IPL 2026 is wild. What do you think about the batting line-ups?")
    assert valid is False
    assert "weak_cta" in reason


def test_validate_post_accepts_clean_post():
    from scripts.content_generator import validate_post
    valid, reason = validate_post(
        "Dota 2's new patch broke every carry hero in the top 1000 MMR bracket. "
        "The ones adapting to support meta are already climbing. Follow for daily breakdowns."
    )
    assert valid is True
    assert reason == ""


def test_validate_post_accepts_post_with_question_in_body_not_end():
    """Soft question in body is OK; only rejected if it's in the final 80 chars."""
    from scripts.content_generator import validate_post
    valid, reason = validate_post(
        "How do top AI labs manage inference cost? Simple: they don't. "
        "They offload it to enterprise contracts. The open-source labs are the ones actually solving it."
    )
    assert valid is True


# ── load_playbooks ────────────────────────────────────────────────────────────

def test_load_playbooks_uses_distilled_when_available(tmp_path, monkeypatch):
    """If distilled file exists and has all 3 keys, use it."""
    distilled = {"voice": "v", "twitter": "t", "strategy": "s"}
    distilled_path = tmp_path / "playbook_distilled.json"
    distilled_path.write_text('{"voice": "v", "twitter": "t", "strategy": "s"}')

    monkeypatch.setattr("scripts.content_generator._DISTILLED_PATH", str(distilled_path))

    from scripts.content_generator import load_playbooks
    result = load_playbooks()
    assert result == distilled


def test_load_playbooks_falls_back_to_full_when_distilled_missing(tmp_path, monkeypatch):
    """Falls back to full playbooks when distilled file does not exist."""
    monkeypatch.setattr(
        "scripts.content_generator._DISTILLED_PATH",
        str(tmp_path / "nonexistent.json"),
    )

    fake_voice = tmp_path / "voice.md"
    fake_voice.write_text("voice content")
    fake_twitter = tmp_path / "twitter.md"
    fake_twitter.write_text("twitter content")
    fake_strategy = tmp_path / "strategy.md"
    fake_strategy.write_text("strategy content")

    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "playbooks": {
                "voice": str(fake_voice),
                "twitter": str(fake_twitter),
                "strategy": str(fake_strategy),
            }
        },
    )

    from scripts.content_generator import load_playbooks
    result = load_playbooks()
    assert result["voice"] == "voice content"
    assert result["twitter"] == "twitter content"
    assert result["strategy"] == "strategy content"


# ── generate ─────────────────────────────────────────────────────────────────

def test_generate_filters_invalid_posts(monkeypatch, tmp_path):
    """generate() drops posts that fail validate_post() before returning."""
    monkeypatch.setattr(
        "scripts.content_generator._DISTILLED_PATH",
        str(tmp_path / "nonexistent.json"),
    )

    fake_playbooks = {"voice": "v", "twitter": "t", "strategy": "s"}
    monkeypatch.setattr("scripts.content_generator.load_playbooks", lambda: fake_playbooks)
    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "handle": "testuser",
            "bio": "test bio",
            "models": {"generation": "claude-haiku-4-5-20251001"},
            "benchmark_accounts": [],
        },
    )

    # One valid, one with hashtag (invalid)
    raw_response = "1. Clean post about Dota 2 patches and meta shifts. Follow for more.\n2. Post with #hashtag inside it."

    monkeypatch.setattr("scripts.content_generator.llm_complete", lambda **kwargs: raw_response)

    from scripts.content_generator import generate
    result = generate(pillar="eSports & Dota 2", funnel="TOFU", trend_context="ctx", num_drafts=2)

    assert len(result) == 1
    assert "#hashtag" not in result[0]


def test_generate_uses_num_drafts_in_prompt(monkeypatch, tmp_path):
    """num_drafts parameter appears in the user message sent to LLM."""
    monkeypatch.setattr(
        "scripts.content_generator._DISTILLED_PATH",
        str(tmp_path / "nonexistent.json"),
    )
    monkeypatch.setattr("scripts.content_generator.load_playbooks", lambda: {"voice": "v", "twitter": "t", "strategy": "s"})
    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "handle": "h", "bio": "b",
            "models": {"generation": "claude-haiku-4-5-20251001"},
            "benchmark_accounts": [],
        },
    )

    captured = {}

    def fake_llm(**kwargs):
        captured["user"] = kwargs.get("user", "")
        return "1. Some post text here without any violations."

    monkeypatch.setattr("scripts.content_generator.llm_complete", fake_llm)

    from scripts.content_generator import generate
    generate(pillar="AI Innovations", funnel="TOFU", trend_context="ctx", num_drafts=3)

    assert "3 posts" in captured["user"]


# ── _load_benchmark_insights ──────────────────────────────────────────────────

def test_load_benchmark_insights_returns_none_when_file_absent(tmp_path, monkeypatch):
    """Returns None when data/benchmark_insights.json does not exist."""
    monkeypatch.chdir(tmp_path)
    from scripts.content_generator import _load_benchmark_insights
    result = _load_benchmark_insights()
    assert result is None


def test_load_benchmark_insights_returns_none_when_json_malformed(tmp_path, monkeypatch):
    """Returns None when the file contains invalid JSON."""
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "benchmark_insights.json").write_text("not valid json {{{{")
    from scripts.content_generator import _load_benchmark_insights
    result = _load_benchmark_insights()
    assert result is None


def test_load_benchmark_insights_returns_none_when_required_keys_missing(tmp_path, monkeypatch):
    """Returns None when top_posts or patterns keys are absent/empty."""
    import json as _json
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Missing both keys
    (data_dir / "benchmark_insights.json").write_text(_json.dumps({"other_key": "value"}))
    from scripts.content_generator import _load_benchmark_insights
    assert _load_benchmark_insights() is None

    # top_posts present but patterns missing
    (data_dir / "benchmark_insights.json").write_text(_json.dumps({"top_posts": [{"text": "x"}]}))
    assert _load_benchmark_insights() is None

    # patterns present but top_posts missing
    (data_dir / "benchmark_insights.json").write_text(_json.dumps({"patterns": {"hook_patterns": ["a"]}}))
    assert _load_benchmark_insights() is None


# ── distill_playbooks ─────────────────────────────────────────────────────────

def test_distill_playbooks_writes_json_to_distilled_path(tmp_path, monkeypatch):
    """distill_playbooks() writes a valid JSON file to _DISTILLED_PATH."""
    import json as _json

    monkeypatch.chdir(tmp_path)

    fake_voice = tmp_path / "voice.md"
    fake_voice.write_text("voice content")
    fake_twitter = tmp_path / "twitter.md"
    fake_twitter.write_text("twitter content")
    fake_strategy = tmp_path / "strategy.md"
    fake_strategy.write_text("strategy content")

    distilled_path = str(tmp_path / "data" / "playbook_distilled.json")
    monkeypatch.setattr("scripts.content_generator._DISTILLED_PATH", distilled_path)
    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "playbooks": {
                "voice": str(fake_voice),
                "twitter": str(fake_twitter),
                "strategy": str(fake_strategy),
            },
            "models": {"generation": "gpt-4o-mini"},
        },
    )

    llm_return = _json.dumps({"voice": "v rules", "twitter": "t rules", "strategy": "s rules"})
    monkeypatch.setattr("scripts.content_generator.llm_complete", lambda **kwargs: llm_return)

    from scripts.content_generator import distill_playbooks
    distill_playbooks()

    import os
    assert os.path.exists(distilled_path)
    with open(distilled_path, encoding="utf-8") as f:
        result = _json.load(f)
    assert result["voice"] == "v rules"
    assert result["twitter"] == "t rules"
    assert result["strategy"] == "s rules"


# ── build_system_prompt — benchmark injection ─────────────────────────────────

def test_build_system_prompt_injects_benchmark_content(tmp_path, monkeypatch):
    """When _load_benchmark_insights returns a valid dict, its content appears in the prompt."""
    monkeypatch.setattr(
        "scripts.content_generator._DISTILLED_PATH",
        str(tmp_path / "nonexistent.json"),
    )
    fake_voice = tmp_path / "voice.md"
    fake_voice.write_text("voice content")
    fake_twitter = tmp_path / "twitter.md"
    fake_twitter.write_text("twitter content")
    fake_strategy = tmp_path / "strategy.md"
    fake_strategy.write_text("strategy content")

    monkeypatch.setattr(
        "scripts.content_generator.get_config",
        lambda: {
            "handle": "testuser",
            "bio": "test bio",
            "playbooks": {
                "voice": str(fake_voice),
                "twitter": str(fake_twitter),
                "strategy": str(fake_strategy),
            },
            "models": {"generation": "gpt-4o-mini"},
            "benchmark_accounts": ["karpathy", "paraschopra"],
        },
    )

    fake_insights = {
        "top_posts": [
            {
                "account": "karpathy",
                "text": "Unique hook pattern text that should appear in the prompt",
                "replies": 10,
                "retweets": 5,
                "likes": 50,
                "score": 99,
            }
        ],
        "patterns": {
            "hook_patterns": ["distinctive_hook_formula_abc"],
            "cta_patterns": ["reply-bait question"],
            "engagement_drivers": ["specificity over vagueness"],
        },
    }
    monkeypatch.setattr(
        "scripts.content_generator._load_benchmark_insights",
        lambda: fake_insights,
    )

    from scripts.content_generator import build_system_prompt
    prompt = build_system_prompt(pillar="AI Innovations", funnel="TOFU")

    assert "distinctive_hook_formula_abc" in prompt
    assert "Unique hook pattern text that should appear in the prompt" in prompt
    assert "karpathy" in prompt
