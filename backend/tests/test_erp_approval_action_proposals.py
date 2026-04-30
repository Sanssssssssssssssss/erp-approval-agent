from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval import (
    ACTION_PROPOSAL_NON_ACTION_STATEMENT,
    ApprovalActionProposal,
    ApprovalActionProposalBundle,
    ApprovalGuardResult,
    ApprovalRecommendation,
    ApprovalRequest,
    ErpContextQuery,
    MockErpContextAdapter,
    build_action_proposals,
    guard_recommendation,
    validate_action_proposals,
)


class ErpApprovalActionProposalTests(unittest.TestCase):
    def _request_and_context(self):
        request = ApprovalRequest(
            approval_type="purchase_requisition",
            approval_id="PR-1001",
            requester="Lin Chen",
            department="Operations",
            amount=24500,
            currency="USD",
            vendor="Acme Supplies",
            cost_center="OPS-CC-10",
            business_purpose="replacement laptops",
            raw_request="Review PR-1001",
        )
        context = MockErpContextAdapter(base_dir=BACKEND_DIR).fetch_context(ErpContextQuery.from_request(request))
        return request, context

    def _build_validated(self, recommendation: ApprovalRecommendation):
        request, context = self._request_and_context()
        recommendation, guard = guard_recommendation(request, context, recommendation)
        bundle = build_action_proposals(request, context, recommendation, guard, "accepted_by_human")
        return request, context, *validate_action_proposals(request, context, bundle)

    def test_request_more_info_recommendation_generates_request_more_info_proposal(self) -> None:
        _request, _context, bundle, validation = self._build_validated(
            ApprovalRecommendation(
                status="request_more_info",
                confidence=0.5,
                summary="Need budget owner confirmation.",
                missing_information=["budget owner confirmation"],
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="request_more_info",
                human_review_required=True,
            )
        )

        self.assertTrue(bundle.proposals)
        self.assertEqual(bundle.proposals[0].action_type, "request_more_info")
        self.assertFalse(bundle.proposals[0].executable)
        self.assertEqual(bundle.proposals[0].non_action_statement, ACTION_PROPOSAL_NON_ACTION_STATEMENT)
        self.assertTrue(bundle.proposals[0].idempotency_key)
        self.assertTrue(validation.passed)

    def test_route_to_finance_recommendation_generates_route_proposal(self) -> None:
        _request, _context, bundle, validation = self._build_validated(
            ApprovalRecommendation(
                status="request_more_info",
                confidence=0.62,
                summary="Finance should inspect cost center funding.",
                missing_information=[],
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="route_to_finance",
                human_review_required=True,
            )
        )

        self.assertEqual(bundle.proposals[0].action_type, "route_to_finance")
        self.assertEqual(bundle.proposals[0].target, "finance")
        self.assertFalse(bundle.proposals[0].executable)
        self.assertTrue(validation.passed)

    def test_recommend_approve_does_not_generate_approve_action(self) -> None:
        _request, _context, bundle, validation = self._build_validated(
            ApprovalRecommendation(
                status="recommend_approve",
                confidence=0.86,
                summary="Mock evidence supports the request.",
                citations=["mock_erp://approval_request/PR-1001", "mock_policy://procurement_policy"],
                proposed_next_action="none",
                human_review_required=False,
            )
        )

        self.assertIn(bundle.proposals[0].action_type, {"add_internal_comment", "manual_review"})
        self.assertNotEqual(bundle.proposals[0].action_type, "approve")
        self.assertFalse(bundle.proposals[0].executable)
        self.assertTrue(validation.passed)

    def test_same_input_generates_stable_idempotency_fingerprint(self) -> None:
        recommendation = ApprovalRecommendation(
            status="request_more_info",
            confidence=0.5,
            summary="Need budget owner confirmation.",
            missing_information=["budget owner confirmation"],
            citations=["mock_erp://approval_request/PR-1001"],
            proposed_next_action="request_more_info",
            human_review_required=True,
        )

        _request, _context, first, _first_validation = self._build_validated(recommendation)
        _request, _context, second, _second_validation = self._build_validated(recommendation)

        self.assertEqual(first.proposals[0].idempotency_fingerprint, second.proposals[0].idempotency_fingerprint)
        self.assertEqual(first.proposals[0].idempotency_key, second.proposals[0].idempotency_key)

    def test_unknown_citation_rejects_proposal_validation(self) -> None:
        request, context = self._request_and_context()
        recommendation = ApprovalRecommendation(
            status="request_more_info",
            confidence=0.5,
            summary="Need external evidence.",
            citations=["mock_erp://missing/NOPE"],
            proposed_next_action="request_more_info",
            human_review_required=True,
        )
        guard = ApprovalGuardResult(passed=True, final_status="request_more_info")
        bundle = build_action_proposals(request, context, recommendation, guard, "accepted_by_human")

        bundle, validation = validate_action_proposals(request, context, bundle)

        self.assertFalse(validation.passed)
        self.assertEqual(bundle.proposals[0].status, "rejected_by_validation")
        self.assertTrue(validation.rejected_proposal_ids)

    def test_payload_execution_semantics_are_blocked(self) -> None:
        request, context = self._request_and_context()
        recommendation, guard = guard_recommendation(
            request,
            context,
            ApprovalRecommendation(
                status="request_more_info",
                confidence=0.5,
                summary="Need budget owner confirmation.",
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="request_more_info",
                human_review_required=True,
            ),
        )
        bundle = build_action_proposals(request, context, recommendation, guard, "accepted_by_human")
        unsafe = bundle.proposals[0].model_copy(
            update={"payload_preview": {"operation": "approve_request", "budget_update": True}}
        )
        bundle = ApprovalActionProposalBundle(request_id=bundle.request_id, review_status=bundle.review_status, proposals=[unsafe])

        bundle, validation = validate_action_proposals(request, context, bundle)

        self.assertFalse(validation.passed)
        self.assertEqual(bundle.proposals[0].status, "blocked")
        self.assertTrue(validation.blocked_proposal_ids)

    def test_invalid_action_type_is_rejected_by_validation(self) -> None:
        request, context = self._request_and_context()
        proposal = ApprovalActionProposal.model_construct(
            proposal_id="bad-proposal",
            action_type="execute_payment",
            status="proposed_only",
            title="Bad proposal",
            summary="Should be rejected.",
            target="erp",
            payload_preview={"message": "No external action."},
            citations=["mock_erp://approval_request/PR-1001"],
            idempotency_key="bad-key",
            idempotency_scope="bad-scope",
            idempotency_fingerprint="bad-fingerprint",
            risk_level="high",
            requires_human_review=True,
            executable=False,
            non_action_statement=ACTION_PROPOSAL_NON_ACTION_STATEMENT,
        )
        bundle = ApprovalActionProposalBundle(request_id=request.approval_id, review_status="accepted_by_human", proposals=[proposal])

        bundle, validation = validate_action_proposals(request, context, bundle)

        self.assertFalse(validation.passed)
        self.assertEqual(bundle.proposals[0].status, "rejected_by_validation")


if __name__ == "__main__":
    unittest.main()
