from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


ERP_TRACE_NON_ACTION_STATEMENT = "No ERP approval, rejection, payment, comment, request-more-info, route, supplier, budget, or contract action was executed."


class ApprovalTraceRecord(BaseModel):
    trace_id: str = ""
    run_id: str = ""
    session_id: str | None = None
    thread_id: str = ""
    turn_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    approval_id: str = ""
    approval_type: str = "unknown"
    requester: str = ""
    department: str = ""
    amount: float | None = None
    currency: str = ""
    vendor: str = ""
    cost_center: str = ""
    context_source_ids: list[str] = Field(default_factory=list)
    recommendation_status: str = ""
    recommendation_confidence: float = 0.0
    human_review_required: bool = True
    missing_information: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    guard_warnings: list[str] = Field(default_factory=list)
    guard_downgraded: bool = False
    review_status: str = ""
    hitl_decision: str = ""
    proposal_ids: list[str] = Field(default_factory=list)
    proposal_action_types: list[str] = Field(default_factory=list)
    proposal_statuses: list[str] = Field(default_factory=list)
    proposal_validation_warnings: list[str] = Field(default_factory=list)
    blocked_proposal_ids: list[str] = Field(default_factory=list)
    rejected_proposal_ids: list[str] = Field(default_factory=list)
    final_answer_preview: str = ""
    non_action_statement: str = ERP_TRACE_NON_ACTION_STATEMENT


class ApprovalTraceSummary(BaseModel):
    trace_id: str = ""
    created_at: str = ""
    approval_id: str = ""
    approval_type: str = "unknown"
    recommendation_status: str = ""
    review_status: str = ""
    proposal_action_types: list[str] = Field(default_factory=list)


class ApprovalAnalyticsSummary(BaseModel):
    total_traces: int = 0
    by_approval_type: dict[str, int] = Field(default_factory=dict)
    by_recommendation_status: dict[str, int] = Field(default_factory=dict)
    by_review_status: dict[str, int] = Field(default_factory=dict)
    human_review_required_count: int = 0
    guard_downgrade_count: int = 0
    top_missing_information: list[dict[str, int | str]] = Field(default_factory=list)
    top_risk_flags: list[dict[str, int | str]] = Field(default_factory=list)
    top_guard_warnings: list[dict[str, int | str]] = Field(default_factory=list)
    proposal_action_type_counts: dict[str, int] = Field(default_factory=dict)
    blocked_proposal_count: int = 0
    rejected_proposal_count: int = 0
    high_risk_trace_ids: list[str] = Field(default_factory=list)


class ApprovalTraceWriteResult(BaseModel):
    success: bool = False
    trace_id: str = ""
    path: str = ""
    created: bool = False
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
