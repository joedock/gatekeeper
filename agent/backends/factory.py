"""Backend factory.

Reads LLM_BACKEND env var and returns the matching LLMBackend instance.
"""

import os

from .anthropic_backend import AnthropicBackend
from .base import LLMBackend
from .ollama_backend import OllamaBackend


def get_backend() -> LLMBackend:
    name = os.environ.get("LLM_BACKEND", "ollama").lower()
    if name == "ollama":
        return OllamaBackend()
    if name == "anthropic":
        return AnthropicBackend()
    raise ValueError(
        f"Unknown LLM_BACKEND={name!r}. Use 'ollama' or 'anthropic'."
    )
