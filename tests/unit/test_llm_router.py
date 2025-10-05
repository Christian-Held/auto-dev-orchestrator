from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.db.models import JobModel
from app.llm.router import LLMRouter, RoutingDecision


@pytest.fixture
def router():
    """Create LLMRouter instance"""
    return LLMRouter()


@pytest.fixture
def job_with_budget():
    """Create JobModel with available budget"""
    return JobModel(
        id="test-job-1",
        task="Test task",
        repo_owner="test-owner",
        repo_name="test-repo",
        branch_base="main",
        budget_usd=10.0,
        cost_usd=0.0,
        max_requests=100,
        max_minutes=60,
    )


@pytest.fixture
def job_low_budget():
    """Create JobModel with low remaining budget"""
    return JobModel(
        id="test-job-2",
        task="Test task",
        repo_owner="test-owner",
        repo_name="test-repo",
        branch_base="main",
        budget_usd=2.0,
        cost_usd=1.8,  # Only $0.20 remaining
        max_requests=100,
        max_minutes=60,
    )


def test_routing_disabled_uses_fallback(router, job_with_budget):
    """When routing disabled, should use legacy model_coder"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = False

    try:
        step = {"title": "Simple task", "complexity": 2}
        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=500,
            estimated_tokens_out=500,
        )

        assert decision.reason == "routing_disabled"
        assert decision.complexity_score == 5  # Default when disabled
    finally:
        settings.llm_routing_enabled = original_routing


def test_simple_task_routes_to_gpt35(router, job_with_budget):
    """Simple tasks (complexity 1-3) should use GPT-3.5"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        step = {"title": "Write boilerplate tests", "complexity": 2}
        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=500,
            estimated_tokens_out=500,
        )

        assert decision.model == settings.model_simple
        assert "simple" in decision.reason
        assert decision.complexity_score == 2
    finally:
        settings.llm_routing_enabled = original_routing


def test_medium_task_routes_to_sonnet(router, job_with_budget):
    """Medium tasks (complexity 4-7) should use Claude Sonnet"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        step = {"title": "Implement feature", "complexity": 5}
        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=1000,
            estimated_tokens_out=1000,
        )

        assert decision.model == settings.model_medium
        assert "medium" in decision.reason
        assert decision.complexity_score == 5
    finally:
        settings.llm_routing_enabled = original_routing


def test_complex_task_routes_to_opus(router, job_with_budget):
    """Complex tasks (complexity 8-10) should use Claude Opus"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        step = {"title": "Redesign database architecture", "complexity": 9}
        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=2000,
            estimated_tokens_out=3000,
        )

        assert decision.model == settings.model_complex
        assert "complex" in decision.reason
        assert decision.complexity_score == 9
    finally:
        settings.llm_routing_enabled = original_routing


def test_budget_constraint_downgrades_model(router, job_low_budget):
    """Low budget should force downgrade to cheaper model"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        # Complex task that would normally use Opus
        step = {"title": "Complex refactoring", "complexity": 8}
        decision = router.select_model(
            step,
            budget_usd=job_low_budget.budget_usd,
            cost_usd=job_low_budget.cost_usd,
            estimated_tokens_in=1000,
            estimated_tokens_out=1000,
        )

        # Should downgrade due to budget
        assert decision.model != settings.model_complex
        assert "budget_downgrade" in decision.reason
    finally:
        settings.llm_routing_enabled = original_routing


def test_large_token_count_upgrades_model(router, job_with_budget):
    """Large token count should upgrade from simple to medium"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        # Simple task but with large token count
        step = {"title": "Write tests", "complexity": 2}
        large_tokens = settings.routing_token_threshold_large + 1000

        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=large_tokens,
            estimated_tokens_out=large_tokens,
        )

        # Should upgrade from simple to medium
        assert decision.model == settings.model_medium
        assert "token_upgrade" in decision.reason
    finally:
        settings.llm_routing_enabled = original_routing


def test_auto_detect_complexity_from_keywords(router, job_with_budget):
    """Should auto-detect complexity from keywords when not provided"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        # Step without explicit complexity field
        step = {"title": "Write unit tests", "rationale": "Add test coverage"}
        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=500,
            estimated_tokens_out=500,
        )

        # Should detect "test" keyword → complexity 1
        assert decision.complexity_score == 1
        assert decision.model == settings.model_simple
    finally:
        settings.llm_routing_enabled = original_routing


def test_auto_detect_architecture_task(router, job_with_budget):
    """Should auto-detect high complexity for architecture tasks"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        step = {
            "title": "Design distributed system architecture",
            "rationale": "Scalability requirements",
        }
        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=2000,
            estimated_tokens_out=2000,
        )

        # Should detect "architecture" keyword → complexity 7
        assert decision.complexity_score == 7
        assert decision.model == settings.model_medium or decision.model == settings.model_complex
    finally:
        settings.llm_routing_enabled = original_routing


def test_estimate_cost_calculates_correctly(router):
    """Should correctly estimate cost from pricing table"""
    settings = get_settings()

    # GPT-3.5-turbo: input=0.0005, output=0.0015
    cost = router._estimate_cost("gpt-3.5-turbo", 1000, 1000)
    expected = (1000 / 1000) * 0.0005 + (1000 / 1000) * 0.0015
    assert abs(cost - expected) < 0.0001  # Float comparison


def test_complexity_clamped_to_valid_range(router, job_with_budget):
    """Complexity should be clamped to 1-10 range"""
    settings = get_settings()
    original_routing = settings.llm_routing_enabled
    settings.llm_routing_enabled = True

    try:
        # Invalid complexity > 10
        step = {"title": "Test", "complexity": 99}
        decision = router.select_model(
            step,
            budget_usd=job_with_budget.budget_usd,
            cost_usd=job_with_budget.cost_usd,
            estimated_tokens_in=500,
            estimated_tokens_out=500,
        )

        # Should clamp to 10
        assert decision.complexity_score == 10
    finally:
        settings.llm_routing_enabled = original_routing
