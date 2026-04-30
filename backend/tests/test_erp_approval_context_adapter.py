from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter


class ErpApprovalContextAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = MockErpContextAdapter(base_dir=BACKEND_DIR)

    def test_pr_1001_returns_request_vendor_budget_and_policy_records(self) -> None:
        bundle = self.adapter.fetch_context(
            ErpContextQuery(
                approval_type="purchase_requisition",
                approval_id="PR-1001",
                vendor="Acme Supplies",
                cost_center="OPS-CC-10",
            )
        )
        record_types = {record.record_type for record in bundle.records}
        source_ids = {record.source_id for record in bundle.records}

        self.assertIn("approval_request", record_types)
        self.assertIn("vendor", record_types)
        self.assertIn("budget", record_types)
        self.assertIn("policy", record_types)
        self.assertIn("mock_erp://approval_request/PR-1001", source_ids)
        self.assertIn("mock_policy://procurement_policy", source_ids)

    def test_unknown_approval_id_falls_back_without_crashing(self) -> None:
        bundle = self.adapter.fetch_context(
            ErpContextQuery(
                approval_type="purchase_requisition",
                approval_id="PR-UNKNOWN",
                vendor="Unknown Vendor",
                cost_center="NOPE",
            )
        )

        self.assertTrue(bundle.records)
        self.assertTrue(all(record.record_type == "policy" for record in bundle.records))

    def test_context_records_have_required_visible_fields(self) -> None:
        bundle = self.adapter.fetch_context(ErpContextQuery(approval_type="invoice_payment", approval_id="INV-3001"))

        self.assertTrue(bundle.records)
        for record in bundle.records:
            self.assertTrue(record.source_id)
            self.assertTrue(record.title)
            self.assertTrue(record.record_type)
            self.assertTrue(record.content)


if __name__ == "__main__":
    unittest.main()
