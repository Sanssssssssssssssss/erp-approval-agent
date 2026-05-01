from __future__ import annotations

from typing import Protocol

from src.backend.domains.erp_approval.connectors.models import ErpConnectorProvider, ErpReadRequest, ErpReadResult


class ErpReadOnlyConnector(Protocol):
    @property
    def provider(self) -> ErpConnectorProvider:
        ...

    def fetch_context(self, request: ErpReadRequest) -> ErpReadResult:
        """Return read-only ERP/policy context records for an approval request."""

    def healthcheck(self) -> dict:
        """Return local connector readiness metadata without performing writes."""
