from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.case_models import CASE_ANALYSIS_NON_ACTION_STATEMENT
from src.backend.domains.erp_approval.case_review import (
    adversarial_review_case,
    build_case_file_from_request_context,
    draft_recommendation_from_case,
    render_case_analysis,
)
from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter
from src.backend.domains.erp_approval.control_matrix import evaluate_control_matrix
from src.backend.domains.erp_approval.schemas import (
    ApprovalContextBundle,
    ApprovalContextRecord,
    ApprovalGuardResult,
    ApprovalRecommendation,
    ApprovalRequest,
)
from src.backend.domains.erp_approval.service import guard_recommendation, parse_approval_request


CASE_REVIEW_NON_ACTION_STATEMENT = "This is a local evidence-first case review. No ERP write action was executed."


class CaseReviewEvidenceInput(BaseModel):
    title: str = ""
    record_type: str = ""
    content: str = ""
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseReviewRequest(BaseModel):
    user_message: str
    approval_type: str = ""
    approval_id: str = ""
    requester: str = ""
    department: str = ""
    amount: float | None = None
    currency: str = ""
    vendor: str = ""
    cost_center: str = ""
    business_purpose: str = ""
    extra_evidence: list[CaseReviewEvidenceInput] = Field(default_factory=list)


class CaseReviewResponse(BaseModel):
    approval_request: dict[str, Any]
    context: dict[str, Any]
    case_file: dict[str, Any]
    evidence_requirements: list[dict[str, Any]]
    evidence_artifacts: list[dict[str, Any]]
    evidence_claims: list[dict[str, Any]]
    evidence_sufficiency: dict[str, Any]
    contradictions: dict[str, Any]
    control_matrix: dict[str, Any]
    risk_assessment: dict[str, Any]
    adversarial_review: dict[str, Any]
    recommendation: dict[str, Any]
    guard_result: dict[str, Any]
    reviewer_memo: str
    non_action_statement: str = CASE_REVIEW_NON_ACTION_STATEMENT


def run_local_case_review(request: CaseReviewRequest, *, base_dir: Path | str | None = None) -> CaseReviewResponse:
    approval_request = _approval_request_from_payload(request)
    adapter = MockErpContextAdapter(base_dir=base_dir)
    base_context = adapter.fetch_context(ErpContextQuery.from_request(approval_request))
    context = _merge_extra_evidence(base_context, request.extra_evidence, approval_request)
    case_file = build_case_file_from_request_context(approval_request, context)
    recommendation = draft_recommendation_from_case(case_file)
    case_file, recommendation = adversarial_review_case(case_file, recommendation)
    recommendation, guard = guard_recommendation(approval_request, context, recommendation)
    memo = render_case_analysis(case_file, recommendation, guard)
    control_matrix = evaluate_control_matrix(case_file)

    return CaseReviewResponse(
        approval_request=approval_request.model_dump(),
        context=context.model_dump(),
        case_file=case_file.model_dump(),
        evidence_requirements=[item.model_dump() for item in case_file.evidence_requirements],
        evidence_artifacts=[item.model_dump() for item in case_file.evidence_artifacts],
        evidence_claims=[item.model_dump() for item in case_file.evidence_claims],
        evidence_sufficiency=case_file.evidence_sufficiency.model_dump(),
        contradictions=case_file.contradictions.model_dump(),
        control_matrix=control_matrix.model_dump(),
        risk_assessment=case_file.risk_assessment.model_dump(),
        adversarial_review=case_file.adversarial_review.model_dump(),
        recommendation=recommendation.model_dump(),
        guard_result=guard.model_dump(),
        reviewer_memo=memo,
        non_action_statement=CASE_REVIEW_NON_ACTION_STATEMENT,
    )


def _approval_request_from_payload(payload: CaseReviewRequest) -> ApprovalRequest:
    request = parse_approval_request("", payload.user_message)
    updates: dict[str, Any] = {}
    for key in (
        "approval_type",
        "approval_id",
        "requester",
        "department",
        "currency",
        "vendor",
        "cost_center",
        "business_purpose",
    ):
        value = getattr(payload, key)
        if isinstance(value, str) and value.strip():
            updates[key] = value.strip()
    if payload.amount is not None:
        updates["amount"] = payload.amount
    if payload.user_message.strip():
        updates["raw_request"] = payload.user_message.strip()
    return request.model_copy(update=updates)


def _merge_extra_evidence(
    context: ApprovalContextBundle,
    evidence: list[CaseReviewEvidenceInput],
    request: ApprovalRequest,
) -> ApprovalContextBundle:
    records = list(context.records)
    seen = {record.source_id for record in records}
    for index, item in enumerate(evidence, start=1):
        content = item.content.strip()
        if not content:
            continue
        record_type = _infer_record_type(item.record_type, item.title, content)
        source_id = item.source_id.strip() or f"local_evidence://{record_type}/{request.approval_id or 'unidentified'}/{index}"
        if source_id in seen:
            continue
        seen.add(source_id)
        metadata = dict(item.metadata or {})
        metadata.setdefault("local_case_review_evidence", True)
        metadata.setdefault("approval_ids", [request.approval_id] if request.approval_id else [])
        metadata.setdefault("read_only", True)
        records.append(
            ApprovalContextRecord(
                source_id=source_id,
                title=item.title.strip() or _default_evidence_title(record_type, index),
                record_type=record_type,
                content=content,
                metadata=metadata,
            )
        )
    return ApprovalContextBundle(request_id=context.request_id or request.approval_id, records=records)


def _infer_record_type(record_type: str, title: str, content: str) -> str:
    explicit = re.sub(r"[^a-z0-9_]+", "_", str(record_type or "").strip().lower()).strip("_")
    if explicit:
        return explicit
    text = f"{title}\n{content}".lower()
    patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("purchase_order", ("purchase order", "po-", " po ", "采购订单")),
        ("goods_receipt", ("goods receipt", "grn", "收货", "入库")),
        ("invoice", ("invoice", "发票")),
        ("receipt", ("receipt", "收据", "小票")),
        ("quote", ("quote", "quotation", "报价")),
        ("budget", ("budget", "预算")),
        ("vendor", ("vendor", "supplier", "供应商")),
        ("sanctions_check", ("sanctions", "制裁")),
        ("bank_info", ("bank", "银行")),
        ("tax_info", ("tax", "税务", "税号")),
        ("contract", ("contract", "合同", "框架协议")),
        ("policy", ("policy", "政策", "制度")),
        ("approval_request", ("approval request", "purchase requisition", "pr-", "审批单", "采购申请")),
        ("payment_terms", ("payment terms", "付款条款")),
        ("duplicate_check", ("duplicate", "重复")),
        ("limit_check", ("limit", "限额")),
    )
    for candidate, needles in patterns:
        if any(needle in text for needle in needles):
            return candidate
    return "local_note"


def _default_evidence_title(record_type: str, index: int) -> str:
    labels = {
        "approval_request": "本地审批单文本证据",
        "invoice": "本地发票文本证据",
        "purchase_order": "本地 PO 文本证据",
        "goods_receipt": "本地 GRN 文本证据",
        "quote": "本地报价文本证据",
        "budget": "本地预算文本证据",
        "vendor": "本地供应商文本证据",
        "policy": "本地政策文本证据",
        "contract": "本地合同文本证据",
    }
    return labels.get(record_type, f"本地补充证据 {index}")
