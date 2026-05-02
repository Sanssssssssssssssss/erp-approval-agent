from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.connectors.models import (
    ERP_CONNECTOR_NON_ACTION_STATEMENT,
    ErpReadRequest,
    ErpReadResult,
)
from src.backend.domains.erp_approval.schemas import ApprovalContextBundle, ApprovalContextRecord, ApprovalRequest


READ_ONLY_RECORD_TYPES = {
    "approval_request",
    "vendor",
    "budget",
    "purchase_order",
    "invoice",
    "goods_receipt",
    "contract",
    "policy",
}

LOCAL_EVIDENCE_RECORD_TYPES = {
    "quote",
    "receipt",
    "duplicate_check",
    "limit_check",
    "payment_terms",
    "sanctions_check",
    "tax_info",
    "bank_info",
    "beneficial_owner",
    "due_diligence",
    "budget_owner",
    "finance_review",
}

CONTEXT_RECORD_TYPES = READ_ONLY_RECORD_TYPES | LOCAL_EVIDENCE_RECORD_TYPES


class ErpContextQuery(BaseModel):
    approval_type: str = "unknown"
    approval_id: str = ""
    vendor: str = ""
    cost_center: str = ""
    purchase_order_id: str = ""
    invoice_id: str = ""
    goods_receipt_id: str = ""
    contract_id: str = ""
    requested_record_types: list[str] = Field(default_factory=list)

    @classmethod
    def from_request(cls, request: ApprovalRequest) -> "ErpContextQuery":
        return cls(
            approval_type=request.approval_type,
            approval_id=request.approval_id,
            vendor=request.vendor,
            cost_center=request.cost_center,
            requested_record_types=sorted(READ_ONLY_RECORD_TYPES),
        )


class ErpContextAdapter(Protocol):
    def fetch_context(self, query: ErpContextQuery) -> ApprovalContextBundle:
        """Return read-only ERP and policy context for an approval query."""


def build_context_bundle_from_records(
    records: list[ApprovalContextRecord | dict],
    *,
    request_id: str = "",
) -> ApprovalContextBundle:
    normalized: list[ApprovalContextRecord] = []
    seen: set[str] = set()
    for item in records:
        try:
            record = item if isinstance(item, ApprovalContextRecord) else ApprovalContextRecord.model_validate(item)
        except Exception:
            continue
        if record.record_type not in CONTEXT_RECORD_TYPES:
            continue
        if not record.source_id or record.source_id in seen:
            continue
        seen.add(record.source_id)
        normalized.append(record)
    return ApprovalContextBundle(request_id=request_id, records=normalized)


def read_request_from_context_query(query: ErpContextQuery) -> ErpReadRequest:
    requested_operations = [
        item
        for item in query.requested_record_types
        if item in READ_ONLY_RECORD_TYPES
    ] or sorted(READ_ONLY_RECORD_TYPES)
    return ErpReadRequest(
        approval_id=query.approval_id,
        approval_type=query.approval_type,
        vendor=query.vendor,
        cost_center=query.cost_center,
        purchase_order_id=query.purchase_order_id,
        invoice_id=query.invoice_id,
        goods_receipt_id=query.goods_receipt_id,
        contract_id=query.contract_id,
        requested_operations=requested_operations,  # type: ignore[arg-type]
        correlation_id=query.approval_id or "unidentified",
    )


class MockErpReadOnlyConnector:
    def __init__(self, *, base_dir: Path | str | None = None, fixture_path: Path | str | None = None) -> None:
        self._adapter = MockErpContextAdapter(base_dir=base_dir, fixture_path=fixture_path)

    @property
    def provider(self):
        return "mock"

    def fetch_context(self, request: ErpReadRequest) -> ErpReadResult:
        query = ErpContextQuery(
            approval_type=request.approval_type,
            approval_id=request.approval_id,
            vendor=request.vendor,
            cost_center=request.cost_center,
            purchase_order_id=request.purchase_order_id,
            invoice_id=request.invoice_id,
            goods_receipt_id=request.goods_receipt_id,
            contract_id=request.contract_id,
            requested_record_types=list(request.requested_operations) or sorted(READ_ONLY_RECORD_TYPES),
        )
        bundle = self._adapter.fetch_context(query)
        return ErpReadResult(
            provider="mock",
            status="success" if bundle.records else "unavailable",
            records=list(bundle.records),
            warnings=[] if bundle.records else ["Mock ERP connector returned no records."],
            diagnostics={"fixture_backed": True, "request_id": bundle.request_id},
            non_action_statement=ERP_CONNECTOR_NON_ACTION_STATEMENT,
        )

    def healthcheck(self) -> dict:
        return {
            "provider": self.provider,
            "enabled": True,
            "allow_network": False,
            "mode": "read_only",
            "read_only": True,
            "non_action_statement": ERP_CONNECTOR_NON_ACTION_STATEMENT,
        }


class MockErpContextAdapter:
    def __init__(self, *, base_dir: Path | str | None = None, fixture_path: Path | str | None = None) -> None:
        self._base_dir = Path(base_dir).resolve() if base_dir is not None else None
        self._fixture_path = Path(fixture_path).resolve() if fixture_path is not None else None

    def fetch_context(self, query: ErpContextQuery) -> ApprovalContextBundle:
        records = self._matching_fixture_records(query)
        if not records:
            records = self._fallback_policy_records(query)
        return build_context_bundle_from_records(records, request_id=query.approval_id or "unidentified")

    def _matching_fixture_records(self, query: ErpContextQuery) -> list[dict]:
        records = self._load_fixture_records()
        if not records:
            return []
        matched = [record for record in records if self._record_matches_query(record, query)]
        if not any(str(item.get("record_type", "")) == "policy" for item in matched):
            matched.extend(self._policy_records_for(query, records))
        return matched

    def _load_fixture_records(self) -> list[dict]:
        path = self._resolved_fixture_path()
        if path is None or not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        records = payload.get("records", payload) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return []
        return [dict(item) for item in records if isinstance(item, dict)]

    def _resolved_fixture_path(self) -> Path | None:
        if self._fixture_path is not None:
            return self._fixture_path
        candidates: list[Path] = []
        if self._base_dir is not None:
            candidates.append(self._base_dir / "fixtures" / "erp_approval" / "mock_context_records.json")
            candidates.append(self._base_dir / "backend" / "fixtures" / "erp_approval" / "mock_context_records.json")
        current = Path(__file__).resolve()
        for parent in current.parents:
            candidates.append(parent / "backend" / "fixtures" / "erp_approval" / "mock_context_records.json")
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0] if candidates else None

    def _record_matches_query(self, record: dict, query: ErpContextQuery) -> bool:
        record_type = str(record.get("record_type", "") or "").strip()
        metadata = dict(record.get("metadata", {}) or {})
        source_id = str(record.get("source_id", "") or "")
        approval_ids = {str(item) for item in metadata.get("approval_ids", []) or []}
        if query.approval_id and (query.approval_id in approval_ids or source_id.endswith(f"/{query.approval_id}")):
            return True
        if record_type == "vendor" and query.vendor:
            return self._same_key(query.vendor, source_id.rsplit("/", 1)[-1]) or self._same_key(query.vendor, metadata.get("vendor_name", ""))
        if record_type == "budget" and query.cost_center:
            return self._same_key(query.cost_center, source_id.rsplit("/", 1)[-1]) or self._same_key(query.cost_center, metadata.get("cost_center", ""))
        if record_type == "policy":
            applies_to = {str(item) for item in metadata.get("applies_to", []) or []}
            return not applies_to or query.approval_type in applies_to or "all" in applies_to
        return False

    def _policy_records_for(self, query: ErpContextQuery, records: list[dict]) -> list[dict]:
        return [
            record
            for record in records
            if str(record.get("record_type", "") or "") == "policy" and self._record_matches_query(record, query)
        ]

    def _fallback_policy_records(self, query: ErpContextQuery) -> list[ApprovalContextRecord]:
        del query
        return [
            ApprovalContextRecord(
                source_id="mock_policy://approval_matrix",
                title="Approval matrix",
                record_type="policy",
                content="Mock approval matrix requiring manager, finance, procurement, or legal review based on request type and risk.",
                metadata={"applies_to": ["all"]},
            ),
            ApprovalContextRecord(
                source_id="mock_policy://procurement_policy",
                title="Procurement policy",
                record_type="policy",
                content="Mock procurement policy requiring vendor, amount, cost center, business purpose, and budget evidence.",
                metadata={"applies_to": ["purchase_requisition", "contract_exception"]},
            ),
            ApprovalContextRecord(
                source_id="mock_policy://expense_policy",
                title="Expense policy",
                record_type="policy",
                content="Mock expense policy requiring receipts, business purpose, requester, department, and exception review.",
                metadata={"applies_to": ["expense"]},
            ),
            ApprovalContextRecord(
                source_id="mock_policy://invoice_payment_policy",
                title="Invoice/payment policy",
                record_type="policy",
                content="Mock invoice policy requiring PO, goods receipt, invoice amount, vendor, and approval authority checks.",
                metadata={"applies_to": ["invoice_payment"]},
            ),
            ApprovalContextRecord(
                source_id="mock_policy://supplier_onboarding_policy",
                title="Supplier onboarding policy",
                record_type="policy",
                content="Mock supplier onboarding policy requiring tax, banking, sanctions, ownership, and procurement due diligence.",
                metadata={"applies_to": ["supplier_onboarding"]},
            ),
            ApprovalContextRecord(
                source_id="mock_policy://budget_policy",
                title="Generic budget policy",
                record_type="policy",
                content="Mock budget policy requiring finance review for budget exceptions or unclear funding.",
                metadata={"applies_to": ["budget_exception", "purchase_requisition", "all"]},
            ),
        ]

    def _same_key(self, left: object, right: object) -> bool:
        return self._normalize_key(left) == self._normalize_key(right)

    def _normalize_key(self, value: object) -> str:
        return str(value or "").strip().lower().replace(" ", "-").replace("_", "-")
