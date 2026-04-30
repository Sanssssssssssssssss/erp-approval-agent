from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

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


if __name__ == "__main__":
    unittest.main()
