from __future__ import annotations

from typing import Any

from src.backend.domains.erp_approval.connectors.models import ErpConnectorProvider, ErpReadOperation


FORBIDDEN_WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE", "MERGE"]

PROVIDER_PROFILES: dict[ErpConnectorProvider, dict[str, Any]] = {
    "sap_s4_odata": {
        "provider": "sap_s4_odata",
        "display_name": "SAP S/4HANA OData",
        "supported_read_operations": [
            "approval_request",
            "vendor",
            "budget",
            "purchase_order",
            "invoice",
            "goods_receipt",
            "contract",
            "policy",
        ],
        "default_source_id_prefix": "sap_s4_odata://",
        "endpoint_templates": {
            "approval_request": "/sap/opu/odata/sap/API_PURCHASEREQ_PROCESS_SRV/A_PurchaseRequisition('{approval_id}')",
            "vendor": "/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_BusinessPartner('{vendor}')",
            "purchase_order": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder('{purchase_order_id}')",
        },
        "read_only_notes": "Metadata only. This profile describes possible GET reads; it is not a live SAP integration.",
        "forbidden_methods": FORBIDDEN_WRITE_METHODS,
        "documentation_notes": "Enable only with explicit read-only credentials and network allow-listing outside Phase 10.",
    },
    "dynamics_fo_odata": {
        "provider": "dynamics_fo_odata",
        "display_name": "Microsoft Dynamics 365 Finance & Operations OData",
        "supported_read_operations": [
            "approval_request",
            "vendor",
            "budget",
            "purchase_order",
            "invoice",
            "goods_receipt",
            "contract",
            "policy",
        ],
        "default_source_id_prefix": "dynamics_fo_odata://",
        "endpoint_templates": {
            "approval_request": "/data/PurchaseRequisitionHeaders('{approval_id}')",
            "vendor": "/data/Vendors('{vendor}')",
            "invoice": "/data/VendorInvoiceHeaders('{invoice_id}')",
        },
        "read_only_notes": "Metadata only. This profile describes possible GET reads; it is not a live Dynamics integration.",
        "forbidden_methods": FORBIDDEN_WRITE_METHODS,
        "documentation_notes": "OAuth/application registration and environment routing remain future work.",
    },
    "oracle_fusion_rest": {
        "provider": "oracle_fusion_rest",
        "display_name": "Oracle Fusion Procurement REST",
        "supported_read_operations": [
            "approval_request",
            "vendor",
            "budget",
            "purchase_order",
            "invoice",
            "goods_receipt",
            "contract",
            "policy",
        ],
        "default_source_id_prefix": "oracle_fusion_rest://",
        "endpoint_templates": {
            "approval_request": "/fscmRestApi/resources/latest/purchaseRequisitions/{approval_id}",
            "vendor": "/fscmRestApi/resources/latest/suppliers/{vendor}",
            "purchase_order": "/fscmRestApi/resources/latest/purchaseOrders/{purchase_order_id}",
        },
        "read_only_notes": "Metadata only. This profile describes possible GET reads; it is not a live Oracle integration.",
        "forbidden_methods": FORBIDDEN_WRITE_METHODS,
        "documentation_notes": "Read-only user setup and endpoint scoping remain future work.",
    },
    "custom_http_json": {
        "provider": "custom_http_json",
        "display_name": "Custom HTTP JSON",
        "supported_read_operations": [
            "approval_request",
            "vendor",
            "budget",
            "purchase_order",
            "invoice",
            "goods_receipt",
            "contract",
            "policy",
        ],
        "default_source_id_prefix": "custom_http_json://",
        "endpoint_templates": {
            "approval_request": "/approval-requests/{approval_id}",
            "vendor": "/vendors/{vendor}",
            "budget": "/budgets/{cost_center}",
        },
        "read_only_notes": "Metadata only. Custom HTTP JSON must remain GET-only in this interface.",
        "forbidden_methods": FORBIDDEN_WRITE_METHODS,
        "documentation_notes": "Schemas and auth handling should be defined per deployment without storing secrets in the repo.",
    },
}


def profile_for(provider: ErpConnectorProvider) -> dict[str, Any]:
    return dict(PROVIDER_PROFILES.get(provider, {}))


def supported_operations_for(provider: ErpConnectorProvider) -> list[ErpReadOperation]:
    profile = PROVIDER_PROFILES.get(provider, {})
    return list(profile.get("supported_read_operations", []))
