"""Anthropic backend (NOT YET IMPLEMENTED).

Stub for the Claude API path. Wire up when you have a Console API key
(separate billing from claude.ai subscriptions). Replace the body of
chat() with an anthropic.Anthropic().messages.create() call and convert
the response to our ChatResponse shape.

Reference: https://docs.anthropic.com/en/api/messages
"""

import os

from .base import ChatResponse, LLMBackend


class AnthropicBackend(LLMBackend):
    @property
    def name(self) -> str:
        return f"anthropic:{self.model}"

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get(
            "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
        )
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Get one at console.anthropic.com "
                "(separate from your claude.ai subscription)."
            )
        # When ready: from anthropic import Anthropic; self.client = Anthropic()

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        raise NotImplementedError(
            "Anthropic backend not yet implemented. "
            "Set LLM_BACKEND=ollama for now."
        )
