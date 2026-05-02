from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_review import build_case_file_from_request_context
from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter
from src.backend.domains.erp_approval.control_matrix import evaluate_control_matrix
from src.backend.domains.erp_approval.schemas import ApprovalRequest


class ErpApprovalControlMatrixTests(unittest.TestCase):
    def test_control_matrix_generates_missing_and_pass_checks(self) -> None:
        request = ApprovalRequest(
            approval_type="purchase_requisition",
            approval_id="PR-1001",
            requester="Lin Chen",
            amount=24500,
            currency="USD",
            vendor="Acme Supplies",
            cost_center="OPS-CC-10",
            raw_request="Review PR-1001",
        )
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(ErpContextQuery.from_request(request))
        case_file = build_case_file_from_request_context(request, context)

        matrix = evaluate_control_matrix(case_file)
        by_id = {check.check_id: check for check in matrix.checks}

        self.assertEqual(by_id["budget_available"].status, "pass")
        self.assertIn(by_id["quote_or_contract_present"].status, {"missing", "fail"})
        self.assertFalse(matrix.passed)
        self.assertTrue(matrix.high_risk)

    def test_budget_exception_insufficient_budget_fails_or_escalates(self) -> None:
        request = ApprovalRequest(
            approval_type="budget_exception",
            approval_id="BUD-6001",
            amount=55000,
            cost_center="FIN-CC-77",
            raw_request="Review BUD-6001",
        )
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(ErpContextQuery.from_request(request))
        case_file = build_case_file_from_request_context(request, context)

        matrix = evaluate_control_matrix(case_file)
        by_id = {check.check_id: check for check in matrix.checks}

        self.assertIn(by_id["available_budget_check"].status, {"fail", "missing"})
        self.assertTrue(matrix.high_risk)


if __name__ == "__main__":
    unittest.main()
