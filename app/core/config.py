from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_port: int = Field(3000, alias="APP_PORT")
    redis_url: str = Field(..., alias="REDIS_URL")
    db_path: Path = Field(Path("./data/orchestrator.db"), alias="DB_PATH")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    model_cto: str = Field("gpt-4.1-mini", alias="MODEL_CTO")
    model_coder: str = Field("gpt-4.1", alias="MODEL_CODER")
    github_token: str = Field("", alias="GITHUB_TOKEN")
    github_owner: str = Field("", alias="GITHUB_OWNER")
    github_repo: str = Field("", alias="GITHUB_REPO")
    budget_usd_max: float = Field(5.0, alias="BUDGET_USD_MAX")
    max_requests: int = Field(300, alias="MAX_REQUESTS")
    max_wallclock_minutes: int = Field(720, alias="MAX_WALLCLOCK_MINUTES")
    allow_direct_push: bool = Field(False, alias="ALLOW_DIRECT_PUSH")
    allow_unsafe_automerge: bool = Field(False, alias="ALLOW_UNSAFE_AUTOMERGE")
    merge_conflict_behavior: str = Field("pr", alias="MERGE_CONFLICT_BEHAVIOR")
    dry_run: bool = Field(False, alias="DRY_RUN")
    log_level: str = Field("info", alias="LOG_LEVEL")
    context_engine_enabled: bool = Field(False, alias="CONTEXT_ENGINE_ENABLED")
    embedding_model: str = Field("text-embedding-3-large", alias="EMBEDDING_MODEL")
    context_budget_tokens: int = Field(64000, alias="CONTEXT_BUDGET_TOKENS")
    context_output_reserve_tokens: int = Field(8000, alias="CONTEXT_OUTPUT_RESERVE_TOKENS")
    context_hard_cap_tokens: int = Field(70000, alias="CONTEXT_HARD_CAP_TOKENS")
    context_compact_threshold_ratio: float = Field(0.6, alias="CONTEXT_COMPACT_THRESHOLD_RATIO")
    memory_max_items_per_job: int = Field(2000, alias="MEMORY_MAX_ITEMS_PER_JOB")
    memory_max_bytes_per_item: int = Field(20000, alias="MEMORY_MAX_BYTES_PER_ITEM")
    retriever_max_files: int = Field(200, alias="RETRIEVER_MAX_FILES")
    retriever_max_snippet_tokens: int = Field(2000, alias="RETRIEVER_MAX_SNIPPET_TOKENS")
    jit_enable: bool = Field(True, alias="JIT_ENABLE")
    curator_topk: int = Field(12, alias="CURATOR_TOPK")
    curator_min_score: float = Field(0.12, alias="CURATOR_MIN_SCORE")

    # Multi-LLM Routing
    llm_routing_enabled: bool = Field(False, alias="LLM_ROUTING_ENABLED")
    default_model_strategy: str = Field("cost_optimized", alias="DEFAULT_MODEL_STRATEGY")
    model_simple: str = Field("gpt-3.5-turbo", alias="MODEL_SIMPLE")
    model_medium: str = Field("claude-sonnet-4.5", alias="MODEL_MEDIUM")
    model_complex: str = Field("claude-opus-4", alias="MODEL_COMPLEX")
    routing_complexity_threshold_medium: int = Field(3, alias="ROUTING_COMPLEXITY_THRESHOLD_MEDIUM")
    routing_complexity_threshold_complex: int = Field(7, alias="ROUTING_COMPLEXITY_THRESHOLD_COMPLEX")
    routing_token_threshold_large: int = Field(5000, alias="ROUTING_TOKEN_THRESHOLD_LARGE")
    routing_fallback_model: str = Field("gpt-4", alias="ROUTING_FALLBACK_MODEL")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    @property
    def database_uri(self) -> str:
        return f"sqlite:///{self.db_path}"


class BudgetLimits(BaseModel):
    budget_usd_max: float
    max_requests: int
    max_wallclock_minutes: int


@lru_cache
def get_settings() -> AppSettings:
    settings = AppSettings()
    db_dir = settings.db_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    return settings


@lru_cache
def get_budget_limits() -> BudgetLimits:
    settings = get_settings()
    return BudgetLimits(
        budget_usd_max=settings.budget_usd_max,
        max_requests=settings.max_requests,
        max_wallclock_minutes=settings.max_wallclock_minutes,
    )


def get_env_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}
