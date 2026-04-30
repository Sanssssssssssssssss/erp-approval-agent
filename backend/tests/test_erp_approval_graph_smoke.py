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


class ErpApprovalGraphSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_erp_nodes_reach_final_answer_with_mocked_model(self) -> None:
        orchestrator = HarnessLangGraphOrchestrator.__new__(HarnessLangGraphOrchestrator)
        orchestrator._context_assembler = ContextAssembler(base_dir=BACKEND_DIR)
        orchestrator._erp_context_adapter = MockErpContextAdapter(base_dir=BACKEND_DIR)
        emitted_answers: list[str] = []

        async def fake_stream_model_answer(_messages, *, system_prompt_override=None, **_kwargs):
            if system_prompt_override == ERP_INTAKE_SYSTEM_PROMPT:
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
                    {"input_tokens": 1, "output_tokens": 1},
                )
            return (
                json.dumps(
                    {
                        "status": "recommend_approve",
                        "confidence": 0.82,
                        "summary": "PR-1001 has matching mock vendor, budget, and procurement policy context.",
                        "rationale": ["Mock context includes request, vendor, budget, and policy records."],
                        "missing_information": [],
                        "risk_flags": [],
                        "citations": [
                            "mock_erp://approval_request/PR-1001",
                            "mock_policy://procurement_policy",
                        ],
                        "proposed_next_action": "manual_review",
                        "human_review_required": False,
                    }
                ),
                {"input_tokens": 2, "output_tokens": 2},
            )

        async def fake_emit_final_answer(content: str, *, usage=None) -> None:
            del usage
            emitted_answers.append(content)

        orchestrator._stream_model_answer = fake_stream_model_answer
        orchestrator._emit_final_answer = fake_emit_final_answer
        orchestrator._record_model_call_snapshot = lambda **kwargs: str(kwargs.get("call_site", ""))
        orchestrator._record_post_turn_snapshot = lambda **_kwargs: None
        orchestrator._write_context_snapshot = lambda **kwargs: (
            {**dict(kwargs.get("state", {}) or {}), **dict(kwargs.get("result", {}) or {})},
            {},
        )

        state = create_initial_graph_state(
            run_id="run-erp-smoke",
            session_id="session-erp-smoke",
            thread_id="thread-erp-smoke",
            user_message="Review PR-1001",
            history=[],
        )
        state["turn_id"] = "run-erp-smoke:0"
        state["path_kind"] = "erp_approval"

        for node in (
            orchestrator.erp_intake_node,
            orchestrator.erp_context_node,
            orchestrator.erp_reasoning_node,
            orchestrator.erp_guard_node,
            orchestrator.erp_hitl_gate_node,
            orchestrator.erp_action_proposal_node,
            orchestrator.erp_finalize_node,
        ):
            state.update(await node(state))

        self.assertTrue(state["answer_finalized"])
        self.assertEqual(state["erp_review_status"], "not_required")
        self.assertIn("ERP approval recommendation", state["final_answer"])
        self.assertIn("Action proposals", state["final_answer"])
        self.assertIn("No ERP write action was executed.", state["final_answer"])
        self.assertIn("No ERP approval, rejection, payment, supplier, contract, or budget action was executed.", state["final_answer"])
        self.assertEqual(emitted_answers, [state["final_answer"]])


if __name__ == "__main__":
    unittest.main()
