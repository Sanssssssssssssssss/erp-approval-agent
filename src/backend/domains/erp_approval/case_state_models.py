from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.case_review_service import CaseReviewEvidenceInput, CaseReviewResponse


CASE_HARNESS_NON_ACTION_STATEMENT = "This is a local approval case state update. No ERP write action was executed."

CaseStage = Literal[
    "draft",
    "collecting_evidence",
    "escalation_review",
    "ready_for_final_review",
    "final_memo_ready",
    "blocked",
]
CaseTurnIntent = Literal[
    "create_case",
    "ask_how_to_prepare",
    "ask_missing_requirements",
    "ask_policy_failure",
    "ask_required_materials",
    "submit_evidence",
    "correct_previous_evidence",
    "withdraw_evidence",
    "ask_status",
    "request_final_memo",
    "request_final_review",
    "off_topic",
]
CasePatchType = Literal[
    "create_case",
    "accept_evidence",
    "reject_evidence",
    "answer_status",
    "final_memo",
    "no_case_change",
]
EvidencePatchDecision = Literal["accepted", "rejected", "needs_clarification", "not_evidence"]


class CaseAcceptedEvidence(BaseModel):
    source_id: str
    title: str = ""
    record_type: str = ""
    content: str = ""
    accepted_at: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_review_input(self) -> CaseReviewEvidenceInput:
        return CaseReviewEvidenceInput(
            title=self.title,
            record_type=self.record_type,
            content=self.content,
            source_id=self.source_id,
            metadata=dict(self.metadata or {}),
        )


class CaseRejectedEvidence(BaseModel):
    source_id: str
    title: str = ""
    record_type: str = ""
    content_preview: str = ""
    rejected_at: str = ""
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CasePolicyFailure(BaseModel):
    requirement_id: str = ""
    policy_source_id: str = ""
    policy_clause_id: str = ""
    policy_clause_text: str = ""
    why_failed: str = ""
    how_to_fix: str = ""
    source_id: str = ""
    resolved: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CasePatch(BaseModel):
    patch_id: str
    turn_id: str
    case_id: str
    patch_type: CasePatchType = "no_case_change"
    turn_intent: CaseTurnIntent = "ask_status"
    evidence_decision: EvidencePatchDecision = "not_evidence"
    accepted_evidence: list[CaseAcceptedEvidence] = Field(default_factory=list)
    rejected_evidence: list[CaseRejectedEvidence] = Field(default_factory=list)
    policy_failures: list[CasePolicyFailure] = Field(default_factory=list)
    requirements_satisfied: list[str] = Field(default_factory=list)
    requirements_missing: list[str] = Field(default_factory=list)
    dossier_patch: str = ""
    rejection_reasons: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    allowed_to_apply: bool = False
    model_review: dict[str, Any] = Field(default_factory=dict)
    non_action_statement: str = CASE_HARNESS_NON_ACTION_STATEMENT


class CaseTurnContract(BaseModel):
    case_id: str
    stage: CaseStage = "draft"
    allowed_intents: list[CaseTurnIntent] = Field(default_factory=list)
    allowed_patch_types: list[CasePatchType] = Field(default_factory=list)
    required_context_blocks: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    output_schema: str = "CasePatch"
    validation_rules: list[str] = Field(default_factory=list)


class ApprovalCaseState(BaseModel):
    case_id: str
    approval_type: str = "unknown"
    approval_id: str = ""
    stage: CaseStage = "draft"
    created_at: str = ""
    updated_at: str = ""
    turn_count: int = 0
    dossier_version: int = 0
    source_request: str = ""
    request: dict[str, Any] = Field(default_factory=dict)
    accepted_evidence: list[CaseAcceptedEvidence] = Field(default_factory=list)
    rejected_evidence: list[CaseRejectedEvidence] = Field(default_factory=list)
    policy_failures: list[CasePolicyFailure] = Field(default_factory=list)
    evidence_requirements: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: dict[str, Any] = Field(default_factory=dict)
    evidence_sufficiency: dict[str, Any] = Field(default_factory=dict)
    control_matrix: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any] = Field(default_factory=dict)
    reviewer_memo: str = ""
    missing_items: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    last_valid_turn_id: str = ""
    audit_event_count: int = 0
    non_action_statement: str = CASE_HARNESS_NON_ACTION_STATEMENT


class CaseAuditEvent(BaseModel):
    turn_id: str
    case_id: str
    event: str
    created_at: str
    details: dict[str, Any] = Field(default_factory=dict)
    non_action_statement: str = CASE_HARNESS_NON_ACTION_STATEMENT


class CaseTurnRequest(BaseModel):
    case_id: str = ""
    user_message: str
    extra_evidence: list[CaseReviewEvidenceInput] = Field(default_factory=list)
    requested_by: str = "local_reviewer"
    expected_turn_count: int | None = None
    client_intent: CaseTurnIntent | Literal[""] = ""


class CaseTurnResponse(BaseModel):
    case_state: ApprovalCaseState
    contract: CaseTurnContract
    patch: CasePatch
    review: CaseReviewResponse
    dossier: str
    audit_events: list[CaseAuditEvent] = Field(default_factory=list)
    storage_paths: dict[str, str] = Field(default_factory=dict)
    operation_scope: str = "persistent_case_turn"
    non_action_statement: str = CASE_HARNESS_NON_ACTION_STATEMENT
