from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.connectors.models import (
    ERP_CONNECTOR_NON_ACTION_STATEMENT,
    ErpConnectorProvider,
)


ErpConnectorDiagnosticStatus = Literal["ok", "blocked", "unavailable", "mock_default"]


class ErpConnectorDiagnostic(BaseModel):
    provider: ErpConnectorProvider
    enabled: bool = False
    allow_network: bool = False
    mode: str = "read_only"
    selected_as_default: bool = False
    status: ErpConnectorDiagnosticStatus = "unavailable"
    warnings: list[str] = Field(default_factory=list)
    redacted_config: dict[str, Any] = Field(default_factory=dict)
    auth_env_var_present: bool = False
    forbidden_methods: list[str] = Field(default_factory=list)
    non_action_statement: str = ERP_CONNECTOR_NON_ACTION_STATEMENT


class ErpConnectorHealthSummary(BaseModel):
    selected_provider: ErpConnectorProvider = "mock"
    diagnostics: list[ErpConnectorDiagnostic] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    non_action_statement: str = ERP_CONNECTOR_NON_ACTION_STATEMENT


class ErpConnectorProviderProfileSummary(BaseModel):
    provider: ErpConnectorProvider
    display_name: str = ""
    supported_read_operations: list[str] = Field(default_factory=list)
    default_source_id_prefix: str = ""
    endpoint_templates: dict[str, str] = Field(default_factory=dict)
    read_only_notes: str = ""
    forbidden_methods: list[str] = Field(default_factory=list)
    documentation_notes: str = ""
    non_action_statement: str = ERP_CONNECTOR_NON_ACTION_STATEMENT
