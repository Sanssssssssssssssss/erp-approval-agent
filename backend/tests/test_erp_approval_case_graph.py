from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.context import ContextAssembler
from src.backend.domains.erp_approval.context_adapter import MockErpContextAdapter
from src.backend.domains.erp_approval.prompts import ERP_INTAKE_SYSTEM_PROMPT
from src.backend.orchestration.executor import HarnessLangGraphOrchestrator
from src.backend.orchestration.state import create_initial_graph_state


class ErpApprovalCaseGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_case_evidence_path_reaches_conservative_recommendation_without_real_llm(self) -> None:
        orchestrator = HarnessLangGraphOrchestrator.__new__(HarnessLangGraphOrchestrator)
        orchestrator._context_assembler = ContextAssembler(base_dir=BACKEND_DIR)
        orchestrator._erp_context_adapter = MockErpContextAdapter(base_dir=BACKEND_DIR)
        orchestrator._record_model_call_snapshot = lambda **kwargs: str(kwargs.get("call_site", ""))
        orchestrator._write_context_snapshot = lambda **kwargs: (
            {**dict(kwargs.get("state", {}) or {}), **dict(kwargs.get("result", {}) or {})},
            {},
        )

        async def fake_stream_model_answer(_messages, *, system_prompt_override=None, **_kwargs):
            self.assertEqual(system_prompt_override, ERP_INTAKE_SYSTEM_PROMPT)
            return (
                json.dumps(
                    {
                        "approval_type": "purchase_requisition",
                        "approval_id": "PR-1001",
                        "requester": "Lin Chen",
                        "department": "Operations",
                        "amount": 24500,
                        "currency": "USD",
                        "vendor": "Acme Supplies",
                        "cost_center": "OPS-CC-10",
                        "business_purpose": "replacement laptops",
                        "raw_request": "PR-1001 laptop purchase",
                    }
                ),
                None,
            )

        orchestrator._stream_model_answer = fake_stream_model_answer
        state = create_initial_graph_state(
            run_id="case-graph",
            session_id="case-graph",
            thread_id="case-graph",
            user_message="Review PR-1001",
            history=[],
        )
        state["turn_id"] = "case-graph:0"
        state["path_kind"] = "erp_approval"

        for node in (
            orchestrator.erp_intake_node,
            orchestrator.erp_context_node,
            orchestrator.erp_case_file_node,
            orchestrator.erp_evidence_requirements_node,
            orchestrator.erp_evidence_claims_node,
            orchestrator.erp_evidence_sufficiency_node,
            orchestrator.erp_control_matrix_node,
            orchestrator.erp_case_recommendation_node,
            orchestrator.erp_adversarial_review_node,
            orchestrator.erp_guard_node,
        ):
            state.update(await node(state))

        self.assertIn("erp_case_file", state)
        self.assertFalse(state["erp_evidence_sufficiency"]["passed"])
        self.assertNotEqual(state["erp_recommendation"]["status"], "recommend_approve")
        self.assertTrue(state["erp_adversarial_review"]["challenged_control_ids"])


if __name__ == "__main__":
    unittest.main()
