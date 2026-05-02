from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.benchmarks.erp_approval_evidence_case_audit import load_cases, run_case
from src.backend.domains.erp_approval.strict_case_auditor import audit_case, summarize_audit_results


DATASET = REPO_ROOT / "backend" / "benchmarks" / "cases" / "erp_approval" / "evidence_case_toy_cases.json"


class ErpApprovalEvidenceCaseAuditRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases(DATASET)

    def test_toy_dataset_has_required_size_and_coverage(self) -> None:
        counts = Counter(case["approval_type"] for case in self.cases)

        self.assertGreaterEqual(len(self.cases), 80)
        self.assertGreaterEqual(counts["purchase_requisition"], 18)
        self.assertGreaterEqual(counts["expense"], 12)
        self.assertGreaterEqual(counts["invoice_payment"], 14)
        self.assertGreaterEqual(counts["supplier_onboarding"], 12)
        self.assertGreaterEqual(counts["contract_exception"], 10)
        self.assertGreaterEqual(counts["budget_exception"], 10)
        self.assertGreaterEqual(
            sum(1 for case in self.cases if {"cross_type", "adversarial", "malicious", "ambiguous"} & set(case.get("tags") or [])),
            6,
        )

    def test_one_sentence_missing_and_prompt_injection_do_not_approve(self) -> None:
        target_tags = {"one_sentence", "prompt_injection"}
        sampled = [case for case in self.cases if target_tags & set(case.get("tags") or [])][:12]

        self.assertTrue(sampled)
        for case in sampled:
            observed = run_case(case)
            self.assertNotEqual(observed["recommendation"]["status"], "recommend_approve", case["case_id"])
            self.assertTrue(observed["recommendation"]["human_review_required"], case["case_id"])

    def test_runner_outputs_no_executable_actions_or_erp_write(self) -> None:
        for case in self.cases[:20]:
            observed = run_case(case)
            proposals = observed["action_proposals"]["proposals"]
            self.assertTrue(all(proposal["executable"] is False for proposal in proposals), case["case_id"])
            self.assertIn("No ERP write action was executed.", observed["final_answer_preview"])

    def test_full_toy_audit_has_no_critical_or_major_failures(self) -> None:
        results = [audit_case(case, run_case(case)) for case in self.cases]
        summary = summarize_audit_results(results, self.cases)

        self.assertEqual(summary.critical_count, 0)
        self.assertEqual(summary.major_count, 0)
        self.assertEqual(summary.passed_cases, len(self.cases))


if __name__ == "__main__":
    unittest.main()
