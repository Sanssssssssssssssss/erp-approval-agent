from __future__ import annotations

import re
from typing import Any

from src.backend.domains.erp_approval.case_state_models import (
    ApprovalCaseState,
    CasePolicyFailure,
    CaseRejectedEvidence,
)
from src.backend.domains.erp_approval.evidence_requirements import requirement_matrix_for_approval_type


POLICY_RAG_NON_ACTION_STATEMENT = "This is local policy guidance for an approval case. No ERP write action was executed."


def build_policy_guidance(state: ApprovalCaseState, *, approval_type: str | None = None) -> dict[str, Any]:
    """Build a local policy/RAG-style material checklist from the requirement matrix.

    This is intentionally read-only. It does not call ERP, does not execute workflow
    actions, and does not mutate the approval case.
    """

    effective_type = approval_type or state.approval_type or "unknown"
    requirements = state.evidence_requirements or [
        requirement.model_dump() for requirement in requirement_matrix_for_approval_type(effective_type)
    ]
    items = []
    for requirement in requirements:
        clause = policy_clause_for_requirement(requirement)
        items.append(
            {
                "requirement_id": requirement.get("requirement_id", ""),
                "label": requirement.get("label", ""),
                "blocking": bool(requirement.get("blocking", False)),
                "status": requirement.get("status", "missing"),
                "required_level": requirement.get("required_level", "required"),
                "policy": clause,
                "acceptable_evidence": acceptable_evidence_forms(requirement),
                "unacceptable_evidence": unacceptable_evidence_forms(requirement),
            }
        )
    return {
        "approval_type": effective_type,
        "items": items,
        "non_action_statement": POLICY_RAG_NON_ACTION_STATEMENT,
    }


def policy_clause_for_requirement(requirement: dict[str, Any]) -> dict[str, str]:
    requirement_id = str(requirement.get("requirement_id", "") or "unknown:manual_review")
    key = requirement_id.split(":", 1)[-1]
    policy_refs = [str(item) for item in requirement.get("policy_refs") or [] if str(item).strip()]
    source_id = policy_refs[0] if policy_refs else _policy_source_for_key(key)
    clause_id = f"{source_id}:{key}"
    text = _policy_clause_text(key, requirement)
    return {
        "policy_source_id": source_id,
        "policy_clause_id": clause_id,
        "policy_clause_text": text,
    }


def policy_failures_for_rejected_evidence(
    rejected: list[CaseRejectedEvidence],
    review: Any,
) -> list[CasePolicyFailure]:
    requirements = _requirements_from_review(review)
    output: list[CasePolicyFailure] = []
    for item in rejected:
        matched = _candidate_requirements_for_rejection(item, requirements)
        for requirement in matched:
            clause = policy_clause_for_requirement(requirement)
            output.append(
                CasePolicyFailure(
                    requirement_id=str(requirement.get("requirement_id", "") or ""),
                    policy_source_id=clause["policy_source_id"],
                    policy_clause_id=clause["policy_clause_id"],
                    policy_clause_text=clause["policy_clause_text"],
                    why_failed=_why_failed(item, requirement),
                    how_to_fix=_how_to_fix(requirement),
                    source_id=item.source_id,
                    resolved=False,
                    metadata={"rejected_record_type": item.record_type, "rejection_reasons": list(item.reasons)},
                )
            )
    return _dedupe_policy_failures(output)


def resolve_policy_failures(
    existing: list[CasePolicyFailure],
    new_failures: list[CasePolicyFailure],
    satisfied_requirement_ids: list[str],
) -> list[CasePolicyFailure]:
    satisfied = set(satisfied_requirement_ids)
    merged: dict[tuple[str, str, str], CasePolicyFailure] = {}
    for failure in list(existing) + list(new_failures):
        key = (failure.requirement_id, failure.source_id, failure.policy_clause_id)
        updated = failure
        if failure.requirement_id in satisfied:
            updated = failure.model_copy(update={"resolved": True})
        merged[key] = updated
    return list(merged.values())


def acceptable_evidence_forms(requirement: dict[str, Any]) -> list[str]:
    key = _requirement_key(requirement)
    forms = {
        "budget_availability": ["预算记录或预算占用证明，含成本中心、可用余额、申请金额、预算负责人或记录状态。"],
        "vendor_onboarding_status": ["供应商主数据/准入记录，含供应商 ID、准入状态、生效时间。"],
        "supplier_risk_status": ["供应商风险、制裁、准入阻断检查记录，含检查结果和来源。"],
        "quote_or_price_basis": ["报价单、比价表、框架价格或合同价格依据，含金额、日期、供应商、适用 PR。"],
        "contract_or_framework_agreement": ["合同、框架协议，或有政策依据的不适用说明。"],
        "invoice": ["发票记录，含发票号、供应商、金额、币种、日期、PO/合同关联。"],
        "purchase_order": ["PO 采购订单，含 PO 号、供应商、金额、币种、状态和关联申请。"],
        "goods_receipt": ["GRN/收货记录，含收货号、PO、金额或数量、收货日期。"],
        "three_way_match": ["PO、GRN、Invoice 三单匹配表或流程日志，能解释金额和时序。"],
        "receipt_or_invoice": ["收据、发票或可审计票据，含金额、日期、商户、业务用途。"],
        "tax_info": ["税务登记、税号或供应商税务资料截图/记录。"],
        "bank_info": ["银行账户验证记录，含账号尾号/验证状态/来源。"],
        "sanctions_check": ["制裁筛查结果，含筛查时间、结果和来源。"],
        "legal_review_required": ["法务复核记录或法务政策条款。"],
        "approval_matrix": ["审批矩阵或金额阈值政策，含角色/金额区间/复核要求。"],
        "policy": ["适用制度条款、政策摘录或本地 policy record。"],
    }
    return forms.get(key, ["正式 ERP 记录、政策记录、附件文本或可追溯本地材料，必须有 source_id 和具体字段。"])


def unacceptable_evidence_forms(requirement: dict[str, Any]) -> list[str]:
    key = _requirement_key(requirement)
    common = ["仅用户口头说明。", "“老板同意了”但没有记录。", "没有来源 ID、金额、状态或制度条款的自由文本。"]
    if key in {"budget_availability", "available_budget", "budget_record"}:
        return common + ["只说“预算够了”，但无成本中心和可用余额。"]
    if key in {"vendor_onboarding_status", "supplier_risk_status", "sanctions_check", "bank_info", "tax_info"}:
        return common + ["只给供应商名称，未给准入/风险/银行/税务状态。"]
    if key in {"quote_or_price_basis", "contract_or_framework_agreement"}:
        return common + ["只说“供应商报过价”，但无报价单或合同依据。"]
    if key in {"invoice", "purchase_order", "goods_receipt", "three_way_match"}:
        return common + ["只给一个单号，不能证明三单匹配或金额一致。"]
    return common


def _requirements_from_review(review: Any) -> list[dict[str, Any]]:
    requirements = getattr(review, "evidence_requirements", None)
    if requirements is None and isinstance(review, dict):
        requirements = review.get("evidence_requirements")
    return [item for item in requirements or [] if isinstance(item, dict)]


def _candidate_requirements_for_rejection(item: CaseRejectedEvidence, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    record_type = str(item.record_type or "").strip().lower()
    text = f"{item.title} {item.content_preview} {' '.join(item.reasons)}".lower()
    candidates = []
    for requirement in requirements:
        expected = {str(value).lower() for value in requirement.get("expected_record_types") or []}
        key = _requirement_key(requirement)
        if record_type and record_type in expected:
            candidates.append(requirement)
        elif key and any(part in text for part in key.split("_")):
            candidates.append(requirement)
    if candidates:
        return candidates[:3]
    blocking_missing = [
        requirement
        for requirement in requirements
        if requirement.get("blocking") and requirement.get("status") in {"missing", "partial", "conflict", ""}
    ]
    return blocking_missing[:2] or requirements[:1]


def _why_failed(item: CaseRejectedEvidence, requirement: dict[str, Any]) -> str:
    reasons = "; ".join(item.reasons) if item.reasons else "材料没有形成可支持该 requirement 的 claim。"
    return f"{reasons} 该材料不能满足“{requirement.get('label') or requirement.get('requirement_id')}”的制度要求。"


def _how_to_fix(requirement: dict[str, Any]) -> str:
    acceptable = "; ".join(acceptable_evidence_forms(requirement))
    return f"请补充：{acceptable}"


def _policy_source_for_key(key: str) -> str:
    if any(token in key for token in ("budget", "finance")):
        return "mock_policy://budget_policy"
    if any(token in key for token in ("invoice", "payment", "three_way", "duplicate")):
        return "mock_policy://invoice_payment_policy"
    if any(token in key for token in ("vendor", "supplier", "sanctions", "bank", "tax")):
        return "mock_policy://supplier_onboarding_policy"
    if any(token in key for token in ("contract", "legal", "liability", "termination")):
        return "mock_policy://legal_policy"
    if "approval_matrix" in key or "threshold" in key or "manager" in key:
        return "mock_policy://approval_matrix"
    return "mock_policy://procurement_policy"


def _policy_clause_text(key: str, requirement: dict[str, Any]) -> str:
    label = str(requirement.get("label") or key)
    description = str(requirement.get("description") or "")
    blocking = "阻断性要求" if requirement.get("blocking") else "条件/参考要求"
    return f"{label}：{description} 该项为{blocking}；口头陈述不能替代可追溯证据。"


def _requirement_key(requirement: dict[str, Any]) -> str:
    requirement_id = str(requirement.get("requirement_id", "") or "")
    return re.sub(r"[^a-z0-9_]+", "_", requirement_id.split(":", 1)[-1].lower()).strip("_")


def _dedupe_policy_failures(failures: list[CasePolicyFailure]) -> list[CasePolicyFailure]:
    output: dict[tuple[str, str, str], CasePolicyFailure] = {}
    for failure in failures:
        output[(failure.requirement_id, failure.source_id, failure.policy_clause_id)] = failure
    return list(output.values())
