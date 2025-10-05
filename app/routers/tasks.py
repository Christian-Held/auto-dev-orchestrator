from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import deps
from app.core.logging import get_logger
from app.db import repo
from app.workers.job_worker import execute_job

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = get_logger(__name__)


class TaskCreateRequest(BaseModel):
    task: str
    repo_owner: str
    repo_name: str
    branch_base: str
    budgetUsd: float = Field(..., ge=0)
    maxRequests: int = Field(..., ge=1)
    maxMinutes: int = Field(..., ge=1)
    modelCTO: str | None = None
    modelCoder: str | None = None


class TaskCreateResponse(BaseModel):
    job_id: str


@router.post("/", response_model=TaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_task(
    payload: TaskCreateRequest,
    request: Request,
    session: Session = Depends(deps.get_db),
):
    spec = request.app.state.agents_spec
    job = repo.create_job(
        session,
        task=payload.task,
        repo_owner=payload.repo_owner,
        repo_name=payload.repo_name,
        branch_base=payload.branch_base,
        budget_usd=payload.budgetUsd,
        max_requests=payload.maxRequests,
        max_minutes=payload.maxMinutes,
        model_cto=payload.modelCTO,
        model_coder=payload.modelCoder,
        agents_hash=spec.digest,
    )
    session.commit()
    execute_job.delay(job.id)
    logger.info("task_enqueued", job_id=job.id)
    return TaskCreateResponse(job_id=job.id)
