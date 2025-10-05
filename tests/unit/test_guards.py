from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from app.core.guards import BudgetGuard, BudgetStatus, LoopDetector, LoopStatus, StallDetector
from app.db.models import JobModel, JobStepModel


class TestBudgetGuard:
    """Tests for BudgetGuard"""

    def test_budget_ok_at_25_percent(self):
        """Budget check should be OK at 25% usage"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.cost_usd = 1.25
        job.budget_usd = 5.0
        job.budget_warnings_sent = []

        result = guard.check_budget(job)

        assert result.status == BudgetStatus.OK
        assert result.budget_used_pct == 0.25
        assert result.remaining_usd == 3.75
        assert not result.should_warn
        assert not result.should_block

    def test_budget_warns_at_50_percent(self):
        """Budget check should warn at 50% usage (first time)"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.cost_usd = 2.5
        job.budget_usd = 5.0
        job.budget_warnings_sent = []

        result = guard.check_budget(job)

        assert result.status == BudgetStatus.WARNING_50
        assert result.budget_used_pct == 0.5
        assert result.should_warn
        assert not result.should_block

    def test_budget_warns_at_75_percent(self):
        """Budget check should warn at 75% usage (first time)"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.cost_usd = 3.75
        job.budget_usd = 5.0
        job.budget_warnings_sent = [0.5]

        result = guard.check_budget(job)

        assert result.status == BudgetStatus.WARNING_75
        assert result.budget_used_pct == 0.75
        assert result.should_warn
        assert not result.should_block

    def test_budget_does_not_warn_again_at_same_threshold(self):
        """Budget check should not warn again if already warned at threshold"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.cost_usd = 2.5
        job.budget_usd = 5.0
        job.budget_warnings_sent = [0.5]

        result = guard.check_budget(job)

        assert result.status == BudgetStatus.WARNING_50
        assert not result.should_warn

    def test_budget_blocks_at_90_percent(self):
        """Budget check should block at 90% usage (hard stop threshold)"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.cost_usd = 4.5
        job.budget_usd = 5.0
        job.budget_warnings_sent = [0.5, 0.75]

        result = guard.check_budget(job)

        assert result.status == BudgetStatus.CRITICAL_90
        assert result.budget_used_pct == 0.9
        assert result.should_block

    def test_budget_blocks_when_exceeded(self):
        """Budget check should block when budget exceeded"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.cost_usd = 5.5
        job.budget_usd = 5.0
        job.budget_warnings_sent = [0.5, 0.75]

        result = guard.check_budget(job)

        assert result.status == BudgetStatus.EXCEEDED
        assert result.budget_used_pct == 1.1
        assert result.should_block

    def test_budget_with_estimated_step_cost(self):
        """Budget check should include estimated step cost in projection"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.cost_usd = 2.0
        job.budget_usd = 5.0
        job.budget_warnings_sent = []

        # Adding 0.5 step cost should push to 50% threshold
        result = guard.check_budget(job, estimated_step_cost=0.5)

        assert result.status == BudgetStatus.WARNING_50
        assert result.budget_used_pct == 0.5
        assert result.should_warn

    def test_record_warning(self):
        """Should record warning threshold in job"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.budget_warnings_sent = []
        session = Mock()

        guard.record_warning(job, 0.5, session)

        assert 0.5 in job.budget_warnings_sent
        session.add.assert_called_once_with(job)

    def test_record_warning_does_not_duplicate(self):
        """Should not duplicate warning threshold"""
        guard = BudgetGuard()
        job = Mock(spec=JobModel)
        job.budget_warnings_sent = [0.5]
        session = Mock()

        guard.record_warning(job, 0.5, session)

        assert job.budget_warnings_sent.count(0.5) == 1


class TestLoopDetector:
    """Tests for LoopDetector"""

    def test_step_retry_ok_at_zero_retries(self):
        """Loop check should be OK with 0 retries"""
        detector = LoopDetector()
        job = Mock(spec=JobModel)
        job.last_failed_step_id = None
        job.consecutive_failures = 0

        step = Mock(spec=JobStepModel)
        step.id = "step-1"
        step.name = "Test Step"
        step.retry_count = 0

        result = detector.check_step_retry(job, step)

        assert result.status == LoopStatus.OK
        assert result.retry_count == 0
        assert not result.should_replan

    def test_step_retry_warning_at_2_retries(self):
        """Loop check should warn at 2 retries"""
        detector = LoopDetector()
        job = Mock(spec=JobModel)
        job.last_failed_step_id = None
        job.consecutive_failures = 0

        step = Mock(spec=JobStepModel)
        step.id = "step-1"
        step.name = "Test Step"
        step.retry_count = 2

        result = detector.check_step_retry(job, step)

        assert result.status == LoopStatus.RETRY_WARNING
        assert result.retry_count == 2
        assert not result.should_replan

    def test_step_retry_loop_detected_at_3_retries(self):
        """Loop check should detect loop at 3 retries"""
        detector = LoopDetector()
        job = Mock(spec=JobModel)
        job.last_failed_step_id = None
        job.consecutive_failures = 0

        step = Mock(spec=JobStepModel)
        step.id = "step-1"
        step.name = "Test Step"
        step.retry_count = 3

        result = detector.check_step_retry(job, step)

        assert result.status == LoopStatus.LOOP_DETECTED
        assert result.retry_count == 3
        assert result.should_replan
        assert "failed 3 times" in result.reason

    def test_consecutive_failures_trigger_replan(self):
        """Loop check should detect loop with 2 consecutive failures on same step"""
        detector = LoopDetector()
        job = Mock(spec=JobModel)
        job.last_failed_step_id = "step-1"
        job.consecutive_failures = 2

        step = Mock(spec=JobStepModel)
        step.id = "step-1"
        step.name = "Test Step"
        step.retry_count = 1

        result = detector.check_step_retry(job, step)

        assert result.status == LoopStatus.LOOP_DETECTED
        assert result.should_replan
        assert "consecutive failures" in result.reason

    def test_file_edit_loop_not_detected_under_threshold(self):
        """File edit loop should not be detected below threshold"""
        detector = LoopDetector()
        step = Mock(spec=JobStepModel)
        step.id = "step-1"
        step.edit_history = ["file1.py", "file2.py", "file1.py", "file1.py"]

        is_loop = detector.check_file_edit_loop(step, "file1.py")

        assert not is_loop

    def test_file_edit_loop_detected_at_5_edits(self):
        """File edit loop should be detected at 5 edits of same file"""
        detector = LoopDetector()
        step = Mock(spec=JobStepModel)
        step.id = "step-1"
        step.edit_history = ["file1.py", "file1.py", "file1.py", "file1.py", "file1.py"]

        is_loop = detector.check_file_edit_loop(step, "file1.py")

        assert is_loop

    def test_file_edit_loop_only_checks_recent_edits(self):
        """File edit loop should only check recent edits (not all history)"""
        detector = LoopDetector()
        step = Mock(spec=JobStepModel)
        step.id = "step-1"
        # 10 old edits of file1, then 4 recent edits of file2
        step.edit_history = ["file1.py"] * 10 + ["file2.py"] * 4

        is_loop = detector.check_file_edit_loop(step, "file2.py")

        assert not is_loop  # Only 4 in recent window

    def test_record_file_edit(self):
        """Should record file edit in step history"""
        detector = LoopDetector()
        step = Mock(spec=JobStepModel)
        step.edit_history = ["file1.py"]
        session = Mock()

        detector.record_file_edit(step, "file2.py", session)

        assert step.edit_history == ["file1.py", "file2.py"]
        session.add.assert_called_once_with(step)

    def test_record_file_edit_keeps_last_20(self):
        """Should keep only last 20 file edits"""
        detector = LoopDetector()
        step = Mock(spec=JobStepModel)
        step.edit_history = [f"file{i}.py" for i in range(20)]
        session = Mock()

        detector.record_file_edit(step, "new_file.py", session)

        assert len(step.edit_history) == 20
        assert step.edit_history[-1] == "new_file.py"
        assert step.edit_history[0] == "file1.py"  # file0.py was dropped


class TestStallDetector:
    """Tests for StallDetector"""

    def test_job_not_stalled_when_just_started(self):
        """Job should not be stalled when just started"""
        detector = StallDetector()
        job = Mock(spec=JobModel)
        job.started_at = datetime.utcnow()
        job.max_minutes = 60
        job.last_progress_at = None

        is_stalled = detector.check_job_stalled(job)

        assert not is_stalled

    def test_job_stalled_when_wall_clock_exceeded(self):
        """Job should be stalled when wall-clock time exceeded"""
        detector = StallDetector()
        job = Mock(spec=JobModel)
        job.started_at = datetime.utcnow() - timedelta(minutes=120)
        job.max_minutes = 60
        job.last_progress_at = None

        is_stalled = detector.check_job_stalled(job)

        assert is_stalled

    def test_job_stalled_when_no_progress_for_30_minutes(self):
        """Job should be stalled when no progress for 30 minutes"""
        detector = StallDetector()
        job = Mock(spec=JobModel)
        job.started_at = datetime.utcnow() - timedelta(minutes=10)
        job.max_minutes = 60
        job.last_progress_at = datetime.utcnow() - timedelta(minutes=31)

        is_stalled = detector.check_job_stalled(job)

        assert is_stalled

    def test_job_not_stalled_when_recent_progress(self):
        """Job should not be stalled when progress made recently"""
        detector = StallDetector()
        job = Mock(spec=JobModel)
        job.started_at = datetime.utcnow() - timedelta(minutes=40)
        job.max_minutes = 60
        job.last_progress_at = datetime.utcnow() - timedelta(minutes=5)

        is_stalled = detector.check_job_stalled(job)

        assert not is_stalled

    def test_calculate_time_since_progress_with_progress(self):
        """Should calculate time since last progress correctly"""
        detector = StallDetector()
        job = Mock(spec=JobModel)
        job.last_progress_at = datetime.utcnow() - timedelta(minutes=15)

        time_since = detector.calculate_time_since_progress(job)

        assert time_since.total_seconds() / 60 >= 14.9  # ~15 minutes (allow small drift)
        assert time_since.total_seconds() / 60 <= 15.1

    def test_calculate_time_since_progress_without_progress(self):
        """Should return 0 when no progress recorded"""
        detector = StallDetector()
        job = Mock(spec=JobModel)
        job.last_progress_at = None

        time_since = detector.calculate_time_since_progress(job)

        assert time_since.total_seconds() == 0

    def test_record_progress(self):
        """Should record progress timestamp"""
        detector = StallDetector()
        job = Mock(spec=JobModel)
        session = Mock()

        before = datetime.utcnow()
        detector.record_progress(job, session)
        after = datetime.utcnow()

        assert job.last_progress_at >= before
        assert job.last_progress_at <= after
        session.add.assert_called_once_with(job)
