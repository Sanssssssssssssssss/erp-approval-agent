from __future__ import annotations

from pathlib import Path

from src.backend.domains.erp_approval.connectors.base import ErpReadOnlyConnector
from src.backend.domains.erp_approval.connectors.models import ErpConnectorConfig, ErpConnectorProvider
from src.backend.domains.erp_approval.connectors.http_readonly import HttpReadOnlyErpConnector
from src.backend.domains.erp_approval.context_adapter import MockErpReadOnlyConnector


class ErpConnectorRegistry:
    def __init__(self, *, default_provider: ErpConnectorProvider = "mock") -> None:
        self._connectors: dict[ErpConnectorProvider, ErpReadOnlyConnector] = {}
        self._default_provider = default_provider

    def register(self, connector: ErpReadOnlyConnector) -> None:
        self._connectors[connector.provider] = connector

    def get(self, provider: ErpConnectorProvider) -> ErpReadOnlyConnector | None:
        return self._connectors.get(provider)

    def default(self) -> ErpReadOnlyConnector:
        connector = self.get(self._default_provider)
        if connector is None:
            raise KeyError(f"No ERP connector registered for default provider {self._default_provider!r}")
        return connector

    def healthcheck(self) -> dict:
        return {provider: connector.healthcheck() for provider, connector in self._connectors.items()}


def build_default_connector_registry(
    base_dir: Path | str | None,
    config: ErpConnectorConfig | None = None,
) -> ErpConnectorRegistry:
    registry = ErpConnectorRegistry(default_provider="mock")
    registry.register(MockErpReadOnlyConnector(base_dir=base_dir))
    if config is not None and config.provider != "mock":
        # Registered for explicit tests/future configuration only. The default connector remains mock.
        registry.register(HttpReadOnlyErpConnector(config))
    return registry
