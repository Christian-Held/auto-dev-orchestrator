from __future__ import annotations

import os
from typing import Any, Dict, List

import litellm

from app.core.config import get_settings
from app.core.logging import get_logger

from .provider import BaseLLMProvider, LLMResponse, estimate_tokens

logger = get_logger(__name__)


class LiteLLMProvider(BaseLLMProvider):
    """Unified provider for OpenAI, Anthropic, and other LLMs via LiteLLM"""

    name = "litellm"

    def __init__(self):
        settings = get_settings()
        # Configure API keys for LiteLLM
        if settings.openai_api_key:
            os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        if settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

        # Suppress LiteLLM verbose logging
        litellm.suppress_debug_info = True

    async def generate(
        self, *, model: str, messages: List[Dict[str, str]], **kwargs: Any
    ) -> LLMResponse:
        """
        Generate completion using LiteLLM's unified interface.

        Automatically handles API key selection based on model prefix:
        - gpt-* → OpenAI
        - claude-* → Anthropic
        """
        logger.info("litellm_call_start", model=model)

        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                **kwargs
            )

            text = response.choices[0].message.content
            tokens_in = response.usage.prompt_tokens if response.usage else estimate_tokens(str(messages))
            tokens_out = response.usage.completion_tokens if response.usage else estimate_tokens(text)

            logger.info(
                "litellm_call_complete",
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out
            )

            return LLMResponse(text=text, tokens_in=tokens_in, tokens_out=tokens_out)

        except Exception as exc:
            logger.error("litellm_call_failed", model=model, error=str(exc))
            raise

    def count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Estimate token count for messages"""
        combined = "\n".join(msg.get("content", "") for msg in messages)
        return estimate_tokens(combined)
