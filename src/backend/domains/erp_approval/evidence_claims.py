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
    "quote_or_contract_present": (
        "quote_or_price_basis",
        "contract_or_framework_agreement",
        "contract_or_payment_terms",
        "contract_or_nda_or_dpa",
    ),
    "policy_present": ("policy",),
    "procurement_policy_present": ("procurement_policy",),
    "expense_policy_present": ("expense_policy",),
    "invoice_payment_policy_present": ("invoice_payment_policy",),
    "supplier_onboarding_policy_present": ("supplier_onboarding_policy",),
    "legal_policy_present": ("legal_policy",),
    "finance_policy_present": ("finance_policy",),
    "approval_matrix_present": ("approval_matrix", "manager_approval_path", "finance_approval_matrix", "amount_threshold"),
    "receipt_present": ("receipt_or_invoice",),
    "invoice_present": ("invoice",),
    "purchase_order_present": ("purchase_order",),
    "goods_receipt_present": ("goods_receipt",),
    "three_way_match_present": ("three_way_match",),
    "supplier_tax_info_present": ("tax_info",),
    "supplier_bank_info_present": ("bank_info",),
    "sanctions_check_present": ("sanctions_check",),
    "beneficial_owner_check_present": ("beneficial_owner_check",),
    "procurement_due_diligence_present": ("procurement_due_diligence",),
    "contract_present": ("contract_text",),
    "exception_clause_present": ("redline_or_exception_clause",),
    "liability_clause_present": ("liability_clause",),
    "termination_clause_present": ("termination_clause",),
    "standard_terms_present": ("standard_terms",),
    "legal_review_required": ("legal_review_required",),
    "payment_terms_present": ("contract_or_payment_terms", "payment_terms"),
    "budget_exception_present": ("exception_reason",),
    "business_purpose_present": ("business_purpose",),
    "cost_center_present": ("cost_center",),
    "requester_identity_present": ("requester_identity",),
    "amount_present": ("amount_threshold",),
    "line_items_present": ("line_items",),
    "split_order_check_present": ("split_order_check",),
    "expense_date_present": ("expense_date",),
    "duplicate_expense_check_present": ("duplicate_expense_check",),
    "amount_limit_check_present": ("amount_limit_check",),
    "duplicate_payment_check_present": ("duplicate_payment_check",),
    "budget_owner_present": ("budget_owner",),
    "finance_review_present": ("finance_approval_matrix",),
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
    by_record_type = defaultdict(list)
    for artifact in artifacts:
        if not _is_user_statement(artifact.source_id):
            by_record_type[artifact.record_type].append(artifact)
    for artifact in artifacts:
        if not artifact.source_id:
            continue
        text = f"{artifact.title}\n{artifact.content}\n{json.dumps(artifact.metadata, ensure_ascii=False)}"
        lowered = text.lower()
        record_type = artifact.record_type
        if record_type == "approval_request":
            claims.extend(_approval_request_claims(case_file, artifact, lowered, text))
        elif record_type == "budget":
            status = _budget_status(lowered, text)
            claims.append(_claim("budget_available", f"Budget record exists; status={status}.", artifact, extracted_value=status, normalized_value=status))
            if artifact.metadata.get("budget_owner") or "budget owner" in lowered or "budget_owner" in lowered:
                claims.append(_claim("budget_owner_present", "Budget owner evidence exists.", artifact))
        elif record_type == "vendor":
            claims.extend(_vendor_claims(artifact, lowered, text))
        elif record_type == "purchase_order":
            claims.append(_claim("purchase_order_present", "Purchase order record exists.", artifact))
        elif record_type == "goods_receipt":
            claims.append(_claim("goods_receipt_present", "Goods receipt record exists.", artifact))
        elif record_type == "invoice":
            claims.append(_claim("invoice_present", "Invoice record exists.", artifact))
        elif record_type == "contract":
            claims.extend(_contract_claims(artifact, lowered, text))
        elif record_type == "policy":
            claims.extend(_policy_claims(artifact, lowered, text))
        elif record_type == "receipt":
            claims.append(_claim("receipt_present", "Receipt or expense invoice artifact exists.", artifact))
        elif record_type == "quote":
            claims.append(_claim("quote_or_contract_present", "Quote or price-basis artifact exists.", artifact))
        elif record_type == "duplicate_check":
            if "expense" in lowered or case_file.approval_type == "expense":
                claims.append(_claim("duplicate_expense_check_present", "Duplicate expense check evidence exists.", artifact))
            if "invoice" in lowered or "payment" in lowered or case_file.approval_type == "invoice_payment":
                claims.append(_claim("duplicate_payment_check_present", "Duplicate payment check evidence exists.", artifact))
        elif record_type == "limit_check":
            claims.append(_claim("amount_limit_check_present", "Amount limit check evidence exists.", artifact))
        elif record_type == "payment_terms":
            claims.append(_claim("payment_terms_present", "Payment terms evidence exists.", artifact))
        elif record_type == "sanctions_check":
            claims.extend(_sanctions_claims(artifact, lowered, text))
        elif record_type == "tax_info":
            claims.append(_claim("supplier_tax_info_present", "Supplier tax information evidence exists.", artifact))
        elif record_type == "bank_info":
            claims.append(_claim("supplier_bank_info_present", "Supplier bank information evidence exists.", artifact))
        elif record_type == "beneficial_owner":
            claims.append(_claim("beneficial_owner_check_present", "Beneficial-owner check evidence exists.", artifact))
        elif record_type == "due_diligence":
            claims.append(_claim("procurement_due_diligence_present", "Procurement due-diligence evidence exists.", artifact))
        elif record_type == "budget_owner":
            claims.append(_claim("budget_owner_present", "Budget owner evidence exists.", artifact))
        elif record_type == "finance_review":
            claims.append(_claim("finance_review_present", "Finance review or finance approval matrix evidence exists.", artifact))

    if by_record_type["purchase_order"] and by_record_type["goods_receipt"] and by_record_type["invoice"]:
        source = by_record_type["invoice"][0]
        claims.append(_claim("three_way_match_present", "PO, GRN, and invoice records are all present for three-way-match review.", source))
    return _dedupe_claims(claims)


def link_claims_to_requirements(
    requirements: list[EvidenceRequirement],
    claims: list[EvidenceClaim],
) -> tuple[list[EvidenceRequirement], list[EvidenceClaim]]:
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
        if updated.verification_status in {"supported", "needs_review", "conflict"}:
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
    explicit_conflicts: list[dict[str, Any]] = []
    for claim in claims:
        if claim.verification_status == "conflict":
            explicit_conflicts.append(
                {
                    "field": "claim_conflict",
                    "values": [str(claim.normalized_value or claim.extracted_value or claim.claim_type)],
                    "claim_ids": [claim.claim_id],
                }
            )
        for source in (claim.metadata, claim.extracted_value, claim.normalized_value):
            if not isinstance(source, dict):
                continue
            for field in ("amount", "vendor_name", "vendor", "cost_center", "status", "invoice_amount", "po_amount", "supplier_status"):
                raw_value = source.get(field)
                if raw_value not in (None, ""):
                    values[_canonical_field(field, source)][_normalize_value(raw_value)].append(claim.claim_id)
    conflicts: list[dict[str, Any]] = list(explicit_conflicts)
    for field, grouped in values.items():
        distinct = {key: ids for key, ids in grouped.items() if key}
        if len(distinct) > 1:
            conflicts.append({"field": field, "values": sorted(distinct), "claim_ids": sorted({item for ids in distinct.values() for item in ids})})
    return ContradictionReport(
        has_conflict=bool(conflicts),
        conflict_items=conflicts,
        severity="high" if conflicts else "low",
        explanation="结构化证据存在冲突，需要人工复核。" if conflicts else "未发现明显的结构化证据冲突。",
    )


def _approval_request_claims(case_file: ApprovalCaseFile, artifact: EvidenceArtifact, lowered: str, text: str) -> list[EvidenceClaim]:
    claims = [_claim("approval_request_present", "Approval request record exists.", artifact, extracted_value=artifact.metadata)]
    _claim_if(artifact.metadata.get("requester") or case_file.requester, claims, "requester_identity_present", "Requester identity exists.", artifact)
    _claim_if(artifact.metadata.get("amount") is not None or case_file.amount is not None, claims, "amount_present", "Amount exists.", artifact)
    _claim_if(artifact.metadata.get("cost_center") or case_file.cost_center, claims, "cost_center_present", "Cost center exists.", artifact)
    _claim_if(case_file.business_purpose or "purpose" in lowered or "business purpose" in lowered or "用途" in text, claims, "business_purpose_present", "Business purpose exists.", artifact)
    _claim_if(artifact.metadata.get("line_items") or "line item" in lowered or "明细" in text, claims, "line_items_present", "Line item detail exists.", artifact)
    _claim_if(artifact.metadata.get("expense_date") or "expense date" in lowered or "发生日期" in text, claims, "expense_date_present", "Expense date exists.", artifact)
    if (
        artifact.metadata.get("split_order_check")
        or any(term in lowered for term in ("no split", "split order check passed", "not split", "single requisition"))
        or any(term in text for term in ("未拆单", "无拆单", "单一申请"))
    ):
        claims.append(_claim("split_order_check_present", "Split-order check evidence exists and does not show splitting.", artifact))
    if case_file.approval_type == "budget_exception":
        claims.append(_claim("budget_exception_present", "Budget exception request exists.", artifact))
        _claim_if(artifact.metadata.get("budget_owner") or "budget owner" in lowered or "预算负责人" in text, claims, "budget_owner_present", "Budget owner exists.", artifact)
    return claims


def _vendor_claims(artifact: EvidenceArtifact, lowered: str, text: str) -> list[EvidenceClaim]:
    supplier_status = str(artifact.metadata.get("supplier_status") or artifact.metadata.get("status") or "").lower()
    blocked = any(term in lowered for term in ("blocked", "inactive", "sanctioned")) or supplier_status in {"blocked", "inactive", "sanctioned"}
    claims = [
        _claim(
            "vendor_onboarded",
            "Vendor record exists." if not blocked else "Vendor record exists but shows a blocking status.",
            artifact,
            extracted_value=supplier_status or None,
            normalized_value=supplier_status or None,
            verification_status="conflict" if blocked else "supported",
        )
    ]
    if blocked:
        claims.append(
            _claim(
                "vendor_risk_clear",
                "Vendor record shows a blocking or non-clear status.",
                artifact,
                extracted_value="blocked",
                normalized_value="blocked",
                verification_status="conflict",
            )
        )
    if "sanctions" in lowered or "制裁" in text:
        sanctions_status = "pending" if any(term in lowered for term in ("pending", "awaiting", "待", "未完成")) else "clear"
        claims.append(
            _claim(
                "sanctions_check_present",
                f"Sanctions check evidence exists; status={sanctions_status}.",
                artifact,
                extracted_value=sanctions_status,
                normalized_value=sanctions_status,
                verification_status="needs_review" if sanctions_status == "pending" else "supported",
            )
        )
        if sanctions_status == "clear":
            claims.append(_claim("vendor_risk_clear", "Vendor sanctions and risk checks are clear.", artifact))
    if "tax" in lowered or "税" in text:
        claims.append(_claim("supplier_tax_info_present", "Supplier tax information exists.", artifact))
    if "bank" in lowered or "银行" in text:
        claims.append(_claim("supplier_bank_info_present", "Supplier bank information exists.", artifact))
    if "beneficial owner" in lowered or "ubo" in lowered or "受益所有人" in text:
        claims.append(_claim("beneficial_owner_check_present", "Beneficial-owner check exists.", artifact))
    if "due diligence" in lowered or "尽调" in text or "准入尽职调查" in text:
        claims.append(_claim("procurement_due_diligence_present", "Procurement due-diligence evidence exists.", artifact))
    if not any(term in lowered for term in ("pending", "blocked", "sanction", "inactive", "制裁", "阻断")) and supplier_status not in {"blocked", "inactive", "sanctioned"}:
        claims.append(_claim("vendor_risk_clear", "Vendor record does not show an onboarding block.", artifact))
    return claims


def _contract_claims(artifact: EvidenceArtifact, lowered: str, text: str) -> list[EvidenceClaim]:
    claims = [
        _claim("contract_present", "Contract or contract-exception record exists.", artifact),
        _claim("quote_or_contract_present", "Contract, framework agreement, NDA, DPA, or payment-terms record exists.", artifact),
    ]
    if any(term in lowered for term in ("standard terms", "standard contract")) or "标准条款" in text:
        claims.append(_claim("standard_terms_present", "Standard terms evidence exists.", artifact))
    if "exception clause" in lowered or "redline" in lowered or "例外条款" in text or "红线" in text:
        claims.append(_claim("exception_clause_present", "Exception clause or redline evidence exists.", artifact))
    if "liability" in lowered or "责任" in text:
        claims.append(_claim("liability_clause_present", "Liability clause evidence exists.", artifact, metadata={"clause": "liability"}))
    if "payment terms" in lowered or "付款条款" in text:
        claims.append(_claim("payment_terms_present", "Payment terms evidence exists.", artifact))
    if "termination" in lowered or "终止" in text:
        claims.append(_claim("termination_clause_present", "Termination clause evidence exists.", artifact, metadata={"clause": "termination"}))
    if "legal" in lowered or "法务" in text:
        claims.append(_claim("legal_review_required", "Legal review evidence exists.", artifact))
    return claims


def _policy_claims(artifact: EvidenceArtifact, lowered: str, text: str) -> list[EvidenceClaim]:
    claims = [_claim("policy_present", "Policy record exists.", artifact)]
    source = artifact.source_id.lower()
    if "procurement_policy" in source or "procurement" in lowered:
        claims.append(_claim("procurement_policy_present", "Procurement policy evidence exists.", artifact))
    if "expense_policy" in source or "expense" in lowered:
        claims.append(_claim("expense_policy_present", "Expense policy evidence exists.", artifact))
    if "invoice_payment_policy" in source or "invoice" in lowered or "payment policy" in lowered:
        claims.append(_claim("invoice_payment_policy_present", "Invoice payment policy evidence exists.", artifact))
    if "supplier_onboarding_policy" in source or "supplier onboarding" in lowered:
        claims.append(_claim("supplier_onboarding_policy_present", "Supplier onboarding policy evidence exists.", artifact))
    if "legal_policy" in source or "legal" in lowered or "法务" in text:
        claims.append(_claim("legal_policy_present", "Legal policy evidence exists.", artifact))
    if "budget_policy" in source or "finance_policy" in source or "budget policy" in lowered or "finance policy" in lowered:
        claims.append(_claim("finance_policy_present", "Finance or budget policy evidence exists.", artifact))
    if "approval_matrix" in artifact.source_id or "approval matrix" in lowered or "审批矩阵" in text:
        claims.append(_claim("approval_matrix_present", "Approval matrix exists.", artifact))
    if "legal" in lowered or "法务" in text:
        claims.append(_claim("legal_review_required", "Policy requires legal review.", artifact))
    if "approval_matrix" in source or "finance approval matrix" in lowered or "财务审批矩阵" in text:
        claims.append(_claim("finance_review_present", "Policy requires finance review.", artifact))
    return claims


def _sanctions_claims(artifact: EvidenceArtifact, lowered: str, text: str) -> list[EvidenceClaim]:
    status = "pending" if "pending" in lowered or "待" in text or "未完成" in text else "clear"
    claims = [
        _claim(
            "sanctions_check_present",
            f"Sanctions check evidence exists; status={status}.",
            artifact,
            extracted_value=status,
            normalized_value=status,
            verification_status="needs_review" if status == "pending" else "supported",
        )
    ]
    if status == "clear":
        claims.append(_claim("vendor_risk_clear", "Sanctions check does not show a blocking risk.", artifact))
    return claims


def _budget_status(lowered: str, text: str) -> str:
    if any(term in lowered for term in ("insufficient", "over budget", "over_budget", "not enough")) or any(term in text for term in ("不足", "超支")):
        return "insufficient"
    return "available"


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
        metadata={"record_type": artifact.record_type, **dict(artifact.metadata or {}), **dict(metadata or {})},
    )


def _claim_if(value: Any, claims: list[EvidenceClaim], claim_type: str, statement: str, artifact: EvidenceArtifact) -> None:
    if value not in (None, "", [], False):
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


def _canonical_field(field: str, source: dict[str, Any] | None = None) -> str:
    record_type = str((source or {}).get("record_type") or "").lower()
    if field in {"vendor_name", "vendor"}:
        return "vendor"
    if field in {"invoice_amount", "po_amount"}:
        return "amount"
    if field == "supplier_status":
        return "vendor_status"
    if field == "status" and record_type:
        return f"{record_type}_status"
    return field
