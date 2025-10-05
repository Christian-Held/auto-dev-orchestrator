from __future__ import annotations

import json
from typing import Dict, List

from app.agents.cto import CTOAgent
from app.agents.prompts import build_prompt, parse_agents_file
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db import repo
from app.db.engine import session_scope
from app.db.models import JobModel, JobStatus
from app.llm.litellm_provider import LiteLLMProvider
from app.llm.openai_provider import OpenAILLMProvider

logger = get_logger(__name__)


async def trigger_replanning(
    job_id: str, reason: str, failed_step_name: str | None = None
) -> List[Dict]:
    """
    Trigger replanning when job is stuck in a loop.

    Args:
        job_id: Job ID to replan
        reason: Why replanning was triggered (e.g., "Step failed 3 times")
        failed_step_name: Name of step that failed repeatedly

    Returns:
        New step plan from CTO

    Raises:
        RuntimeError: If max replanning attempts exceeded
        ValueError: If job not found
    """
    logger.info("replanning_triggered", job_id=job_id, reason=reason)

    with session_scope() as session:
        job = repo.get_job(session, job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Check if exceeded max replans
        replan_count = job.replan_count or 0
        settings = get_settings()
        max_replans = getattr(settings, "max_replan_attempts", 2)

        if replan_count >= max_replans:
            logger.error("max_replans_exceeded", job_id=job_id, replan_count=replan_count)
            repo.update_job_status(session, job, JobStatus.FAILED)
            job.last_action = f"Max replans ({max_replans}) exceeded: {reason}"
            session.add(job)
            session.commit()
            raise RuntimeError(f"Max replanning attempts ({max_replans}) exceeded")

        # Update job status
        repo.update_job_status(session, job, JobStatus.REPLANNING)
        job.replan_count = replan_count + 1
        job.consecutive_failures = 0  # Reset consecutive failures
        session.add(job)
        session.commit()

        task = job.task
        model_cto = job.model_cto or settings.model_cto

    # Build replanning context
    context_parts = [
        f"Original Task: {task}",
        f"Replanning Reason: {reason}",
    ]

    if failed_step_name:
        context_parts.append(f"Failed Step: {failed_step_name}")

    context_parts.extend(
        [
            "",
            "IMPORTANT: Create an alternative approach.",
            "The previous plan failed repeatedly, so try a DIFFERENT strategy:",
            "- Use different tools/libraries",
            "- Break down into smaller steps",
            "- Add validation/checks between steps",
            "- Consider alternative implementation approach",
        ]
    )

    replan_context = "\n".join(context_parts)

    # Call CTO agent
    spec = parse_agents_file()

    # Use appropriate provider
    if settings.llm_routing_enabled:
        provider = LiteLLMProvider()
    else:
        provider = OpenAILLMProvider()

    cto_agent = CTOAgent(provider, spec, model_cto, dry_run=settings.dry_run)

    section = spec.section("CTO-AI")
    prompt = build_prompt(section, replan_context)
    messages = [{"role": "system", "content": prompt}]

    new_plan, tokens_in, tokens_out = await cto_agent.create_plan(task, messages=messages)

    # Record replanning cost
    with session_scope() as session:
        job = repo.get_job(session, job_id)

        # Import here to avoid circular dependency
        from app.workers.job_worker import _calculate_cost

        cost = _calculate_cost(model_cto, tokens_in, tokens_out)
        repo.increment_costs(
            session,
            job,
            provider=provider.name,
            model=model_cto,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )
        repo.update_job_status(session, job, JobStatus.RUNNING)
        job.last_action = f"Replanned (attempt {job.replan_count}): {reason}"
        session.add(job)
        session.commit()

    logger.info("replanning_complete", job_id=job_id, new_plan_steps=len(new_plan), replan_attempt=replan_count + 1)

    return new_plan
