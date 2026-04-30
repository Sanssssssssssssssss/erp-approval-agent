from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from src.backend.context import ContextAssembler
from src.backend.domains.erp_approval import (
    ApprovalRecommendation,
    ApprovalRequest,
    ErpContextQuery,
    MockErpContextAdapter,
    guard_recommendation,
)
from src.backend.orchestration.executor import (
    ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID,
    ERP_RECOMMENDATION_REVIEW_NON_ACTION,
    HarnessLangGraphOrchestrator,
)
from src.backend.orchestration.state import create_initial_graph_state


class FakeRuntime:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def now(self) -> str:
        return "2026-04-30T00:00:00+00:00"

    def current_segment_index(self, _handle) -> int:
        return 0

    def governor_for(self, _run_id: str):
        return SimpleNamespace(snapshot=lambda: {})

    async def emit(self, _handle, name: str, payload: dict) -> None:
        self.events.append((name, payload))


class FakeInterrupt(Exception):
    def __init__(self, payload: dict) -> None:
        super().__init__("fake interrupt")
        self.payload = payload


class ErpApprovalHitlGateTests(unittest.IsolatedAsyncioTestCase):
    def _orchestrator(self) -> tuple[HarnessLangGraphOrchestrator, FakeRuntime]:
        orchestrator = HarnessLangGraphOrchestrator.__new__(HarnessLangGraphOrchestrator)
        runtime = FakeRuntime()
        handle = SimpleNamespace(
            run_id="run-hitl",
            metadata=SimpleNamespace(session_id="session-hitl", thread_id="thread-hitl"),
        )
        orchestrator._bindings = SimpleNamespace(
            runtime=runtime,
            handle=handle,
            context=SimpleNamespace(approval_overrides=set()),
        )
        orchestrator._context_assembler = ContextAssembler(base_dir=BACKEND_DIR)
        orchestrator._erp_context_adapter = MockErpContextAdapter(base_dir=BACKEND_DIR)
        orchestrator._resume_checkpoint_id = "checkpoint-hitl"
        orchestrator._resume_source = "hitl_api"
        orchestrator._write_context_snapshot = lambda **kwargs: (
            {**dict(kwargs.get("state", {}) or {}), **dict(kwargs.get("result", {}) or {})},
            {},
        )
        orchestrator._record_post_turn_snapshot = lambda **_kwargs: None
        return orchestrator, runtime

    def _state_with_recommendation(
        self,
        recommendation: ApprovalRecommendation,
    ) -> dict:
        adapter = MockErpContextAdapter(base_dir=BACKEND_DIR)
        request = ApprovalRequest(
            approval_type="purchase_requisition",
            approval_id="PR-1001",
            requester="Lin Chen",
            department="Operations",
            amount=24500,
            currency="USD",
            vendor="Acme Supplies",
            cost_center="OPS-CC-10",
            business_purpose="replacement laptops",
            raw_request="Review PR-1001",
        )
        context = adapter.fetch_context(ErpContextQuery.from_request(request))
        guarded, guard = guard_recommendation(request, context, recommendation)
        state = create_initial_graph_state(
            run_id="run-hitl",
            session_id="session-hitl",
            thread_id="thread-hitl",
            user_message="Review PR-1001",
            history=[],
        )
        state.update(
            {
                "turn_id": "run-hitl:0",
                "path_kind": "erp_approval",
                "checkpoint_meta": {
                    **dict(state.get("checkpoint_meta", {}) or {}),
                    "checkpoint_id": "checkpoint-hitl",
                },
                "erp_request": request.model_dump(),
                "erp_context": context.model_dump(),
                "erp_recommendation": guarded.model_dump(),
                "erp_guard_result": guard.model_dump(),
            }
        )
        return state

    async def test_no_human_review_skips_hitl(self) -> None:
        orchestrator, _runtime = self._orchestrator()
        state = self._state_with_recommendation(
            ApprovalRecommendation(
                status="recommend_approve",
                confidence=0.84,
                summary="Mock context supports the recommendation.",
                rationale=["Vendor, budget, request, and policy context are present."],
                citations=["mock_erp://approval_request/PR-1001", "mock_policy://procurement_policy"],
                proposed_next_action="none",
                human_review_required=False,
            )
        )
        orchestrator._erp_hitl_interrupt = lambda _request: (_ for _ in ()).throw(AssertionError("unexpected HITL"))

        result = await orchestrator.erp_hitl_gate_node(state)

        self.assertEqual(result["erp_review_status"], "not_required")
        self.assertIsNone(result["erp_hitl_request"])

    def test_hitl_request_payload_contains_non_action_statement(self) -> None:
        orchestrator, _runtime = self._orchestrator()
        state = self._state_with_recommendation(
            ApprovalRecommendation(
                status="request_more_info",
                confidence=0.42,
                summary="More evidence is needed.",
                missing_information=["budget owner confirmation"],
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="request_more_info",
                human_review_required=True,
            )
        )
        request = orchestrator._erp_request_from_state(state)
        context = orchestrator._erp_context_from_state(state, request=request)
        recommendation = orchestrator._erp_recommendation_from_state(state)
        recommendation, guard = orchestrator._erp_guard_from_state(state, request, context, recommendation)

        payload = orchestrator._build_erp_hitl_request(state, request, context, recommendation, guard)

        self.assertEqual(payload["capability_id"], ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID)
        self.assertEqual(payload["display_name"], "ERP approval recommendation review")
        self.assertEqual(payload["proposed_input"]["explicit_non_action_statement"], ERP_RECOMMENDATION_REVIEW_NON_ACTION)
        self.assertIn("mock_erp://approval_request/PR-1001", payload["proposed_input"]["context_source_ids"])

    async def test_human_review_required_invokes_hitl_interrupt(self) -> None:
        orchestrator, _runtime = self._orchestrator()
        state = self._state_with_recommendation(
            ApprovalRecommendation(
                status="request_more_info",
                confidence=0.42,
                summary="More evidence is needed.",
                missing_information=["budget owner confirmation"],
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="request_more_info",
                human_review_required=True,
            )
        )
        orchestrator._erp_hitl_interrupt = lambda request: (_ for _ in ()).throw(FakeInterrupt(request))

        with self.assertRaises(FakeInterrupt) as raised:
            await orchestrator.erp_hitl_gate_node(state)

        self.assertEqual(raised.exception.payload["capability_id"], ERP_RECOMMENDATION_REVIEW_CAPABILITY_ID)
        self.assertEqual(
            raised.exception.payload["proposed_input"]["explicit_non_action_statement"],
            ERP_RECOMMENDATION_REVIEW_NON_ACTION,
        )

    async def test_approve_resume_accepts_recommendation_only(self) -> None:
        orchestrator, runtime = self._orchestrator()
        state = self._state_with_recommendation(
            ApprovalRecommendation(
                status="request_more_info",
                confidence=0.5,
                summary="More evidence is needed.",
                missing_information=["budget owner confirmation"],
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="request_more_info",
                human_review_required=True,
            )
        )
        orchestrator._erp_hitl_interrupt = lambda _request: {
            "decision": "approve",
            "actor_id": "tester",
            "actor_type": "unit_test",
            "decision_id": "decision-approve",
        }

        result = await orchestrator.erp_hitl_gate_node(state)

        self.assertEqual(result["erp_review_status"], "accepted_by_human")
        self.assertEqual(result["erp_hitl_decision"]["decision"], "approve")
        self.assertTrue(any(name == "hitl.approved" for name, _payload in runtime.events))

    async def test_reject_resume_final_answer_does_not_wrap_as_executable(self) -> None:
        orchestrator, _runtime = self._orchestrator()
        emitted: list[str] = []

        async def fake_emit_final_answer(content: str, *, usage=None) -> None:
            del usage
            emitted.append(content)

        orchestrator._emit_final_answer = fake_emit_final_answer
        state = self._state_with_recommendation(
            ApprovalRecommendation(
                status="escalate",
                confidence=0.5,
                summary="Escalation is needed.",
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="manual_review",
                human_review_required=True,
            )
        )
        orchestrator._erp_hitl_interrupt = lambda _request: {"decision": "reject", "decision_id": "decision-reject"}

        state.update(await orchestrator.erp_hitl_gate_node(state))
        state.update(await orchestrator.erp_finalize_node(state))

        self.assertEqual(state["erp_review_status"], "rejected_by_human")
        self.assertIn("Human reviewer rejected the agent recommendation.", state["final_answer"])
        self.assertIn("No ERP approval, rejection, payment, supplier, contract, or budget action was executed.", state["final_answer"])
        self.assertNotIn("Status: escalate", state["final_answer"])
        self.assertEqual(emitted, [state["final_answer"]])

    async def test_edit_resume_revalidates_edited_recommendation(self) -> None:
        orchestrator, _runtime = self._orchestrator()
        state = self._state_with_recommendation(
            ApprovalRecommendation(
                status="request_more_info",
                confidence=0.5,
                summary="More evidence is needed.",
                missing_information=["budget owner confirmation"],
                citations=["mock_erp://approval_request/PR-1001"],
                proposed_next_action="request_more_info",
                human_review_required=True,
            )
        )
        orchestrator._erp_hitl_interrupt = lambda _request: {
            "decision": "edit",
            "edited_input": {
                "recommendation": {
                    "status": "recommend_approve",
                    "confidence": 0.9,
                    "summary": "Edited recommendation still lacks budget confirmation.",
                    "rationale": ["Human reviewer edited the recommendation."],
                    "missing_information": ["budget owner confirmation"],
                    "risk_flags": [],
                    "citations": ["mock_erp://approval_request/PR-1001"],
                    "proposed_next_action": "none",
                    "human_review_required": False,
                }
            },
            "decision_id": "decision-edit",
        }

        result = await orchestrator.erp_hitl_gate_node(state)

        self.assertEqual(result["erp_review_status"], "edited_by_human")
        self.assertEqual(result["erp_recommendation"]["status"], "request_more_info")
        self.assertTrue(result["erp_recommendation"]["human_review_required"])
        self.assertTrue(result["erp_guard_result"]["downgraded"])

    async def test_final_answer_always_contains_no_action_statement(self) -> None:
        orchestrator, _runtime = self._orchestrator()
        emitted: list[str] = []

        async def fake_emit_final_answer(content: str, *, usage=None) -> None:
            del usage
            emitted.append(content)

        orchestrator._emit_final_answer = fake_emit_final_answer
        state = self._state_with_recommendation(
            ApprovalRecommendation(
                status="recommend_approve",
                confidence=0.84,
                summary="Mock context supports the recommendation.",
                citations=["mock_erp://approval_request/PR-1001", "mock_policy://procurement_policy"],
                proposed_next_action="none",
                human_review_required=False,
            )
        )
        state.update(await orchestrator.erp_hitl_gate_node(state))
        state.update(await orchestrator.erp_finalize_node(state))

        self.assertIn("Human review status: not_required", state["final_answer"])
        self.assertIn("No ERP approval, rejection, payment, supplier, contract, or budget action was executed.", state["final_answer"])
        self.assertEqual(emitted, [state["final_answer"]])


if __name__ == "__main__":
    unittest.main()
