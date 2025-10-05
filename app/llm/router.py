from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.pricing import get_pricing_table
from app.db.models import JobModel
from app.llm.provider import estimate_tokens

logger = get_logger(__name__)


@dataclass
class RoutingDecision:
    """Decision made by the router for model selection"""

    model: str
    reason: str
    complexity_score: int
    estimated_cost: float


class LLMRouter:
    """
    Intelligent routing between LLM models based on:
    1. Task complexity (from step["complexity"] or auto-detected)
    2. Estimated token count
    3. Remaining budget in job
    """

    # Keywords for automatic complexity detection
    COMPLEXITY_KEYWORDS = {
        1: ["test", "boilerplate", "config", "typing", "import", "format", "lint"],
        2: ["refactor", "rename", "extract", "cleanup", "documentation", "comment"],
        3: ["endpoint", "route", "validation", "model", "schema", "crud"],
        4: ["feature", "component", "service", "integration"],
        5: ["business logic", "workflow", "state machine", "orchestration"],
        6: ["migration", "database", "optimization", "caching"],
        7: ["architecture", "design pattern", "scalability", "distributed"],
        8: ["security", "authentication", "authorization", "encryption"],
        9: ["performance", "profiling", "debugging", "race condition"],
        10: ["critical bug", "data loss", "system failure", "incident"],
    }

    def __init__(self):
        self.settings = get_settings()
        self.pricing = get_pricing_table()

    def select_model(
        self,
        step: Dict[str, Any],
        job: JobModel,
        estimated_tokens_in: int = 0,
        estimated_tokens_out: int = 0,
    ) -> RoutingDecision:
        """
        Route to optimal model based on complexity, tokens, and budget.

        Args:
            step: StepPlan dict with optional "complexity" field
            job: JobModel with budget tracking
            estimated_tokens_in: Estimated input tokens
            estimated_tokens_out: Estimated output tokens

        Returns:
            RoutingDecision with selected model and reasoning
        """
        if not self.settings.llm_routing_enabled:
            # Fallback to legacy behavior
            model = job.model_coder or self.settings.model_coder
            return RoutingDecision(
                model=model, reason="routing_disabled", complexity_score=5, estimated_cost=0.0
            )

        # 1. Determine complexity (from step or auto-detect)
        complexity = self._get_complexity(step)

        # 2. Select base model tier from complexity
        remaining_budget = job.budget_usd - (job.cost_usd or 0.0)
        candidate_model, reason = self._select_by_complexity(complexity)

        # 3. Check if large token count requires upgrade
        total_tokens = estimated_tokens_in + estimated_tokens_out
        if total_tokens > self.settings.routing_token_threshold_large:
            if candidate_model == self.settings.model_simple:
                candidate_model = self.settings.model_medium
                reason = f"token_upgrade_{total_tokens}_tokens"

        # 4. Budget constraint: downgrade if necessary
        estimated_cost = self._estimate_cost(candidate_model, estimated_tokens_in, estimated_tokens_out)

        # Allow using max 50% of remaining budget per step
        budget_per_step = remaining_budget * 0.5

        if estimated_cost > budget_per_step and budget_per_step > 0:
            # Downgrade to cheaper model
            if candidate_model == self.settings.model_complex:
                candidate_model = self.settings.model_medium
                reason = "budget_downgrade_from_complex"
                estimated_cost = self._estimate_cost(
                    candidate_model, estimated_tokens_in, estimated_tokens_out
                )

            if estimated_cost > budget_per_step and candidate_model == self.settings.model_medium:
                candidate_model = self.settings.model_simple
                reason = "budget_downgrade_from_medium"
                estimated_cost = self._estimate_cost(
                    candidate_model, estimated_tokens_in, estimated_tokens_out
                )

        logger.info(
            "llm_routing_decision",
            model=candidate_model,
            complexity=complexity,
            reason=reason,
            estimated_cost=estimated_cost,
            remaining_budget=remaining_budget,
            tokens_in=estimated_tokens_in,
            tokens_out=estimated_tokens_out,
        )

        return RoutingDecision(
            model=candidate_model,
            reason=reason,
            complexity_score=complexity,
            estimated_cost=estimated_cost,
        )

    def _get_complexity(self, step: Dict[str, Any]) -> int:
        """
        Get complexity score from step or auto-detect from title/rationale.

        Returns:
            Complexity score 1-10
        """
        # Check if complexity explicitly provided
        if "complexity" in step and isinstance(step["complexity"], int):
            return max(1, min(10, step["complexity"]))  # Clamp to 1-10

        # Auto-detect from keywords
        text = " ".join(
            [
                step.get("title", ""),
                step.get("rationale", ""),
                step.get("acceptance", ""),
            ]
        ).lower()

        detected_complexity = 5  # Default medium complexity
        max_score = 0

        for complexity_level, keywords in self.COMPLEXITY_KEYWORDS.items():
            for keyword in keywords:
                if re.search(r"\b" + re.escape(keyword) + r"\b", text):
                    if complexity_level > max_score:
                        max_score = complexity_level
                        detected_complexity = complexity_level

        logger.debug(
            "complexity_auto_detected", step_title=step.get("title"), detected=detected_complexity
        )

        return detected_complexity

    def _select_by_complexity(self, complexity: int) -> tuple[str, str]:
        """
        Select model tier based on complexity score.

        Returns:
            Tuple of (model_name, reason)
        """
        if complexity <= self.settings.routing_complexity_threshold_medium:
            return self.settings.model_simple, f"simple_task_complexity_{complexity}"
        elif complexity <= self.settings.routing_complexity_threshold_complex:
            return self.settings.model_medium, f"medium_task_complexity_{complexity}"
        else:
            return self.settings.model_complex, f"complex_task_complexity_{complexity}"

    def _estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """
        Estimate cost for a model call.

        Returns:
            Estimated cost in USD
        """
        try:
            pricing = self.pricing.get(model)
            return (tokens_in / 1000) * pricing.input + (tokens_out / 1000) * pricing.output
        except KeyError:
            logger.warning("pricing_not_found", model=model)
            # Fallback to default pricing
            pricing = self.pricing.get("default")
            return (tokens_in / 1000) * pricing.input + (tokens_out / 1000) * pricing.output
