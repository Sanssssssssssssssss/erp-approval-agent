from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.benchmarks.erp_approval_case_harness_stress import build_scenarios, run_stress_suite, summarize_results


class ErpApprovalCaseHarnessStressTests(unittest.TestCase):
    def test_stress_suite_has_many_scenarios_and_no_critical_failures(self) -> None:
        scenarios = build_scenarios()
        self.assertGreaterEqual(len(scenarios), 60)

        with tempfile.TemporaryDirectory() as temp_dir:
            results = run_stress_suite(scenarios, Path(temp_dir))
        summary = summarize_results(results)

        self.assertGreaterEqual(summary["turns"], 70)
        self.assertEqual(summary["critical"], 0)
        self.assertEqual(summary["major"], 0)
        self.assertGreaterEqual(summary["recommend_approve_turns"], 1)
        self.assertGreaterEqual(summary["blocked_or_escalated_turns"], 1)


if __name__ == "__main__":
    unittest.main()
