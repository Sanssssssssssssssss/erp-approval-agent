from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.analytics import summarize_trace_trends, summarize_traces
from src.backend.domains.erp_approval.trace_models import ApprovalTraceRecord


class ErpApprovalAnalyticsTests(unittest.TestCase):
    def test_empty_trace_list_returns_zero_summary(self) -> None:
        summary = summarize_traces([])

        self.assertEqual(summary.total_traces, 0)
        self.assertEqual(summary.by_approval_type, {})
        self.assertEqual(summary.blocked_proposal_count, 0)

    def test_summarize_counts_status_review_missing_risk_and_proposals(self) -> None:
        records = [
            ApprovalTraceRecord(
                trace_id="trace-1",
                approval_type="purchase_requisition",
                recommendation_status="request_more_info",
                review_status="accepted_by_human",
                human_review_required=True,
                guard_downgraded=True,
                missing_information=["receipt", "budget"],
                risk_flags=["budget_unclear"],
                guard_warnings=["low confidence"],
                proposal_action_types=["request_more_info"],
                blocked_proposal_ids=["blocked-1"],
            ),
            ApprovalTraceRecord(
                trace_id="trace-2",
                approval_type="expense",
                recommendation_status="recommend_approve",
                review_status="not_required",
                human_review_required=False,
                missing_information=["receipt"],
                proposal_action_types=["add_internal_comment"],
                rejected_proposal_ids=["rejected-1"],
            ),
        ]

        summary = summarize_traces(records)

        self.assertEqual(summary.total_traces, 2)
        self.assertEqual(summary.by_approval_type["expense"], 1)
        self.assertEqual(summary.by_recommendation_status["request_more_info"], 1)
        self.assertEqual(summary.by_review_status["accepted_by_human"], 1)
        self.assertEqual(summary.human_review_required_count, 1)
        self.assertEqual(summary.guard_downgrade_count, 1)
        self.assertEqual(summary.top_missing_information[0], {"item": "receipt", "count": 2})
        self.assertEqual(summary.proposal_action_type_counts["request_more_info"], 1)
        self.assertEqual(summary.blocked_proposal_count, 1)
        self.assertEqual(summary.rejected_proposal_count, 1)
        self.assertIn("trace-1", summary.high_risk_trace_ids)

    def test_summarize_trace_trends_groups_by_created_at_date(self) -> None:
        records = [
            ApprovalTraceRecord(
                trace_id="trace-1",
                created_at="2026-05-01T08:00:00+00:00",
                recommendation_status="request_more_info",
                review_status="accepted_by_human",
                human_review_required=True,
                guard_downgraded=True,
                blocked_proposal_ids=["blocked-1"],
            ),
            ApprovalTraceRecord(
                trace_id="trace-2",
                created_at="2026-05-01T09:00:00+00:00",
                recommendation_status="request_more_info",
                review_status="accepted_by_human",
                human_review_required=True,
                rejected_proposal_ids=["rejected-1"],
            ),
            ApprovalTraceRecord(
                trace_id="trace-3",
                created_at="2026-05-02T09:00:00+00:00",
                recommendation_status="recommend_approve",
                review_status="not_required",
                human_review_required=False,
            ),
        ]

        trends = summarize_trace_trends(records)

        self.assertEqual(trends.bucket_field, "created_at_date")
        self.assertEqual(len(trends.buckets), 2)
        self.assertEqual(trends.buckets[0].bucket, "2026-05-01")
        self.assertEqual(trends.buckets[0].total_traces, 2)
        self.assertEqual(trends.buckets[0].human_review_required_count, 2)
        self.assertEqual(trends.buckets[0].guard_downgrade_count, 1)
        self.assertEqual(trends.buckets[0].blocked_proposal_count, 1)
        self.assertEqual(trends.buckets[0].rejected_proposal_count, 1)
        self.assertEqual(trends.buckets[0].by_recommendation_status["request_more_info"], 2)
        self.assertEqual(trends.buckets[1].by_review_status["not_required"], 1)


if __name__ == "__main__":
    unittest.main()
