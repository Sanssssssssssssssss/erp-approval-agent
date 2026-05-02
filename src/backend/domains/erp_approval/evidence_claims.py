from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from src.backend.domains.erp_approval.case_models import (
    ApprovalCaseFile,
    ContradictionReport,
    EvidenceArtifact,
    EvidenceClaim,
    EvidenceRequirement,
)
from src.backend.domains.erp_approval.schemas import ApprovalContextBundle, ApprovalRequest


CLAIM_REQUIREMENT_HINTS = {
    "approval_request_present": ("approval_request", "expense_claim", "vendor_profile", "exception_reason"),
    "budget_available": ("budget_availability", "budget_record", "available_budget"),
    "vendor_onboarded": ("vendor_onboarding_status", "vendor_record", "vendor_profile"),
    "vendor_risk_clear": ("supplier_risk_status",),
    "quote_or_contract_present": ("quote_or_price_basis", "contract_or_framework_agreement", "contract_or_payment_terms", "contract_or_nda_or_dpa"),
    "policy_present": ("policy", "procurement_policy", "expense_policy", "invoice_payment_policy", "supplier_onboarding_policy", "legal_policy", "finance_policy"),
    "approval_matrix_present": ("approval_matrix", "manager_approval_path", "finance_approval_matrix", "amount_threshold"),
    "receipt_present": ("receipt_or_invoice",),
    "invoice_present": ("invoice",),
    "purchase_order_present": ("purchase_order",),
    "goods_receipt_present": ("goods_receipt",),
    "three_way_match_present": ("three_way_match",),
    "supplier_tax_info_present": ("tax_info",),
    "supplier_bank_info_present": ("bank_info",),
    "sanctions_check_present": ("sanctions_check",),
    "contract_present": ("contract_text", "redline_or_exception_clause", "liability_clause", "payment_terms", "termination_clause"),
    "legal_review_required": ("legal_review_required",),
    "budget_exception_present": ("exception_reason",),
    "business_purpose_present": ("business_purpose",),
    "cost_center_present": ("cost_center",),
    "requester_identity_present": ("requester_identity",),
    "amount_present": ("amount_limit_check", "amount_threshold"),
}


def build_evidence_artifacts(request: ApprovalRequest, context: ApprovalContextBundle) -> list[EvidenceArtifact]:
    artifacts: list[EvidenceArtifact] = []
    if request.raw_request:
        artifacts.append(
            EvidenceArtifact(
                artifact_id="artifact:user_statement:current_request",
                artifact_type="user_statement",
                source_id="user_statement://current_request",
                title="User approval request statement",
                content=request.raw_request,
                record_type="user_statement",
                metadata=request.model_dump(),
            )
        )
    for index, record in enumerate(context.records):
        artifact_type = "policy_record" if record.record_type == "policy" else "erp_record"
        artifacts.append(
            EvidenceArtifact(
                artifact_id=f"artifact:{index}:{record.source_id}",
                artifact_type=artifact_type,  # type: ignore[arg-type]
                source_id=record.source_id,
                title=record.title,
                content=record.content,
                record_type=record.record_type,
                metadata=dict(record.metadata or {}),
            )
        )
    return artifacts


def extract_claims_from_artifacts(case_file: ApprovalCaseFile, artifacts: list[EvidenceArtifact]) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    by_record_type = {artifact.record_type: artifact for artifact in artifacts if not _is_user_statement(artifact.source_id)}
    for artifact in artifacts:
        if not artifact.source_id:
            continue
        text = f"{artifact.title}\n{artifact.content}\n{json.dumps(artifact.metadata, ensure_ascii=False)}"
        lowered = text.lower()
        record_type = artifact.record_type
        if record_type == "approval_request":
            claims.append(_claim("approval_request_present", "审批请求记录存在。", artifact, extracted_value=artifact.metadata))
            _claim_if(artifact.metadata.get("requester") or case_file.requester, claims, "requester_identity_present", "申请人身份存在。", artifact)
            _claim_if(artifact.metadata.get("amount") is not None or case_file.amount is not None, claims, "amount_present", "金额字段存在。", artifact)
            _claim_if(artifact.metadata.get("cost_center") or case_file.cost_center, claims, "cost_center_present", "成本中心存在。", artifact)
            _claim_if(case_file.business_purpose or "purpose" in lowered or "用途" in text, claims, "business_purpose_present", "业务目的存在。", artifact)
            if case_file.approval_type == "budget_exception":
                claims.append(_claim("budget_exception_present", "预算例外请求存在。", artifact))
        elif record_type == "budget":
            status = "insufficient" if any(term in lowered for term in ("insufficient", "不足", "超支")) else "available"
            claims.append(_claim("budget_available", f"预算记录存在，当前指示为 {status}。", artifact, extracted_value=status, normalized_value=status))
        elif record_type == "vendor":
            claims.append(_claim("vendor_onboarded", "供应商记录存在。", artifact))
            if "sanctions" in lowered or "制裁" in text:
                sanctions_status = "pending" if any(term in lowered for term in ("pending", "待", "未完成")) else "present"
                claims.append(
                    _claim(
                        "sanctions_check_present",
                        f"供应商制裁检查记录存在，状态为 {sanctions_status}。",
                        artifact,
                        extracted_value=sanctions_status,
                        normalized_value=sanctions_status,
                        verification_status="needs_review" if sanctions_status == "pending" else "supported",
                    )
                )
            if "tax" in lowered or "税" in text:
                claims.append(_claim("supplier_tax_info_present", "供应商税务信息存在。", artifact))
            if "bank" in lowered or "银行" in text:
                claims.append(_claim("supplier_bank_info_present", "供应商银行信息存在。", artifact))
            if not any(term in lowered for term in ("pending", "blocked", "sanction", "制裁", "阻断")):
                claims.append(_claim("vendor_risk_clear", "供应商记录未显示准入阻断。", artifact))
        elif record_type == "purchase_order":
            claims.append(_claim("purchase_order_present", "采购订单记录存在。", artifact))
        elif record_type == "goods_receipt":
            claims.append(_claim("goods_receipt_present", "收货记录存在。", artifact))
        elif record_type == "invoice":
            claims.append(_claim("invoice_present", "发票记录存在。", artifact))
        elif record_type == "contract":
            claims.append(_claim("contract_present", "合同或合同例外记录存在。", artifact))
            if any(term in lowered for term in ("liability", "责任")):
                claims.append(_claim("contract_present", "责任条款证据存在。", artifact, metadata={"clause": "liability"}))
            if any(term in lowered for term in ("termination", "终止")):
                claims.append(_claim("contract_present", "终止条款证据存在。", artifact, metadata={"clause": "termination"}))
            if any(term in lowered for term in ("legal", "法务")):
                claims.append(_claim("legal_review_required", "合同例外需要法务复核。", artifact))
        elif record_type == "policy":
            claims.append(_claim("policy_present", "政策记录存在。", artifact))
            if "approval_matrix" in artifact.source_id or "approval matrix" in lowered or "审批矩阵" in text:
                claims.append(_claim("approval_matrix_present", "审批矩阵存在。", artifact))
            if any(term in lowered for term in ("legal", "法务")):
                claims.append(_claim("legal_review_required", "政策要求法务复核。", artifact))
            if "receipt" in lowered or "收据" in text:
                claims.append(_claim("receipt_present", "费用政策提及收据要求。", artifact, verification_status="needs_review"))

    if {"purchase_order", "goods_receipt", "invoice"}.issubset(by_record_type):
        source = by_record_type["invoice"]
        claims.append(_claim("three_way_match_present", "PO、GRN、Invoice 三类记录均存在，可进入三单匹配复核。", source))
    return _dedupe_claims(claims)


def link_claims_to_requirements(
    requirements: list[EvidenceRequirement],
    claims: list[EvidenceClaim],
) -> tuple[list[EvidenceRequirement], list[EvidenceClaim]]:
    requirement_by_id = {item.requirement_id: item for item in requirements}
    updated_claims: list[EvidenceClaim] = []
    support_map: dict[str, list[str]] = defaultdict(list)
    for claim in claims:
        supported_ids = set(claim.supports_requirement_ids)
        for requirement in requirements:
            key = requirement.requirement_id.split(":", 1)[-1]
            hints = CLAIM_REQUIREMENT_HINTS.get(claim.claim_type, ())
            if key in hints or claim.claim_type == f"{key}_present":
                if not (_is_user_statement(claim.source_id) and requirement.blocking):
                    supported_ids.add(requirement.requirement_id)
        updated = claim.model_copy(update={"supports_requirement_ids": sorted(supported_ids)})
        updated_claims.append(updated)
        if updated.verification_status == "conflict":
            for requirement_id in supported_ids:
                support_map[requirement_id].append(updated.claim_id)
        elif updated.verification_status in {"supported", "needs_review"}:
            for requirement_id in supported_ids:
                support_map[requirement_id].append(updated.claim_id)

    updated_requirements: list[EvidenceRequirement] = []
    for requirement in requirements:
        claim_ids = support_map.get(requirement.requirement_id, [])
        status = "satisfied" if claim_ids else requirement.status
        if claim_ids and any(_claim_by_id(updated_claims, claim_id).verification_status == "needs_review" for claim_id in claim_ids):
            status = "partial"
        if claim_ids and any(_claim_by_id(updated_claims, claim_id).verification_status == "conflict" for claim_id in claim_ids):
            status = "conflict"
        if requirement.required_level == "optional" and not claim_ids:
            status = "not_applicable"
        updated_requirements.append(requirement.model_copy(update={"satisfied_by_claim_ids": claim_ids, "status": status}))
    return updated_requirements, updated_claims


def detect_contradictions(claims: list[EvidenceClaim]) -> ContradictionReport:
    values: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for claim in claims:
        metadata = dict(claim.metadata or {})
        for field in ("amount", "vendor_name", "vendor", "cost_center", "status"):
            raw_value = metadata.get(field)
            if raw_value in (None, ""):
                continue
            values[field][_normalize_value(raw_value)].append(claim.claim_id)
        if isinstance(claim.extracted_value, dict):
            for field in ("amount", "vendor_name", "vendor", "cost_center", "status"):
                raw_value = claim.extracted_value.get(field)
                if raw_value not in (None, ""):
                    values[field][_normalize_value(raw_value)].append(claim.claim_id)
        if isinstance(claim.normalized_value, dict):
            for field in ("amount", "vendor_name", "vendor", "cost_center", "status"):
                raw_value = claim.normalized_value.get(field)
                if raw_value not in (None, ""):
                    values[field][_normalize_value(raw_value)].append(claim.claim_id)
    conflicts: list[dict[str, Any]] = []
    for field, grouped in values.items():
        distinct = {key: ids for key, ids in grouped.items() if key}
        if len(distinct) > 1:
            conflicts.append({"field": field, "values": sorted(distinct), "claim_ids": sorted({item for ids in distinct.values() for item in ids})})
    return ContradictionReport(
        has_conflict=bool(conflicts),
        conflict_items=conflicts,
        severity="high" if conflicts else "low",
        explanation="发现证据字段冲突，需要人工复核。" if conflicts else "未发现明显证据冲突。",
    )


def _claim(
    claim_type: str,
    statement: str,
    artifact: EvidenceArtifact,
    *,
    extracted_value: Any = None,
    normalized_value: Any = None,
    verification_status: str = "supported",
    metadata: dict[str, Any] | None = None,
) -> EvidenceClaim:
    safe_key = re.sub(r"[^a-z0-9]+", "-", f"{claim_type}-{artifact.source_id}".lower()).strip("-")
    return EvidenceClaim(
        claim_id=f"claim:{safe_key}",
        claim_type=claim_type,
        statement=statement,
        source_id=artifact.source_id,
        locator=artifact.title,
        extracted_value=extracted_value,
        normalized_value=normalized_value,
        confidence=0.75 if verification_status == "supported" else 0.55,
        verification_status=verification_status,  # type: ignore[arg-type]
        metadata={**dict(artifact.metadata or {}), **dict(metadata or {})},
    )


def _claim_if(value: Any, claims: list[EvidenceClaim], claim_type: str, statement: str, artifact: EvidenceArtifact) -> None:
    if value not in (None, "", []):
        claims.append(_claim(claim_type, statement, artifact, extracted_value=value, normalized_value=value))


def _dedupe_claims(claims: list[EvidenceClaim]) -> list[EvidenceClaim]:
    seen: set[str] = set()
    deduped: list[EvidenceClaim] = []
    for claim in claims:
        if claim.claim_id in seen:
            continue
        seen.add(claim.claim_id)
        deduped.append(claim)
    return deduped


def _claim_by_id(claims: list[EvidenceClaim], claim_id: str) -> EvidenceClaim:
    for claim in claims:
        if claim.claim_id == claim_id:
            return claim
    return EvidenceClaim(claim_id=claim_id, claim_type="unknown", statement="", source_id="", verification_status="unsupported")


def _is_user_statement(source_id: str) -> bool:
    return str(source_id or "").startswith("user_statement://")


def _normalize_value(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())
