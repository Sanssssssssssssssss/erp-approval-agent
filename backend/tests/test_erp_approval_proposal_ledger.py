from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.proposal_ledger import (
    ApprovalActionProposalRepository,
    build_proposal_records_from_state,
)
from src.backend.domains.erp_approval.proposal_ledger_models import ApprovalActionProposalQuery


def sample_proposal_state() -> dict:
    return {
        "run_id": "run-proposal",
        "session_id": "session-proposal",
        "thread_id": "thread-proposal",
        "turn_id": "run-proposal:0",
        "erp_request": {
            "approval_id": "PR-1001",
            "approval_type": "purchase_requisition",
        },
        "erp_recommendation": {
            "status": "request_more_info",
        },
        "erp_review_status": "accepted_by_human",
        "erp_action_proposals": {
            "request_id": "PR-1001",
            "review_status": "accepted_by_human",
            "proposals": [
                {
                    "proposal_id": "erp-action-proposal-abc123",
                    "action_type": "request_more_info",
                    "status": "proposed_only",
                    "title": "Request more information proposal",
                    "summary": "Ask for budget owner confirmation.",
                    "target": "Lin Chen",
                    "payload_preview": {"missing_information": ["budget owner confirmation"]},
                    "citations": ["mock_erp://approval_request/PR-1001"],
                    "idempotency_key": "approval_action_proposal:PR-1001:request_more_info:abc123",
                    "idempotency_scope": "approval_action_proposal:PR-1001:request_more_info",
                    "idempotency_fingerprint": "abc123",
                    "risk_level": "medium",
                    "requires_human_review": True,
                    "executable": False,
                    "non_action_statement": "This is a proposed action only. No ERP write action was executed.",
                }
            ],
        },
        "erp_action_validation_result": {
            "warnings": ["erp-action-proposal-abc123: warning"],
            "blocked_proposal_ids": [],
            "rejected_proposal_ids": [],
        },
    }


class ErpApprovalProposalLedgerTests(unittest.TestCase):
    def test_build_proposal_records_from_state(self) -> None:
        records = build_proposal_records_from_state(sample_proposal_state(), "erp-trace:run-proposal:0", "2026-05-01T00:00:00+00:00")

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.proposal_id, "erp-action-proposal-abc123")
        self.assertEqual(record.trace_id, "erp-trace:run-proposal:0")
        self.assertEqual(record.approval_id, "PR-1001")
        self.assertEqual(record.action_type, "request_more_info")
        self.assertEqual(record.payload_preview["missing_information"], ["budget owner confirmation"])
        self.assertTrue(record.idempotency_key)
        self.assertFalse(record.executable)
        self.assertIn("No ERP write action was executed", record.non_action_statement)

    def test_upsert_many_dedupes_by_proposal_record_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            records = build_proposal_records_from_state(sample_proposal_state(), "erp-trace:run-proposal:0", "2026-05-01T00:00:00+00:00")
            first = repository.upsert_many(records)
            second = repository.upsert_many([records[0].model_copy(update={"updated_at": "2026-05-01T00:01:00+00:00"})])
            persisted = repository.list_recent(limit=10)

        self.assertEqual(len(first), 1)
        self.assertTrue(first[0].success)
        self.assertTrue(first[0].created)
        self.assertFalse(second[0].created)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].updated_at, "2026-05-01T00:01:00+00:00")

    def test_by_trace_id_and_query_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            first = build_proposal_records_from_state(sample_proposal_state(), "trace-1", "2026-05-01T00:00:00+00:00")[0]
            second = first.model_copy(
                update={
                    "proposal_record_id": "erp-proposal-record:proposal-2:trace-2",
                    "proposal_id": "proposal-2",
                    "trace_id": "trace-2",
                    "approval_id": "EXP-2001",
                    "action_type": "route_to_finance",
                    "status": "blocked",
                    "risk_level": "high",
                    "blocked": True,
                }
            )
            repository.upsert_many([first, second])

            by_trace = repository.by_trace_id("trace-1")
            by_action = repository.query(ApprovalActionProposalQuery(action_type="route_to_finance"))
            by_status = repository.query(ApprovalActionProposalQuery(status="blocked"))
            by_approval = repository.query(ApprovalActionProposalQuery(approval_id="EXP-2001"))
            by_risk = repository.query(ApprovalActionProposalQuery(risk_level="high"))

        self.assertEqual([record.trace_id for record in by_trace], ["trace-1"])
        self.assertEqual([record.proposal_id for record in by_action], ["proposal-2"])
        self.assertEqual([record.proposal_id for record in by_status], ["proposal-2"])
        self.assertEqual([record.proposal_id for record in by_approval], ["proposal-2"])
        self.assertEqual([record.proposal_id for record in by_risk], ["proposal-2"])


if __name__ == "__main__":
    unittest.main()
