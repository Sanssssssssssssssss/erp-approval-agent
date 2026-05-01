from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PROPOSAL_LEDGER_NON_ACTION_STATEMENT = "No ERP write action was executed."
AuditCompletenessSeverity = Literal["info", "warning", "error"]


class ApprovalActionProposalRecord(BaseModel):
    proposal_record_id: str = ""
    proposal_id: str = ""
    trace_id: str = ""
    run_id: str = ""
    session_id: str | None = None
    thread_id: str = ""
    turn_id: str = ""
    approval_id: str = ""
    approval_type: str = "unknown"
    created_at: str = ""
    updated_at: str = ""
    review_status: str = ""
    recommendation_status: str = ""
    action_type: str = ""
    status: str = ""
    title: str = ""
    summary: str = ""
    target: str = ""
    payload_preview: dict[str, Any] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)
    idempotency_key: str = ""
    idempotency_scope: str = ""
    idempotency_fingerprint: str = ""
    risk_level: str = ""
    requires_human_review: bool = True
    executable: bool = False
    non_action_statement: str = PROPOSAL_LEDGER_NON_ACTION_STATEMENT
    validation_warnings: list[str] = Field(default_factory=list)
    blocked: bool = False
    rejected_by_validation: bool = False


class ApprovalActionProposalWriteResult(BaseModel):
    success: bool = False
    proposal_record_id: str = ""
    path: str = ""
    created: bool = False
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalActionProposalQuery(BaseModel):
    limit: int = Field(default=100, ge=0, le=5000)
    action_type: str | None = None
    status: str | None = None
    approval_id: str | None = None
    trace_id: str | None = None
    risk_level: str | None = None
    requires_human_review: bool | None = None
    blocked: bool | None = None
    rejected_by_validation: bool | None = None


class ApprovalActionProposalListResponse(BaseModel):
    proposals: list[ApprovalActionProposalRecord] = Field(default_factory=list)
    total: int = 0
    query: ApprovalActionProposalQuery = Field(default_factory=ApprovalActionProposalQuery)


class ApprovalAuditCompletenessCheck(BaseModel):
    check_name: str = ""
    passed: bool = False
    severity: AuditCompletenessSeverity = "info"
    message: str = ""


class ApprovalAuditPackageTrace(BaseModel):
    trace_id: str = ""
    approval_id: str = ""
    approval_type: str = "unknown"
    created_at: str = ""
    recommendation_status: str = ""
    review_status: str = ""
    context_source_ids: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    guard_warnings: list[str] = Field(default_factory=list)
    proposal_ids: list[str] = Field(default_factory=list)
    non_action_statement: str = PROPOSAL_LEDGER_NON_ACTION_STATEMENT


class ApprovalAuditPackageProposal(BaseModel):
    proposal_record_id: str = ""
    proposal_id: str = ""
    trace_id: str = ""
    approval_id: str = ""
    action_type: str = ""
    status: str = ""
    title: str = ""
    summary: str = ""
    target: str = ""
    citations: list[str] = Field(default_factory=list)
    idempotency_key: str = ""
    idempotency_scope: str = ""
    idempotency_fingerprint: str = ""
    risk_level: str = ""
    requires_human_review: bool = True
    executable: bool = False
    validation_warnings: list[str] = Field(default_factory=list)
    blocked: bool = False
    rejected_by_validation: bool = False
    non_action_statement: str = PROPOSAL_LEDGER_NON_ACTION_STATEMENT


class ApprovalAuditPackage(BaseModel):
    package_id: str = ""
    created_at: str = ""
    trace_ids: list[str] = Field(default_factory=list)
    proposal_record_ids: list[str] = Field(default_factory=list)
    traces: list[ApprovalAuditPackageTrace] = Field(default_factory=list)
    proposals: list[ApprovalAuditPackageProposal] = Field(default_factory=list)
    completeness_checks: list[ApprovalAuditCompletenessCheck] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    non_action_statement: str = PROPOSAL_LEDGER_NON_ACTION_STATEMENT
