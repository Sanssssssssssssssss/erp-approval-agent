from __future__ import annotations

import asyncio
from typing import Any

from src.backend.domains.erp_approval.case_harness import CaseHarness
from src.backend.domains.erp_approval.case_state_models import (
    CASE_HARNESS_NON_ACTION_STATEMENT,
    CaseTurnRequest,
    CaseTurnResponse,
)


class CaseTurnExecutor:
    """Runs a local approval case turn inside the HarnessRuntime lifecycle."""

    def __init__(self, harness: CaseHarness, request: CaseTurnRequest) -> None:
        self.harness = harness
        self.request = request
        self.response: CaseTurnResponse | None = None

    async def execute(self, runtime, handle, *, message: str, history: list[dict[str, Any]]) -> None:
        del history
        await runtime.emit(
            handle,
            "route.decided",
            {
                "intent": "erp_approval_case_turn",
                "needs_tools": False,
                "needs_retrieval": False,
                "allowed_tools": [],
                "confidence": 1.0,
                "reason_short": "Local evidence-first case turn is handled by CaseHarness.",
                "source": "case_harness",
            },
        )
        await runtime.emit(
            handle,
            "case.turn.started",
            {
                "case_id": self.request.case_id,
                "requested_by": self.request.requested_by,
                "extra_evidence_count": len(self.request.extra_evidence),
                "message_preview": message[:240],
                "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
            },
        )
        self.response = await asyncio.to_thread(self.harness.handle_turn, self.request)
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
                "storage_paths": dict(self.response.storage_paths or {}),
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
