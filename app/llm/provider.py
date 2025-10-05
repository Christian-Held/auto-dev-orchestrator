from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


class LLMResponse:
    def __init__(self, text: str, tokens_in: int = 0, tokens_out: int = 0):
        self.text = text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out


@dataclass
class ModelCapability:
    """Model capability metadata for routing decisions"""
    name: str
    complexity_tier: str  # "simple" | "medium" | "complex"
    cost_per_1m_input: float  # USD per 1M tokens
    cost_per_1m_output: float  # USD per 1M tokens
    max_context_tokens: int = 128000  # Default context window


class BaseLLMProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, *, model: str, messages: List[Dict[str, str]], **kwargs: Any) -> LLMResponse:
        ...

    def count_tokens(self, messages: List[Dict[str, str]]) -> int:
        combined = "\n".join(msg.get("content", "") for msg in messages)
        return estimate_tokens(combined)


def estimate_tokens(text: str) -> int:
    # Cheap heuristic: 1 token ≈ 4 chars
    return max(1, len(text) // 4)


class DryRunLLMProvider(BaseLLMProvider):
    name = "dry-run"

    async def generate(self, *, model: str, messages: List[Dict[str, str]], **kwargs: Any) -> LLMResponse:
        combined = "\n".join(msg.get("content", "") for msg in messages)
        response = f"DRY-RUN ({model}) RESPONSE: {combined[:200]}"
        tokens = estimate_tokens(combined)
        return LLMResponse(text=response, tokens_in=tokens, tokens_out=tokens // 2)

    def count_tokens(self, messages: List[Dict[str, str]]) -> int:  # pragma: no cover - trivial
        return super().count_tokens(messages)
