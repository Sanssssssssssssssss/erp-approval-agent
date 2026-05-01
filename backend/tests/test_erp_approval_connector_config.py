from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval import (
    ErpReadRequest,
    build_connector_registry_from_config,
    build_connector_registry_from_env,
    connector_selection_summary,
    load_erp_connector_config_from_env,
    redacted_connector_config,
)
from src.backend.orchestration.state import GRAPH_VERSION, create_initial_graph_state


class ErpApprovalConnectorConfigTests(unittest.TestCase):
    def test_env_loader_defaults_to_disabled_mock_without_network(self) -> None:
        config = load_erp_connector_config_from_env({})

        self.assertEqual(config.provider, "mock")
        self.assertFalse(config.enabled)
        self.assertFalse(config.allow_network)
        self.assertEqual(config.mode, "read_only")
        self.assertEqual(config.timeout_seconds, 10)

    def test_invalid_env_values_fall_back_safely(self) -> None:
        config = load_erp_connector_config_from_env(
            {
                "ERP_CONNECTOR_PROVIDER": "production_sap",
                "ERP_CONNECTOR_AUTH_TYPE": "oauth-secret",
                "ERP_CONNECTOR_TIMEOUT_SECONDS": "not-a-number",
            }
        )

        self.assertEqual(config.provider, "mock")
        self.assertEqual(config.auth_type, "none")
        self.assertEqual(config.timeout_seconds, 10)
        self.assertTrue(config.metadata["config_warnings"])

    def test_non_mock_without_explicit_opt_in_is_not_default_or_registered(self) -> None:
        config = load_erp_connector_config_from_env(
            {
                "ERP_CONNECTOR_PROVIDER": "custom_http_json",
                "ERP_CONNECTOR_ENABLED": "true",
                "ERP_CONNECTOR_ALLOW_NETWORK": "true",
                "ERP_CONNECTOR_BASE_URL": "https://erp.example",
            }
        )
        registry = build_connector_registry_from_config(BACKEND_DIR, config)
        summary = registry.diagnostic_summary()

        self.assertEqual(registry.default().provider, "mock")
        self.assertIsNone(registry.get("custom_http_json"))
        self.assertTrue(connector_selection_summary(config)["non_mock_blocked"])
        custom_diagnostic = [item for item in summary.diagnostics if item.provider == "custom_http_json"][0]
        self.assertEqual(custom_diagnostic.status, "blocked")

    def test_explicit_opt_in_does_not_enable_network(self) -> None:
        config = load_erp_connector_config_from_env(
            {
                "ERP_CONNECTOR_PROVIDER": "custom_http_json",
                "ERP_CONNECTOR_ENABLED": "true",
                "ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN": "true",
                "ERP_CONNECTOR_ALLOW_NETWORK": "false",
                "ERP_CONNECTOR_BASE_URL": "https://erp.example",
                "ERP_CONNECTOR_USE_AS_DEFAULT": "true",
            }
        )
        registry = build_connector_registry_from_config(BACKEND_DIR, config)

        self.assertEqual(registry.default().provider, "mock")
        self.assertIsNotNone(registry.get("custom_http_json"))
        result = registry.get("custom_http_json").fetch_context(ErpReadRequest(approval_id="PR-1001"))  # type: ignore[union-attr]
        self.assertEqual(result.status, "blocked")
        self.assertIn("network access is disabled", " ".join(result.warnings).lower())

    def test_redacted_config_never_contains_secret_value(self) -> None:
        config = load_erp_connector_config_from_env(
            {
                "ERP_CONNECTOR_PROVIDER": "custom_http_json",
                "ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN": "true",
                "ERP_CONNECTOR_BASE_URL": "https://user:password@example.test/path?token=abc&company=100&api_key=xyz&password=pw&secret=s&signature=sig",
                "ERP_CONNECTOR_AUTH_TYPE": "bearer",
                "ERP_CONNECTOR_AUTH_ENV_VAR": "ERP_SECRET_FOR_TEST",
                "ERP_SECRET_FOR_TEST": "dummy-token-not-for-output",
            }
        )
        redacted = redacted_connector_config(config)

        self.assertTrue(redacted["auth_env_var_present"])
        self.assertEqual(redacted["auth_env_var"], "ERP_SECRET_FOR_TEST")
        self.assertNotIn("dummy-token-not-for-output", str(redacted))
        self.assertNotIn("password=pw", str(redacted))
        self.assertNotIn("abc", str(redacted))
        self.assertNotIn("xyz", str(redacted))
        self.assertIn("<redacted>@example.test", redacted["base_url"])
        self.assertIn("token=<redacted>", redacted["base_url"])
        self.assertIn("company=100", redacted["base_url"])
        self.assertIn("api_key=<redacted>", redacted["base_url"])
        self.assertIn("secret=<redacted>", redacted["base_url"])
        self.assertIn("signature=<redacted>", redacted["base_url"])

    def test_registry_from_env_default_remains_mock(self) -> None:
        registry = build_connector_registry_from_env(
            BACKEND_DIR,
            {
                "ERP_CONNECTOR_PROVIDER": "custom_http_json",
                "ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN": "true",
                "ERP_CONNECTOR_ENABLED": "true",
                "ERP_CONNECTOR_ALLOW_NETWORK": "true",
                "ERP_CONNECTOR_BASE_URL": "https://erp.example",
            },
        )

        self.assertEqual(registry.default().provider, "mock")

    def test_use_as_default_requires_all_explicit_read_only_gates(self) -> None:
        config = load_erp_connector_config_from_env(
            {
                "ERP_CONNECTOR_PROVIDER": "custom_http_json",
                "ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN": "true",
                "ERP_CONNECTOR_USE_AS_DEFAULT": "true",
                "ERP_CONNECTOR_ENABLED": "true",
                "ERP_CONNECTOR_ALLOW_NETWORK": "true",
                "ERP_CONNECTOR_BASE_URL": "https://erp.example",
            }
        )
        registry = build_connector_registry_from_config(BACKEND_DIR, config)

        self.assertEqual(registry.default().provider, "custom_http_json")
        self.assertEqual(registry.diagnostic_summary().selected_provider, "custom_http_json")

    def test_graph_version_is_phase14(self) -> None:
        state = create_initial_graph_state(run_id="run", session_id="session", thread_id="thread", user_message="", history=[])

        self.assertEqual(GRAPH_VERSION, "phase14")
        self.assertEqual(state["checkpoint_meta"]["graph_version"], "phase14")
        self.assertNotEqual(state["checkpoint_meta"]["graph_version"], "phase7")


if __name__ == "__main__":
    unittest.main()
