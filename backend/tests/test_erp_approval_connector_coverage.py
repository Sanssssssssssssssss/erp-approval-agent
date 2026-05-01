from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval import (
    ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    build_replay_coverage_matrix,
    list_provider_fixtures,
)


EXPECTED_PROVIDERS = {"sap_s4_odata", "dynamics_fo_odata", "oracle_fusion_rest", "custom_http_json"}
EXPECTED_OPERATIONS = {
    "approval_request",
    "vendor",
    "budget",
    "purchase_order",
    "invoice",
    "goods_receipt",
    "contract",
    "policy",
}


class ErpApprovalConnectorCoverageTests(unittest.TestCase):
    def test_coverage_matrix_matches_fixture_count_and_passes(self) -> None:
        fixtures = list_provider_fixtures(BACKEND_DIR)
        coverage = build_replay_coverage_matrix(BACKEND_DIR, "2026-05-01T00:00:00+00:00")

        self.assertEqual(coverage.total_items, len(fixtures))
        self.assertEqual(coverage.total_items, 32)
        self.assertEqual(coverage.passed_items, coverage.total_items)
        self.assertEqual(coverage.failed_items, 0)
        self.assertEqual(coverage.non_action_statement, ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT)

    def test_coverage_matrix_groups_by_provider_and_operation(self) -> None:
        coverage = build_replay_coverage_matrix(BACKEND_DIR, "2026-05-01T00:00:00+00:00")

        self.assertEqual(set(coverage.by_provider), EXPECTED_PROVIDERS)
        self.assertEqual(set(coverage.by_operation), EXPECTED_OPERATIONS)
        self.assertTrue(all(count == 8 for count in coverage.by_provider.values()))
        self.assertTrue(all(count == 4 for count in coverage.by_operation.values()))

    def test_coverage_items_include_replay_validation_details(self) -> None:
        coverage = build_replay_coverage_matrix(BACKEND_DIR, "2026-05-01T00:00:00+00:00")

        for item in coverage.items:
            with self.subTest(fixture=item.fixture_name):
                self.assertEqual(item.replay_status, "success")
                self.assertTrue(item.validation_passed)
                self.assertEqual(item.record_count, 1)
                self.assertTrue(item.source_ids)
                self.assertFalse(item.failed_checks)
                self.assertTrue(item.source_ids[0].startswith(f"{item.provider}://{item.operation}/"))


if __name__ == "__main__":
    unittest.main()
