"""Ollama backend.

Wraps ollama-python's chat API and converts its tool-call format into
our backend-neutral ToolCall/ChatResponse types.
"""

import os
import uuid

import ollama

from .base import ChatResponse, LLMBackend, ToolCall


class OllamaBackend(LLMBackend):
    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
    ):
        self.model = model or os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
        host = host or os.environ.get("OLLAMA_HOST", "http://192.168.68.71:11434")
        self.client = ollama.Client(host=host)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        # Ollama wants the system prompt as a leading system message.
        ollama_messages: list[dict] = []
        if system:
            ollama_messages.append({"role": "system", "content": system})
        ollama_messages.extend(messages)

        kwargs = {
            "model": self.model,
            "messages": ollama_messages,
            "options": {"num_predict": max_tokens},
        }
        if tools:
            kwargs["tools"] = tools

        raw = self.client.chat(**kwargs)
        msg = raw["message"]

        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc["function"]
            tool_calls.append(
                ToolCall(
                    name=fn["name"],
                    arguments=fn.get("arguments", {}) or {},
                    # Ollama doesn't return call IDs; we synthesize one so the
                    # downstream agent loop can match results to calls.
                    call_id=str(uuid.uuid4()),
                )
            )

        stop_reason = "tool_use" if tool_calls else "end_turn"

        return ChatResponse(
            text=msg.get("content", "") or "",
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw=raw,
        )
