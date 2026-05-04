from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.domains.erp_approval.case_harness import CaseHarness
from src.backend.domains.erp_approval.case_stage_model import CaseStageModelReviewer
from src.backend.domains.erp_approval.case_state_models import CaseTurnRequest
from src.backend.domains.erp_approval.policy_rag import build_policy_rag_context


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = []

    def invoke(self, messages):
        self.messages.append(messages)
        return _FakeResponse(self.content)


class ErpApprovalPolicyRagTests(unittest.TestCase):
    def test_policy_rag_uses_existing_knowledge_index_for_erp_policy(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            base_dir = Path(temp_dir)
            policy_dir = base_dir / "knowledge" / "ERP Approval" / "policies"
            policy_dir.mkdir(parents=True)
            (policy_dir / "procurement_policy.md").write_text(
                "\n".join(
                    [
                        "# Procurement Policy",
                        "Purchase requisitions require budget availability, vendor onboarding status, quote evidence, and approval matrix.",
                        "Budget evidence must include cost center, available budget, requested amount, and budget owner.",
                    ]
                ),
                encoding="utf-8",
            )
            harness = CaseHarness(base_dir)
            state = harness._create_state(
                CaseTurnRequest(user_message="Create purchase requisition PR-RAG-001 for replacement laptops."),
                "2026-05-04T00:00:00Z",
            )

            context = build_policy_rag_context(
                base_dir=base_dir,
                state=state,
                user_message="What materials are required?",
                purpose="materials_guidance",
                stage_model=None,
            )

            self.assertTrue(context.used)
            self.assertIn(context.status, {"success", "partial"})
            self.assertTrue(context.evidences)
            self.assertTrue(all(item.source_path.startswith("knowledge/ERP Approval") for item in context.evidences))
            self.assertTrue(any("budget availability" in item.snippet.lower() for item in context.evidences))

    def test_policy_rag_query_rewrite_can_be_model_planned_but_retrieval_stays_local(self) -> None:
        model = _FakeModel(
            """
            {
              "need_rag": true,
              "rewritten_queries": ["purchase requisition budget vendor onboarding approval matrix policy"],
              "query_hints": ["budget", "vendor onboarding", "approval matrix"],
              "reason": "Need policy clauses for required materials.",
              "non_action_statement": "This is a local approval case state update. No ERP write action was executed."
            }
            """
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            base_dir = Path(temp_dir)
            policy_dir = base_dir / "knowledge" / "ERP Approval" / "policies"
            policy_dir.mkdir(parents=True)
            (policy_dir / "procurement_policy.md").write_text(
                "Approval matrix and budget evidence are required for purchase requisition review.",
                encoding="utf-8",
            )
            harness = CaseHarness(base_dir, stage_model=CaseStageModelReviewer(model))
            state = harness._create_state(
                CaseTurnRequest(user_message="Create purchase requisition PR-RAG-002."),
                "2026-05-04T00:00:00Z",
            )

            context = build_policy_rag_context(
                base_dir=base_dir,
                state=state,
                user_message="需要准备哪些材料？",
                purpose="materials_guidance",
                stage_model=harness.stage_model,
            )

            self.assertTrue(context.plan.planner_used)
            self.assertEqual(context.plan.planner_status, "executed")
            self.assertEqual(context.plan.rewritten_queries[0], "purchase requisition budget vendor onboarding approval matrix policy")
            self.assertTrue(context.evidences)
            self.assertEqual(len(model.messages), 1)
            self.assertIn("ERP policy RAG query planner", model.messages[0][0]["content"])


if __name__ == "__main__":
    unittest.main()
