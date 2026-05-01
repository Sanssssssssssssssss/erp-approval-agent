from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.schemas import ApprovalContextRecord


ERP_CONNECTOR_NON_ACTION_STATEMENT = "Read-only connector. No ERP write action was executed."

ErpConnectorProvider = Literal[
    "mock",
    "sap_s4_odata",
    "dynamics_fo_odata",
    "oracle_fusion_rest",
    "custom_http_json",
]
ErpConnectorMode = Literal["read_only"]
ErpConnectorAuthType = Literal["none", "bearer", "basic", "api_key"]
ErpReadOperation = Literal[
    "approval_request",
    "vendor",
    "budget",
    "purchase_order",
    "invoice",
    "goods_receipt",
    "contract",
    "policy",
]
ErpReadResultStatus = Literal["success", "partial", "unavailable", "blocked"]


class ErpConnectorConfig(BaseModel):
    provider: ErpConnectorProvider = "mock"
    mode: ErpConnectorMode = "read_only"
    base_url: str = ""
    tenant_id: str = ""
    company_id: str = ""
    timeout_seconds: float = Field(default=10.0, ge=0.1, le=120.0)
    enabled: bool = False
    allow_network: bool = False
    auth_type: ErpConnectorAuthType = "none"
    auth_env_var: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErpReadRequest(BaseModel):
    approval_id: str = ""
    approval_type: str = "unknown"
    vendor: str = ""
    cost_center: str = ""
    purchase_order_id: str = ""
    invoice_id: str = ""
    goods_receipt_id: str = ""
    contract_id: str = ""
    requested_operations: list[ErpReadOperation] = Field(default_factory=list)
    actor_id: str = ""
    actor_role: str = ""
    correlation_id: str = ""


class ErpReadResult(BaseModel):
    provider: ErpConnectorProvider = "mock"
    status: ErpReadResultStatus = "unavailable"
    records: list[ApprovalContextRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    non_action_statement: str = ERP_CONNECTOR_NON_ACTION_STATEMENT
