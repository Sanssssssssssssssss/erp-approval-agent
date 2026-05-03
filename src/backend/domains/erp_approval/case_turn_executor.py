from __future__ import annotations

import asyncio
from typing import Any

from src.backend.domains.erp_approval.case_harness import CaseHarness
from src.backend.domains.erp_approval.case_state_models import (
    CASE_HARNESS_NON_ACTION_STATEMENT,
    CaseTurnRequest,
    CaseTurnResponse,
)
from src.backend.domains.erp_approval.case_turn_graph import CASE_TURN_GRAPH_NAME, CASE_TURN_GRAPH_NODES, run_case_turn_graph_state_sync


class CaseTurnExecutor:
    """Runs one approval case turn through a Harness-owned LangGraph case graph."""

    def __init__(self, harness: CaseHarness, request: CaseTurnRequest) -> None:
        self.harness = harness
        self.request = request
        self.response: CaseTurnResponse | None = None
        self.graph_steps: list[str] = []

    async def execute(self, runtime, handle, *, message: str, history: list[dict[str, Any]]) -> None:
        del history
        lock_case_id = self.harness._lock_case_id(self.request)
        await runtime.emit(
            handle,
            "route.decided",
            {
                "intent": "erp_approval_case_turn",
                "needs_tools": False,
                "needs_retrieval": False,
                "allowed_tools": [],
                "confidence": 1.0,
                "reason_short": "Local evidence-first case turn is handled by the LangGraph case-turn graph.",
                "source": CASE_TURN_GRAPH_NAME,
            },
        )
        await runtime.emit(
            handle,
            "case.turn.started",
            {
                "case_id": lock_case_id,
                "requested_by": self.request.requested_by,
                "extra_evidence_count": len(self.request.extra_evidence),
                "message_preview": message[:240],
                "graph_name": CASE_TURN_GRAPH_NAME,
                "graph_nodes": list(CASE_TURN_GRAPH_NODES),
                "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
            },
        )
        graph_state = await asyncio.to_thread(run_case_turn_graph_state_sync, self.harness, self.request, message=message)
        self.response = graph_state["response"]
        self.graph_steps = list(graph_state.get("graph_steps", []))
        patch = self.response.patch
        state = self.response.case_state
        await runtime.emit(
            handle,
            "case.patch.validated",
            {
                "case_id": patch.case_id,
                "patch_id": patch.patch_id,
                "patch_type": patch.patch_type,
                "turn_intent": patch.turn_intent,
                "evidence_decision": patch.evidence_decision,
                "allowed_to_apply": patch.allowed_to_apply,
                "accepted_evidence_count": len(patch.accepted_evidence),
                "rejected_evidence_count": len(patch.rejected_evidence),
                "missing_requirement_count": len(patch.requirements_missing),
                "warning_count": len(patch.warnings),
                "stage_model_used": bool((patch.model_review or {}).get("used")),
                "graph_name": CASE_TURN_GRAPH_NAME,
                "graph_steps": self.graph_steps,
                "non_action_statement": patch.non_action_statement,
            },
        )
        await runtime.emit(
            handle,
            "case.state.persisted",
            {
                "case_id": state.case_id,
                "stage": state.stage,
                "turn_count": state.turn_count,
                "dossier_version": state.dossier_version,
                "state_mutated": self.response.operation_scope != "read_only_case_turn",
                "audit_only": self.response.operation_scope == "read_only_case_turn",
                "storage_paths": dict(self.response.storage_paths or {}),
                "graph_name": CASE_TURN_GRAPH_NAME,
                "graph_steps": self.graph_steps,
                "non_action_statement": state.non_action_statement,
            },
        )
        await runtime.emit(
            handle,
            "answer.completed",
            {
                "content": self.response.dossier,
                "segment_index": runtime.current_segment_index(handle),
                "final": True,
            },
        )
