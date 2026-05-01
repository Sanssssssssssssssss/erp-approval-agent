from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.backend.domains.erp_approval.schemas import (
    ACTION_PROPOSAL_NON_ACTION_STATEMENT,
    ApprovalActionProposal,
    ApprovalActionProposalBundle,
    ApprovalActionValidationResult,
    ApprovalContextBundle,
    ApprovalGuardResult,
    ApprovalRecommendation,
    ApprovalRequest,
)


ALLOWED_ACTION_TYPES = {
    "none",
    "request_more_info",
    "add_internal_comment",
    "route_to_manager",
    "route_to_finance",
    "route_to_procurement",
    "route_to_legal",
    "manual_review",
}

DANGEROUS_EXECUTION_PATTERNS = (
    re.compile(r"\bexecute[_\s-]*(approve|reject|payment|budget|contract|supplier|vendor)\b", re.IGNORECASE),
    re.compile(r"\b(final[_\s-]*)?(approve|reject)[_\s-]*(request|approval|document|invoice|payment)?\b", re.IGNORECASE),
    re.compile(r"\b(issue|release|send|execute|process)[_\s-]*payment\b", re.IGNORECASE),
    re.compile(r"\bpayment[_\s-]*(issue|release|send|execute|process)\b", re.IGNORECASE),
    re.compile(r"\b(activate|onboard|enable)[_\s-]*(supplier|vendor)\b", re.IGNORECASE),
    re.compile(r"\b(supplier|vendor)[_\s-]*(activation|activate|onboarding|onboard|enable)\b", re.IGNORECASE),
    re.compile(r"\b(update|change|commit)[_\s-]*budget\b", re.IGNORECASE),
    re.compile(r"\bbudget[_\s-]*(update|change|commit)\b", re.IGNORECASE),
    re.compile(r"\b(sign|execute|commit)[_\s-]*contract\b", re.IGNORECASE),
    re.compile(r"\bcontract[_\s-]*(sign|execute|commit)\b", re.IGNORECASE),
)


def build_action_proposals(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
    guard: ApprovalGuardResult,
    review_status: str,
) -> ApprovalActionProposalBundle:
    del context
    action_type = _action_type_for_recommendation(recommendation)
    if action_type == "none":
        return ApprovalActionProposalBundle(request_id=request.approval_id, review_status=review_status, proposals=[])

    target = _target_for_action(action_type, request)
    payload_preview = _payload_preview_for_action(action_type, request, recommendation, guard)
    requires_review = (
        recommendation.human_review_required
        or guard.human_review_required
        or recommendation.status in {"blocked", "recommend_reject", "escalate", "request_more_info"}
        or action_type != "none"
    )
    risk_level = _risk_level_for_proposal(recommendation, guard, action_type)
    idempotency = _idempotency_fields(request=request, action_type=action_type, target=target, payload_preview=payload_preview)
    proposal = ApprovalActionProposal(
        proposal_id=f"erp-action-proposal-{idempotency['idempotency_fingerprint'][:12]}",
        action_type=action_type,
        status="proposed_only",
        title=_title_for_action(action_type),
        summary=_summary_for_action(action_type, recommendation),
        target=target,
        payload_preview=payload_preview,
        citations=list(recommendation.citations),
        idempotency_key=idempotency["idempotency_key"],
        idempotency_scope=idempotency["idempotency_scope"],
        idempotency_fingerprint=idempotency["idempotency_fingerprint"],
        risk_level=risk_level,
        requires_human_review=requires_review,
        executable=False,
        non_action_statement=ACTION_PROPOSAL_NON_ACTION_STATEMENT,
    )
    return ApprovalActionProposalBundle(
        request_id=request.approval_id,
        review_status=review_status,
        proposals=[proposal],
    )


def validate_action_proposals(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    bundle: ApprovalActionProposalBundle,
) -> tuple[ApprovalActionProposalBundle, ApprovalActionValidationResult]:
    del request
    context_source_ids = {record.source_id for record in context.records}
    warnings: list[str] = []
    blocked: list[str] = []
    rejected: list[str] = []
    proposals: list[ApprovalActionProposal] = []

    for proposal in bundle.proposals:
        proposal_id = proposal.proposal_id or "unidentified"
        updates: dict[str, Any] = {
            "executable": False,
            "non_action_statement": ACTION_PROPOSAL_NON_ACTION_STATEMENT,
        }
        action_type = str(getattr(proposal, "action_type", "") or "")

        if action_type not in ALLOWED_ACTION_TYPES:
            updates["status"] = "rejected_by_validation"
            rejected.append(proposal_id)
            warnings.append(f"{proposal_id}: action_type is not allowed: {action_type}")

        invalid_citations = [citation for citation in proposal.citations if citation not in context_source_ids]
        if invalid_citations:
            updates["status"] = "rejected_by_validation"
            rejected.append(proposal_id)
            warnings.append(f"{proposal_id}: citations are outside the current context bundle: {', '.join(invalid_citations)}")

        if _payload_has_execution_semantics(proposal.payload_preview):
            updates["status"] = "blocked"
            blocked.append(proposal_id)
            warnings.append(f"{proposal_id}: payload_preview contains ERP execution semantics and was blocked.")

        if not proposal.idempotency_key or not proposal.idempotency_fingerprint:
            updates["status"] = "rejected_by_validation"
            rejected.append(proposal_id)
            warnings.append(f"{proposal_id}: idempotency fields are required.")

        proposals.append(proposal.model_copy(update=updates))

    blocked_unique = sorted(set(blocked))
    rejected_unique = sorted(set(rejected))
    result = ApprovalActionValidationResult(
        passed=not blocked_unique and not rejected_unique and not warnings,
        warnings=warnings,
        blocked_proposal_ids=blocked_unique,
        rejected_proposal_ids=rejected_unique,
    )
    return bundle.model_copy(update={"proposals": proposals, "non_action_statement": ACTION_PROPOSAL_NON_ACTION_STATEMENT}), result


def render_action_proposals(
    bundle: ApprovalActionProposalBundle,
    validation: ApprovalActionValidationResult,
) -> str:
    lines = [
        "## 后续动作草案",
        "",
        "以下内容只是本地草案，不会触发工具调用，也不会写入 ERP。",
        "未执行任何 ERP 写入动作。",
    ]
    if not bundle.proposals:
        lines.extend(["", "- 无可用动作草案。"])
    for proposal in bundle.proposals:
        lines.extend(
            [
                "",
                f"- proposal_id：{proposal.proposal_id}",
                f"  动作类型：{_action_type_label(str(proposal.action_type))}",
                f"  状态：{_proposal_status_label(str(proposal.status))}",
                f"  摘要：{_proposal_summary_cn(proposal.action_type, proposal.summary)}",
                f"  需要人工复核：{'需要' if proposal.requires_human_review else '不需要'}",
                f"  可执行：{'false' if not proposal.executable else 'true'}",
                f"  幂等键：{proposal.idempotency_key}",
            ]
        )
    if validation.warnings:
        lines.extend(["", "### 动作草案校验提示"])
        lines.extend(f"- {_warning_cn(warning)}" for warning in validation.warnings)
    return "\n".join(lines).strip()


def _action_type_label(action_type: str) -> str:
    labels = {
        "none": "无",
        "request_more_info": "请求补充信息草案",
        "add_internal_comment": "内部备注草案",
        "route_to_manager": "转交经理复核草案",
        "route_to_finance": "转交财务复核草案",
        "route_to_procurement": "转交采购复核草案",
        "route_to_legal": "转交法务复核草案",
        "manual_review": "人工复核草案",
    }
    return labels.get(action_type, action_type)


def _proposal_status_label(status: str) -> str:
    labels = {
        "proposed_only": "仅草案",
        "blocked": "已阻断",
        "rejected_by_validation": "校验拒绝",
    }
    return labels.get(status, status)


def _proposal_summary_cn(action_type: str, summary: str) -> str:
    value = str(summary or "")
    prefix_replacements = {
        "Prepare a request for more information:": "准备一份补充信息请求草案，内容包括：",
        "Prepare an internal comment draft:": "准备一份内部备注草案，内容包括：",
        "Prepare a routing draft:": "准备一份转交复核草案，内容包括：",
        "Prepare a manual review entry:": "准备一份人工复核草案，内容包括：",
    }
    for source, target in prefix_replacements.items():
        if value.startswith(source):
            return f"{target}{value.removeprefix(source).strip()}".strip()
    if any("\u4e00" <= char <= "\u9fff" for char in str(summary or "")):
        return value
    labels = {
        "request_more_info": "准备一份补充信息请求草案，但不会发送。",
        "add_internal_comment": "准备一份内部备注草案，但不会写入 ERP。",
        "route_to_manager": "准备一份转交经理复核草案，但不会实际转交。",
        "route_to_finance": "准备一份转交财务复核草案，但不会实际转交。",
        "route_to_procurement": "准备一份转交采购复核草案，但不会实际转交。",
        "route_to_legal": "准备一份转交法务复核草案，但不会实际转交。",
        "manual_review": "准备一份人工复核草案，但不会执行 ERP 动作。",
    }
    return labels.get(str(action_type), "没有可展示摘要。")


def _warning_cn(warning: str) -> str:
    value = str(warning or "")
    if any("\u4e00" <= char <= "\u9fff" for char in value):
        return value
    return (
        value.replace("Human reviewer rejected the agent recommendation; no action proposals were generated.", "人工复核人拒绝了 Agent 建议，因此没有生成动作草案。")
        .replace("payload_preview contains ERP execution semantics and was blocked.", "payload_preview 包含 ERP 执行语义，已被阻断。")
        .replace("idempotency fields are required.", "缺少必需的幂等字段。")
        .replace("citations are outside the current context bundle", "citation 不属于当前上下文包")
    )


def _action_type_for_recommendation(recommendation: ApprovalRecommendation) -> str:
    if recommendation.status == "recommend_approve":
        return "manual_review" if recommendation.proposed_next_action == "manual_review" else "add_internal_comment"
    if recommendation.status in {"blocked", "recommend_reject", "escalate"}:
        return "manual_review"
    proposed = str(recommendation.proposed_next_action or "none")
    if proposed in {"request_more_info", "route_to_manager", "route_to_finance", "route_to_procurement", "route_to_legal", "manual_review"}:
        return proposed
    return "none"


def _target_for_action(action_type: str, request: ApprovalRequest) -> str:
    if action_type == "request_more_info":
        return request.requester or "requester"
    if action_type == "route_to_manager":
        return "manager"
    if action_type == "route_to_finance":
        return "finance"
    if action_type == "route_to_procurement":
        return "procurement"
    if action_type == "route_to_legal":
        return "legal"
    if action_type == "add_internal_comment":
        return "approval_workbench"
    if action_type == "manual_review":
        return "manual_review_queue"
    return "none"


def _payload_preview_for_action(
    action_type: str,
    request: ApprovalRequest,
    recommendation: ApprovalRecommendation,
    guard: ApprovalGuardResult,
) -> dict[str, Any]:
    base = {
        "approval_id": request.approval_id,
        "approval_type": request.approval_type,
        "recommendation_status": recommendation.status,
        "non_action": True,
    }
    if action_type == "request_more_info":
        return {
            **base,
            "missing_information": list(recommendation.missing_information),
            "message_draft": "Request additional information before any ERP write action is considered.",
        }
    if action_type.startswith("route_to_"):
        return {
            **base,
            "route_target": action_type.replace("route_to_", ""),
            "reason": recommendation.summary,
        }
    if action_type == "add_internal_comment":
        return {
            **base,
            "comment_draft": recommendation.summary,
            "guard_warnings": list(guard.warnings),
        }
    if action_type == "manual_review":
        return {
            **base,
            "review_reason": recommendation.summary or "Manual review required by validation guard.",
            "guard_warnings": list(guard.warnings),
        }
    return base


def _title_for_action(action_type: str) -> str:
    titles = {
        "request_more_info": "Request more information proposal",
        "add_internal_comment": "Internal comment proposal",
        "route_to_manager": "Manager routing proposal",
        "route_to_finance": "Finance routing proposal",
        "route_to_procurement": "Procurement routing proposal",
        "route_to_legal": "Legal routing proposal",
        "manual_review": "Manual review proposal",
    }
    return titles.get(action_type, "No action proposal")


def _summary_for_action(action_type: str, recommendation: ApprovalRecommendation) -> str:
    if action_type == "request_more_info":
        missing = ", ".join(recommendation.missing_information) or "additional approval evidence"
        return f"Prepare a request for more information: {missing}."
    if action_type.startswith("route_to_"):
        return f"Prepare a routing proposal based on the recommendation: {recommendation.summary}"
    if action_type == "add_internal_comment":
        return f"Prepare an internal comment summarizing the recommendation: {recommendation.summary}"
    if action_type == "manual_review":
        return f"Prepare a manual review proposal: {recommendation.summary}"
    return "No follow-up action proposal is available."


def _risk_level_for_proposal(
    recommendation: ApprovalRecommendation,
    guard: ApprovalGuardResult,
    action_type: str,
) -> str:
    if recommendation.status in {"blocked", "recommend_reject", "escalate"} or guard.warnings:
        return "high"
    if action_type in {"route_to_finance", "route_to_legal", "manual_review", "request_more_info"}:
        return "medium"
    return "low"


def _idempotency_fields(
    *,
    request: ApprovalRequest,
    action_type: str,
    target: str,
    payload_preview: dict[str, Any],
) -> dict[str, str]:
    approval_id = request.approval_id or "unidentified"
    scope = f"approval_action_proposal:{approval_id}:{action_type}:{target}"
    source = {
        "approval_id": approval_id,
        "action_type": action_type,
        "target": target,
        "payload_preview": payload_preview,
    }
    fingerprint = hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "idempotency_scope": scope,
        "idempotency_fingerprint": fingerprint,
        "idempotency_key": f"{scope}:{fingerprint[:16]}",
    }


def _payload_has_execution_semantics(payload: Any) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True) if isinstance(payload, (dict, list)) else str(payload or "")
    normalized = rendered.replace("\\", " ")
    return any(pattern.search(normalized) for pattern in DANGEROUS_EXECUTION_PATTERNS)
