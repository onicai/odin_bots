"""AI backend abstraction for persona chat.

Phase 1: Claude only, text-only chat (no tool use yet).
"""

import os
from abc import ABC, abstractmethod

from odin_bots.persona import Persona


class APIKeyMissingError(Exception):
    """Raised when a required API key is not configured."""


class AIBackend(ABC):
    """Abstract base class for AI chat backends."""

    @abstractmethod
    def chat(self, messages: list[dict], system: str) -> str:
        """Send messages to AI and return response text.

        Args:
            messages: Conversation history as list of {"role": ..., "content": ...}.
            system: System prompt text.

        Returns:
            Assistant response text.
        """


class ClaudeBackend(AIBackend):
    """Claude API backend via anthropic SDK."""

    def __init__(self, model: str, api_key: str | None = None):
        import anthropic

        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or key == "your-api-key-here":
            raise APIKeyMissingError(
                "ANTHROPIC_API_KEY is not set.\n"
                "Get your API key at: https://console.anthropic.com/settings/keys\n"
                "Then add it to .env:\n"
                "  ANTHROPIC_API_KEY=sk-ant-..."
            )
        self.client = anthropic.Anthropic(api_key=key)
        self.model = model

    def chat(self, messages: list[dict], system: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        return response.content[0].text


def create_backend(persona: Persona) -> AIBackend:
    """Create an AI backend from persona config.

    Args:
        persona: Loaded persona with ai_backend and ai_model fields.

    Returns:
        Configured AIBackend instance.

    Raises:
        ValueError: If the AI backend is not supported.
    """
    if persona.ai_backend == "claude":
        return ClaudeBackend(model=persona.ai_model)
    raise ValueError(
        f"Unsupported AI backend: '{persona.ai_backend}'. "
        f"Currently supported: claude"
    )
