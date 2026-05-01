from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.proposal_ledger import build_audit_package, run_completeness_checks
from src.backend.domains.erp_approval.proposal_ledger_models import ApprovalActionProposalRecord
from src.backend.domains.erp_approval.trace_models import ApprovalTraceRecord


def trace_record() -> ApprovalTraceRecord:
    return ApprovalTraceRecord(
        trace_id="trace-audit",
        approval_id="PR-1001",
        approval_type="purchase_requisition",
        created_at="2026-05-01T00:00:00+00:00",
        context_source_ids=["mock_erp://approval_request/PR-1001"],
        recommendation_status="request_more_info",
        citations=["mock_erp://approval_request/PR-1001"],
        review_status="accepted_by_human",
        proposal_ids=["proposal-audit"],
    )


def proposal_record(**updates) -> ApprovalActionProposalRecord:
    base = ApprovalActionProposalRecord(
        proposal_record_id="erp-proposal-record:proposal-audit:trace-audit",
        proposal_id="proposal-audit",
        trace_id="trace-audit",
        approval_id="PR-1001",
        action_type="request_more_info",
        status="proposed_only",
        payload_preview={"message_draft": "Ask for budget owner confirmation."},
        citations=["mock_erp://approval_request/PR-1001"],
        idempotency_key="key",
        idempotency_scope="scope",
        idempotency_fingerprint="fingerprint",
        executable=False,
        non_action_statement="No ERP write action was executed.",
    )
    return base.model_copy(update=updates)


class ErpApprovalAuditPackageTests(unittest.TestCase):
    def test_audit_package_contains_traces_proposals_and_checks(self) -> None:
        package = build_audit_package([trace_record()], [proposal_record()], "2026-05-01T00:00:00+00:00")

        self.assertTrue(package.package_id.startswith("erp-audit-package:"))
        self.assertEqual(package.trace_ids, ["trace-audit"])
        self.assertEqual(package.proposal_record_ids, ["erp-proposal-record:proposal-audit:trace-audit"])
        self.assertEqual(len(package.traces), 1)
        self.assertEqual(len(package.proposals), 1)
        self.assertTrue(package.completeness_checks)
        self.assertIn("No ERP write action was executed", package.non_action_statement)

    def test_completeness_checks_detect_missing_citations_idempotency_and_executable_true(self) -> None:
        trace = trace_record().model_copy(update={"citations": []})
        proposal = proposal_record(idempotency_key="", idempotency_fingerprint="", executable=True)

        checks = run_completeness_checks(trace, [proposal])
        failed = {check.check_name for check in checks if not check.passed}

        self.assertIn("has_citations", failed)
        self.assertIn("proposal_has_idempotency", failed)
        self.assertIn("proposal_executable_false", failed)

    def test_completeness_checks_detect_proposal_citations_outside_trace_context(self) -> None:
        proposal = proposal_record(citations=["mock_policy://missing"])

        checks = run_completeness_checks(trace_record(), [proposal])
        failed = {check.check_name for check in checks if not check.passed}

        self.assertIn("proposal_citations_present_in_trace_context", failed)


if __name__ == "__main__":
    unittest.main()
