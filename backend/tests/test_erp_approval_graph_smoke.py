from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.context import ContextAssembler
from src.backend.domains.erp_approval.context_adapter import MockErpContextAdapter
from src.backend.domains.erp_approval.proposal_ledger import ApprovalActionProposalRepository
from src.backend.domains.erp_approval.prompts import ERP_INTAKE_SYSTEM_PROMPT
from src.backend.domains.erp_approval.trace_store import ApprovalTraceRepository
from src.backend.orchestration.executor import HarnessLangGraphOrchestrator
from src.backend.orchestration.state import create_initial_graph_state


class ErpApprovalGraphSmokeTests(unittest.IsolatedAsyncioTestCase):
    def _orchestrator(self, trace_repository=None, proposal_repository=None):
        orchestrator = HarnessLangGraphOrchestrator.__new__(HarnessLangGraphOrchestrator)
        orchestrator._context_assembler = ContextAssembler(base_dir=BACKEND_DIR)
        orchestrator._erp_context_adapter = MockErpContextAdapter(base_dir=BACKEND_DIR)
        orchestrator._resume_checkpoint_id = ""
        orchestrator._resume_source = ""
        if trace_repository is not None:
            orchestrator._erp_trace_repository = trace_repository
        if proposal_repository is not None:
            orchestrator._erp_proposal_repository = proposal_repository
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

        class FakeRuntime:
            def now(self) -> str:
                return "2026-01-01T00:00:00+00:00"

            async def emit(self, *_args, **_kwargs) -> None:
                return None

        class FakeHandle:
            run_id = "run-erp-smoke"
            metadata = {}

        class FakeBindings:
            runtime = FakeRuntime()
            handle = FakeHandle()
            context = None

        orchestrator._stream_model_answer = fake_stream_model_answer
        orchestrator._emit_final_answer = fake_emit_final_answer
        orchestrator._bindings_or_raise = lambda: FakeBindings()
        orchestrator._erp_hitl_interrupt = lambda _request: {
            "decision": "approve",
            "actor_id": "test-user",
            "actor_type": "test",
            "decided_at": "2026-01-01T00:00:00+00:00",
        }
        orchestrator._record_model_call_snapshot = lambda **kwargs: str(kwargs.get("call_site", ""))
        orchestrator._record_post_turn_snapshot = lambda **_kwargs: None
        orchestrator._write_context_snapshot = lambda **kwargs: (
            {**dict(kwargs.get("state", {}) or {}), **dict(kwargs.get("result", {}) or {})},
            {},
        )
        return orchestrator, emitted_answers

    async def test_erp_nodes_reach_final_answer_with_mocked_model_and_writes_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            proposal_repository = ApprovalActionProposalRepository(Path(temp_dir) / "action_proposals.jsonl")
            orchestrator, emitted_answers = self._orchestrator(trace_repository, proposal_repository)

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
                orchestrator.erp_case_file_node,
                orchestrator.erp_evidence_requirements_node,
                orchestrator.erp_evidence_claims_node,
                orchestrator.erp_evidence_sufficiency_node,
                orchestrator.erp_control_matrix_node,
                orchestrator.erp_case_recommendation_node,
                orchestrator.erp_adversarial_review_node,
                orchestrator.erp_guard_node,
                orchestrator.erp_hitl_gate_node,
                orchestrator.erp_action_proposal_node,
                orchestrator.erp_finalize_node,
            ):
                state.update(await node(state))

            traces = trace_repository.list_recent(limit=10)
            proposal_records = proposal_repository.list_recent(limit=10)

        self.assertTrue(state["answer_finalized"])
        self.assertEqual(state["erp_review_status"], "accepted_by_human")
        self.assertIn("必需证据清单", state["final_answer"])
        self.assertIn("控制矩阵检查", state["final_answer"])
        self.assertIn("No ERP write action was executed", state["final_answer"])
        self.assertTrue(state["erp_trace_write_result"]["success"])
        self.assertEqual(len(state["erp_proposal_write_results"]), 1)
        self.assertTrue(state["erp_proposal_write_results"][0]["success"])
        self.assertEqual(len(traces), 1)
        self.assertNotEqual(traces[0].recommendation_status, "recommend_approve")
        self.assertEqual(len(proposal_records), 1)
        self.assertEqual(proposal_records[0].trace_id, traces[0].trace_id)
        self.assertFalse(proposal_records[0].executable)
        self.assertEqual(emitted_answers, [state["final_answer"]])

    async def test_erp_finalize_trace_write_failure_does_not_block_final_answer(self) -> None:
        class FailingTraceRepository:
            def upsert(self, _record):
                raise OSError("trace write failed")

        orchestrator, emitted_answers = self._orchestrator(FailingTraceRepository())
        state = create_initial_graph_state(
            run_id="run-erp-trace-fail",
            session_id="session-erp-trace-fail",
            thread_id="thread-erp-trace-fail",
            user_message="Review PR-1001",
            history=[],
        )
        state["turn_id"] = "run-erp-trace-fail:0"
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
            orchestrator.erp_hitl_gate_node,
            orchestrator.erp_action_proposal_node,
            orchestrator.erp_finalize_node,
        ):
            state.update(await node(state))

        self.assertTrue(state["answer_finalized"])
        self.assertIn("必需证据清单", state["final_answer"])
        self.assertIsNone(state["erp_trace_write_result"])
        self.assertEqual(emitted_answers, [state["final_answer"]])

    async def test_erp_finalize_proposal_ledger_failure_does_not_block_final_answer(self) -> None:
        class FailingProposalRepository:
            def upsert_many(self, _records):
                raise OSError("proposal write failed")

        with tempfile.TemporaryDirectory() as temp_dir:
            trace_repository = ApprovalTraceRepository(Path(temp_dir) / "approval_traces.jsonl")
            orchestrator, emitted_answers = self._orchestrator(trace_repository, FailingProposalRepository())
            state = create_initial_graph_state(
                run_id="run-erp-proposal-fail",
                session_id="session-erp-proposal-fail",
                thread_id="thread-erp-proposal-fail",
                user_message="Review PR-1001",
                history=[],
            )
            state["turn_id"] = "run-erp-proposal-fail:0"
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
                orchestrator.erp_hitl_gate_node,
                orchestrator.erp_action_proposal_node,
                orchestrator.erp_finalize_node,
            ):
                state.update(await node(state))

        self.assertTrue(state["answer_finalized"])
        self.assertTrue(state["erp_trace_write_result"]["success"])
        self.assertEqual(state["erp_proposal_write_results"], [])
        self.assertEqual(emitted_answers, [state["final_answer"]])


if __name__ == "__main__":
    unittest.main()
