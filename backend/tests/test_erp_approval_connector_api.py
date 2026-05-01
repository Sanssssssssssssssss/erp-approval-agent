from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.api import erp_approval as erp_approval_api


class ErpApprovalConnectorApiTests(unittest.TestCase):
    def test_connector_config_and_health_are_read_only_get_endpoints(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")
        with patch.dict(
            "os.environ",
            {
                "ERP_CONNECTOR_PROVIDER": "mock",
                "ERP_CONNECTOR_ENABLED": "false",
                "ERP_CONNECTOR_ALLOW_NETWORK": "false",
            },
            clear=False,
        ):
            client = TestClient(app)
            config_response = client.get("/api/erp-approval/connectors/config")
            health_response = client.get("/api/erp-approval/connectors/health")

        self.assertEqual(config_response.status_code, 200)
        self.assertEqual(config_response.json()["config"]["provider"], "mock")
        self.assertFalse(config_response.json()["config"]["enabled"])
        self.assertFalse(config_response.json()["config"]["allow_network"])
        self.assertIn("No ERP write action was executed", config_response.json()["non_action_statement"])
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json()["selected_provider"], "mock")
        self.assertEqual(health_response.json()["diagnostics"][0]["status"], "mock_default")
        self.assertIn("POST", health_response.json()["diagnostics"][0]["forbidden_methods"])

        for route in app.routes:
            path = getattr(route, "path", "")
            if path.startswith("/api/erp-approval/connectors"):
                self.assertEqual(getattr(route, "methods", set()), {"GET"})

    def test_connector_health_does_not_trigger_network_for_non_mock_config(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")
        with patch.dict(
            "os.environ",
            {
                "ERP_CONNECTOR_PROVIDER": "custom_http_json",
                "ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN": "true",
                "ERP_CONNECTOR_ENABLED": "true",
                "ERP_CONNECTOR_ALLOW_NETWORK": "false",
                "ERP_CONNECTOR_BASE_URL": "https://erp.example",
            },
            clear=False,
        ):
            client = TestClient(app)
            response = client.get("/api/erp-approval/connectors/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected_provider"], "mock")
        custom = [item for item in payload["diagnostics"] if item["provider"] == "custom_http_json"][0]
        self.assertEqual(custom["status"], "blocked")
        self.assertIn("Connector network access is disabled", " ".join(custom["warnings"]))

    def test_profiles_api_returns_provider_metadata_and_404s_unknown_provider(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")
        client = TestClient(app)

        list_response = client.get("/api/erp-approval/connectors/profiles")
        detail_response = client.get("/api/erp-approval/connectors/profiles/sap_s4_odata")
        missing_response = client.get("/api/erp-approval/connectors/profiles/not_a_provider")

        self.assertEqual(list_response.status_code, 200)
        providers = {item["provider"] for item in list_response.json()}
        self.assertTrue({"sap_s4_odata", "dynamics_fo_odata", "oracle_fusion_rest", "custom_http_json"}.issubset(providers))
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("SAP", detail_response.json()["display_name"])
        for method in ("POST", "PUT", "PATCH", "DELETE", "MERGE"):
            self.assertIn(method, detail_response.json()["forbidden_methods"])
        self.assertIn("Metadata only", detail_response.json()["read_only_notes"])
        self.assertEqual(missing_response.status_code, 404)

    def test_replay_api_lists_fixtures_and_replays_without_network(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")
        client = TestClient(app)

        with patch("urllib.request.urlopen", side_effect=AssertionError("network should not be accessed")):
            fixtures_response = client.get("/api/erp-approval/connectors/replay/fixtures")
            coverage_response = client.get("/api/erp-approval/connectors/replay/coverage")
            replay_response = client.get(
                "/api/erp-approval/connectors/replay",
                params={
                    "provider": "sap_s4_odata",
                    "operation": "approval_request",
                    "fixture_name": "sap_s4_odata_purchase_requisition.json",
                    "approval_id": "PR-1001",
                    "correlation_id": "api-replay",
                },
            )
            missing_response = client.get(
                "/api/erp-approval/connectors/replay",
                params={
                    "provider": "sap_s4_odata",
                    "operation": "approval_request",
                    "fixture_name": "missing.json",
                },
            )

        self.assertEqual(fixtures_response.status_code, 200)
        self.assertEqual(len(fixtures_response.json()), 32)
        self.assertEqual(coverage_response.status_code, 200)
        coverage_payload = coverage_response.json()
        self.assertEqual(coverage_payload["total_items"], 32)
        self.assertEqual(coverage_payload["failed_items"], 0)
        self.assertIn("No ERP network or write action was executed", coverage_payload["non_action_statement"])
        self.assertEqual(replay_response.status_code, 200)
        replay_payload = replay_response.json()
        self.assertEqual(replay_payload["status"], "success")
        self.assertFalse(replay_payload["network_accessed"])
        self.assertTrue(replay_payload["validation"]["passed"])
        self.assertIn("No ERP network or write action was executed", replay_payload["non_action_statement"])
        self.assertTrue(replay_payload["source_ids"][0].startswith("sap_s4_odata://approval_request/"))
        self.assertEqual(missing_response.status_code, 404)

    def test_replay_api_rejects_invalid_provider_without_secret_exposure(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")
        client = TestClient(app)

        response = client.get(
            "/api/erp-approval/connectors/replay",
            params={
                "provider": "not_a_provider",
                "operation": "approval_request",
                "fixture_name": "sap_s4_odata_purchase_requisition.json",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("secret", response.text.lower())

    def test_connector_api_has_no_live_connect_or_execute_routes(self) -> None:
        app = FastAPI()
        app.include_router(erp_approval_api.router, prefix="/api")

        connector_routes = [
            getattr(route, "path", "")
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/erp-approval/connectors")
        ]

        self.assertTrue(any(path.endswith("/replay/coverage") for path in connector_routes))
        self.assertFalse(any("/execute" in path for path in connector_routes))
        self.assertFalse(any("/test-live" in path for path in connector_routes))
        self.assertFalse(any(path.endswith("/connect") for path in connector_routes))


if __name__ == "__main__":
    unittest.main()
