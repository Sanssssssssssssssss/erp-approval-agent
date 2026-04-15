from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.knowledge.orchestrator import KnowledgeOrchestrator
from src.backend.knowledge.retrieval_strategy import (
    BaselineHybridRagStrategy,
    RetrievalRequest,
    RetrievalResult,
)
from src.backend.knowledge.types import Evidence, HybridRetrievalResult


class RetrievalStrategyTests(unittest.TestCase):
    def test_baseline_hybrid_strategy_returns_diagnostics(self) -> None:
        strategy = BaselineHybridRagStrategy()
        evidence = Evidence(
            source_path="knowledge/RFP Security/security_controls.md",
            source_type="md",
            locator="Identity and access management / paragraph 1",
            snippet="The service supports SAML 2.0 and OpenID Connect single sign-on.",
            channel="vector",
            score=0.9,
        )
        with patch(
            "src.backend.knowledge.retrieval_strategy.hybrid_retriever.retrieve",
            return_value=HybridRetrievalResult(
                vector_evidences=[evidence],
                bm25_evidences=[],
                query_variants=["security questionnaire sso protocols"],
                entity_hints=[],
            ),
        ):
            result = strategy.retrieve(
                RetrievalRequest(
                    query="Which SSO protocols are supported?",
                    top_k=5,
                    rewrite_enabled=False,
                    reranker_enabled=False,
                )
            )

        self.assertEqual(result.strategy, "baseline_hybrid")
        self.assertEqual(result.query_variants, ["Which SSO protocols are supported?"])
        self.assertIn("retrieved_ids", result.diagnostics)
        self.assertTrue(result.evidences)

    def test_knowledge_orchestrator_delegates_to_configured_strategy(self) -> None:
        orchestrator = KnowledgeOrchestrator()
        stub_result = RetrievalResult(
            status="success",
            evidences=[],
            steps=[],
            strategy="baseline_hybrid",
            question_type="direct_fact",
            query_variants=["test query"],
        )
        fake_strategy = SimpleNamespace(retrieve=lambda request: stub_result)
        with (
            patch(
                "src.backend.knowledge.orchestrator.get_settings",
                return_value=SimpleNamespace(
                    retrieval_strategy="baseline_hybrid",
                    retrieval_top_k=7,
                    retrieval_rewrite_enabled=False,
                    retrieval_reranker_enabled=False,
                ),
            ),
            patch("src.backend.knowledge.orchestrator.get_retrieval_strategy", return_value=fake_strategy),
        ):
            result = orchestrator._build_formal_retrieval_result("test query")

        self.assertEqual(result.strategy, "baseline_hybrid")
        self.assertEqual(result.query_variants, ["test query"])
