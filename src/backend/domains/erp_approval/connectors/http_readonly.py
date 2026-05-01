from __future__ import annotations

import os
import urllib.request
from typing import Any, Callable

from src.backend.domains.erp_approval.connectors.models import (
    ERP_CONNECTOR_NON_ACTION_STATEMENT,
    ErpConnectorConfig,
    ErpConnectorProvider,
    ErpReadOperation,
    ErpReadRequest,
    ErpReadResult,
)
from src.backend.domains.erp_approval.connectors.mappers import map_provider_payload_to_records
from src.backend.domains.erp_approval.connectors.provider_profiles import FORBIDDEN_WRITE_METHODS, profile_for
from src.backend.domains.erp_approval.schemas import ApprovalContextRecord


Transport = Callable[[str, str, dict[str, str], float], dict[str, Any]]


class HttpReadOnlyErpConnector:
    def __init__(self, config: ErpConnectorConfig, *, transport: Transport | None = None) -> None:
        self.config = config
        self._transport = transport
        self._profile = profile_for(config.provider)

    @property
    def provider(self) -> ErpConnectorProvider:
        return self.config.provider

    def healthcheck(self) -> dict:
        return {
            "provider": self.provider,
            "enabled": self.config.enabled,
            "allow_network": self.config.allow_network,
            "mode": self.config.mode,
            "read_only": True,
            "forbidden_methods": FORBIDDEN_WRITE_METHODS,
            "non_action_statement": ERP_CONNECTOR_NON_ACTION_STATEMENT,
        }

    def is_method_allowed(self, method: str) -> bool:
        normalized = method.strip().upper()
        return normalized == "GET" and normalized not in FORBIDDEN_WRITE_METHODS

    def fetch_context(self, request: ErpReadRequest) -> ErpReadResult:
        warnings = self._blocked_warnings()
        if warnings:
            return ErpReadResult(
                provider=self.provider,
                status="blocked",
                records=[],
                warnings=warnings,
                diagnostics=self.healthcheck(),
                non_action_statement=ERP_CONNECTOR_NON_ACTION_STATEMENT,
            )

        records = []
        diagnostics: dict[str, Any] = {"requested_operations": list(request.requested_operations)}
        operations = request.requested_operations or ["approval_request", "vendor", "budget", "purchase_order", "invoice", "goods_receipt", "contract", "policy"]
        for operation in operations:
            operation_value = str(operation)
            url = self._url_for(operation_value, request)
            if not url:
                continue
            payload = self._get(url)
            records.extend(self._records_from_payload(operation_value, payload, request))

        status = "success" if records else "unavailable"
        return ErpReadResult(
            provider=self.provider,
            status=status,
            records=records,
            warnings=[] if records else ["No read-only records were returned by the connector transport."],
            diagnostics=diagnostics,
            non_action_statement=ERP_CONNECTOR_NON_ACTION_STATEMENT,
        )

    def _blocked_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.config.mode != "read_only":
            warnings.append("Connector mode must be read_only.")
        if not self.config.enabled:
            warnings.append("Connector is disabled.")
        if not self.config.allow_network:
            warnings.append("Connector network access is disabled.")
        if self.config.provider == "mock":
            warnings.append("HTTP connector cannot use the mock provider.")
        if self.config.auth_type != "none":
            if not self.config.auth_env_var:
                warnings.append("Connector auth_env_var is required for non-none auth.")
            elif not self._auth_env_var_present():
                warnings.append("Connector auth environment variable is not set.")
        if not self.config.base_url.strip():
            warnings.append("Connector base_url is required for HTTP reads.")
        return warnings

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.config.auth_type == "bearer" and self.config.auth_env_var and self._auth_env_var_present():
            headers["Authorization"] = "Bearer <redacted>"
        elif self.config.auth_type == "api_key" and self.config.auth_env_var and self._auth_env_var_present():
            headers["X-API-Key"] = "<redacted>"
        elif self.config.auth_type == "basic" and self.config.auth_env_var and self._auth_env_var_present():
            headers["Authorization"] = "Basic <redacted>"
        return headers

    def _auth_env_var_present(self) -> bool:
        metadata = dict(self.config.metadata or {})
        if "auth_env_var_present" in metadata:
            return bool(metadata.get("auth_env_var_present"))
        return bool(self.config.auth_env_var and os.environ.get(self.config.auth_env_var))

    def _get(self, url: str) -> dict[str, Any]:
        if not self.is_method_allowed("GET"):
            return {"warning": "GET method was unexpectedly blocked."}
        headers = self._headers()
        if self._transport is not None:
            return self._transport("GET", url, headers, self.config.timeout_seconds)
        request = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:  # nosec B310 - disabled by default and allow_network-gated.
            import json

            return json.loads(response.read().decode("utf-8"))

    def _url_for(self, operation: str, request: ErpReadRequest) -> str:
        template = dict(self._profile.get("endpoint_templates", {})).get(operation)
        if not template:
            return ""
        base = self.config.base_url.rstrip("/")
        values = {
            "approval_id": request.approval_id,
            "vendor": request.vendor,
            "cost_center": request.cost_center,
            "purchase_order_id": request.purchase_order_id,
            "invoice_id": request.invoice_id,
            "goods_receipt_id": request.goods_receipt_id,
            "contract_id": request.contract_id,
            "tenant_id": self.config.tenant_id,
            "company_id": self.config.company_id,
        }
        try:
            path = template.format(**values)
        except Exception:
            return ""
        if "{" in path or "}" in path:
            return ""
        return f"{base}{path}"

    def _records_from_payload(self, operation: str, payload: dict[str, Any], request: ErpReadRequest) -> list[ApprovalContextRecord]:
        return map_provider_payload_to_records(self.provider, operation, payload, request)

    def _entity_id_for(self, operation: str, request: ErpReadRequest) -> str:
        mapping: dict[str, str] = {
            "approval_request": request.approval_id,
            "vendor": request.vendor,
            "budget": request.cost_center,
            "purchase_order": request.purchase_order_id,
            "invoice": request.invoice_id,
            "goods_receipt": request.goods_receipt_id,
            "contract": request.contract_id,
            "policy": request.approval_type,
        }
        return mapping.get(operation, "")
