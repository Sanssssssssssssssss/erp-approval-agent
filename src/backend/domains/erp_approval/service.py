from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from typing import Any

from pydantic import ValidationError

from src.backend.domains.erp_approval.schemas import (
    ApprovalContextBundle,
    ApprovalGuardResult,
    ApprovalRecommendation,
    ApprovalRequest,
)


FINAL_ACTION_TERMS = {
    "approve",
    "reject",
    "final_approve",
    "final_reject",
    "execute_approve",
    "execute_reject",
    "approve_request",
    "reject_request",
    "issue_payment",
    "execute_payment",
    "release_payment",
    "onboard_supplier",
    "activate_supplier",
    "update_budget",
    "execute_budget",
    "execute_contract",
    "sign_contract",
}
FINAL_ACTION_KEYWORDS = ("approve", "reject", "payment", "supplier", "vendor", "budget", "contract")

STATUS_LABELS = {
    "recommend_approve": "建议通过",
    "recommend_reject": "建议拒绝",
    "request_more_info": "需要补充信息",
    "escalate": "升级人工复核",
    "blocked": "已阻断",
}

NEXT_ACTION_LABELS = {
    "none": "暂无下一步草案",
    "request_more_info": "请求补充信息",
    "route_to_manager": "转交经理复核",
    "route_to_finance": "转交财务复核",
    "route_to_procurement": "转交采购复核",
    "route_to_legal": "转交法务复核",
    "manual_review": "人工复核",
}

APPROVAL_TYPE_LABELS = {
    "expense": "费用报销",
    "purchase_requisition": "采购申请",
    "invoice_payment": "发票付款",
    "supplier_onboarding": "供应商准入",
    "contract_exception": "合同例外",
    "budget_exception": "预算例外",
    "unknown": "未知类型",
}

COMMON_TEXT_LABELS = {
    "valid structured approval recommendation": "有效的结构化审批建议",
    "budget owner confirmation": "预算负责人确认",
    "approval_request record is missing": "缺少审批请求记录",
    "approval_request record": "审批请求记录",
    "requester identity": "申请人身份",
    "requester": "申请人",
    "budget": "预算",
    "vendor": "供应商",
    "policy": "政策",
    "manual review": "人工复核",
    "unparsed_model_output": "模型输出未能解析",
}


def extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "")
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("No JSON object found")


def parse_approval_request(text: str, raw_user_message: str) -> ApprovalRequest:
    try:
        payload = extract_json_object(text)
        request = ApprovalRequest.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        request = ApprovalRequest(raw_request=str(raw_user_message or text or ""), business_purpose=str(raw_user_message or text or "")[:500])
    if str(raw_user_message or "").strip():
        request = request.model_copy(update={"raw_request": str(raw_user_message or "")})
    elif not request.raw_request:
        request = request.model_copy(update={"raw_request": str(text or "")})
    return _apply_deterministic_request_hints(request, str(raw_user_message or text or ""))


def parse_recommendation(text: str) -> ApprovalRecommendation:
    try:
        payload = extract_json_object(text)
        return ApprovalRecommendation.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        return ApprovalRecommendation(
            status="request_more_info",
            confidence=0.0,
            summary="模型输出没有符合 ERP 审批建议 JSON 结构，因此已转为保守建议。",
            rationale=["由于模型输出无法解析为结构化审批建议，系统采用需要补充信息的保守结果。"],
            missing_information=["有效的结构化审批建议"],
            risk_flags=["模型输出未能解析"],
            citations=[],
            proposed_next_action="request_more_info",
            human_review_required=True,
        )


def build_contextual_fallback_recommendation(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
) -> ApprovalRecommendation:
    """Build a conservative, context-grounded fallback when model JSON parsing fails."""

    source_ids = [record.source_id for record in context.records]
    by_type = {record.record_type: [] for record in context.records}
    for record in context.records:
        by_type.setdefault(record.record_type, []).append(record)

    approval_id = request.approval_id or "未识别审批单"
    if request.approval_type == "contract_exception":
        return ApprovalRecommendation(
            status="escalate",
            confidence=0.45,
            summary=f"合同例外 {approval_id} 涉及非标准责任上限或终止条款，建议升级法务复核。",
            rationale=[
                "合同例外通常需要法务判断条款风险，Agent 不能替代最终法律审批。",
                "当前上下文包含合同例外记录和审批矩阵/采购政策，可形成升级复核建议。",
            ],
            missing_information=[],
            risk_flags=["非标准责任条款可能扩大公司义务或损失暴露。", "终止条款例外需要法务确认。"],
            citations=_preferred_citations(source_ids, ("contract", "approval_request", "approval_matrix", "procurement_policy")),
            proposed_next_action="route_to_legal",
            human_review_required=True,
        )
    if request.approval_type == "invoice_payment" and all(by_type.get(key) for key in ("purchase_order", "goods_receipt", "invoice")):
        return ApprovalRecommendation(
            status="recommend_approve",
            confidence=0.72,
            summary=f"发票付款 {approval_id} 已找到 PO、GRN 和 invoice 三单记录，当前证据支持建议通过付款复核。",
            rationale=[
                "上下文同时包含采购订单、收货记录和发票记录，可支持三单匹配复核。",
                "发票付款政策要求比对 PO、GRN、invoice、供应商和金额。",
            ],
            missing_information=[],
            risk_flags=["仍需人工确认这是建议而非付款执行。"],
            citations=_preferred_citations(source_ids, ("purchase_order", "goods_receipt", "invoice", "invoice_payment_policy")),
            proposed_next_action="route_to_finance",
            human_review_required=True,
        )
    if request.approval_type == "budget_exception":
        return ApprovalRecommendation(
            status="escalate",
            confidence=0.5,
            summary=f"预算例外 {approval_id} 需要财务复核，不能由 Agent 自动判断通过。",
            rationale=["预算例外或资金不足需要财务审核。"],
            missing_information=[],
            risk_flags=["可能存在资金不足或预算例外风险。"],
            citations=_preferred_citations(source_ids, ("budget", "budget_policy", "approval_matrix")),
            proposed_next_action="route_to_finance",
            human_review_required=True,
        )
    return ApprovalRecommendation(
        status="request_more_info",
        confidence=0.0,
        summary=f"{approval_id} 的模型输出没有形成可解析 JSON，系统已按保守策略要求补充信息。",
        rationale=["模型调用已完成，但输出无法解析为结构化审批建议，因此不能直接展示为审批结论。"],
        missing_information=["可解析的结构化审批建议 JSON"],
        risk_flags=["模型输出格式异常"],
        citations=_preferred_citations(source_ids, ("approval_request", "approval_matrix")),
        proposed_next_action="request_more_info",
        human_review_required=True,
    )


def guard_recommendation(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
) -> tuple[ApprovalRecommendation, ApprovalGuardResult]:
    recommendation = repair_recommendation_with_context(request, context, recommendation)
    warnings: list[str] = []
    updates: dict[str, Any] = {}
    original_status = recommendation.status
    context_source_ids = {record.source_id for record in context.records}

    if recommendation.status == "recommend_approve" and recommendation.missing_information:
        updates["status"] = "request_more_info"
        updates["proposed_next_action"] = "request_more_info"
        updates["human_review_required"] = True
        warnings.append("recommend_approve downgraded because missing_information is present.")

    effective_status = str(updates.get("status", recommendation.status))
    if effective_status == "recommend_approve" and recommendation.confidence < 0.72:
        updates["status"] = "escalate"
        updates["proposed_next_action"] = "manual_review"
        updates["human_review_required"] = True
        warnings.append("recommend_approve downgraded because confidence is below 0.72.")

    proposed_action = str(updates.get("proposed_next_action", recommendation.proposed_next_action) or "")
    normalized_action = proposed_action.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_action in FINAL_ACTION_TERMS or normalized_action.startswith("execute_"):
        updates["proposed_next_action"] = "manual_review"
        updates["human_review_required"] = True
        warnings.append("Proposed irreversible ERP execution action replaced with manual_review.")
    elif normalized_action not in {
        "none",
        "request_more_info",
        "route_to_manager",
        "route_to_finance",
        "route_to_procurement",
        "route_to_legal",
        "manual_review",
    } and any(keyword in normalized_action for keyword in FINAL_ACTION_KEYWORDS):
        updates["proposed_next_action"] = "manual_review"
        updates["human_review_required"] = True
        warnings.append("Proposed ERP write-like action replaced with manual_review.")

    if not recommendation.citations:
        updates["human_review_required"] = True
        warnings.append("No citations were provided; human review is required.")
        if str(updates.get("status", recommendation.status)) == "recommend_approve":
            updates["status"] = "escalate"
            updates["proposed_next_action"] = "manual_review"
            warnings.append("recommend_approve downgraded because no citations were provided.")
    else:
        invalid_citations = [citation for citation in recommendation.citations if citation not in context_source_ids]
        if invalid_citations:
            updates["human_review_required"] = True
            warnings.append("Unknown citation source_id values: " + ", ".join(invalid_citations))
            if str(updates.get("status", recommendation.status)) == "recommend_approve":
                updates["status"] = "escalate"
                updates["proposed_next_action"] = "manual_review"
                warnings.append("recommend_approve downgraded because citations are outside the current context bundle.")

    final_status = str(updates.get("status", recommendation.status))
    if final_status in {"blocked", "recommend_reject", "escalate", "request_more_info"} or recommendation.missing_information:
        updates["human_review_required"] = True

    guarded = recommendation.model_copy(update=updates) if updates else recommendation
    guard = ApprovalGuardResult(
        passed=not warnings,
        downgraded=guarded.status != original_status,
        original_status=original_status,
        final_status=guarded.status,
        warnings=warnings,
        human_review_required=guarded.human_review_required,
    )
    return guarded, guard


def repair_recommendation_with_context(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
) -> ApprovalRecommendation:
    """Normalize fragile LLM output before deterministic guard checks.

    The LLM is allowed to reason first, but source IDs, object IDs, and blocking
    missing-information semantics must be tightened deterministically.
    """

    alias_map = _context_identifier_alias_map(request, context)
    context_source_ids = [record.source_id for record in context.records]

    def normalize_text(value: str) -> str:
        return _translate_business_terms(_replace_known_identifiers(_normalize_request_references(str(value or ""), request), alias_map))

    missing_information = [normalize_text(item) for item in recommendation.missing_information]
    risk_flags = [normalize_text(item) for item in recommendation.risk_flags]
    if recommendation.status == "recommend_approve" and missing_information:
        blocking_missing: list[str] = []
        non_blocking_notes: list[str] = []
        for item in missing_information:
            if _is_non_blocking_missing_item(item, request, context):
                non_blocking_notes.append(item)
            else:
                blocking_missing.append(item)
        missing_information = blocking_missing
        risk_flags = [*risk_flags, *[f"后续人工复核关注：{item}" for item in non_blocking_notes]]

    citations = _repair_citations(recommendation.citations, context_source_ids, alias_map)
    updates = {
        "summary": _enrich_summary_with_request_fields(request, normalize_text(recommendation.summary)),
        "rationale": [normalize_text(item) for item in recommendation.rationale],
        "missing_information": missing_information,
        "risk_flags": risk_flags,
        "citations": citations,
    }
    if (
        recommendation.status == "recommend_approve"
        and not missing_information
        and recommendation.proposed_next_action == "request_more_info"
    ):
        updates["proposed_next_action"] = _default_next_action_for_recommend_approve(request)
    return recommendation.model_copy(update=updates)


def validate_approval_recommendation(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
) -> tuple[ApprovalRecommendation, ApprovalGuardResult]:
    return guard_recommendation(request, context, recommendation)


def render_recommendation(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
    guard: ApprovalGuardResult,
) -> str:
    model_citations = list(recommendation.citations)
    fallback_sources = [] if model_citations else [record.source_id for record in context.records[:2]]
    status_label = STATUS_LABELS.get(str(recommendation.status), str(recommendation.status))
    next_action_label = NEXT_ACTION_LABELS.get(str(recommendation.proposed_next_action), str(recommendation.proposed_next_action))
    approval_type_label = APPROVAL_TYPE_LABELS.get(str(request.approval_type), str(request.approval_type))
    summary = _recommendation_summary_cn(request, recommendation)
    lines = [
        "## ERP 审批建议",
        "",
        f"- 审批单：{approval_type_label} / {request.approval_id or '未识别'}",
        f"- 当前建议：{status_label}",
        f"- 置信度：{recommendation.confidence:.2f}",
        f"- 建议下一步：{next_action_label}",
        f"- 是否需要人工复核：{'需要' if recommendation.human_review_required else '不需要'}",
        "",
        f"### 结论摘要\n{summary}",
    ]
    rationale = [
        _friendly_text(_normalize_request_references(item, request))
        for item in recommendation.rationale
        if _should_show_model_text(item)
    ]
    if rationale:
        lines.extend(["", "### 推理依据"])
        lines.extend(f"- {item}" for item in rationale)
    if recommendation.missing_information:
        lines.extend(["", "### 需要补充的信息"])
        lines.extend(f"- {_friendly_text(_normalize_request_references(item, request))}" for item in recommendation.missing_information)
    if recommendation.risk_flags:
        lines.extend(["", "### 风险点"])
        lines.extend(f"- {_friendly_text(_normalize_request_references(item, request))}" for item in recommendation.risk_flags)
    if guard.warnings:
        lines.extend(["", "### Guard 校验提示"])
        lines.extend(f"- {_friendly_text(_normalize_request_references(item, request))}" for item in guard.warnings)
    lines.extend(["", "### 证据引用"])
    if model_citations:
        lines.extend(f"- {item}" for item in model_citations)
    else:
        lines.append("- 模型没有提供 citation；下面仅列出系统 fallback 的上下文来源。")
    if fallback_sources:
        lines.extend(["", "### Fallback 上下文来源（不是模型 citation）"])
        lines.extend(f"- {item}" for item in fallback_sources)
    lines.extend(
        [
            "",
            "### 重要边界",
            "- 这是审批建议，不是 ERP 最终审批结果。",
            "- 未执行任何 ERP 通过、驳回、付款、供应商、合同或预算写入动作。",
        ]
    )
    return "\n".join(lines).strip()


def _apply_deterministic_request_hints(request: ApprovalRequest, raw_message: str) -> ApprovalRequest:
    raw = str(raw_message or "")
    updates: dict[str, Any] = {}

    approval_id = _first_match(raw, r"\b(?:PR|PO|EXP|INV|VEND|CON|BUD)-?\d+\b")
    if approval_id and (not request.approval_id or request.approval_id != approval_id):
        updates["approval_id"] = approval_id

    approval_type = _approval_type_from_text(raw)
    if approval_type != "unknown" and (request.approval_type == "unknown" or not request.approval_type):
        updates["approval_type"] = approval_type

    department = _first_group(raw, r"(?:申请部门|部门)\s*[:：]?\s*([A-Za-z0-9_\-\u4e00-\u9fff ]+?)(?:[,，。；;]|金额|供应商|成本中心|用途|$)")
    if department and not request.department:
        updates["department"] = department.strip()

    requester = _first_group(raw, r"(?:申请人|requester)\s*[:：]?\s*([A-Za-z0-9_\-\u4e00-\u9fff ]+?)(?:[,，。；;]|部门|金额|供应商|成本中心|用途|$)")
    if requester and not request.requester:
        updates["requester"] = requester.strip()

    vendor = _last_group(raw, r"(?:供应商|vendor)\s*[:：]?\s*([A-Za-z0-9_\-\u4e00-\u9fff &.]+?)(?:[,，。；;]|成本中心|用途|金额|请关注|$)")
    if vendor and request.vendor != vendor.strip():
        updates["vendor"] = vendor.strip()

    cost_center = _first_group(raw, r"(?:成本中心|cost\s*center)\s*[:：]?\s*([A-Za-z0-9_\-]+)")
    if cost_center and not request.cost_center:
        updates["cost_center"] = cost_center.strip()

    purpose = _first_group(raw, r"(?:用途是|用途|用于|business purpose)\s*[:：]?\s*([^,，。；;]+)")
    if purpose and (
        not request.business_purpose
        or request.business_purpose.strip() == raw.strip()
        or len(request.business_purpose.strip()) > max(120, len(purpose.strip()) * 3)
    ):
        updates["business_purpose"] = purpose.strip()

    amount_match = re.search(
        r"(?:金额|amount)\s*[:：]?\s*(?:USD|US\$|\$)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(USD|CNY|RMB|EUR|GBP)?",
        raw,
        re.IGNORECASE,
    ) or re.search(r"(?:USD|US\$|\$)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(USD|CNY|RMB|EUR|GBP)?", raw, re.IGNORECASE)
    if amount_match:
        raw_amount = float(amount_match.group(1).replace(",", ""))
        if request.amount is None or abs(float(request.amount) - raw_amount) > 0.001:
            updates["amount"] = raw_amount
    if amount_match and not request.currency:
        currency = (amount_match.group(2) or ("USD" if "$" in amount_match.group(0) else "")).upper()
        if currency == "RMB":
            currency = "CNY"
        updates["currency"] = currency

    if raw and not request.raw_request:
        updates["raw_request"] = raw
    return request.model_copy(update=updates) if updates else request


def _approval_type_from_text(text: str) -> str:
    lower = text.lower()
    id_match = re.search(r"\b(PR|EXP|INV|VEND|CON|BUD)-?\d+\b", text, re.IGNORECASE)
    if id_match:
        prefix = id_match.group(1).upper()
        if prefix == "PR":
            return "purchase_requisition"
        if prefix == "EXP":
            return "expense"
        if prefix == "INV":
            return "invoice_payment"
        if prefix == "VEND":
            return "supplier_onboarding"
        if prefix == "CON":
            return "contract_exception"
        if prefix == "BUD":
            return "budget_exception"
    if any(token in text for token in ("采购申请", "采购审批")) or "purchase requisition" in lower or re.search(r"\bPR-\d+\b", text):
        return "purchase_requisition"
    if any(token in text for token in ("费用报销", "报销")) or "expense" in lower:
        return "expense"
    if any(token in text for token in ("发票付款", "付款申请")) or "invoice" in lower:
        return "invoice_payment"
    if any(token in text for token in ("供应商准入", "供应商 onboarding")) or "vendor onboarding" in lower:
        return "supplier_onboarding"
    if "合同例外" in text or "contract exception" in lower:
        return "contract_exception"
    if "预算例外" in text or "budget exception" in lower:
        return "budget_exception"
    return "unknown"


def _first_match(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _first_group(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _last_group(text: str, pattern: str) -> str:
    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    return matches[-1].group(1).strip() if matches else ""


def _recommendation_summary_cn(request: ApprovalRequest, recommendation: ApprovalRecommendation) -> str:
    if _should_show_model_text(recommendation.summary):
        return _friendly_text(_normalize_request_references(recommendation.summary, request))
    if recommendation.status == "recommend_approve":
        return "当前证据支持“建议通过”，但这只是 Agent 建议，不会执行 ERP 审批动作。"
    if recommendation.status == "recommend_reject":
        return "当前证据支持“建议拒绝”，但仍需要人工复核后再决定。"
    if recommendation.status == "request_more_info":
        return "当前信息不足，建议先补充关键信息，再继续审批判断。"
    if recommendation.status == "escalate":
        return "当前风险或证据不足以由 Agent 单独判断，建议升级给人工复核。"
    if recommendation.status == "blocked":
        return "当前审批建议被 guard 阻断，不能作为可执行建议使用。"
    return "当前仅生成审批建议，没有执行任何 ERP 动作。"


def _should_show_model_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _friendly_text(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return "无"
    if value.startswith("Unknown citation source_id values:"):
        return value.replace("Unknown citation source_id values:", "模型引用了不属于当前上下文的 citation：", 1)
    warning_labels = {
        "recommend_approve downgraded because missing_information is present.": "由于仍有缺失信息，系统已把“建议通过”降级为补充信息。",
        "recommend_approve downgraded because confidence is below 0.72.": "由于置信度低于 0.72，系统已把“建议通过”降级为人工复核。",
        "Proposed irreversible ERP execution action replaced with manual_review.": "检测到不可逆 ERP 执行动作，已替换为人工复核。",
        "Proposed ERP write-like action replaced with manual_review.": "检测到类似 ERP 写入的动作，已替换为人工复核。",
        "No citations were provided; human review is required.": "模型没有提供 citation，因此必须人工复核。",
        "recommend_approve downgraded because no citations were provided.": "由于没有 citation，系统已把“建议通过”降级为人工复核。",
        "recommend_approve downgraded because citations are outside the current context bundle.": "由于 citation 不属于当前上下文，系统已把“建议通过”降级为人工复核。",
    }
    if value in warning_labels:
        return warning_labels[value]
    lowered = value.lower()
    if lowered in COMMON_TEXT_LABELS:
        return COMMON_TEXT_LABELS[lowered]
    rendered = value if "://" in value else value.replace("_", " ")
    replacements = {
        "recommend approve": "建议通过",
        "request more info": "请求补充信息",
        "manual review": "人工复核",
        "approval request": "审批请求",
        "requester": "申请人",
        "vendor": "供应商",
        "budget": "预算",
        "policy": "政策",
        "citation": "证据引用",
    }
    for source, target in replacements.items():
        rendered = re.sub(source, target, rendered, flags=re.IGNORECASE)
    return rendered


def _translate_business_terms(text: str) -> str:
    rendered = str(text or "")
    replacements = {
        "client travel": "客户差旅",
        "replacement laptops": "更换笔记本电脑",
        "accelerated implementation support": "加速实施支持",
    }
    for source, target in replacements.items():
        rendered = re.sub(re.escape(source), target, rendered, flags=re.IGNORECASE)
    return rendered


def _enrich_summary_with_request_fields(request: ApprovalRequest, summary: str) -> str:
    rendered = str(summary or "").strip()
    additions: list[str] = []
    if request.department and request.department not in rendered:
        additions.append(f"申请部门：{request.department}")
    if request.vendor and request.vendor not in rendered:
        additions.append(f"供应商：{request.vendor}")
    if request.cost_center and request.cost_center not in rendered:
        additions.append(f"成本中心：{request.cost_center}")
    if not additions:
        return rendered
    return f"{rendered}（{'; '.join(additions)}）" if rendered else "；".join(additions)


def _normalize_request_references(text: str, request: ApprovalRequest) -> str:
    value = str(text or "")
    approval_id = str(request.approval_id or "").strip()
    match = re.match(r"^([A-Za-z]+)-(\d{3,})$", approval_id)
    if not match:
        return value
    prefix, digits = match.groups()
    truncated = f"{prefix}-{digits[:-1]}"
    pattern = re.compile(rf"\b{re.escape(truncated)}\b(?!\d)", re.IGNORECASE)
    return pattern.sub(approval_id, value)


def _context_identifier_alias_map(request: ApprovalRequest, context: ApprovalContextBundle) -> dict[str, str]:
    aliases: dict[str, str] = {}
    identifiers = [str(request.approval_id or "").strip()]
    for record in context.records:
        source_id = str(record.source_id or "").strip()
        if source_id:
            identifiers.append(source_id.rsplit("/", 1)[-1])
        metadata = dict(record.metadata or {})
        for value in metadata.values():
            if isinstance(value, str):
                identifiers.append(value.strip())
            elif isinstance(value, list):
                identifiers.extend(str(item).strip() for item in value if str(item or "").strip())
    for identifier in identifiers:
        if not identifier:
            continue
        match = re.match(r"^([A-Za-z]+)-(\d{3,})$", identifier)
        if match:
            prefix, digits = match.groups()
            aliases[f"{prefix}-{digits[:-1]}"] = identifier
        normalized_vendor = identifier.strip().lower().replace(" ", "-").replace("_", "-")
        if normalized_vendor and normalized_vendor != identifier:
            aliases[normalized_vendor] = identifier
    return aliases


def _replace_known_identifiers(text: str, alias_map: dict[str, str]) -> str:
    rendered = str(text or "")
    for alias, canonical in sorted(alias_map.items(), key=lambda item: len(item[0]), reverse=True):
        if not alias or not canonical or alias == canonical:
            continue
        pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(alias)}(?![A-Za-z0-9_-])", re.IGNORECASE)
        rendered = pattern.sub(lambda _match, value=canonical: value, rendered)
    return rendered


def _repair_citations(
    citations: list[str],
    context_source_ids: list[str],
    alias_map: dict[str, str],
) -> list[str]:
    repaired: list[str] = []
    seen: set[str] = set()
    context_set = set(context_source_ids)
    for item in citations:
        candidate = _replace_known_identifiers(str(item or "").strip(), alias_map)
        if not candidate:
            continue
        if candidate not in context_set:
            candidate = _closest_context_source_id(candidate, context_source_ids) or candidate
        if candidate and candidate not in seen:
            seen.add(candidate)
            repaired.append(candidate)
    return repaired


def _closest_context_source_id(candidate: str, context_source_ids: list[str]) -> str:
    normalized_candidate = _source_id_similarity_key(candidate)
    best_score = 0.0
    best_source = ""
    for source_id in context_source_ids:
        score = SequenceMatcher(None, normalized_candidate, _source_id_similarity_key(source_id)).ratio()
        if score > best_score:
            best_score = score
            best_source = source_id
    return best_source if best_score >= 0.84 else ""


def _source_id_similarity_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _is_non_blocking_missing_item(
    item: str,
    request: ApprovalRequest,
    context: ApprovalContextBundle,
) -> bool:
    value = str(item or "").strip().lower()
    if not value:
        return True
    context_text = "\n".join(
        [
            str(request.model_dump()),
            *[record.content for record in context.records],
            *[json.dumps(record.metadata, ensure_ascii=False) for record in context.records],
        ]
    ).lower()
    if any(term in value for term in ("direct manager", "manager confirmation", "经理", "直接经理", "审批人", "approver")):
        return True
    if any(term in value for term in ("approval matrix", "审批矩阵", "threshold", "阈值", "审批层级")):
        return True
    if any(term in value for term in ("po generation", "purchase order generation", "采购订单生成", "生成后的", "future po")):
        return True
    if any(term in value for term in ("requester", "申请人")) and any(term in context_text for term in ("requester", "申请人")):
        return True
    return False


def _default_next_action_for_recommend_approve(request: ApprovalRequest) -> str:
    if request.approval_type == "invoice_payment":
        return "route_to_finance"
    if request.approval_type == "purchase_requisition":
        return "route_to_procurement"
    if request.approval_type == "expense":
        return "route_to_manager"
    if request.approval_type == "supplier_onboarding":
        return "route_to_procurement"
    if request.approval_type == "contract_exception":
        return "route_to_legal"
    if request.approval_type == "budget_exception":
        return "route_to_finance"
    return "manual_review"


def _preferred_citations(source_ids: list[str], keywords: tuple[str, ...]) -> list[str]:
    selected: list[str] = []
    for keyword in keywords:
        for source_id in source_ids:
            if keyword in source_id and source_id not in selected:
                selected.append(source_id)
    if selected:
        return selected
    return source_ids[:3]
