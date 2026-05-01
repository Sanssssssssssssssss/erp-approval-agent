from __future__ import annotations

import os
from collections.abc import Mapping
from typing import get_args
from urllib.parse import parse_qsl, quote_plus, urlsplit, urlunsplit

from src.backend.domains.erp_approval.connectors.models import (
    ERP_CONNECTOR_NON_ACTION_STATEMENT,
    ErpConnectorAuthType,
    ErpConnectorConfig,
    ErpConnectorProvider,
)


_VALID_PROVIDERS = set(get_args(ErpConnectorProvider))
_VALID_AUTH_TYPES = set(get_args(ErpConnectorAuthType))
_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off", ""}
_SENSITIVE_QUERY_KEYS = {"token", "access_token", "api_key", "apikey", "key", "password", "secret", "signature", "sig"}


def load_erp_connector_config_from_env(env: Mapping[str, str] | None = None) -> ErpConnectorConfig:
    source = os.environ if env is None else env
    warnings: list[str] = []

    provider = _safe_choice(
        _env_str(source, "ERP_CONNECTOR_PROVIDER", "mock").lower(),
        valid_values=_VALID_PROVIDERS,
        default="mock",
        field_name="ERP_CONNECTOR_PROVIDER",
        warnings=warnings,
    )
    auth_type = _safe_choice(
        _env_str(source, "ERP_CONNECTOR_AUTH_TYPE", "none").lower(),
        valid_values=_VALID_AUTH_TYPES,
        default="none",
        field_name="ERP_CONNECTOR_AUTH_TYPE",
        warnings=warnings,
    )
    timeout_seconds = _safe_timeout(_env_str(source, "ERP_CONNECTOR_TIMEOUT_SECONDS", "10"), warnings)
    explicit_read_only_opt_in = _env_bool(source, "ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN", default=False, warnings=warnings)
    use_as_default = _env_bool(source, "ERP_CONNECTOR_USE_AS_DEFAULT", default=False, warnings=warnings)
    enabled = _env_bool(source, "ERP_CONNECTOR_ENABLED", default=False, warnings=warnings)
    allow_network = _env_bool(source, "ERP_CONNECTOR_ALLOW_NETWORK", default=False, warnings=warnings)
    auth_env_var = _env_str(source, "ERP_CONNECTOR_AUTH_ENV_VAR", "")

    if provider != "mock" and not explicit_read_only_opt_in:
        warnings.append("Non-mock ERP connector provider is blocked without explicit read-only opt-in.")
    if explicit_read_only_opt_in and not allow_network:
        warnings.append("Explicit read-only opt-in does not enable network access; allow_network remains false.")

    metadata = {
        "config_warnings": warnings,
        "explicit_read_only_opt_in": explicit_read_only_opt_in,
        "use_as_default": use_as_default,
        "auth_env_var_present": bool(auth_env_var and source.get(auth_env_var)),
        "non_action_statement": ERP_CONNECTOR_NON_ACTION_STATEMENT,
    }
    return ErpConnectorConfig(
        provider=provider,
        mode="read_only",
        base_url=_env_str(source, "ERP_CONNECTOR_BASE_URL", ""),
        tenant_id=_env_str(source, "ERP_CONNECTOR_TENANT_ID", ""),
        company_id=_env_str(source, "ERP_CONNECTOR_COMPANY_ID", ""),
        timeout_seconds=timeout_seconds,
        enabled=enabled,
        allow_network=allow_network,
        auth_type=auth_type,
        auth_env_var=auth_env_var,
        metadata=metadata,
    )


def redacted_connector_config(config: ErpConnectorConfig) -> dict:
    payload = config.model_dump()
    metadata = dict(payload.get("metadata", {}) or {})
    auth_env_var = str(payload.get("auth_env_var") or "")
    if "auth_env_var_present" in metadata:
        auth_env_var_present = bool(metadata.get("auth_env_var_present"))
    else:
        auth_env_var_present = bool(auth_env_var and os.environ.get(auth_env_var))

    payload["mode"] = "read_only"
    payload["base_url"] = _redact_url_userinfo(str(payload.get("base_url") or ""))
    payload["auth_env_var_present"] = auth_env_var_present
    payload["metadata"] = {
        key: value
        for key, value in metadata.items()
        if key.lower() not in {"auth_secret", "auth_token", "secret_value", *_SENSITIVE_QUERY_KEYS}
    }
    payload["non_action_statement"] = ERP_CONNECTOR_NON_ACTION_STATEMENT
    return payload


def connector_selection_summary(config: ErpConnectorConfig) -> dict:
    metadata = dict(config.metadata or {})
    explicit_opt_in = bool(metadata.get("explicit_read_only_opt_in", False))
    use_as_default = bool(metadata.get("use_as_default", False))
    warnings = list(metadata.get("config_warnings", []) or [])

    selected_provider: ErpConnectorProvider = "mock"
    non_mock_blocked = False
    if config.provider != "mock":
        if not explicit_opt_in:
            non_mock_blocked = True
        elif use_as_default and config.enabled and config.allow_network:
            selected_provider = config.provider
        elif use_as_default:
            warnings.append("Non-mock connector cannot be selected as default unless enabled, network-allowed, and explicitly opted in.")

    return {
        "configured_provider": config.provider,
        "selected_default_provider": selected_provider,
        "enabled": config.enabled,
        "allow_network": config.allow_network,
        "mode": "read_only",
        "explicit_read_only_opt_in": explicit_opt_in,
        "use_as_default": use_as_default,
        "non_mock_blocked": non_mock_blocked,
        "warnings": warnings,
        "non_action_statement": ERP_CONNECTOR_NON_ACTION_STATEMENT,
    }


def _env_str(source: Mapping[str, str], key: str, default: str) -> str:
    value = source.get(key, default)
    return str(value if value is not None else default).strip()


def _env_bool(source: Mapping[str, str], key: str, *, default: bool, warnings: list[str]) -> bool:
    raw = _env_str(source, key, "true" if default else "false").lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    warnings.append(f"{key} has invalid boolean value; using {default}.")
    return default


def _safe_choice(value: str, *, valid_values: set[str], default: str, field_name: str, warnings: list[str]) -> str:
    if value in valid_values:
        return value
    warnings.append(f"{field_name} has invalid value {value!r}; using {default}.")
    return default


def _safe_timeout(value: str, warnings: list[str]) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        warnings.append("ERP_CONNECTOR_TIMEOUT_SECONDS is invalid; using 10.")
        return 10.0
    if timeout < 0.1 or timeout > 120.0:
        warnings.append("ERP_CONNECTOR_TIMEOUT_SECONDS is outside 0.1-120; using 10.")
        return 10.0
    return timeout


def _redact_url_userinfo(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<redacted-url>"
    netloc = parts.netloc
    if "@" in parts.netloc:
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        netloc = f"<redacted>@{host}{port}"
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    redacted_query = "&".join(
        f"{quote_plus(key)}={'<redacted>' if key.lower() in _SENSITIVE_QUERY_KEYS else quote_plus(value)}"
        for key, value in query_pairs
    )
    return urlunsplit((parts.scheme, netloc, parts.path, redacted_query, parts.fragment))
