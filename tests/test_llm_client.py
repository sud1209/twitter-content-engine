import pytest
from unittest.mock import patch, MagicMock


def test_complete_routes_claude_to_anthropic(monkeypatch):
    """Claude model prefix routes to Anthropic SDK."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="anthropic response")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("scripts.llm_client.Anthropic", return_value=mock_client):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        from scripts.llm_client import complete
        result = complete(
            model="claude-haiku-4-5-20251001",
            system="You are a helper.",
            user="Say hello.",
        )

    assert result == "anthropic response"
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
    assert call_kwargs["system"] == "You are a helper."


def test_complete_routes_gpt_to_openai(monkeypatch):
    """Non-claude model prefix routes to OpenAI SDK."""
    mock_choice = MagicMock()
    mock_choice.message.content = "openai response"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("scripts.llm_client.OpenAI", return_value=mock_client):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from scripts.llm_client import complete
        result = complete(
            model="gpt-4o-mini",
            system="You are a helper.",
            user="Say hello.",
        )

    assert result == "openai response"
    mock_client.chat.completions.create.assert_called_once()


def test_complete_returns_string():
    """complete() always returns a plain string."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="hello")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("scripts.llm_client.Anthropic", return_value=mock_client):
        from scripts.llm_client import complete
        result = complete("claude-haiku-4-5-20251001", "sys", "usr")

    assert isinstance(result, str)


def test_complete_passes_max_tokens():
    """max_tokens parameter is forwarded to the API call."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("scripts.llm_client.Anthropic", return_value=mock_client):
        from scripts.llm_client import complete
        complete("claude-haiku-4-5-20251001", "sys", "usr", max_tokens=500)

    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["max_tokens"] == 500
