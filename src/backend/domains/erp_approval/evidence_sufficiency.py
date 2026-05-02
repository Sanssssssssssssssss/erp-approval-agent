from __future__ import annotations

from src.backend.domains.erp_approval.case_models import ContradictionReport, EvidenceClaim, EvidenceRequirement, EvidenceSufficiencyReport


QUESTION_TEMPLATES = {
    "budget": "请补充预算占用或预算可用性证明。",
    "budget_availability": "请补充预算占用或预算可用性证明。",
    "available_budget": "请补充可用预算、预算负责人或资金不足说明。",
    "vendor": "请补充供应商准入状态或供应商风险记录。",
    "supplier": "请补充供应商准入状态、制裁筛查、税务和银行资料。",
    "quote": "请补充报价、价格依据或框架协议材料。",
    "purchase_order": "请补充 PO 采购订单材料。",
    "goods_receipt": "请补充 GRN/收货记录。",
    "invoice": "请补充发票记录和三单匹配材料。",
    "three_way_match": "请补充 PO/GRN/Invoice 三单匹配材料。",
    "receipt": "请补充收据或发票附件。",
    "contract": "请补充合同文本、例外条款或付款条款材料。",
    "legal": "请补充法务复核意见或合同政策依据。",
    "approval_matrix": "请补充审批矩阵或审批路径依据。",
    "requester": "请补充申请人身份和部门归属。",
    "line_items": "请补充采购明细、数量、单价或附件。",
}


def evaluate_evidence_sufficiency(
    requirements: list[EvidenceRequirement],
    claims: list[EvidenceClaim],
    contradictions: ContradictionReport,
) -> EvidenceSufficiencyReport:
    required = [item for item in requirements if item.required_level == "required"]
    satisfied = [item for item in required if item.status == "satisfied"]
    missing = [item.requirement_id for item in required if item.status == "missing"]
    partial = [item.requirement_id for item in required if item.status == "partial"]
    conflict = [item.requirement_id for item in required if item.status == "conflict"]
    blocking_gaps = [
        f"{item.label}：{item.description}"
        for item in requirements
        if item.blocking and item.status in {"missing", "partial", "conflict"}
    ]
    warnings: list[str] = []
    non_user_supported_claims = [
        claim for claim in claims
        if claim.source_id and not claim.source_id.startswith("user_statement://") and claim.verification_status in {"supported", "needs_review"}
    ]
    if not non_user_supported_claims:
        warnings.append("当前只有用户陈述，没有 ERP、policy 或附件证据；不能形成通过建议。")
    if contradictions.has_conflict:
        warnings.append("发现证据冲突；必须人工复核后才能继续。")
    completeness_score = len(satisfied) / len(required) if required else 0.0
    passed = (
        not missing
        and not partial
        and not conflict
        and not contradictions.has_conflict
        and bool(non_user_supported_claims)
    )
    report = EvidenceSufficiencyReport(
        passed=passed,
        completeness_score=round(completeness_score, 3),
        missing_requirement_ids=missing,
        partial_requirement_ids=partial,
        conflict_requirement_ids=conflict,
        blocking_gaps=blocking_gaps,
        warnings=warnings,
    )
    return report.model_copy(update={"next_questions": required_questions_for_missing_evidence(report, requirements)})


def required_questions_for_missing_evidence(
    report: EvidenceSufficiencyReport,
    requirements: list[EvidenceRequirement],
) -> list[str]:
    target_ids = set(report.missing_requirement_ids + report.partial_requirement_ids + report.conflict_requirement_ids)
    questions: list[str] = []
    for requirement in requirements:
        if requirement.requirement_id not in target_ids:
            continue
        key = requirement.requirement_id.split(":", 1)[-1]
        question = ""
        for token, template in QUESTION_TEMPLATES.items():
            if token in key:
                question = template
                break
        if not question:
            question = f"请补充“{requirement.label}”相关证据。"
        if question not in questions:
            questions.append(question)
    return questions[:8]
