from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CASE_ANALYSIS_NON_ACTION_STATEMENT = "This is an approval case analysis. No ERP write action was executed."

EvidenceRequiredLevel = Literal["required", "conditional", "optional"]
EvidenceRequirementStatus = Literal["satisfied", "missing", "partial", "conflict", "not_applicable"]
EvidenceArtifactType = Literal["erp_record", "policy_record", "attachment", "user_statement", "mock_document"]
EvidenceVerificationStatus = Literal["supported", "unsupported", "conflict", "needs_review"]
ControlCheckStatus = Literal["pass", "fail", "missing", "conflict", "not_applicable"]
ControlSeverity = Literal["low", "medium", "high", "critical"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class EvidenceRequirement(BaseModel):
    requirement_id: str
    approval_type: str = "unknown"
    label: str
    description: str = ""
    required_level: EvidenceRequiredLevel = "required"
    blocking: bool = True
    expected_record_types: list[str] = Field(default_factory=list)
    expected_artifact_types: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)
    satisfied_by_claim_ids: list[str] = Field(default_factory=list)
    status: EvidenceRequirementStatus = "missing"


class EvidenceArtifact(BaseModel):
    artifact_id: str
    artifact_type: EvidenceArtifactType = "erp_record"
    source_id: str = ""
    title: str = ""
    content: str = ""
    record_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceClaim(BaseModel):
    claim_id: str
    claim_type: str
    statement: str
    source_id: str
    locator: str = ""
    extracted_value: Any = None
    normalized_value: Any = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    supports_requirement_ids: list[str] = Field(default_factory=list)
    contradicts_claim_ids: list[str] = Field(default_factory=list)
    verification_status: EvidenceVerificationStatus = "supported"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceSufficiencyReport(BaseModel):
    passed: bool = False
    completeness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_requirement_ids: list[str] = Field(default_factory=list)
    partial_requirement_ids: list[str] = Field(default_factory=list)
    conflict_requirement_ids: list[str] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)


class ContradictionReport(BaseModel):
    has_conflict: bool = False
    conflict_items: list[dict[str, Any]] = Field(default_factory=list)
    severity: str = "low"
    explanation: str = ""


class ControlCheck(BaseModel):
    check_id: str
    check_type: str
    label: str
    status: ControlCheckStatus = "missing"
    severity: ControlSeverity = "medium"
    required_requirement_ids: list[str] = Field(default_factory=list)
    supporting_claim_ids: list[str] = Field(default_factory=list)
    failing_claim_ids: list[str] = Field(default_factory=list)
    explanation: str = ""
    recommended_next_action: str = "request_more_info"


class ControlMatrixResult(BaseModel):
    passed: bool = False
    high_risk: bool = False
    checks: list[ControlCheck] = Field(default_factory=list)
    failed_check_ids: list[str] = Field(default_factory=list)
    missing_check_ids: list[str] = Field(default_factory=list)
    conflict_check_ids: list[str] = Field(default_factory=list)
    escalation_reasons: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class ApprovalPathPlan(BaseModel):
    approver_roles: list[str] = Field(default_factory=list)
    required_reviewers: list[str] = Field(default_factory=list)
    escalation_required: bool = False
    escalation_targets: list[str] = Field(default_factory=list)
    reason: str = ""


class RiskAssessment(BaseModel):
    risk_level: RiskLevel = "medium"
    risk_factors: list[str] = Field(default_factory=list)
    policy_friction: list[str] = Field(default_factory=list)
    fraud_or_error_signals: list[str] = Field(default_factory=list)
    explanation: str = ""


class AdversarialReview(BaseModel):
    passed: bool = False
    issues: list[str] = Field(default_factory=list)
    challenged_claim_ids: list[str] = Field(default_factory=list)
    challenged_control_ids: list[str] = Field(default_factory=list)
    recommendation_risks: list[str] = Field(default_factory=list)
    required_corrections: list[str] = Field(default_factory=list)


class ApprovalCaseFile(BaseModel):
    case_id: str = ""
    approval_type: str = "unknown"
    approval_id: str = ""
    request_header: dict[str, Any] = Field(default_factory=dict)
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    requester: str = ""
    department: str = ""
    amount: float | None = None
    currency: str = ""
    vendor: str = ""
    cost_center: str = ""
    business_purpose: str = ""
    source_request: str = ""
    context_source_ids: list[str] = Field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = Field(default_factory=list)
    evidence_artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    evidence_claims: list[EvidenceClaim] = Field(default_factory=list)
    evidence_sufficiency: EvidenceSufficiencyReport = Field(default_factory=EvidenceSufficiencyReport)
    contradictions: ContradictionReport = Field(default_factory=ContradictionReport)
    control_checks: list[ControlCheck] = Field(default_factory=list)
    approval_path: ApprovalPathPlan = Field(default_factory=ApprovalPathPlan)
    risk_assessment: RiskAssessment = Field(default_factory=RiskAssessment)
    adversarial_review: AdversarialReview = Field(default_factory=AdversarialReview)
    recommendation_status: str = "request_more_info"
    non_action_statement: str = CASE_ANALYSIS_NON_ACTION_STATEMENT
