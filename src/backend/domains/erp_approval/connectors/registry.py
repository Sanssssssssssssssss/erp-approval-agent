from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from src.backend.domains.erp_approval.connectors.base import ErpReadOnlyConnector
from src.backend.domains.erp_approval.connectors.config import (
    connector_selection_summary,
    load_erp_connector_config_from_env,
    redacted_connector_config,
)
from src.backend.domains.erp_approval.connectors.diagnostics import ErpConnectorDiagnostic, ErpConnectorHealthSummary
from src.backend.domains.erp_approval.connectors.models import ErpConnectorConfig, ErpConnectorProvider
from src.backend.domains.erp_approval.connectors.http_readonly import HttpReadOnlyErpConnector
from src.backend.domains.erp_approval.connectors.provider_profiles import FORBIDDEN_WRITE_METHODS
from src.backend.domains.erp_approval.context_adapter import MockErpReadOnlyConnector


class ErpConnectorRegistry:
    def __init__(
        self,
        *,
        default_provider: ErpConnectorProvider = "mock",
        diagnostics: dict[ErpConnectorProvider, ErpConnectorDiagnostic] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self._connectors: dict[ErpConnectorProvider, ErpReadOnlyConnector] = {}
        self._default_provider = default_provider
        self._diagnostics = diagnostics if diagnostics is not None else {}
        self._warnings = list(warnings or [])

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

    @property
    def selected_provider(self) -> ErpConnectorProvider:
        return self._default_provider

    def diagnostic_summary(self) -> ErpConnectorHealthSummary:
        diagnostics = list(self._diagnostics.values())
        for provider, connector in self._connectors.items():
            if provider not in self._diagnostics:
                health = connector.healthcheck()
                diagnostics.append(
                    ErpConnectorDiagnostic(
                        provider=provider,
                        enabled=bool(health.get("enabled", provider == "mock")),
                        allow_network=bool(health.get("allow_network", False)),
                        mode=str(health.get("mode") or "read_only"),
                        selected_as_default=provider == self._default_provider,
                        status="mock_default" if provider == "mock" and provider == self._default_provider else "ok",
                        warnings=[],
                        redacted_config={},
                        auth_env_var_present=False,
                        forbidden_methods=FORBIDDEN_WRITE_METHODS,
                    )
                )
        return ErpConnectorHealthSummary(
            selected_provider=self._default_provider,
            diagnostics=diagnostics,
            warnings=list(self._warnings),
        )


def build_default_connector_registry(
    base_dir: Path | str | None,
    config: ErpConnectorConfig | None = None,
) -> ErpConnectorRegistry:
    return build_connector_registry_from_config(base_dir, config or ErpConnectorConfig(provider="mock"))


def build_connector_registry_from_env(
    base_dir: Path | str | None,
    env: Mapping[str, str] | None = None,
) -> ErpConnectorRegistry:
    return build_connector_registry_from_config(base_dir, load_erp_connector_config_from_env(env))


def build_connector_registry_from_config(
    base_dir: Path | str | None,
    config: ErpConnectorConfig,
    *,
    transport=None,
) -> ErpConnectorRegistry:
    selection = connector_selection_summary(config)
    default_provider: ErpConnectorProvider = selection["selected_default_provider"]
    warnings = list(selection.get("warnings", []) or [])
    diagnostics: dict[ErpConnectorProvider, ErpConnectorDiagnostic] = {}
    mock_config = ErpConnectorConfig(
        provider="mock",
        mode="read_only",
        enabled=True,
        allow_network=False,
        metadata={"config_warnings": [], "explicit_read_only_opt_in": False, "use_as_default": False},
    )
    diagnostics["mock"] = _diagnostic_for_config(
        mock_config,
        selected_as_default=default_provider == "mock",
        status="mock_default" if default_provider == "mock" else "ok",
        warnings=[],
    )
    registry = ErpConnectorRegistry(default_provider=default_provider, diagnostics=diagnostics, warnings=warnings)
    registry.register(MockErpReadOnlyConnector(base_dir=base_dir))

    explicit_opt_in = bool((config.metadata or {}).get("explicit_read_only_opt_in", False))
    if config.provider == "mock":
        return registry
    if not explicit_opt_in:
        diagnostics[config.provider] = _diagnostic_for_config(
            config,
            selected_as_default=False,
            status="blocked",
            warnings=[*warnings, "Non-mock connector was not registered because explicit read-only opt-in is false."],
        )
        return registry

    registry.register(HttpReadOnlyErpConnector(config, transport=transport))
    connector_warnings = _config_blocking_warnings(config)
    status = "ok" if not connector_warnings else "blocked"
    diagnostics[config.provider] = _diagnostic_for_config(
        config,
        selected_as_default=default_provider == config.provider,
        status=status,
        warnings=[*warnings, *connector_warnings],
    )
    return registry


def _diagnostic_for_config(
    config: ErpConnectorConfig,
    *,
    selected_as_default: bool,
    status: str,
    warnings: list[str],
) -> ErpConnectorDiagnostic:
    redacted = redacted_connector_config(config)
    return ErpConnectorDiagnostic(
        provider=config.provider,
        enabled=config.enabled,
        allow_network=config.allow_network,
        mode="read_only",
        selected_as_default=selected_as_default,
        status=status,
        warnings=list(dict.fromkeys(warnings)),
        redacted_config=redacted,
        auth_env_var_present=bool(redacted.get("auth_env_var_present")),
        forbidden_methods=FORBIDDEN_WRITE_METHODS,
    )


def _config_blocking_warnings(config: ErpConnectorConfig) -> list[str]:
    warnings: list[str] = []
    if config.mode != "read_only":
        warnings.append("Connector mode must be read_only.")
    if not config.enabled:
        warnings.append("Connector is disabled.")
    if not config.allow_network:
        warnings.append("Connector network access is disabled.")
    if not config.base_url.strip():
        warnings.append("Connector base_url is required for HTTP reads.")
    return warnings
