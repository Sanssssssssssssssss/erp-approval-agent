from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.backend.domains.erp_approval import ApprovalTraceRepository, default_trace_path
from src.backend.runtime.agent_manager import agent_manager
from src.backend.runtime.config import get_settings

router = APIRouter()


def _repository() -> ApprovalTraceRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return ApprovalTraceRepository(default_trace_path(base_dir))


@router.get("/erp-approval/traces")
async def list_erp_approval_traces(limit: int = Query(default=100, ge=0, le=1000)) -> list[dict]:
    return [record.model_dump() for record in _repository().list_recent(limit=limit)]


@router.get("/erp-approval/traces/{trace_id}")
async def get_erp_approval_trace(trace_id: str) -> dict:
    record = _repository().get(trace_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ERP approval trace not found")
    return record.model_dump()


@router.get("/erp-approval/analytics/summary")
async def get_erp_approval_analytics_summary(limit: int = Query(default=500, ge=0, le=5000)) -> dict:
    return _repository().summarize(limit=limit).model_dump()
