import pytest
from unittest.mock import patch, MagicMock
from scripts.content_generator import load_playbooks, build_system_prompt, parse_drafts, PLAYBOOK_PATHS


def test_playbook_paths_all_exist():
    import os
    for path in PLAYBOOK_PATHS.values():
        assert os.path.exists(path), f"Missing playbook: {path}"


def test_load_playbooks_returns_dict_with_content():
    playbooks = load_playbooks()
    assert "voice" in playbooks
    assert "twitter" in playbooks
    assert "strategy" in playbooks
    assert len(playbooks["voice"]) > 100  # not empty


def test_build_system_prompt_contains_pillar(mocker):
    mocker.patch("scripts.content_generator.load_playbooks", return_value={
        "voice": "Voice content here",
        "twitter": "Twitter rules here",
        "strategy": "Strategy here",
    })
    prompt = build_system_prompt(pillar="AI for Real Estate", funnel="TOFU")
    assert "AI for Real Estate" in prompt
    assert "TOFU" in prompt
    assert "Voice content here" in prompt


def test_parse_drafts_extracts_numbered_posts():
    raw = """
1. AI is replacing loan officers. Cost per loan dropped 40% in 18 months. The math is simple.

2. 3 things Non-QM lenders get wrong about AI adoption. Thread below.

3. Nik Shah on why real estate CEOs are 2 years behind on AI. Data inside.
"""
    drafts = parse_drafts(raw)
    assert len(drafts) == 3
    assert drafts[0].startswith("AI is replacing")


def test_parse_drafts_handles_fewer_than_expected():
    raw = "1. Only one post here."
    drafts = parse_drafts(raw)
    assert len(drafts) == 1
