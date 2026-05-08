"""LLM backend abstraction.

Both Ollama and Anthropic implementations conform to the same chat() interface,
allowing the agent loop to be backend-agnostic. Switch backends via the
LLM_BACKEND env var.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""
    name: str
    arguments: dict[str, Any]
    call_id: str  # Used to match tool_use → tool_result in the conversation


@dataclass
class ChatResponse:
    """Backend-neutral response from a chat call."""
    text: str  # The model's text content (may be empty if only tool calls)
    tool_calls: list[ToolCall]  # Tool calls the model wants executed
    stop_reason: str  # "end_turn", "tool_use", "max_tokens", etc.
    raw: Any  # Backend-specific raw response for debugging


class LLMBackend(ABC):
    """Abstract interface every concrete backend must implement."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        """Send a chat completion request.

        Args:
            messages: Conversation history. Each message is
                {"role": "user"|"assistant"|"tool", "content": str | list, ...}.
                Tool results are passed as role="tool" with a tool_call_id.
            tools: Tool definitions in JSON Schema. The same schema works
                across backends because we'll normalize at the backend layer.
            system: System prompt (separate from messages for both backends).
            max_tokens: Cap on response length.

        Returns:
            ChatResponse with text and any tool calls the model wants.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend identifier for logs."""
        ...
