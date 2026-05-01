from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval import (
    ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    ErpConnectorReplayRequest,
    list_provider_fixtures,
    replay_provider_fixture,
    validate_replay_record,
)


class ErpApprovalConnectorReplayTests(unittest.TestCase):
    def test_list_provider_fixtures_returns_four_provider_fixtures(self) -> None:
        fixtures = list_provider_fixtures(BACKEND_DIR)

        self.assertEqual(len(fixtures), 4)
        self.assertEqual(
            {fixture.provider for fixture in fixtures},
            {"sap_s4_odata", "dynamics_fo_odata", "oracle_fusion_rest", "custom_http_json"},
        )
        self.assertTrue(all(fixture.operation == "approval_request" for fixture in fixtures))

    def test_replay_provider_fixtures_output_context_records(self) -> None:
        cases = [
            ("sap_s4_odata", "sap_s4_odata_purchase_requisition.json"),
            ("dynamics_fo_odata", "dynamics_fo_odata_purchase_requisition.json"),
            ("oracle_fusion_rest", "oracle_fusion_rest_purchase_requisition.json"),
            ("custom_http_json", "custom_http_json_purchase_requisition.json"),
        ]

        for provider, fixture_name in cases:
            with self.subTest(provider=provider):
                record = replay_provider_fixture(
                    BACKEND_DIR,
                    ErpConnectorReplayRequest(
                        provider=provider,
                        operation="approval_request",
                        fixture_name=fixture_name,
                        approval_id="PR-1001",
                        correlation_id=f"corr-{provider}",
                    ),
                    "2026-05-01T00:00:00+00:00",
                )

                self.assertEqual(record.status, "success")
                self.assertFalse(record.network_accessed)
                self.assertTrue(record.dry_run)
                self.assertEqual(record.record_count, 1)
                self.assertEqual(len(record.records), 1)
                self.assertTrue(record.source_ids[0].startswith(f"{provider}://approval_request/"))
                self.assertTrue(record.validation.passed)
                self.assertIn("No ERP network or write action was executed", record.non_action_statement)
                context_record = record.records[0]
                self.assertTrue(context_record.source_id)
                self.assertTrue(context_record.title)
                self.assertTrue(context_record.record_type)
                self.assertTrue(context_record.content)
                self.assertTrue(context_record.metadata["read_only"])
                self.assertEqual(context_record.metadata["provider"], provider)
                self.assertEqual(context_record.metadata["operation"], "approval_request")

    def test_replay_validation_detects_missing_fields_without_network(self) -> None:
        record = replay_provider_fixture(
            BACKEND_DIR,
            ErpConnectorReplayRequest(
                provider="custom_http_json",
                operation="approval_request",
                fixture_name="custom_http_json_purchase_requisition.json",
                approval_id="PR-1001",
            ),
            "2026-05-01T00:00:00+00:00",
        )
        broken = record.model_copy(update={"network_accessed": True, "non_action_statement": ""})
        validation = validate_replay_record(broken)

        self.assertFalse(validation.passed)
        self.assertIn("network_accessed", validation.failed_checks)
        self.assertIn("non_action_statement", validation.failed_checks)
        self.assertIn("source_id", validation.checked_fields)

    def test_provider_mismatch_and_missing_fixture_do_not_crash(self) -> None:
        mismatch = replay_provider_fixture(
            BACKEND_DIR,
            ErpConnectorReplayRequest(
                provider="sap_s4_odata",
                operation="approval_request",
                fixture_name="custom_http_json_purchase_requisition.json",
                approval_id="PR-1001",
            ),
            "2026-05-01T00:00:00+00:00",
        )
        missing = replay_provider_fixture(
            BACKEND_DIR,
            ErpConnectorReplayRequest(
                provider="custom_http_json",
                operation="approval_request",
                fixture_name="custom_http_json_missing.json",
                approval_id="PR-1001",
            ),
            "2026-05-01T00:00:00+00:00",
        )

        self.assertEqual(mismatch.status, "blocked")
        self.assertFalse(mismatch.network_accessed)
        self.assertFalse(mismatch.validation.passed)
        self.assertEqual(missing.status, "failed")
        self.assertFalse(missing.network_accessed)
        self.assertEqual(missing.non_action_statement, ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT)

    def test_replay_requires_dry_run_and_confirm_no_network(self) -> None:
        record = replay_provider_fixture(
            BACKEND_DIR,
            ErpConnectorReplayRequest(
                provider="custom_http_json",
                operation="approval_request",
                fixture_name="custom_http_json_purchase_requisition.json",
                dry_run=False,
                confirm_no_network=False,
            ),
            "2026-05-01T00:00:00+00:00",
        )

        self.assertEqual(record.status, "blocked")
        self.assertFalse(record.network_accessed)
        self.assertIn("dry_run=true", " ".join(record.warnings))
        self.assertIn("confirm_no_network=true", " ".join(record.warnings))


if __name__ == "__main__":
    unittest.main()
