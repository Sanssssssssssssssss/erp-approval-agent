from __future__ import annotations

from typing import Any

from src.backend.domains.erp_approval.connectors.models import ErpConnectorProvider, ErpReadOperation, ErpReadRequest
from src.backend.domains.erp_approval.connectors.provider_profiles import profile_for
from src.backend.domains.erp_approval.schemas import ApprovalContextRecord


def map_provider_payload_to_records(
    provider: ErpConnectorProvider,
    operation: ErpReadOperation | str,
    payload: Any,
    request: ErpReadRequest,
) -> list[ApprovalContextRecord]:
    records: list[ApprovalContextRecord] = []
    for item in normalize_provider_payload(payload):
        entity_id = _entity_id_for(str(operation), item, request)
        content = item.get("content") or item.get("summary") or item.get("description") or item.get("name") or item
        metadata = dict(item.get("metadata", {}) or {})
        metadata.update(
            {
                "provider": provider,
                "read_only": True,
                "operation": str(operation),
                "correlation_id": request.correlation_id,
            }
        )
        records.append(
            ApprovalContextRecord(
                source_id=str(item.get("source_id") or source_id_for_provider(provider, operation, entity_id)),
                title=str(item.get("title") or _title_for(provider, operation, entity_id, item)),
                record_type=str(item.get("record_type") or operation),
                content=content if isinstance(content, str) else str(content),
                metadata=metadata,
            )
        )
    return records


def source_id_for_provider(provider: ErpConnectorProvider, operation: ErpReadOperation | str, entity_id: str) -> str:
    profile = profile_for(provider)
    prefix = str(profile.get("default_source_id_prefix") or f"{provider}://")
    return f"{prefix}{operation}/{entity_id or 'unknown'}"


def normalize_provider_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("records"), list):
        return [dict(item) for item in payload["records"] if isinstance(item, dict)]
    if isinstance(payload.get("value"), list):
        return [dict(item) for item in payload["value"] if isinstance(item, dict)]
    d_section = payload.get("d")
    if isinstance(d_section, dict) and isinstance(d_section.get("results"), list):
        return [dict(item) for item in d_section["results"] if isinstance(item, dict)]
    return [dict(payload)]


def _entity_id_for(operation: str, payload: dict[str, Any], request: ErpReadRequest) -> str:
    request_mapping: dict[str, str] = {
        "approval_request": request.approval_id,
        "vendor": request.vendor,
        "budget": request.cost_center,
        "purchase_order": request.purchase_order_id,
        "invoice": request.invoice_id,
        "goods_receipt": request.goods_receipt_id,
        "contract": request.contract_id,
        "policy": request.approval_type,
    }
    explicit = _first_payload_value(
        payload,
        [
            "id",
            "ID",
            "Id",
            "approval_id",
            "ApprovalId",
            "PurchaseRequisition",
            "PurchaseRequisitionNumber",
            "purchaseRequisitionNumber",
            "Requisition",
            *_operation_id_keys(operation),
            "name",
        ],
    )
    return explicit or request_mapping.get(operation, "") or "unknown"


def _title_for(provider: ErpConnectorProvider, operation: ErpReadOperation | str, entity_id: str, payload: dict[str, Any]) -> str:
    label = payload.get("display_name") or payload.get("name") or payload.get("Description") or payload.get("description") or entity_id
    return f"{provider} {operation} {label}".strip()


def _first_payload_value(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _operation_id_keys(operation: str) -> list[str]:
    return {
        "vendor": [
            "Vendor",
            "VendorId",
            "Supplier",
            "SupplierId",
            "BusinessPartner",
            "vendor_id",
            "supplier_id",
        ],
        "budget": [
            "CostCenter",
            "cost_center",
            "BudgetId",
            "budget_id",
        ],
        "purchase_order": [
            "PurchaseOrder",
            "PurchaseOrderNumber",
            "purchase_order_id",
            "po_number",
        ],
        "invoice": [
            "Invoice",
            "InvoiceNumber",
            "invoice_id",
        ],
        "goods_receipt": [
            "GoodsReceipt",
            "GoodsReceiptNumber",
            "GRN",
            "goods_receipt_id",
        ],
        "contract": [
            "Contract",
            "ContractNumber",
            "contract_id",
        ],
        "policy": [
            "PolicyId",
            "policy_id",
            "PolicyName",
            "policy_name",
        ],
    }.get(operation, [])
