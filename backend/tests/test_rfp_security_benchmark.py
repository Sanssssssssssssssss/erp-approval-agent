from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from benchmarks.case_loader import BenchmarkSelection, load_cases
from benchmarks.rfp_security_suite import run_rfp_security_suite
from src.backend.knowledge.retrieval_strategy import RetrievalResult
from src.backend.knowledge.types import Evidence, RetrievalStep


class RfpSecurityBenchmarkTests(unittest.TestCase):
    def test_case_loader_exposes_rfp_security_cases(self) -> None:
        cases = load_cases(BenchmarkSelection(module="rag", rag_subtype="rfp_security"))
        self.assertGreaterEqual(len(cases), 20)

    def test_rfp_security_suite_returns_summary_with_strategy_metrics(self) -> None:
        fake_result = RetrievalResult(
            status="success",
            evidences=[
                Evidence(
                    source_path="knowledge/RFP Security/security_controls.md",
                    source_type="md",
                    locator="Identity and access management / paragraph 1",
                    snippet="The service supports SAML 2.0 and OpenID Connect single sign-on.",
                    channel="vector",
                    score=0.9,
                )
            ],
            steps=[RetrievalStep(kind="knowledge", stage="vector", title="Vector retrieval")],
            reason="stub",
            strategy="baseline_hybrid",
            question_type="direct_fact",
            query_variants=["Which SSO protocols are supported?"],
            diagnostics={"retrieved_ids": ["knowledge/RFP Security/security_controls.md"]},
        )
        fake_strategy = type("FakeStrategy", (), {"retrieve": lambda self, request: fake_result})()
        with (
            patch(
                "benchmarks.rfp_security_suite.ensure_index_ready",
                return_value=({"ready": True, "building": False}, {"md", "json", "txt"}),
            ),
            patch("benchmarks.rfp_security_suite.get_retrieval_strategy", return_value=fake_strategy),
        ):
            payload = run_rfp_security_suite(limit=1, rewrite_enabled=False, reranker_enabled=False, top_k=5)

        self.assertEqual(payload["selection"]["rag_subtype"], "rfp_security")
        self.assertEqual(payload["strategy_config"]["strategy"], "baseline_hybrid")
        self.assertIn("groundedness", payload["summary"])
        self.assertEqual(len(payload["cases"]), 1)
        self.assertEqual(
            payload["cases"][0]["final_evidence_ids"],
            [
                "knowledge/RFP Security/security_controls.md|Identity and access management / paragraph 1",
                "knowledge/RFP Security/security_controls.md",
            ],
        )
