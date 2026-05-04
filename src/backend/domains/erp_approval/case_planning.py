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
        "planner": "case_boundary_snapshot",
        "ready_for_final_memo": ready,
        "next_action": next_action,
        "priority_requirements": [_plan_item(item) for item in next_items],
        "unresolved_policy_failure_count": len(unresolved_policy),
        "strategy": _strategy_text(state.approval_type, next_items, ready, unresolved_policy),
        "suggested_user_prompt": _suggested_prompt(next_items, ready, unresolved_policy),
        "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
    }


def build_case_supervisor_plan_with_model(
    *,
    stage_model: Any | None,
    state: ApprovalCaseState,
    review: CaseReviewResponse,
    patch: CasePatch | None = None,
    context_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    boundary_snapshot = build_case_supervisor_plan(state, review, patch)
    if stage_model is None:
        return _model_required_plan(boundary_snapshot, reason="stage_model_not_configured")
    payload = {
        "case_state": {
            "case_id": state.case_id,
            "approval_type": state.approval_type,
            "approval_id": state.approval_id,
            "stage": state.stage,
            "accepted_evidence": [item.model_dump() for item in state.accepted_evidence[-20:]],
            "rejected_evidence": [item.model_dump() for item in state.rejected_evidence[-12:]],
            "policy_failures": [item.model_dump() for item in state.policy_failures if not item.resolved],
            "missing_items": state.missing_items,
            "next_questions": state.next_questions,
        },
        "current_patch": patch.model_dump() if patch is not None else {},
        "review": {
            "evidence_requirements": review.evidence_requirements,
            "evidence_sufficiency": review.evidence_sufficiency,
            "control_matrix": review.control_matrix,
            "contradictions": review.contradictions,
            "recommendation": review.recommendation,
        },
        "case_context_pack": context_pack or {},
        "case_boundary_snapshot": boundary_snapshot,
        "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
    }
    output, error = stage_model.review_custom_json_role(
        role_name="case_supervisor",
        system_prompt=CASE_SUPERVISOR_PROMPT,
        payload=payload,
    )
    if error or not output:
        return _model_required_plan(boundary_snapshot, reason=error or "empty supervisor plan")
    return validate_case_supervisor_plan(output, state=state, review=review, patch=patch, boundary_snapshot=boundary_snapshot, model_error=error)


def validate_case_supervisor_plan(
    output: dict[str, Any],
    *,
    state: ApprovalCaseState,
    review: CaseReviewResponse,
    patch: CasePatch | None,
    boundary_snapshot: dict[str, Any],
    model_error: str = "",
) -> dict[str, Any]:
    known_requirements = {str(item.get("requirement_id", "") or "") for item in review.evidence_requirements}
    known_sources = {item.source_id for item in state.accepted_evidence}
    if patch is not None:
        known_sources.update(item.source_id for item in patch.accepted_evidence)
        known_sources.update(item.source_id for item in patch.rejected_evidence)

    warnings: list[str] = []
    sanitized_items: list[dict[str, Any]] = []
    for item in output.get("priority_requirements") or []:
        if not isinstance(item, dict):
            continue
        requirement_id = str(item.get("requirement_id", "") or "").strip()
        if requirement_id and requirement_id not in known_requirements:
            warnings.append(f"LLM supervisor referenced unknown requirement_id: {requirement_id}")
        source_ids = [str(source_id).strip() for source_id in item.get("source_ids", []) or [] if str(source_id or "").strip()]
        unknown_sources = [source_id for source_id in source_ids if source_id not in known_sources]
        if unknown_sources:
            warnings.append(f"LLM supervisor referenced source_id outside current case: {', '.join(unknown_sources)}")
        sanitized_items.append(
            {
                "requirement_id": requirement_id,
                "label": str(item.get("label") or requirement_id),
                "status": str(item.get("status") or "missing"),
                "blocking": bool(item.get("blocking", True)),
                "why_now": _clean_text(str(item.get("why_now") or item.get("reason") or "当前优先补齐")),
                "source_ids": source_ids,
                "unknown_requirement": bool(requirement_id and requirement_id not in known_requirements),
                "unknown_source_ids": unknown_sources,
            }
        )

    strategy = _clean_text(str(output.get("strategy") or ""))
    suggested_prompt = _clean_text(str(output.get("suggested_user_prompt") or ""))
    next_action = str(output.get("next_action") or "collect_priority_evidence")
    if next_action not in {"collect_priority_evidence", "fix_rejected_policy_failures", "generate_final_reviewer_memo", "ask_clarifying_question", "escalate_to_human_reviewer"}:
        warnings.append(f"LLM supervisor proposed unsupported next_action: {next_action}")
    ready = bool(output.get("ready_for_final_memo", False))
    if ready and not boundary_snapshot.get("ready_for_final_memo"):
        warnings.append(
            "LLM supervisor claimed final memo readiness while the boundary snapshot is not ready; "
            "the model judgment is preserved for review."
        )

    return {
        "role": "case_supervisor",
        "planner": "llm_case_supervisor",
        "ready_for_final_memo": ready,
        "next_action": next_action,
        "priority_requirements": sanitized_items,
        "strategy": strategy,
        "suggested_user_prompt": suggested_prompt,
        "case_boundary_snapshot": boundary_snapshot,
        "model_confidence": _float_or_default(output.get("confidence"), 0.0),
        "model_warnings": warnings + [str(item) for item in output.get("warnings", []) or [] if str(item or "").strip()],
        "model_error": model_error,
        "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
    }


def _model_required_plan(boundary_snapshot: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "role": "case_supervisor",
        "planner": "model_required",
        "ready_for_final_memo": False,
        "next_action": "await_llm_case_supervisor",
        "priority_requirements": [],
        "strategy": "",
        "suggested_user_prompt": "",
        "case_boundary_snapshot": boundary_snapshot,
        "model_error": reason,
        "model_required": True,
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


CASE_SUPERVISOR_PROMPT = """Role: LLM Case Supervisor for an evidence-first ERP approval case.

You do not approve, reject, pay, route, comment, update suppliers, update budgets, sign contracts, or execute ERP actions.
You only propose the next case-planning step for a local approval dossier.

Use the current case_state, evidence requirements, policy failures, sufficiency report, control matrix, contradictions,
and current patch. Decide the most useful next step for the human user.

Return JSON only:
{
  "ready_for_final_memo": false,
  "next_action": "collect_priority_evidence|fix_rejected_policy_failures|generate_final_reviewer_memo|ask_clarifying_question|escalate_to_human_reviewer",
  "priority_requirements": [
    {
      "requirement_id": "known requirement_id only",
      "label": "中文短标签",
      "status": "missing|partial|conflict|satisfied|review_failed",
      "blocking": true,
      "why_now": "中文说明为什么下一步先处理它",
      "source_ids": []
    }
  ],
  "strategy": "中文案卷推进计划，说明优先级和原因",
  "suggested_user_prompt": "中文，建议用户下一轮可以怎么说或提交什么",
  "warnings": [],
  "confidence": 0.0,
  "non_action_statement": "This is a local approval case state update. No ERP write action was executed."
}

Rules:
- Reference only requirement_id values present in the input.
- Reference only source_id values present in current case evidence or current patch.
- If case_boundary_snapshot says not ready, do not claim ready_for_final_memo=true.
- If policy_failures are unresolved, prioritize fixing rejected policy failures.
- If blocking evidence is missing, prioritize the top 1-4 missing blocking requirements.
- Never include ERP execution wording.
- Keep explanations practical and concise.
"""


FORBIDDEN_PLAN_TERMS = (
    "execute",
    "executed",
    "approve in erp",
    "reject in erp",
    "send payment",
    "post comment",
    "route in erp",
    "activate supplier",
    "update budget",
    "sign contract",
    "执行审批",
    "执行付款",
    "写入erp",
    "通过erp",
    "驳回erp",
    "发送评论",
    "激活供应商",
    "更新预算",
    "签署合同",
)


def _clean_text(value: str) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_PLAN_TERMS):
        return "该建议包含 ERP 执行语义，不能作为审批资料专员的案卷推进回复。"
    return text


def _float_or_default(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))
