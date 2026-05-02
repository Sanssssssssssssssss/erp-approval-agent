from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.evidence_requirements import requirement_matrix_for_approval_type


class ErpApprovalEvidenceRequirementTests(unittest.TestCase):
    def test_purchase_requisition_requirement_matrix_contains_blocking_evidence(self) -> None:
        requirements = requirement_matrix_for_approval_type("purchase_requisition", amount=24500)
        ids = {item.requirement_id for item in requirements}

        for key in (
            "purchase_requisition:approval_request",
            "purchase_requisition:line_items",
            "purchase_requisition:budget_availability",
            "purchase_requisition:vendor_onboarding_status",
            "purchase_requisition:supplier_risk_status",
            "purchase_requisition:quote_or_price_basis",
            "purchase_requisition:procurement_policy",
            "purchase_requisition:approval_matrix",
            "purchase_requisition:cost_center",
            "purchase_requisition:requester_identity",
            "purchase_requisition:amount_threshold",
            "purchase_requisition:split_order_check",
        ):
            self.assertIn(key, ids)

        blocking = {item.requirement_id for item in requirements if item.blocking and item.required_level == "required"}
        self.assertIn("purchase_requisition:budget_availability", blocking)
        self.assertIn("purchase_requisition:quote_or_price_basis", blocking)

    def test_unknown_type_defaults_to_manual_review_evidence(self) -> None:
        requirements = requirement_matrix_for_approval_type("unknown")
        ids = {item.requirement_id for item in requirements}

        self.assertIn("unknown:approval_request", ids)
        self.assertIn("unknown:policy", ids)
        self.assertIn("unknown:approval_matrix", ids)
        self.assertIn("unknown:manual_review", ids)


if __name__ == "__main__":
    unittest.main()
