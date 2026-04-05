"""
LLM Client — provider-agnostic completion wrapper.
Routes to Anthropic or OpenAI based on model name prefix.
Usage: from scripts.llm_client import complete
"""

import os
from anthropic import Anthropic
from openai import OpenAI


def complete(model: str, system: str, user: str, max_tokens: int = 2000) -> str:
    """
    Call the LLM and return the response text.

    Routes by model name:
    - "claude-*" → Anthropic Messages API (reads ANTHROPIC_API_KEY)
    - anything else → OpenAI Chat Completions API (reads OPENAI_API_KEY)

    Args:
        model: Model identifier string (e.g. "claude-haiku-4-5-20251001")
        system: System prompt string
        user: User message string
        max_tokens: Maximum tokens in response

    Returns:
        Response text as a plain string
    """
    if model.startswith("claude"):
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
