from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_review import (
    adversarial_review_case,
    build_case_file_from_request_context,
    draft_recommendation_from_case,
)
from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter
from src.backend.domains.erp_approval.schemas import ApprovalRecommendation, ApprovalRequest


class ErpApprovalCaseReviewTests(unittest.TestCase):
    def _case_for(self, request: ApprovalRequest):
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(ErpContextQuery.from_request(request))
        return build_case_file_from_request_context(request, context)

    def test_purchase_requisition_missing_quote_and_line_items_cannot_approve(self) -> None:
        case_file = self._case_for(
            ApprovalRequest(
                approval_type="purchase_requisition",
                approval_id="PR-1001",
                requester="Lin Chen",
                amount=24500,
                vendor="Acme Supplies",
                cost_center="OPS-CC-10",
            )
        )

        recommendation = draft_recommendation_from_case(case_file)

        self.assertNotEqual(recommendation.status, "recommend_approve")
        self.assertTrue(recommendation.missing_information)

    def test_invoice_payment_missing_po_grn_invoice_cannot_approve(self) -> None:
        case_file = build_case_file_from_request_context(
            ApprovalRequest(approval_type="invoice_payment", approval_id="INV-MISSING", raw_request="Pay invoice"),
            MockErpContextAdapter(fixture_path=BACKEND_DIR / "missing-fixture.json").fetch_context(
                ErpContextQuery(approval_type="invoice_payment", approval_id="INV-MISSING")
            ),
        )

        recommendation = draft_recommendation_from_case(case_file)

        self.assertNotEqual(recommendation.status, "recommend_approve")
        self.assertTrue(any("invoice" in item.lower() or "po" in item.lower() for item in recommendation.missing_information))

    def test_supplier_onboarding_missing_checks_cannot_approve(self) -> None:
        case_file = self._case_for(ApprovalRequest(approval_type="supplier_onboarding", approval_id="VEND-4001"))

        recommendation = draft_recommendation_from_case(case_file)

        self.assertNotEqual(recommendation.status, "recommend_approve")
        self.assertIn(recommendation.status, {"request_more_info", "escalate", "blocked"})

    def test_contract_exception_routes_to_legal_or_escalates(self) -> None:
        case_file = self._case_for(ApprovalRequest(approval_type="contract_exception", approval_id="CON-5001"))

        recommendation = draft_recommendation_from_case(case_file)

        self.assertIn(recommendation.status, {"request_more_info", "escalate", "blocked"})
        self.assertIn(recommendation.proposed_next_action, {"route_to_legal", "manual_review", "request_more_info"})

    def test_budget_exception_insufficient_budget_needs_finance_review(self) -> None:
        case_file = self._case_for(ApprovalRequest(approval_type="budget_exception", approval_id="BUD-6001", cost_center="FIN-CC-77"))

        recommendation = draft_recommendation_from_case(case_file)

        self.assertIn(recommendation.status, {"escalate", "blocked", "request_more_info"})
        self.assertIn(recommendation.proposed_next_action, {"route_to_finance", "manual_review", "request_more_info"})

    def test_adversarial_review_downgrades_unsupported_approve(self) -> None:
        case_file = self._case_for(ApprovalRequest(approval_type="purchase_requisition", approval_id="PR-1001"))
        recommendation = ApprovalRecommendation(
            status="recommend_approve",
            confidence=0.95,
            summary="Looks good.",
            citations=["mock_erp://missing/source"],
            proposed_next_action="route_to_procurement",
            human_review_required=False,
        )

        case_file, revised = adversarial_review_case(case_file, recommendation)

        self.assertNotEqual(revised.status, "recommend_approve")
        self.assertFalse(case_file.adversarial_review.passed)


if __name__ == "__main__":
    unittest.main()
