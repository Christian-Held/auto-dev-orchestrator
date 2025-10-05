from __future__ import annotations

import json
from typing import Dict

from app.core.logging import get_logger
from app.llm.provider import BaseLLMProvider

from .prompts import AgentsSpec, build_prompt

logger = get_logger(__name__)


class CoderAgent:
    def __init__(self, provider: BaseLLMProvider, spec: AgentsSpec, model: str, dry_run: bool = False):
        self.provider = provider
        self.spec = spec
        self.model = model
        self.dry_run = dry_run

    async def implement_step(
        self,
        task: str,
        step: Dict[str, str],
        *,
        messages: list[Dict[str, str]] | None = None,
        model: str | None = None
    ) -> Dict[str, str]:
        if messages is None:
            context = json.dumps({"task": task, "step": step}, ensure_ascii=False, indent=2)
            prompt = build_prompt(self.spec.section("CODER-AI"), context)
            messages = [{"role": "system", "content": prompt}]

        # Allow model override (for routing)
        selected_model = model or self.model

        logger.info("coder_step_request", model=selected_model, step=step.get("title"))
        response = await self.provider.generate(model=selected_model, messages=messages)
        if self.dry_run:
            logger.info("coder_step_dry_run")
            return {
                "diff": "",
                "summary": f"Dry run executed step {step.get('title')}",
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
            }
        return {
            "diff": response.text,
            "summary": f"Model output: {response.text[:120]}",
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
        }
