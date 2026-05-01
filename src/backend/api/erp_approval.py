from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from src.backend.domains.erp_approval import (
    ApprovalActionProposalQuery,
    ApprovalActionProposalRepository,
    ApprovalTraceQuery,
    ApprovalTraceRepository,
    build_audit_package,
    default_proposal_ledger_path,
    default_trace_path,
)
from src.backend.runtime.agent_manager import agent_manager
from src.backend.runtime.config import get_settings

router = APIRouter()


def _repository() -> ApprovalTraceRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return ApprovalTraceRepository(default_trace_path(base_dir))


def _proposal_repository() -> ApprovalActionProposalRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return ApprovalActionProposalRepository(default_proposal_ledger_path(base_dir))


@router.get("/erp-approval/traces")
async def list_erp_approval_traces(
    limit: int = Query(default=100, ge=0, le=1000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[dict]:
    query = _trace_query(
        limit=limit,
        approval_type=approval_type,
        recommendation_status=recommendation_status,
        review_status=review_status,
        proposal_action_type=proposal_action_type,
        human_review_required=human_review_required,
        guard_downgraded=guard_downgraded,
        high_risk_only=high_risk_only,
        text_query=text_query,
        date_from=date_from,
        date_to=date_to,
    )
    return [record.model_dump() for record in _repository().query(query)]


@router.get("/erp-approval/traces/{trace_id}")
async def get_erp_approval_trace(trace_id: str) -> dict:
    record = _repository().get(trace_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ERP approval trace not found")
    return record.model_dump()


@router.get("/erp-approval/traces/{trace_id}/proposals")
async def list_erp_approval_trace_proposals(trace_id: str) -> list[dict]:
    return [record.model_dump() for record in _proposal_repository().by_trace_id(trace_id)]


@router.get("/erp-approval/proposals")
async def list_erp_approval_proposals(
    limit: int = Query(default=100, ge=0, le=1000),
    action_type: str | None = None,
    status: str | None = None,
    approval_id: str | None = None,
    trace_id: str | None = None,
    risk_level: str | None = None,
    requires_human_review: bool | None = None,
    blocked: bool | None = None,
    rejected_by_validation: bool | None = None,
) -> list[dict]:
    query = _proposal_query(
        limit=limit,
        action_type=action_type,
        status=status,
        approval_id=approval_id,
        trace_id=trace_id,
        risk_level=risk_level,
        requires_human_review=requires_human_review,
        blocked=blocked,
        rejected_by_validation=rejected_by_validation,
    )
    return [record.model_dump() for record in _proposal_repository().query(query)]


@router.get("/erp-approval/proposals/{proposal_record_id}")
async def get_erp_approval_proposal(proposal_record_id: str) -> dict:
    record = _proposal_repository().get(proposal_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ERP approval proposal record not found")
    return record.model_dump()


@router.get("/erp-approval/analytics/summary")
async def get_erp_approval_analytics_summary(limit: int = Query(default=500, ge=0, le=5000)) -> dict:
    return _repository().summarize(limit=limit).model_dump()


@router.get("/erp-approval/audit-package")
async def get_erp_approval_audit_package(
    trace_ids: str = "",
    limit: int = Query(default=100, ge=0, le=1000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    trace_repository = _repository()
    proposal_repository = _proposal_repository()
    ids = [item.strip() for item in trace_ids.split(",") if item.strip()]
    if ids:
        traces = [record for trace_id in ids if (record := trace_repository.get(trace_id)) is not None]
    else:
        traces = trace_repository.query(
            _trace_query(
                limit=limit,
                approval_type=approval_type,
                recommendation_status=recommendation_status,
                review_status=review_status,
                proposal_action_type=proposal_action_type,
                human_review_required=human_review_required,
                guard_downgraded=guard_downgraded,
                high_risk_only=high_risk_only,
                text_query=text_query,
                date_from=date_from,
                date_to=date_to,
            )
        )
    proposals = []
    for trace in traces:
        proposals.extend(proposal_repository.by_trace_id(trace.trace_id))
    return build_audit_package(traces, proposals, _now()).model_dump()


@router.get("/erp-approval/analytics/trends")
async def get_erp_approval_analytics_trends(
    limit: int = Query(default=500, ge=0, le=5000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    return _repository().trend_summary(
        _trace_query(
            limit=limit,
            approval_type=approval_type,
            recommendation_status=recommendation_status,
            review_status=review_status,
            proposal_action_type=proposal_action_type,
            human_review_required=human_review_required,
            guard_downgraded=guard_downgraded,
            high_risk_only=high_risk_only,
            text_query=text_query,
            date_from=date_from,
            date_to=date_to,
        )
    ).model_dump()


@router.get("/erp-approval/export.json")
async def export_erp_approval_traces_json(
    limit: int = Query(default=500, ge=0, le=5000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    return _repository().export_json(
        _trace_query(
            limit=limit,
            approval_type=approval_type,
            recommendation_status=recommendation_status,
            review_status=review_status,
            proposal_action_type=proposal_action_type,
            human_review_required=human_review_required,
            guard_downgraded=guard_downgraded,
            high_risk_only=high_risk_only,
            text_query=text_query,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.get("/erp-approval/export.csv")
async def export_erp_approval_traces_csv(
    limit: int = Query(default=500, ge=0, le=5000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> Response:
    content = _repository().export_csv(
        _trace_query(
            limit=limit,
            approval_type=approval_type,
            recommendation_status=recommendation_status,
            review_status=review_status,
            proposal_action_type=proposal_action_type,
            human_review_required=human_review_required,
            guard_downgraded=guard_downgraded,
            high_risk_only=high_risk_only,
            text_query=text_query,
            date_from=date_from,
            date_to=date_to,
        )
    )
    return Response(content=content, media_type="text/csv")


def _trace_query(
    *,
    limit: int,
    approval_type: str | None,
    recommendation_status: str | None,
    review_status: str | None,
    proposal_action_type: str | None,
    human_review_required: bool | None,
    guard_downgraded: bool | None,
    high_risk_only: bool,
    text_query: str,
    date_from: str,
    date_to: str,
) -> ApprovalTraceQuery:
    return ApprovalTraceQuery(
        limit=limit,
        approval_type=_clean_optional(approval_type),
        recommendation_status=_clean_optional(recommendation_status),
        review_status=_clean_optional(review_status),
        proposal_action_type=_clean_optional(proposal_action_type),
        human_review_required=human_review_required,
        guard_downgraded=guard_downgraded,
        high_risk_only=high_risk_only,
        text_query=text_query.strip(),
        date_from=date_from.strip(),
        date_to=date_to.strip(),
    )


def _clean_optional(value: str | None) -> str | None:
    cleaned = value.strip() if isinstance(value, str) else ""
    return cleaned or None


def _proposal_query(
    *,
    limit: int,
    action_type: str | None,
    status: str | None,
    approval_id: str | None,
    trace_id: str | None,
    risk_level: str | None,
    requires_human_review: bool | None,
    blocked: bool | None,
    rejected_by_validation: bool | None,
) -> ApprovalActionProposalQuery:
    return ApprovalActionProposalQuery(
        limit=limit,
        action_type=_clean_optional(action_type),
        status=_clean_optional(status),
        approval_id=_clean_optional(approval_id),
        trace_id=_clean_optional(trace_id),
        risk_level=_clean_optional(risk_level),
        requires_human_review=requires_human_review,
        blocked=blocked,
        rejected_by_validation=rejected_by_validation,
    )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
