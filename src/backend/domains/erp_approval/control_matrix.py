from __future__ import annotations

from collections.abc import Iterable

from src.backend.domains.erp_approval.case_models import (
    ApprovalCaseFile,
    ControlCheck,
    ControlMatrixResult,
    EvidenceClaim,
    EvidenceRequirement,
)


GENERAL_CONTROL_REQUIREMENTS = {
    "approval_matrix_present": "approval_matrix",
    "requester_identity_present": "requester_identity",
    "amount_present": "amount_threshold",
    "policy_present": "policy",
}

TYPE_CONTROL_REQUIREMENTS: dict[str, dict[str, str]] = {
    "purchase_requisition": {
        "budget_available": "budget_availability",
        "vendor_onboarded": "vendor_onboarding_status",
        "supplier_risk_clear": "supplier_risk_status",
        "quote_or_contract_present": "quote_or_price_basis",
        "amount_threshold_review": "amount_threshold",
        "split_order_check": "split_order_check",
        "cost_center_present": "cost_center",
    },
    "expense": {
        "receipt_present": "receipt_or_invoice",
        "expense_policy_present": "expense_policy",
        "duplicate_expense_check": "duplicate_expense_check",
        "expense_limit_check": "amount_limit_check",
        "business_purpose_present": "business_purpose",
    },
    "invoice_payment": {
        "invoice_present": "invoice",
        "purchase_order_present": "purchase_order",
        "goods_receipt_present": "goods_receipt",
        "three_way_match": "three_way_match",
        "duplicate_payment_check": "duplicate_payment_check",
        "payment_terms_check": "contract_or_payment_terms",
    },
    "supplier_onboarding": {
        "supplier_risk_clear": "vendor_profile",
        "tax_info_present": "tax_info",
        "bank_info_present": "bank_info",
        "sanctions_check": "sanctions_check",
        "beneficial_owner_check": "beneficial_owner_check",
        "procurement_due_diligence": "procurement_due_diligence",
        "legal_or_contract_docs": "contract_or_nda_or_dpa",
    },
    "contract_exception": {
        "contract_text_present": "contract_text",
        "exception_clause_present": "redline_or_exception_clause",
        "legal_review_required": "legal_review_required",
        "liability_clause_review": "liability_clause",
        "payment_terms_review": "payment_terms",
        "termination_clause_review": "termination_clause",
    },
    "budget_exception": {
        "budget_record_present": "budget_record",
        "available_budget_check": "available_budget",
        "budget_owner_present": "budget_owner",
        "finance_review_required": "finance_approval_matrix",
    },
}

HIGH_SEVERITY_CONTROLS = {
    "evidence_sufficiency",
    "citation_support",
    "approval_matrix_present",
    "policy_present",
    "budget_available",
    "supplier_risk_clear",
    "three_way_match",
    "duplicate_payment_check",
    "sanctions_check",
    "beneficial_owner_check",
    "legal_review_required",
    "available_budget_check",
    "finance_review_required",
}

CRITICAL_CONTROLS = {"no_final_execution"}


def build_control_checks(case_file: ApprovalCaseFile) -> list[ControlCheck]:
    requirements = list(case_file.evidence_requirements)
    claims = list(case_file.evidence_claims)
    checks: list[ControlCheck] = [
        _evidence_sufficiency_check(case_file),
        _citation_support_check(case_file),
        _no_final_execution_check(),
    ]
    for check_id, requirement_key in GENERAL_CONTROL_REQUIREMENTS.items():
        checks.append(_check_from_requirement(check_id, requirement_key, requirements, claims))
    for check_id, requirement_key in TYPE_CONTROL_REQUIREMENTS.get(str(case_file.approval_type), {}).items():
        checks.append(_check_from_requirement(check_id, requirement_key, requirements, claims))
    return checks


def evaluate_control_matrix(case_file: ApprovalCaseFile) -> ControlMatrixResult:
    checks = build_control_checks(case_file)
    failed = [check.check_id for check in checks if check.status == "fail"]
    missing = [check.check_id for check in checks if check.status == "missing"]
    conflicts = [check.check_id for check in checks if check.status == "conflict"]
    high_risk = any(
        check.status in {"fail", "missing", "conflict"} and check.severity in {"high", "critical"}
        for check in checks
    )
    blocking_reasons = [
        check.explanation
        for check in checks
        if check.status in {"fail", "missing", "conflict"} and check.severity in {"high", "critical"}
    ]
    escalation_reasons = [
        check.explanation
        for check in checks
        if check.status in {"fail", "missing", "conflict"} and check.recommended_next_action in {"escalate", "manual_review"}
    ]
    return ControlMatrixResult(
        passed=not failed and not missing and not conflicts,
        high_risk=high_risk,
        checks=checks,
        failed_check_ids=failed,
        missing_check_ids=missing,
        conflict_check_ids=conflicts,
        escalation_reasons=_unique(escalation_reasons),
        blocking_reasons=_unique(blocking_reasons),
    )


def _evidence_sufficiency_check(case_file: ApprovalCaseFile) -> ControlCheck:
    report = case_file.evidence_sufficiency
    return ControlCheck(
        check_id="evidence_sufficiency",
        check_type="general",
        label="Evidence sufficiency",
        status="pass" if report.passed else "fail",
        severity="high",
        explanation=(
            "Evidence sufficiency passed."
            if report.passed
            else "Blocking evidence gaps remain: " + "; ".join(report.blocking_gaps or report.next_questions or ["missing evidence"])
        ),
        recommended_next_action="manual_review" if report.passed else "request_more_info",
    )


def _citation_support_check(case_file: ApprovalCaseFile) -> ControlCheck:
    supported_claims = [
        claim
        for claim in case_file.evidence_claims
        if claim.source_id and claim.verification_status == "supported" and not claim.source_id.startswith("user_statement://")
    ]
    return ControlCheck(
        check_id="citation_support",
        check_type="general",
        label="Citation support",
        status="pass" if supported_claims else "missing",
        severity="high",
        supporting_claim_ids=[claim.claim_id for claim in supported_claims[:12]],
        explanation=(
            "Structured claims have non-user source_id support."
            if supported_claims
            else "No non-user evidence claims are available to support a recommendation."
        ),
        recommended_next_action="manual_review" if supported_claims else "request_more_info",
    )


def _no_final_execution_check() -> ControlCheck:
    return ControlCheck(
        check_id="no_final_execution",
        check_type="boundary",
        label="No final execution",
        status="pass",
        severity="critical",
        explanation="This workflow only analyzes an approval case and never executes ERP write actions.",
        recommended_next_action="manual_review",
    )


def _check_from_requirement(
    check_id: str,
    requirement_key: str,
    requirements: list[EvidenceRequirement],
    claims: list[EvidenceClaim],
) -> ControlCheck:
    requirement = _find_requirement(requirements, requirement_key)
    supporting = _claims_for_requirement(claims, requirement.requirement_id if requirement else "")
    status = _status_from_requirement(requirement, supporting)
    severity = "high" if check_id in HIGH_SEVERITY_CONTROLS else "medium"
    if check_id in CRITICAL_CONTROLS:
        severity = "critical"
    if check_id in {"amount_present", "cost_center_present", "business_purpose_present"}:
        severity = "medium"
    failing_claims = [claim.claim_id for claim in supporting if claim.verification_status in {"conflict", "unsupported"}]
    if _has_negative_claim(check_id, supporting):
        status = "fail"
        failing_claims = failing_claims or [claim.claim_id for claim in supporting]
    label = check_id.replace("_", " ").title()
    explanation = _check_explanation(check_id, requirement, status, supporting)
    next_action = "manual_review" if status == "pass" else _next_action_for_check(check_id)
    return ControlCheck(
        check_id=check_id,
        check_type="approval_control",
        label=label,
        status=status,
        severity=severity,
        required_requirement_ids=[requirement.requirement_id] if requirement else [],
        supporting_claim_ids=[claim.claim_id for claim in supporting if claim.verification_status == "supported"],
        failing_claim_ids=failing_claims,
        explanation=explanation,
        recommended_next_action=next_action,
    )


def _find_requirement(requirements: list[EvidenceRequirement], key: str) -> EvidenceRequirement | None:
    suffix = ":" + key
    for requirement in requirements:
        if requirement.requirement_id.endswith(suffix) or requirement.requirement_id == key:
            return requirement
    return None


def _claims_for_requirement(claims: list[EvidenceClaim], requirement_id: str) -> list[EvidenceClaim]:
    if not requirement_id:
        return []
    return [claim for claim in claims if requirement_id in claim.supports_requirement_ids]


def _status_from_requirement(requirement: EvidenceRequirement | None, supporting: list[EvidenceClaim]) -> str:
    if requirement is None:
        return "not_applicable"
    if requirement.status == "satisfied":
        return "pass"
    if requirement.status == "conflict" or any(claim.verification_status == "conflict" for claim in supporting):
        return "conflict"
    if requirement.status in {"missing", "partial"}:
        return "missing"
    if requirement.status == "not_applicable":
        return "not_applicable"
    return "missing"


def _has_negative_claim(check_id: str, claims: Iterable[EvidenceClaim]) -> bool:
    for claim in claims:
        value = str(claim.normalized_value if claim.normalized_value is not None else claim.extracted_value).lower()
        if check_id in {"budget_available", "available_budget_check"} and value in {"insufficient", "over_budget", "false"}:
            return True
        if check_id in {"vendor_onboarded", "supplier_risk_clear", "sanctions_check"} and value in {
            "pending",
            "blocked",
            "sanctioned",
            "false",
        }:
            return True
    return False


def _check_explanation(
    check_id: str,
    requirement: EvidenceRequirement | None,
    status: str,
    supporting: list[EvidenceClaim],
) -> str:
    if requirement is None:
        return f"{check_id} is not applicable to this approval type."
    if status == "pass":
        return f"{requirement.label} is supported by {len(supporting)} evidence claim(s)."
    if status == "fail":
        return f"{requirement.label} has negative or failing evidence and needs escalation."
    if status == "conflict":
        return f"{requirement.label} has conflicting evidence."
    return f"{requirement.label} is missing or only partially supported."


def _next_action_for_check(check_id: str) -> str:
    if check_id in {"legal_review_required", "liability_clause_review", "termination_clause_review"}:
        return "escalate"
    if check_id in {"budget_available", "available_budget_check", "finance_review_required"}:
        return "escalate"
    if check_id in {"sanctions_check", "beneficial_owner_check", "supplier_risk_clear"}:
        return "escalate"
    return "request_more_info"


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
