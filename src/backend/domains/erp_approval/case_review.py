from __future__ import annotations

from collections.abc import Iterable

from src.backend.domains.erp_approval.case_models import (
    AdversarialReview,
    ApprovalCaseFile,
    ApprovalPathPlan,
    CASE_ANALYSIS_NON_ACTION_STATEMENT,
    RiskAssessment,
)
from src.backend.domains.erp_approval.control_matrix import evaluate_control_matrix
from src.backend.domains.erp_approval.evidence_claims import (
    build_evidence_artifacts,
    detect_contradictions,
    extract_claims_from_artifacts,
    link_claims_to_requirements,
)
from src.backend.domains.erp_approval.evidence_requirements import build_evidence_requirements
from src.backend.domains.erp_approval.evidence_sufficiency import evaluate_evidence_sufficiency
from src.backend.domains.erp_approval.schemas import (
    ApprovalContextBundle,
    ApprovalGuardResult,
    ApprovalRecommendation,
    ApprovalRequest,
)


STATUS_LABELS_CN = {
    "recommend_approve": "建议通过（仅建议，不执行）",
    "recommend_reject": "建议拒绝（仅建议，不执行）",
    "request_more_info": "要求补充材料",
    "escalate": "升级人工复核",
    "blocked": "阻断",
}

NEXT_ACTION_CN = {
    "none": "无",
    "request_more_info": "补充材料",
    "route_to_manager": "经理复核",
    "route_to_finance": "财务复核",
    "route_to_procurement": "采购复核",
    "route_to_legal": "法务复核",
    "manual_review": "人工复核",
}

APPROVAL_TYPE_CN = {
    "expense": "费用报销",
    "purchase_requisition": "采购申请",
    "invoice_payment": "发票付款",
    "supplier_onboarding": "供应商准入",
    "contract_exception": "合同例外",
    "budget_exception": "预算例外",
    "unknown": "未知审批",
}


def build_case_file(request: ApprovalRequest, context: ApprovalContextBundle) -> ApprovalCaseFile:
    context_source_ids = [record.source_id for record in context.records if record.source_id]
    context_header = _approval_request_header(context)
    approval_type = _first_non_empty(request.approval_type if request.approval_type != "unknown" else "", context_header.get("approval_type"), "unknown")
    approval_id = _first_non_empty(request.approval_id, context_header.get("approval_id"))
    case_id = f"erp-case:{approval_id or 'unidentified'}"
    return ApprovalCaseFile(
        case_id=case_id,
        approval_type=approval_type,
        approval_id=approval_id,
        request_header=request.model_dump(),
        line_items=_line_items_from_context(context_header),
        requester=_first_non_empty(request.requester, context_header.get("requester")),
        department=_first_non_empty(request.department, context_header.get("department")),
        amount=request.amount if request.amount is not None else _float_or_none(context_header.get("amount")),
        currency=_first_non_empty(request.currency, context_header.get("currency")),
        vendor=_first_non_empty(request.vendor, context_header.get("vendor_name"), context_header.get("vendor")),
        cost_center=_first_non_empty(request.cost_center, context_header.get("cost_center")),
        business_purpose=_first_non_empty(request.business_purpose, context_header.get("business_purpose"), context_header.get("purpose")),
        source_request=request.raw_request,
        context_source_ids=context_source_ids,
        non_action_statement=CASE_ANALYSIS_NON_ACTION_STATEMENT,
    )


def complete_case_analysis(case_file: ApprovalCaseFile) -> ApprovalCaseFile:
    requirements = list(case_file.evidence_requirements) or build_evidence_requirements(case_file)
    artifacts = list(case_file.evidence_artifacts)
    claims = list(case_file.evidence_claims)
    if not claims:
        claims = extract_claims_from_artifacts(case_file, artifacts)
    requirements, claims = link_claims_to_requirements(requirements, claims)
    contradictions = detect_contradictions(claims)
    sufficiency = evaluate_evidence_sufficiency(requirements, claims, contradictions)
    interim = case_file.model_copy(
        update={
            "evidence_requirements": requirements,
            "evidence_artifacts": artifacts,
            "evidence_claims": claims,
            "contradictions": contradictions,
            "evidence_sufficiency": sufficiency,
        }
    )
    control_matrix = evaluate_control_matrix(interim)
    risk = _build_risk_assessment(interim, control_matrix)
    approval_path = _build_approval_path(interim, control_matrix)
    return interim.model_copy(
        update={
            "control_checks": control_matrix.checks,
            "risk_assessment": risk,
            "approval_path": approval_path,
        }
    )


def build_case_file_from_request_context(request: ApprovalRequest, context: ApprovalContextBundle) -> ApprovalCaseFile:
    case_file = build_case_file(request, context)
    artifacts = build_evidence_artifacts(request, context)
    case_file = case_file.model_copy(update={"evidence_artifacts": artifacts})
    return complete_case_analysis(case_file)


def draft_recommendation_from_case(case_file: ApprovalCaseFile) -> ApprovalRecommendation:
    control_matrix = evaluate_control_matrix(case_file)
    citations = _supporting_source_ids(case_file)
    missing = _missing_information(case_file, control_matrix)
    risk_flags = _risk_flags(case_file, control_matrix)
    status = "request_more_info"
    confidence = min(0.45 + 0.45 * case_file.evidence_sufficiency.completeness_score, 0.86)
    next_action = "request_more_info"
    summary = "当前案件证据不足，不能形成通过建议。"
    rationale = [
        "审批建议必须由 ERP/政策/附件等证据支持；一句话用户描述只能创建案件草稿，不能证明审批可通过。",
        f"证据完整度为 {case_file.evidence_sufficiency.completeness_score:.2f}。",
    ]

    if case_file.contradictions.has_conflict:
        status = "escalate"
        next_action = "manual_review"
        summary = "当前案件存在证据冲突，不能形成通过建议。"
        risk_flags.append("存在证据冲突，需要人工核对。")
    elif any(check.severity == "critical" and check.status in {"fail", "conflict"} for check in control_matrix.checks):
        status = "blocked"
        next_action = "manual_review"
        summary = "关键控制项失败，当前审批案件被阻断。"
    elif control_matrix.high_risk:
        status = "escalate"
        next_action = _escalation_next_action(case_file)
        summary = "当前案件存在高风险或高严重度缺口，需要升级复核。"
    elif not case_file.evidence_sufficiency.passed:
        status = "request_more_info"
        next_action = "request_more_info"
    elif control_matrix.passed and citations and not case_file.contradictions.has_conflict:
        if case_file.approval_type == "contract_exception":
            status = "escalate"
            next_action = "route_to_legal"
            summary = "合同例外即使证据完整，也必须进入法务复核；当前仅形成复核建议，不执行 ERP 动作。"
            confidence = max(confidence, 0.76)
        elif case_file.approval_type == "budget_exception":
            status = "escalate"
            next_action = "route_to_finance"
            summary = "预算例外即使证据完整，也必须进入财务复核；当前仅形成复核建议，不执行 ERP 动作。"
            confidence = max(confidence, 0.76)
        else:
            status = "recommend_approve"
            next_action = _approve_next_action(case_file)
            summary = "当前证据链和控制矩阵均通过，可形成建议通过，但仍不执行 ERP 动作。"
            confidence = max(confidence, 0.78)
    elif control_matrix.failed_check_ids:
        status = "escalate"
        next_action = _escalation_next_action(case_file)
        summary = "控制矩阵仍有失败项，需要升级复核。"

    return ApprovalRecommendation(
        status=status,  # type: ignore[arg-type]
        confidence=round(float(confidence), 2),
        summary=summary,
        rationale=rationale + _top_control_explanations(control_matrix),
        missing_information=missing,
        risk_flags=_unique(risk_flags),
        citations=citations,
        proposed_next_action=next_action,  # type: ignore[arg-type]
        human_review_required=status != "recommend_approve" or control_matrix.high_risk,
    )


def adversarial_review_case(
    case_file: ApprovalCaseFile,
    recommendation: ApprovalRecommendation,
) -> tuple[ApprovalCaseFile, ApprovalRecommendation]:
    issues: list[str] = []
    challenged_claims: list[str] = []
    challenged_controls: list[str] = []
    risks: list[str] = []
    corrections: list[str] = []
    valid_sources = set(case_file.context_source_ids)
    if case_file.source_request:
        valid_sources.add("user_statement://current_request")

    if case_file.evidence_sufficiency.blocking_gaps:
        issues.append("仍存在 blocking evidence gaps。")
        corrections.extend(case_file.evidence_sufficiency.blocking_gaps)
    unsupported_citations = [citation for citation in recommendation.citations if citation not in valid_sources]
    if unsupported_citations:
        issues.append("recommendation 包含不属于当前 case context 的 citation。")
        corrections.append("移除或补充 unsupported citation: " + ", ".join(unsupported_citations))
    if recommendation.status == "recommend_approve" and (
        not case_file.evidence_sufficiency.passed
        or any(check.status in {"fail", "missing", "conflict"} and check.severity in {"high", "critical"} for check in case_file.control_checks)
        or case_file.contradictions.has_conflict
    ):
        issues.append("recommend_approve 过强，证据或控制矩阵尚未支持。")
        risks.append("审批建议强度超过证据充分性。")
    if recommendation.citations and all(str(citation).startswith("user_statement://") for citation in recommendation.citations):
        issues.append("不能只依赖用户陈述作为强证据。")
        risks.append("user_statement 被当作强证据。")
    prompt_boundary_issues = _prompt_boundary_issues(case_file.source_request)
    if prompt_boundary_issues:
        issues.extend(prompt_boundary_issues)
        risks.append("用户输入包含越权或 prompt-injection 风险，不能覆盖证据链和政策边界。")
        corrections.append("忽略用户关于跳过政策、跳过 citation、直接批准或执行 ERP 动作的指令。")
    if recommendation.proposed_next_action in {"none"} and recommendation.status in {"request_more_info", "escalate", "blocked"}:
        issues.append("next action 过弱，无法处理缺证据或风险。")
    for claim in case_file.evidence_claims:
        if claim.verification_status in {"unsupported", "conflict", "needs_review"}:
            challenged_claims.append(claim.claim_id)
    for check in case_file.control_checks:
        if check.status in {"fail", "missing", "conflict"}:
            challenged_controls.append(check.check_id)

    updates: dict[str, object] = {}
    if issues:
        updates["human_review_required"] = True
        if recommendation.status == "recommend_approve":
            updates["status"] = "escalate" if case_file.risk_assessment.risk_level in {"high", "critical"} else "request_more_info"
            updates["proposed_next_action"] = _escalation_next_action(case_file) if updates["status"] == "escalate" else "request_more_info"
            updates["summary"] = "自我挑战发现证据或控制缺口，已降级审批建议。"
            updates["missing_information"] = _unique([*recommendation.missing_information, *corrections])
            updates["risk_flags"] = _unique([*recommendation.risk_flags, *risks, *issues])
    revised = recommendation.model_copy(update=updates) if updates else recommendation
    review = AdversarialReview(
        passed=not issues,
        issues=_unique(issues),
        challenged_claim_ids=_unique(challenged_claims),
        challenged_control_ids=_unique(challenged_controls),
        recommendation_risks=_unique(risks),
        required_corrections=_unique(corrections),
    )
    return case_file.model_copy(update={"adversarial_review": review, "recommendation_status": revised.status}), revised


def render_case_analysis(
    case_file: ApprovalCaseFile,
    recommendation: ApprovalRecommendation,
    guard: ApprovalGuardResult | None = None,
) -> str:
    guard = guard or ApprovalGuardResult()
    lines: list[str] = [
        "## 案件概览 / Case overview",
        "",
        f"- 案件：{case_file.case_id or '未识别'}",
        f"- 审批类型：{APPROVAL_TYPE_CN.get(case_file.approval_type, case_file.approval_type)}",
        f"- 审批单号：{case_file.approval_id or '未识别'}",
        f"- 申请人：{case_file.requester or '缺失'}",
        f"- 部门：{case_file.department or '缺失'}",
        f"- 金额：{case_file.amount if case_file.amount is not None else '缺失'} {case_file.currency or ''}".strip(),
        f"- 供应商：{case_file.vendor or '缺失'}",
        f"- 成本中心：{case_file.cost_center or '缺失'}",
        "",
        "一句话输入只能创建审批案件草稿；只有 ERP、政策、附件或 mock document 证据能支持 blocking requirement。",
        "",
        "## 必需证据清单 / Required evidence checklist",
        "",
    ]
    for requirement in case_file.evidence_requirements:
        marker = _status_marker(requirement.status)
        blocking = "blocking" if requirement.blocking else "non-blocking"
        lines.append(f"- {marker} `{requirement.requirement_id}` {requirement.label} ({requirement.required_level}, {blocking})")
        if requirement.satisfied_by_claim_ids:
            lines.append(f"  - 支持 claims：{', '.join(requirement.satisfied_by_claim_ids[:6])}")
    lines.extend(["", "## 证据材料与链接 / Evidence artifacts and links", ""])
    artifact_lines = _render_evidence_artifact_lines(case_file)
    if artifact_lines:
        lines.extend(artifact_lines)
    else:
        lines.append("- 没有可展示的 ERP、政策、附件或 mock document 证据。")
    lines.extend(["", "## 证据声明 / Evidence claims", ""])
    if case_file.evidence_claims:
        for claim in case_file.evidence_claims[:20]:
            lines.append(
                f"- `{claim.claim_id}` {claim.claim_type}: {claim.statement} "
                f"[source: {claim.source_id or 'missing'}, status: {claim.verification_status}]"
            )
    else:
        lines.append("- 没有可用证据声明。")
    lines.extend(["", "## 证据充分性 / Evidence sufficiency", ""])
    suff = case_file.evidence_sufficiency
    if not suff.passed:
        lines.append("当前案件证据不足，不能形成通过建议。")
    lines.extend(
        [
            f"- passed：{str(suff.passed).lower()}",
            f"- completeness_score：{suff.completeness_score:.2f}",
            f"- missing：{', '.join(suff.missing_requirement_ids) if suff.missing_requirement_ids else '无'}",
            f"- partial：{', '.join(suff.partial_requirement_ids) if suff.partial_requirement_ids else '无'}",
            f"- conflict：{', '.join(suff.conflict_requirement_ids) if suff.conflict_requirement_ids else '无'}",
        ]
    )
    if suff.blocking_gaps:
        lines.append("- blocking gaps：")
        lines.extend(f"  - {gap}" for gap in suff.blocking_gaps)
    if suff.next_questions:
        lines.append("- 建议补证问题：")
        lines.extend(f"  - {question}" for question in suff.next_questions)
    lines.extend(["", "## 矛盾检测 / Contradictions", ""])
    if case_file.contradictions.has_conflict:
        lines.append(f"- severity：{case_file.contradictions.severity}")
        lines.append(f"- explanation：{case_file.contradictions.explanation}")
        for item in case_file.contradictions.conflict_items[:8]:
            lines.append(f"  - {item}")
    else:
        lines.append("- 未发现明确结构化冲突。")
    lines.extend(["", "## 控制矩阵检查 / Control matrix checks", ""])
    if case_file.control_checks:
        for check in case_file.control_checks:
            lines.append(
                f"- {_status_marker(check.status)} `{check.check_id}` {check.label}: "
                f"{check.status} / {check.severity} - {check.explanation}"
            )
    else:
        lines.append("- 控制矩阵未生成。")
    lines.extend(["", "## 风险评估 / Risk assessment", ""])
    risk = case_file.risk_assessment
    lines.extend(
        [
            f"- risk_level：{risk.risk_level}",
            f"- explanation：{risk.explanation or '无'}",
        ]
    )
    if risk.risk_factors:
        lines.append("- risk_factors：")
        lines.extend(f"  - {item}" for item in risk.risk_factors)
    if risk.policy_friction:
        lines.append("- policy_friction：")
        lines.extend(f"  - {item}" for item in risk.policy_friction)
    lines.extend(["", "## 自我挑战 / Adversarial review", ""])
    review = case_file.adversarial_review
    lines.extend(
        [
            f"- passed：{str(review.passed).lower()}",
            f"- issues：{'; '.join(review.issues) if review.issues else '无'}",
            f"- challenged_claim_ids：{', '.join(review.challenged_claim_ids[:12]) if review.challenged_claim_ids else '无'}",
            f"- challenged_control_ids：{', '.join(review.challenged_control_ids[:12]) if review.challenged_control_ids else '无'}",
        ]
    )
    lines.extend(["", "## 审批建议 / Recommendation", ""])
    lines.extend(
        [
            f"- 当前建议：{STATUS_LABELS_CN.get(str(recommendation.status), str(recommendation.status))}",
            f"- 置信度：{recommendation.confidence:.2f}",
            f"- 下一步：{NEXT_ACTION_CN.get(str(recommendation.proposed_next_action), str(recommendation.proposed_next_action))}",
            f"- 需要人工复核：{'是' if recommendation.human_review_required else '否'}",
            f"- 摘要：{recommendation.summary}",
        ]
    )
    if recommendation.rationale:
        lines.append("- 理由：")
        lines.extend(f"  - {item}" for item in recommendation.rationale)
    if recommendation.missing_information:
        lines.append("- 缺失信息：")
        lines.extend(f"  - {item}" for item in recommendation.missing_information)
    if recommendation.risk_flags:
        lines.append("- 风险点：")
        lines.extend(f"  - {item}" for item in recommendation.risk_flags)
    if recommendation.citations:
        lines.append("- citations：")
        lines.extend(f"  - {citation}" for citation in recommendation.citations)
    if guard.warnings:
        lines.append("- guard warnings：")
        lines.extend(f"  - {warning}" for warning in guard.warnings)
    lines.extend(
        [
            "",
            "## 非执行边界 / Non-action boundary",
            "",
            "- No ERP write action was executed.",
            "- 未执行任何 ERP 通过、驳回、付款、供应商、合同或预算写入动作。",
            f"- {case_file.non_action_statement}",
        ]
    )
    return "\n".join(lines).strip()


def _build_risk_assessment(case_file: ApprovalCaseFile, control_matrix) -> RiskAssessment:
    factors: list[str] = []
    friction: list[str] = []
    fraud_or_error: list[str] = []
    if case_file.contradictions.has_conflict:
        factors.append("存在证据冲突。")
        fraud_or_error.append("关键字段冲突可能代表录入错误或证据不一致。")
    if case_file.evidence_sufficiency.blocking_gaps:
        factors.extend(case_file.evidence_sufficiency.blocking_gaps[:6])
    for check in control_matrix.checks:
        if check.status in {"fail", "conflict"}:
            factors.append(check.explanation)
        elif check.status == "missing":
            friction.append(check.explanation)
    risk_level = "low"
    if any(check.severity == "critical" and check.status in {"fail", "conflict"} for check in control_matrix.checks):
        risk_level = "critical"
    elif control_matrix.high_risk or case_file.contradictions.has_conflict:
        risk_level = "high"
    elif factors or friction:
        risk_level = "medium"
    return RiskAssessment(
        risk_level=risk_level,  # type: ignore[arg-type]
        risk_factors=_unique(factors),
        policy_friction=_unique(friction),
        fraud_or_error_signals=_unique(fraud_or_error),
        explanation="风险等级由证据充分性、控制矩阵缺口和冲突检测确定。",
    )


def _build_approval_path(case_file: ApprovalCaseFile, control_matrix) -> ApprovalPathPlan:
    roles = ["manager"]
    targets: list[str] = []
    approval_type = str(case_file.approval_type)
    if approval_type in {"purchase_requisition", "supplier_onboarding"}:
        roles.append("procurement")
    if approval_type in {"invoice_payment", "budget_exception"} or any("budget" in item for item in control_matrix.failed_check_ids):
        roles.append("finance")
    if approval_type == "contract_exception" or any("legal" in item for item in control_matrix.failed_check_ids):
        roles.append("legal")
    if control_matrix.high_risk:
        targets = [role for role in roles if role != "manager"] or ["manager"]
    return ApprovalPathPlan(
        approver_roles=_unique(roles),
        required_reviewers=_unique(roles),
        escalation_required=control_matrix.high_risk or bool(control_matrix.conflict_check_ids),
        escalation_targets=_unique(targets),
        reason="审批路径由审批类型、证据缺口和控制矩阵风险决定。",
    )


def _supporting_source_ids(case_file: ApprovalCaseFile) -> list[str]:
    source_ids: list[str] = []
    satisfied_requirement_ids = {req.requirement_id for req in case_file.evidence_requirements if req.status == "satisfied"}
    for claim in case_file.evidence_claims:
        if not claim.source_id or claim.source_id.startswith("user_statement://"):
            continue
        if claim.verification_status != "supported":
            continue
        if not satisfied_requirement_ids.intersection(claim.supports_requirement_ids):
            continue
        source_ids.append(claim.source_id)
    return _unique(source_ids)[:12]


def _missing_information(case_file: ApprovalCaseFile, control_matrix) -> list[str]:
    items: list[str] = []
    items.extend(case_file.evidence_sufficiency.blocking_gaps)
    items.extend(check.explanation for check in control_matrix.checks if check.status in {"missing", "conflict", "fail"})
    return _unique(items)


def _risk_flags(case_file: ApprovalCaseFile, control_matrix) -> list[str]:
    flags: list[str] = []
    flags.extend(case_file.risk_assessment.risk_factors)
    flags.extend(case_file.risk_assessment.fraud_or_error_signals)
    flags.extend(control_matrix.escalation_reasons)
    return _unique(flags)


def _top_control_explanations(control_matrix) -> list[str]:
    explanations = [check.explanation for check in control_matrix.checks if check.status in {"fail", "missing", "conflict"}]
    if not explanations:
        explanations = [check.explanation for check in control_matrix.checks if check.status == "pass"]
    return _unique(explanations)[:8]


def _escalation_next_action(case_file: ApprovalCaseFile) -> str:
    if case_file.approval_type in {"invoice_payment", "budget_exception"}:
        return "route_to_finance"
    if case_file.approval_type == "contract_exception":
        return "route_to_legal"
    if case_file.approval_type in {"purchase_requisition", "supplier_onboarding"}:
        return "route_to_procurement"
    return "manual_review"


def _approve_next_action(case_file: ApprovalCaseFile) -> str:
    if case_file.approval_type == "expense":
        return "route_to_manager"
    if case_file.approval_type == "invoice_payment":
        return "route_to_finance"
    if case_file.approval_type in {"purchase_requisition", "supplier_onboarding"}:
        return "route_to_procurement"
    if case_file.approval_type == "contract_exception":
        return "route_to_legal"
    return "manual_review"


def _approval_request_header(context: ApprovalContextBundle) -> dict[str, object]:
    for record in context.records:
        if record.record_type != "approval_request":
            continue
        header = dict(record.metadata or {})
        if not header.get("approval_id"):
            header["approval_id"] = record.source_id.rsplit("/", 1)[-1] if record.source_id else ""
        return header
    return {}


def _first_non_empty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _line_items_from_context(header: dict[str, object]) -> list[dict[str, object]]:
    raw = header.get("line_items")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _prompt_boundary_issues(source_request: str) -> list[str]:
    text = str(source_request or "").lower()
    if not text:
        return []
    patterns = (
        "忽略政策",
        "跳过政策",
        "不需要 citation",
        "不需要引用",
        "直接批准",
        "直接通过",
        "自动通过",
        "执行审批",
        "执行付款",
        "ignore policy",
        "skip policy",
        "no citation",
        "no citations",
        "directly approve",
        "auto approve",
        "execute approval",
        "execute payment",
    )
    if any(pattern in text for pattern in patterns):
        return ["用户输入包含试图跳过政策、引用、人工复核或 ERP 非执行边界的指令。"]
    return []


def _render_evidence_artifact_lines(case_file: ApprovalCaseFile) -> list[str]:
    lines: list[str] = []
    for artifact in case_file.evidence_artifacts:
        if artifact.source_id.startswith("user_statement://"):
            lines.append("- 用户输入：只作为案件草稿来源，不能单独满足 blocking evidence。")
            continue
        metadata = dict(artifact.metadata or {})
        refs = _artifact_refs(metadata)
        lines.append(f"- `{artifact.record_type}` {artifact.title} — source_id: `{artifact.source_id}`")
        if refs:
            for ref in refs[:8]:
                lines.append(f"  - 证据位置：{ref}")
        else:
            lines.append("  - 证据位置：当前 mock ERP/policy context record；未附本地文件路径。")
    return lines[:80]


def _artifact_refs(metadata: dict[str, object]) -> list[str]:
    refs: list[str] = []
    for key in ("file_path", "local_path", "document_path", "document_link", "purchase_link", "invoice_link", "po_link", "grn_link", "url"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
    evidence_files = metadata.get("evidence_files")
    if isinstance(evidence_files, list):
        refs.extend(str(item).strip() for item in evidence_files if str(item).strip())
    return _unique(refs)


def _status_marker(status: str) -> str:
    return {
        "satisfied": "[OK]",
        "pass": "[OK]",
        "missing": "[MISSING]",
        "partial": "[PARTIAL]",
        "conflict": "[CONFLICT]",
        "fail": "[FAIL]",
        "not_applicable": "[N/A]",
    }.get(str(status), "[?]")


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
