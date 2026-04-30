from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.context_adapter import ErpContextQuery, MockErpContextAdapter
from src.backend.domains.erp_approval.mock_context import build_mock_context
from src.backend.domains.erp_approval.schemas import ApprovalRecommendation, ApprovalRequest
from src.backend.domains.erp_approval.service import (
    extract_json_object,
    guard_recommendation,
    parse_approval_request,
    parse_recommendation,
)


class ErpApprovalDomainTests(unittest.TestCase):
    def test_extract_json_object_handles_wrapped_json(self) -> None:
        payload = extract_json_object('prefix {"status": "request_more_info", "confidence": 0.4} suffix')

        self.assertEqual(payload["status"], "request_more_info")
        self.assertEqual(payload["confidence"], 0.4)

    def test_parse_approval_request_from_json(self) -> None:
        raw = json.dumps(
            {
                "approval_type": "purchase_requisition",
                "approval_id": "PR-100",
                "requester": "Lin",
                "department": "Ops",
                "amount": 1200,
                "currency": "USD",
                "vendor": "Acme",
                "cost_center": "CC-1",
                "business_purpose": "replacement laptops",
                "raw_request": "PR-100",
            }
        )

        request = parse_approval_request(raw, "fallback")

        self.assertEqual(request.approval_type, "purchase_requisition")
        self.assertEqual(request.approval_id, "PR-100")
        self.assertEqual(request.amount, 1200)

    def test_invalid_recommendation_falls_back_safely(self) -> None:
        recommendation = parse_recommendation("not json")

        self.assertEqual(recommendation.status, "request_more_info")
        self.assertTrue(recommendation.human_review_required)
        self.assertIn("valid structured approval recommendation", recommendation.missing_information)

    def test_guard_downgrades_approve_with_missing_information(self) -> None:
        request = ApprovalRequest(approval_type="expense", approval_id="EXP-1")
        context = build_mock_context(request)
        recommendation = ApprovalRecommendation(
            status="recommend_approve",
            confidence=0.9,
            summary="Looks acceptable.",
            missing_information=["receipt"],
            citations=["mock_policy://expense_policy"],
            proposed_next_action="none",
            human_review_required=False,
        )

        guarded, guard = guard_recommendation(request, context, recommendation)

        self.assertEqual(guarded.status, "request_more_info")
        self.assertEqual(guarded.proposed_next_action, "request_more_info")
        self.assertTrue(guarded.human_review_required)
        self.assertTrue(guard.downgraded)

    def test_guard_downgrades_low_confidence_approve(self) -> None:
        request = ApprovalRequest(approval_type="invoice_payment", approval_id="INV-1")
        context = build_mock_context(request)
        recommendation = ApprovalRecommendation(
            status="recommend_approve",
            confidence=0.6,
            summary="Possibly acceptable.",
            citations=["mock_policy://invoice_payment_policy"],
            proposed_next_action="none",
            human_review_required=False,
        )

        guarded, guard = guard_recommendation(request, context, recommendation)

        self.assertEqual(guarded.status, "escalate")
        self.assertEqual(guarded.proposed_next_action, "manual_review")
        self.assertTrue(guarded.human_review_required)
        self.assertTrue(guard.downgraded)

    def test_guard_downgrades_approve_without_citations(self) -> None:
        request = ApprovalRequest(approval_type="purchase_requisition", approval_id="PR-1001")
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(
            ErpContextQuery(approval_type="purchase_requisition", approval_id="PR-1001")
        )
        recommendation = ApprovalRecommendation(
            status="recommend_approve",
            confidence=0.9,
            summary="Looks acceptable.",
            citations=[],
            proposed_next_action="none",
            human_review_required=False,
        )

        guarded, guard = guard_recommendation(request, context, recommendation)

        self.assertEqual(guarded.status, "escalate")
        self.assertEqual(guarded.proposed_next_action, "manual_review")
        self.assertTrue(guarded.human_review_required)
        self.assertTrue(guard.downgraded)

    def test_guard_warns_and_downgrades_unknown_citation_source_id(self) -> None:
        request = ApprovalRequest(approval_type="purchase_requisition", approval_id="PR-1001")
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(
            ErpContextQuery(approval_type="purchase_requisition", approval_id="PR-1001")
        )
        recommendation = ApprovalRecommendation(
            status="recommend_approve",
            confidence=0.9,
            summary="Looks acceptable.",
            citations=["mock_erp://missing/NOPE"],
            proposed_next_action="none",
            human_review_required=False,
        )

        guarded, guard = guard_recommendation(request, context, recommendation)

        self.assertEqual(guarded.status, "escalate")
        self.assertTrue(guarded.human_review_required)
        self.assertTrue(any("Unknown citation" in warning for warning in guard.warnings))

    def test_guard_replaces_final_execution_action_with_manual_review(self) -> None:
        request = ApprovalRequest(approval_type="purchase_requisition", approval_id="PR-1001")
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(
            ErpContextQuery(approval_type="purchase_requisition", approval_id="PR-1001")
        )
        recommendation = ApprovalRecommendation.model_construct(
            status="request_more_info",
            confidence=0.8,
            summary="Needs follow-up.",
            rationale=[],
            missing_information=["budget owner confirmation"],
            risk_flags=[],
            citations=["mock_erp://approval_request/PR-1001"],
            proposed_next_action="execute_approve",
            human_review_required=False,
        )

        guarded, guard = guard_recommendation(request, context, recommendation)

        self.assertEqual(guarded.proposed_next_action, "manual_review")
        self.assertTrue(guarded.human_review_required)
        self.assertTrue(any("irreversible ERP execution" in warning for warning in guard.warnings))


if __name__ == "__main__":
    unittest.main()
