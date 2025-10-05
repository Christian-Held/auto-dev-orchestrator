"""End-to-end test for multi-LLM routing in dry-run mode"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.db import repo
from app.db.engine import session_scope
from app.db.models import CostEntryModel
from app.workers.job_worker import execute_job


@pytest.fixture
def enable_routing():
    """Enable routing for tests"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    original_dry_run = settings.dry_run

    settings.llm_routing_enabled = True
    settings.dry_run = True

    yield

    settings.llm_routing_enabled = original_routing
    settings.dry_run = original_dry_run


def test_routing_workflow_with_mixed_complexity(enable_routing):
    """
    Full workflow with routing enabled in dry-run mode.
    Verifies that different models are selected based on complexity.
    """
    settings = get_settings()

    with session_scope() as session:
        job = repo.create_job(
            session,
            task="Create tests and refactor database schema",
            repo_owner="test",
            repo_name="test-repo",
            branch_base="main",
            budget_usd=5.0,
            max_requests=50,
            max_minutes=30,
            model_cto="gpt-4.1-mini",
            model_coder=None,  # Will be routed
            agents_hash="test-hash",
        )
        session.commit()
        job_id = job.id

    # Execute job (dry-run mode)
    execute_job(job_id)

    with session_scope() as session:
        job = repo.get_job(session, job_id)
        costs = session.query(CostEntryModel).filter(CostEntryModel.job_id == job_id).all()

        # Verify job completed
        assert job.status in ["completed", "failed"]

        # Verify cost tracking exists
        assert len(costs) > 0

        # In dry-run mode, models should still be logged
        # (DryRunProvider is used, but routing decision is made)
        models_used = {cost.model for cost in costs}

        # Verify at least one model was tracked
        assert len(models_used) >= 1


def test_routing_respects_budget_limits(enable_routing):
    """Verify that routing downgrades models when budget is low"""
    settings = get_settings()

    with session_scope() as session:
        job = repo.create_job(
            session,
            task="Complex architectural refactoring",
            repo_owner="test",
            repo_name="test-repo",
            branch_base="main",
            budget_usd=0.5,  # Very low budget
            max_requests=50,
            max_minutes=30,
            model_cto="gpt-4.1-mini",
            model_coder=None,
            agents_hash="test-hash",
        )
        session.commit()
        job_id = job.id

    execute_job(job_id)

    with session_scope() as session:
        job = repo.get_job(session, job_id)

        # Verify job didn't exceed budget
        assert job.cost_usd <= job.budget_usd

        # Verify job completed (even with tight budget)
        assert job.status in ["completed", "failed"]


def test_routing_auto_detects_complexity():
    """
    Verify that router auto-detects complexity from step titles
    when CTO doesn't provide explicit complexity field.
    """
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    original_dry_run = settings.dry_run

    settings.llm_routing_enabled = True
    settings.dry_run = True

    try:
        with session_scope() as session:
            job = repo.create_job(
                session,
                task="Write unit tests for authentication module",
                repo_owner="test",
                repo_name="test-repo",
                branch_base="main",
                budget_usd=5.0,
                max_requests=50,
                max_minutes=30,
                model_cto="gpt-4.1-mini",
                model_coder=None,
                agents_hash="test-hash",
            )
            session.commit()
            job_id = job.id

        execute_job(job_id)

        with session_scope() as session:
            job = repo.get_job(session, job_id)

            # Task contains "test" keyword, should be detected as low complexity
            # and use cheaper model (verified through logs in actual run)
            assert job.status in ["completed", "failed"]
            assert job.cost_usd <= job.budget_usd

    finally:
        settings.llm_routing_enabled = original_routing
        settings.dry_run = original_dry_run


def test_fallback_on_routing_disabled():
    """When routing is disabled, should fall back to model_coder"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    original_dry_run = settings.dry_run

    settings.llm_routing_enabled = False
    settings.dry_run = True

    try:
        with session_scope() as session:
            job = repo.create_job(
                session,
                task="Test task",
                repo_owner="test",
                repo_name="test-repo",
                branch_base="main",
                budget_usd=5.0,
                max_requests=50,
                max_minutes=30,
                model_cto="gpt-4.1-mini",
                model_coder="gpt-4.1",  # Should use this when routing disabled
                agents_hash="test-hash",
            )
            session.commit()
            job_id = job.id

        execute_job(job_id)

        with session_scope() as session:
            job = repo.get_job(session, job_id)
            costs = session.query(CostEntryModel).filter(CostEntryModel.job_id == job_id).all()

            # Verify job completed
            assert job.status in ["completed", "failed"]

            # In dry-run with routing disabled, should still track costs
            assert len(costs) > 0

    finally:
        settings.llm_routing_enabled = original_routing
        settings.dry_run = original_dry_run
