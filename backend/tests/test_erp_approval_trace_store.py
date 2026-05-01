from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.trace_models import ApprovalTraceQuery, ApprovalTraceRecord
from src.backend.domains.erp_approval.trace_store import ApprovalTraceRepository, build_trace_record_from_state


def sample_trace_state() -> dict:
    return {
        "run_id": "run-trace",
        "session_id": "session-trace",
        "thread_id": "thread-trace",
        "turn_id": "run-trace:0",
        "erp_request": {
            "approval_id": "PR-1001",
            "approval_type": "purchase_requisition",
            "requester": "Lin Chen",
            "department": "Operations",
            "amount": 24500,
            "currency": "USD",
            "vendor": "Acme Supplies",
            "cost_center": "OPS-CC-10",
        },
        "erp_context": {
            "request_id": "PR-1001",
            "records": [
                {"source_id": "mock_erp://approval_request/PR-1001"},
                {"source_id": "mock_policy://procurement_policy"},
            ],
        },
        "erp_recommendation": {
            "status": "request_more_info",
            "confidence": 0.55,
            "human_review_required": True,
            "missing_information": ["budget owner confirmation"],
            "risk_flags": ["budget_unclear"],
            "citations": ["mock_erp://approval_request/PR-1001"],
        },
        "erp_guard_result": {
            "warnings": ["No citations were provided; human review is required."],
            "downgraded": True,
        },
        "erp_review_status": "accepted_by_human",
        "erp_hitl_decision": {"decision": "approve"},
        "erp_action_proposals": {
            "proposals": [
                {
                    "proposal_id": "proposal-1",
                    "action_type": "request_more_info",
                    "status": "proposed_only",
                }
            ]
        },
        "erp_action_validation_result": {
            "warnings": ["proposal warning"],
            "blocked_proposal_ids": ["blocked-1"],
            "rejected_proposal_ids": [],
        },
        "final_answer": "This preview says Status: recommend_approve but structured data says request_more_info.",
    }


def sample_record(
    trace_id: str,
    *,
    created_at: str = "2026-05-01T00:00:00+00:00",
    approval_id: str = "PR-1001",
    approval_type: str = "purchase_requisition",
    requester: str = "Lin Chen",
    vendor: str = "Acme Supplies",
    cost_center: str = "OPS-CC-10",
    recommendation_status: str = "request_more_info",
    review_status: str = "accepted_by_human",
    proposal_action_types: list[str] | None = None,
    human_review_required: bool = True,
    guard_downgraded: bool = False,
    risk_flags: list[str] | None = None,
    guard_warnings: list[str] | None = None,
    blocked_proposal_ids: list[str] | None = None,
    rejected_proposal_ids: list[str] | None = None,
    final_answer_preview: str = "",
) -> ApprovalTraceRecord:
    return ApprovalTraceRecord(
        trace_id=trace_id,
        run_id=trace_id,
        created_at=created_at,
        updated_at=created_at,
        approval_id=approval_id,
        approval_type=approval_type,
        requester=requester,
        department="Operations",
        vendor=vendor,
        cost_center=cost_center,
        recommendation_status=recommendation_status,
        review_status=review_status,
        proposal_action_types=proposal_action_types or [],
        human_review_required=human_review_required,
        guard_downgraded=guard_downgraded,
        risk_flags=risk_flags or [],
        guard_warnings=guard_warnings or [],
        blocked_proposal_ids=blocked_proposal_ids or [],
        rejected_proposal_ids=rejected_proposal_ids or [],
        final_answer_preview=final_answer_preview,
    )


class ErpApprovalTraceStoreTests(unittest.TestCase):
    def test_build_trace_record_uses_structured_state_not_final_answer_parse(self) -> None:
        record = build_trace_record_from_state(sample_trace_state(), "2026-05-01T00:00:00+00:00")

        self.assertEqual(record.trace_id, "erp-trace:run-trace:run-trace:0")
        self.assertEqual(record.recommendation_status, "request_more_info")
        self.assertEqual(record.approval_id, "PR-1001")
        self.assertLessEqual(len(record.final_answer_preview), 800)
        self.assertIn("mock_erp://approval_request/PR-1001", record.context_source_ids)

    def test_upsert_same_trace_id_does_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            record = build_trace_record_from_state(sample_trace_state(), "2026-05-01T00:00:00+00:00")

            first = repository.upsert(record)
            second = repository.upsert(record.model_copy(update={"updated_at": "2026-05-01T00:01:00+00:00"}))
            records = repository.list_recent(limit=10)

        self.assertTrue(first.success)
        self.assertTrue(first.created)
        self.assertTrue(second.success)
        self.assertFalse(second.created)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].updated_at, "2026-05-01T00:01:00+00:00")

    def test_list_recent_returns_most_recent_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            first_state = sample_trace_state()
            second_state = sample_trace_state()
            second_state["run_id"] = "run-trace-2"
            second_state["turn_id"] = "run-trace-2:0"
            repository.upsert(build_trace_record_from_state(first_state, "2026-05-01T00:00:00+00:00"))
            repository.upsert(build_trace_record_from_state(second_state, "2026-05-01T00:01:00+00:00"))

            records = repository.list_recent(limit=2)

        self.assertEqual([record.run_id for record in records], ["run-trace-2", "run-trace"])
        self.assertIsNotNone(records[0].trace_id)

    def test_query_filters_structured_trace_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            repository.upsert(
                sample_record(
                    "trace-pr",
                    proposal_action_types=["request_more_info"],
                    human_review_required=True,
                    guard_downgraded=True,
                )
            )
            repository.upsert(
                sample_record(
                    "trace-exp",
                    approval_id="EXP-2001",
                    approval_type="expense",
                    recommendation_status="recommend_approve",
                    review_status="not_required",
                    proposal_action_types=["add_internal_comment"],
                    human_review_required=False,
                )
            )

            by_type = repository.query(ApprovalTraceQuery(approval_type="expense"))
            by_status = repository.query(ApprovalTraceQuery(recommendation_status="recommend_approve"))
            by_review = repository.query(ApprovalTraceQuery(review_status="accepted_by_human"))
            by_action = repository.query(ApprovalTraceQuery(proposal_action_type="request_more_info"))
            by_human_review = repository.query(ApprovalTraceQuery(human_review_required=False))
            by_guard = repository.query(ApprovalTraceQuery(guard_downgraded=True))

        self.assertEqual([record.trace_id for record in by_type], ["trace-exp"])
        self.assertEqual([record.trace_id for record in by_status], ["trace-exp"])
        self.assertEqual([record.trace_id for record in by_review], ["trace-pr"])
        self.assertEqual([record.trace_id for record in by_action], ["trace-pr"])
        self.assertEqual([record.trace_id for record in by_human_review], ["trace-exp"])
        self.assertEqual([record.trace_id for record in by_guard], ["trace-pr"])

    def test_high_risk_only_matches_risk_warnings_blocked_or_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            repository.upsert(sample_record("trace-safe", recommendation_status="recommend_approve", human_review_required=False))
            repository.upsert(sample_record("trace-risk", risk_flags=["budget_unclear"]))
            repository.upsert(sample_record("trace-warning", guard_warnings=["unknown citation"]))
            repository.upsert(sample_record("trace-blocked", blocked_proposal_ids=["proposal-1"]))
            repository.upsert(sample_record("trace-escalate", recommendation_status="escalate"))

            records = repository.query(ApprovalTraceQuery(high_risk_only=True, limit=10))

        self.assertEqual(
            {record.trace_id for record in records},
            {"trace-risk", "trace-warning", "trace-blocked", "trace-escalate"},
        )

    def test_text_query_uses_structured_fields_not_final_answer_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            repository.upsert(
                sample_record(
                    "trace-text",
                    approval_id="INV-3001",
                    requester="Mina Park",
                    vendor="Northwind Logistics",
                    cost_center="FIN-AP-01",
                    final_answer_preview="HiddenVendorOnly appears in final answer preview.",
                )
            )

            by_approval_id = repository.query(ApprovalTraceQuery(text_query="INV-3001"))
            by_vendor = repository.query(ApprovalTraceQuery(text_query="northwind"))
            by_requester = repository.query(ApprovalTraceQuery(text_query="mina"))
            by_cost_center = repository.query(ApprovalTraceQuery(text_query="FIN-AP-01"))
            by_trace_id = repository.query(ApprovalTraceQuery(text_query="trace-text"))
            by_final_preview_only = repository.query(ApprovalTraceQuery(text_query="HiddenVendorOnly"))

        self.assertEqual(len(by_approval_id), 1)
        self.assertEqual(len(by_vendor), 1)
        self.assertEqual(len(by_requester), 1)
        self.assertEqual(len(by_cost_center), 1)
        self.assertEqual(len(by_trace_id), 1)
        self.assertEqual(by_final_preview_only, [])

    def test_query_filters_by_iso_date_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            repository.upsert(sample_record("trace-0501", created_at="2026-05-01T09:00:00+00:00"))
            repository.upsert(sample_record("trace-0502", created_at="2026-05-02T09:00:00+00:00"))
            repository.upsert(sample_record("trace-0503", created_at="2026-05-03T09:00:00+00:00"))

            records = repository.query(ApprovalTraceQuery(date_from="2026-05-02", date_to="2026-05-03", limit=10))

        self.assertEqual([record.trace_id for record in records], ["trace-0503", "trace-0502"])

    def test_export_csv_and_json_are_structured_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            repository.upsert(sample_record("trace-export", proposal_action_types=["route_to_finance"]))

            csv_payload = repository.export_csv(ApprovalTraceQuery(limit=10))
            json_payload = repository.export_json(ApprovalTraceQuery(limit=10))

        self.assertEqual(
            csv_payload.splitlines()[0],
            "trace_id,created_at,approval_id,approval_type,recommendation_status,review_status,human_review_required,guard_downgraded,proposal_action_types,blocked_proposal_ids,rejected_proposal_ids",
        )
        self.assertEqual(json_payload["total"], 1)
        self.assertEqual(json_payload["records"][0]["trace_id"], "trace-export")

    def test_trend_summary_groups_by_created_at_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            repository.upsert(sample_record("trace-trend-1", created_at="2026-05-01T09:00:00+00:00"))
            repository.upsert(sample_record("trace-trend-2", created_at="2026-05-01T10:00:00+00:00", blocked_proposal_ids=["blocked-1"]))
            repository.upsert(sample_record("trace-trend-3", created_at="2026-05-02T09:00:00+00:00", review_status="not_required", human_review_required=False))

            summary = repository.trend_summary(ApprovalTraceQuery(limit=10))

        self.assertEqual(summary.bucket_field, "created_at_date")
        self.assertEqual([bucket.bucket for bucket in summary.buckets], ["2026-05-01", "2026-05-02"])
        self.assertEqual(summary.buckets[0].total_traces, 2)
        self.assertEqual(summary.buckets[0].blocked_proposal_count, 1)


if __name__ == "__main__":
    unittest.main()
