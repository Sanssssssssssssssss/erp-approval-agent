from __future__ import annotations

from typing import Any

from src.backend.domains.erp_approval.case_review_service import CaseReviewResponse
from src.backend.domains.erp_approval.case_state_models import (
    ApprovalCaseState,
    CASE_HARNESS_NON_ACTION_STATEMENT,
    CasePatch,
)


PLAN_GROUPS: dict[str, list[str]] = {
    "purchase_requisition": [
        "approval_request",
        "line_items",
        "cost_center",
        "budget_availability",
        "vendor_onboarding_status",
        "supplier_risk_status",
        "quote_or_price_basis",
        "contract_or_framework_agreement",
        "procurement_policy",
        "approval_matrix",
    ],
    "expense": ["expense_claim", "receipt_or_invoice", "expense_policy", "business_purpose", "cost_center", "duplicate_expense_check"],
    "invoice_payment": ["invoice", "purchase_order", "goods_receipt", "vendor_record", "three_way_match", "duplicate_payment_check", "invoice_payment_policy"],
    "supplier_onboarding": ["vendor_profile", "tax_info", "bank_info", "sanctions_check", "beneficial_owner_check", "procurement_due_diligence"],
    "contract_exception": ["contract_text", "redline_or_exception_clause", "standard_terms", "legal_policy", "legal_review_required"],
    "budget_exception": ["budget_record", "budget_owner", "available_budget", "exception_reason", "finance_policy", "finance_approval_matrix"],
}


def build_case_supervisor_plan(state: ApprovalCaseState, review: CaseReviewResponse, patch: CasePatch | None = None) -> dict[str, Any]:
    requirements = [dict(item) for item in (review.evidence_requirements or state.evidence_requirements or [])]
    missing = [item for item in requirements if str(item.get("status", "")) in {"missing", "partial", "conflict"}]
    blocking = [item for item in missing if bool(item.get("blocking", False))]
    unresolved_policy = [item for item in state.policy_failures if not item.resolved]
    if patch is not None:
        unresolved_policy.extend(item for item in patch.policy_failures if not item.resolved)

    priority_ids = PLAN_GROUPS.get(state.approval_type, ["approval_request", "policy", "approval_matrix", "manual_review"])
    ordered_blocking = sorted(
        blocking,
        key=lambda item: _priority_index(str(item.get("requirement_id", "")), priority_ids),
    )
    next_items = ordered_blocking[:4] or missing[:4]
    ready = (
        not ordered_blocking
        and not unresolved_policy
        and bool(review.evidence_sufficiency.get("passed"))
        and bool(review.control_matrix.get("passed"))
        and not bool((review.contradictions or {}).get("has_conflict"))
    )
    next_action = "generate_final_reviewer_memo" if ready else "collect_priority_evidence"
    if unresolved_policy:
        next_action = "fix_rejected_policy_failures"

    return {
        "role": "case_supervisor",
        "ready_for_final_memo": ready,
        "next_action": next_action,
        "priority_requirements": [_plan_item(item) for item in next_items],
        "unresolved_policy_failure_count": len(unresolved_policy),
        "strategy": _strategy_text(state.approval_type, next_items, ready, unresolved_policy),
        "suggested_user_prompt": _suggested_prompt(next_items, ready, unresolved_policy),
        "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
    }


def _priority_index(requirement_id: str, priority_ids: list[str]) -> int:
    if requirement_id in priority_ids:
        return priority_ids.index(requirement_id)
    for index, prefix in enumerate(priority_ids):
        if requirement_id.startswith(prefix) or prefix in requirement_id:
            return index
    return len(priority_ids) + 10


def _plan_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": item.get("requirement_id", ""),
        "label": item.get("label") or item.get("requirement_id", ""),
        "status": item.get("status", "missing"),
        "blocking": bool(item.get("blocking", False)),
        "why_now": "blocking evidence，缺失会阻止最终 reviewer memo" if item.get("blocking") else "补齐后可提高案卷完整度",
    }


def _strategy_text(approval_type: str, next_items: list[dict[str, Any]], ready: bool, unresolved_policy: list[Any]) -> str:
    if ready:
        return "当前案卷已满足 blocking evidence 和控制矩阵，可以询问用户是否生成最终 reviewer memo。"
    if unresolved_policy:
        return "先修复被退回材料对应的制度失败，再继续补新材料。"
    if next_items:
        labels = "、".join(str(item.get("label") or item.get("requirement_id")) for item in next_items[:4])
        return f"建议下一轮优先补：{labels}。这些是当前最影响案卷推进的材料。"
    return f"{approval_type or '当前'}案卷继续收集可追溯证据，并保持人工 reviewer 边界。"


def _suggested_prompt(next_items: list[dict[str, Any]], ready: bool, unresolved_policy: list[Any]) -> str:
    if ready:
        return "请生成最终 reviewer memo / submission package。"
    if unresolved_policy:
        return "请说明上一份被退回材料如何按制度修正，或提交修正后的材料。"
    if next_items:
        label = str(next_items[0].get("label") or next_items[0].get("requirement_id"))
        return f"请先提交「{label}」对应的可追溯材料。"
    return "请提交下一份带 source_id 的正式证据材料。"
