from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import JobModel, JobStepModel

logger = get_logger(__name__)


class BudgetStatus(Enum):
    """Budget utilization status levels"""

    OK = "ok"
    WARNING_50 = "warning_50"
    WARNING_75 = "warning_75"
    CRITICAL_90 = "critical_90"
    EXCEEDED = "exceeded"


class LoopStatus(Enum):
    """Loop detection status levels"""

    OK = "ok"
    RETRY_WARNING = "retry_warning"  # 2 retries
    LOOP_DETECTED = "loop_detected"  # 3+ retries
    FILE_LOOP_DETECTED = "file_loop_detected"  # 5+ same file edits


@dataclass
class BudgetCheckResult:
    """Result of budget check"""

    status: BudgetStatus
    budget_used_pct: float
    remaining_usd: float
    should_warn: bool
    should_block: bool


@dataclass
class LoopCheckResult:
    """Result of loop detection check"""

    status: LoopStatus
    retry_count: int
    should_replan: bool
    reason: str


class BudgetGuard:
    """Guards against budget overruns with progressive warnings"""

    def __init__(self):
        self.settings = get_settings()

    def check_budget(self, job: JobModel, estimated_step_cost: float = 0.0) -> BudgetCheckResult:
        """
        Check budget status before executing a step.

        Args:
            job: JobModel to check budget for
            estimated_step_cost: Estimated cost of upcoming step

        Returns:
            BudgetCheckResult with current status and recommendations
        """
        current_cost = job.cost_usd or 0.0
        projected_cost = current_cost + estimated_step_cost
        budget = job.budget_usd

        budget_used_pct = projected_cost / budget if budget > 0 else 0.0
        remaining = budget - projected_cost

        # Determine status
        if budget_used_pct >= 1.0:
            status = BudgetStatus.EXCEEDED
        elif budget_used_pct >= self.settings.budget_hard_stop_threshold:
            status = BudgetStatus.CRITICAL_90
        elif budget_used_pct >= 0.75:
            status = BudgetStatus.WARNING_75
        elif budget_used_pct >= 0.5:
            status = BudgetStatus.WARNING_50
        else:
            status = BudgetStatus.OK

        # Check if should warn (not warned before at this threshold)
        should_warn = False
        warnings_sent = job.budget_warnings_sent or []

        if status == BudgetStatus.WARNING_50 and 0.5 not in warnings_sent:
            should_warn = True
        elif status == BudgetStatus.WARNING_75 and 0.75 not in warnings_sent:
            should_warn = True

        # Block if >= 90% or exceeded
        should_block = status in [BudgetStatus.CRITICAL_90, BudgetStatus.EXCEEDED]

        logger.info(
            "budget_check",
            job_id=job.id,
            status=status.value,
            budget_used_pct=f"{budget_used_pct:.1%}",
            remaining_usd=f"${remaining:.2f}",
            should_block=should_block,
        )

        return BudgetCheckResult(
            status=status,
            budget_used_pct=budget_used_pct,
            remaining_usd=remaining,
            should_warn=should_warn,
            should_block=should_block,
        )

    def record_warning(self, job: JobModel, threshold: float, session):
        """
        Record that budget warning was sent at threshold.

        Args:
            job: JobModel to update
            threshold: Warning threshold (0.5, 0.75, etc.)
            session: SQLAlchemy session
        """
        warnings = list(job.budget_warnings_sent or [])
        if threshold not in warnings:
            warnings.append(threshold)
            job.budget_warnings_sent = warnings
            session.add(job)
            logger.info("budget_warning_recorded", job_id=job.id, threshold=threshold)


class LoopDetector:
    """Detects infinite loops in job execution"""

    def __init__(self):
        self.settings = get_settings()

    def check_step_retry(self, job: JobModel, step: JobStepModel) -> LoopCheckResult:
        """
        Check if step is stuck in retry loop.

        Args:
            job: JobModel being executed
            step: JobStepModel that failed

        Returns:
            LoopCheckResult with retry count and replan recommendation
        """
        retry_count = step.retry_count or 0
        max_retries = self.settings.max_step_retries

        # Check if same step failed consecutively
        is_same_step = job.last_failed_step_id == step.id
        consecutive = job.consecutive_failures or 0 if is_same_step else 0

        if retry_count >= max_retries:
            status = LoopStatus.LOOP_DETECTED
            should_replan = True
            reason = f"Step '{step.name}' failed {retry_count} times"
        elif consecutive >= 2:
            status = LoopStatus.LOOP_DETECTED
            should_replan = True
            reason = f"{consecutive} consecutive failures on same step"
        elif retry_count >= 2:
            status = LoopStatus.RETRY_WARNING
            should_replan = False
            reason = f"Step retry count: {retry_count}/{max_retries}"
        else:
            status = LoopStatus.OK
            should_replan = False
            reason = "Normal execution"

        logger.info(
            "loop_check_step",
            job_id=job.id,
            step_id=step.id,
            status=status.value,
            retry_count=retry_count,
            consecutive_failures=consecutive,
            should_replan=should_replan,
        )

        return LoopCheckResult(
            status=status, retry_count=retry_count, should_replan=should_replan, reason=reason
        )

    def check_file_edit_loop(self, step: JobStepModel, filepath: str) -> bool:
        """
        Check if step is editing same file repeatedly.

        Args:
            step: JobStepModel to check
            filepath: File path being edited

        Returns:
            True if file edit loop detected
        """
        edit_history = step.edit_history or []
        max_edits = self.settings.max_file_edits_per_step

        # Count occurrences of filepath in recent edits
        recent_edits = edit_history[-max_edits:] if len(edit_history) > max_edits else edit_history
        same_file_count = recent_edits.count(filepath)

        is_loop = same_file_count >= max_edits

        if is_loop:
            logger.warning("file_edit_loop_detected", step_id=step.id, filepath=filepath, edit_count=same_file_count)

        return is_loop

    def record_file_edit(self, step: JobStepModel, filepath: str, session):
        """
        Record that step edited a file.

        Args:
            step: JobStepModel that edited file
            filepath: Path of edited file
            session: SQLAlchemy session
        """
        history = list(step.edit_history or [])
        history.append(filepath)
        # Keep last 20 edits
        step.edit_history = history[-20:]
        session.add(step)


class StallDetector:
    """Detects stalled jobs"""

    def __init__(self):
        self.settings = get_settings()

    def check_job_stalled(self, job: JobModel) -> bool:
        """
        Check if job has made no progress recently.

        Args:
            job: JobModel to check

        Returns:
            True if job is stalled
        """
        if not job.started_at:
            return False

        now = datetime.utcnow()

        # Check wall-clock timeout
        elapsed = now - job.started_at
        max_duration = timedelta(minutes=job.max_minutes)

        if elapsed > max_duration:
            logger.warning(
                "job_timeout",
                job_id=job.id,
                elapsed_minutes=elapsed.total_seconds() / 60,
                max_minutes=job.max_minutes,
            )
            return True

        # Check stall timeout (no progress in configured minutes)
        last_progress = job.last_progress_at or job.started_at
        time_since_progress = now - last_progress
        stall_timeout = timedelta(minutes=self.settings.stall_timeout_minutes)

        if time_since_progress > stall_timeout:
            logger.warning(
                "job_stalled",
                job_id=job.id,
                minutes_since_progress=time_since_progress.total_seconds() / 60,
            )
            return True

        return False

    def calculate_time_since_progress(self, job: JobModel) -> timedelta:
        """
        Calculate time since last progress.

        Args:
            job: JobModel to check

        Returns:
            Timedelta since last progress
        """
        if not job.last_progress_at:
            return timedelta(0)
        return datetime.utcnow() - job.last_progress_at

    def record_progress(self, job: JobModel, session):
        """
        Record that job made progress.

        Args:
            job: JobModel that made progress
            session: SQLAlchemy session
        """
        job.last_progress_at = datetime.utcnow()
        session.add(job)
        logger.debug("progress_recorded", job_id=job.id)
