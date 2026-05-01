from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.context import ContextAssembler
from src.backend.domains.erp_approval import (
    ErpConnectorConfig,
    ErpReadRequest,
    HttpReadOnlyErpConnector,
    build_default_connector_registry,
)
from src.backend.domains.erp_approval.connectors.provider_profiles import FORBIDDEN_WRITE_METHODS, PROVIDER_PROFILES
from src.backend.orchestration.executor import HarnessLangGraphOrchestrator
from src.backend.orchestration.state import create_initial_graph_state


class ErpApprovalConnectorTests(unittest.IsolatedAsyncioTestCase):
    def test_default_registry_uses_mock_connector(self) -> None:
        registry = build_default_connector_registry(BACKEND_DIR)

        connector = registry.default()
        result = connector.fetch_context(
            ErpReadRequest(
                approval_id="PR-1001",
                approval_type="purchase_requisition",
                vendor="Acme Supplies",
                cost_center="OPS-CC-10",
            )
        )

        self.assertEqual(connector.provider, "mock")
        self.assertEqual(result.provider, "mock")
        self.assertTrue(result.records)
        self.assertTrue(all(record.source_id for record in result.records))
        self.assertTrue(all(record.title for record in result.records))
        self.assertTrue(all(record.record_type for record in result.records))
        self.assertTrue(all(record.content for record in result.records))
        self.assertIn("No ERP write action was executed", result.non_action_statement)

    def test_provider_profiles_are_read_only_metadata(self) -> None:
        for provider in ("sap_s4_odata", "dynamics_fo_odata", "oracle_fusion_rest", "custom_http_json"):
            profile = PROVIDER_PROFILES[provider]
            self.assertTrue(profile["supported_read_operations"])
            self.assertTrue(str(profile["default_source_id_prefix"]).startswith(f"{provider}://"))
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                self.assertIn(method, profile["forbidden_methods"])

    def test_http_connector_blocks_when_disabled_or_network_disabled(self) -> None:
        disabled = HttpReadOnlyErpConnector(
            ErpConnectorConfig(provider="custom_http_json", enabled=False, allow_network=False, base_url="https://erp.example")
        )
        network_disabled = HttpReadOnlyErpConnector(
            ErpConnectorConfig(provider="custom_http_json", enabled=True, allow_network=False, base_url="https://erp.example")
        )

        disabled_result = disabled.fetch_context(ErpReadRequest(approval_id="PR-1001"))
        network_result = network_disabled.fetch_context(ErpReadRequest(approval_id="PR-1001"))

        self.assertEqual(disabled_result.status, "blocked")
        self.assertIn("disabled", " ".join(disabled_result.warnings).lower())
        self.assertEqual(network_result.status, "blocked")
        self.assertIn("network access is disabled", " ".join(network_result.warnings).lower())

    def test_http_connector_forbids_write_methods(self) -> None:
        connector = HttpReadOnlyErpConnector(ErpConnectorConfig(provider="custom_http_json"))

        self.assertTrue(connector.is_method_allowed("GET"))
        for method in [*FORBIDDEN_WRITE_METHODS, "post", "delete"]:
            self.assertFalse(connector.is_method_allowed(method))

    def test_http_connector_fake_transport_uses_get_and_maps_records(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_transport(method: str, url: str, headers: dict[str, str], timeout: float) -> dict:
            del headers, timeout
            calls.append((method, url))
            return {
                "title": "Read-only PR-1001",
                "content": "Fake read-only approval request context.",
                "metadata": {"approval_ids": ["PR-1001"]},
            }

        connector = HttpReadOnlyErpConnector(
            ErpConnectorConfig(
                provider="custom_http_json",
                enabled=True,
                allow_network=True,
                base_url="https://erp.example",
                auth_type="none",
            ),
            transport=fake_transport,
        )

        result = connector.fetch_context(
            ErpReadRequest(
                approval_id="PR-1001",
                requested_operations=["approval_request"],
                correlation_id="corr-1",
            )
        )

        self.assertEqual(calls, [("GET", "https://erp.example/approval-requests/PR-1001")])
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].source_id, "custom_http_json://approval_request/PR-1001")
        self.assertEqual(result.records[0].record_type, "approval_request")
        self.assertEqual(result.records[0].metadata["correlation_id"], "corr-1")

    def test_http_connector_missing_auth_env_var_blocks_without_secret(self) -> None:
        connector = HttpReadOnlyErpConnector(
            ErpConnectorConfig(
                provider="custom_http_json",
                enabled=True,
                allow_network=True,
                base_url="https://erp.example",
                auth_type="bearer",
                auth_env_var="ERP_APPROVAL_TEST_MISSING_SECRET",
            )
        )

        result = connector.fetch_context(ErpReadRequest(approval_id="PR-1001"))

        self.assertEqual(result.status, "blocked")
        warning_text = " ".join(result.warnings)
        self.assertIn("environment variable is not set", warning_text)
        self.assertNotIn("Bearer", warning_text)
        self.assertNotIn("secret", warning_text.lower())

    async def test_erp_context_node_defaults_to_mock_connector(self) -> None:
        orchestrator = HarnessLangGraphOrchestrator.__new__(HarnessLangGraphOrchestrator)
        orchestrator._context_assembler = ContextAssembler(base_dir=BACKEND_DIR)
        orchestrator._erp_connector_registry = build_default_connector_registry(BACKEND_DIR)
        orchestrator._record_post_turn_snapshot = lambda **_kwargs: None
        orchestrator._write_context_snapshot = lambda **kwargs: (
            {**dict(kwargs.get("state", {}) or {}), **dict(kwargs.get("result", {}) or {})},
            {},
        )

        state = create_initial_graph_state(
            run_id="run-connectors",
            session_id="session-connectors",
            thread_id="thread-connectors",
            user_message="Review PR-1001",
            history=[],
        )
        state["path_kind"] = "erp_approval"
        state["turn_id"] = "run-connectors:0"
        state["erp_request"] = {
            "approval_id": "PR-1001",
            "approval_type": "purchase_requisition",
            "vendor": "Acme Supplies",
            "cost_center": "OPS-CC-10",
        }

        updates = await orchestrator.erp_context_node(state)

        self.assertEqual(updates["erp_connector_result"]["provider"], "mock")
        self.assertEqual(updates["erp_connector_warnings"], [])
        self.assertTrue(updates["erp_context"]["records"])


if __name__ == "__main__":
    unittest.main()
