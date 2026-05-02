from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.strict_case_auditor import (
    audit_case,
    summarize_audit_results,
    trace_failure_to_stage,
)


class ErpApprovalStrictCaseAuditorTests(unittest.TestCase):
    def test_must_not_approve_is_critical_and_traced(self) -> None:
        case = {
            "case_id": "STRICT-001",
            "approval_type": "purchase_requisition",
            "expected_status_family": "escalate",
            "must_not_recommend_approve": True,
            "must_require_human_review": True,
            "expected_blocking_missing_requirements": ["purchase_requisition:budget_availability"],
            "expected_control_failures": ["budget_available"],
        }
        observed = {
            "recommendation": {"status": "recommend_approve", "human_review_required": False, "citations": []},
            "case_file": {"context_source_ids": [], "evidence_requirements": [], "evidence_claims": []},
            "evidence_sufficiency": {"passed": False, "missing_requirement_ids": ["purchase_requisition:budget_availability"]},
            "control_matrix": {"passed": False, "checks": [], "missing_check_ids": ["budget_available"]},
            "contradictions": {"has_conflict": False},
            "action_proposals": {"proposals": [{"executable": False}]},
            "final_answer_preview": "No ERP write action was executed.",
        }

        result = audit_case(case, observed)

        self.assertFalse(result.passed)
        self.assertEqual(result.severity, "critical")
        self.assertTrue(any(root.stage == "recommendation_drafter" for root in result.root_causes))

    def test_summary_counts_severities(self) -> None:
        passing = audit_case(
            {
                "case_id": "STRICT-PASS",
                "approval_type": "expense",
                "expected_status_family": "request_more_info",
                "must_not_recommend_approve": True,
            },
            {
                "recommendation": {"status": "request_more_info", "human_review_required": True, "citations": []},
                "case_file": {"context_source_ids": [], "evidence_requirements": [], "evidence_claims": []},
                "evidence_sufficiency": {"passed": False, "missing_requirement_ids": [], "partial_requirement_ids": [], "blocking_gaps": [], "next_questions": []},
                "control_matrix": {"passed": False, "checks": [], "missing_check_ids": []},
                "contradictions": {"has_conflict": False},
                "action_proposals": {"proposals": []},
                "final_answer_preview": "No ERP write action was executed.",
            },
        )
        failing = passing.model_copy(update={"case_id": "STRICT-MAJOR", "passed": False, "severity": "major"})

        summary = summarize_audit_results([passing, failing], [{"case_id": "STRICT-PASS", "approval_type": "expense"}, {"case_id": "STRICT-MAJOR", "approval_type": "expense"}])

        self.assertEqual(summary.total_cases, 2)
        self.assertEqual(summary.major_count, 1)
        self.assertEqual(summary.passed_cases, 1)

    def test_trace_failure_to_stage_handles_unreported_requirements(self) -> None:
        roots = trace_failure_to_stage(
            {"case_id": "STRICT-ROOT"},
            {"evidence_sufficiency": {}, "control_matrix": {}, "contradictions": {}, "recommendation": {}},
            ["Expected missing requirements were not reported: purchase_requisition:budget_availability"],
        )

        self.assertEqual(roots[0].stage, "evidence_requirement_planner")


if __name__ == "__main__":
    unittest.main()
