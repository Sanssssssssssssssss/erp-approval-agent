from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.benchmarks.erp_approval_case_harness_benchmark import build_benchmark_cases, run_benchmark, summarize_benchmark


class ErpApprovalCaseHarnessBenchmarkTests(unittest.TestCase):
    def test_maturity_benchmark_scores_many_cases_without_major_failures(self) -> None:
        cases = build_benchmark_cases()
        self.assertGreaterEqual(len(cases), 300)

        with tempfile.TemporaryDirectory() as temp_dir:
            results = run_benchmark(cases, Path(temp_dir))
        summary = summarize_benchmark(results)

        self.assertGreaterEqual(summary["turn_count"], 400)
        self.assertEqual(summary["critical_failures"], 0)
        self.assertEqual(summary["major_failures"], 0)
        self.assertGreaterEqual(summary["average_score"], 95)
        self.assertGreaterEqual(summary["p10_score"], 90)
        self.assertEqual(summary["grade_counts"]["F"], 0)


if __name__ == "__main__":
    unittest.main()
