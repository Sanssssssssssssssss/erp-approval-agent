from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from src.backend.domains.erp_approval.case_harness import (
    _event,
    _now,
    classify_case_turn,
    render_case_dossier,
)
from src.backend.domains.erp_approval.case_patch_validator import contract_for_state
from src.backend.domains.erp_approval.case_state_models import (
    ApprovalCaseState,
    CASE_HARNESS_NON_ACTION_STATEMENT,
    CaseAuditEvent,
    CasePatch,
    CaseTurnRequest,
    CaseTurnResponse,
)


class CaseTurnGraphState(TypedDict, total=False):
    harness: Any
    request: CaseTurnRequest
    message: str
    now: str
    existing_state: ApprovalCaseState | None
    case_state: ApprovalCaseState
    turn_id: str
    intent: str
    contract: Any
    context_pack: dict[str, Any]
    candidates: list[Any]
    provisional_review: Any
    model_decision: Any
    model_error: str
    accepted: list[Any]
    rejected: list[Any]
    warnings: list[str]
    review: Any
    patch: CasePatch
    audit_events: list[CaseAuditEvent]
    dossier: str
    response: CaseTurnResponse
    graph_steps: list[str]
    conflict: bool


def compile_case_turn_graph():
    """Compile the Harness-owned LangGraph case-turn state machine.

    The graph owns the case-turn orchestration. CaseHarness remains a domain module
    used by graph nodes for storage, validation, review helpers, and dossier output.
    """

    graph = StateGraph(CaseTurnGraphState)
    graph.add_node("load_case_state", load_case_state_node)
    graph.add_node("classify_turn", classify_turn_node)
    graph.add_node("assemble_case_context", assemble_case_context_node)
    graph.add_node("review_submission", review_submission_node)
    graph.add_node("propose_patch", propose_patch_node)
    graph.add_node("validate_patch", validate_patch_node)
    graph.add_node("persist_case", persist_case_node)
    graph.add_node("respond", respond_node)

    graph.set_entry_point("load_case_state")
    graph.add_edge("load_case_state", "classify_turn")
    graph.add_edge("classify_turn", "assemble_case_context")
    graph.add_edge("assemble_case_context", "review_submission")
    graph.add_edge("review_submission", "propose_patch")
    graph.add_edge("propose_patch", "validate_patch")
    graph.add_edge("validate_patch", "persist_case")
    graph.add_edge("persist_case", "respond")
    graph.add_edge("respond", END)
    return graph.compile()


def run_case_turn_graph_state_sync(harness: Any, request: CaseTurnRequest, *, message: str | None = None) -> CaseTurnGraphState:
    lock_case_id = harness._lock_case_id(request)
    with harness.store.case_lock(lock_case_id):
        graph = compile_case_turn_graph()
        return graph.invoke(
            {
                "harness": harness,
                "request": request,
                "message": message if message is not None else request.user_message,
                "graph_steps": [],
            }
        )


def run_case_turn_graph_sync(harness: Any, request: CaseTurnRequest, *, message: str | None = None) -> CaseTurnResponse:
    result = run_case_turn_graph_state_sync(harness, request, message=message)
    return result["response"]


def load_case_state_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    request = state["request"]
    now = _now()
    existing_state = harness.store.get(request.case_id) if request.case_id.strip() else None
    case_state = existing_state or harness._create_state(request, now)
    turn_id = f"turn-{case_state.turn_count + 1:04d}"
    contract = contract_for_state(case_state)
    graph_steps = _steps(state, "load_case_state")

    if existing_state is not None and request.expected_turn_count is not None and request.expected_turn_count != existing_state.turn_count:
        review = harness._review(existing_state, request.user_message, [])
        patch = CasePatch(
            patch_id=f"case-patch-conflict:{existing_state.case_id}:{turn_id}",
            turn_id=turn_id,
            case_id=existing_state.case_id,
            patch_type="no_case_change",
            turn_intent="ask_status",
            evidence_decision="not_evidence",
            warnings=[
                f"case_state version conflict: expected turn_count {request.expected_turn_count}, current turn_count {existing_state.turn_count}.",
                "This turn was not written to the approval case. Refresh the case state and resubmit.",
            ],
            allowed_to_apply=False,
        )
        return {
            **state,
            "now": now,
            "existing_state": existing_state,
            "case_state": existing_state,
            "turn_id": turn_id,
            "contract": contract,
            "review": review,
            "patch": patch,
            "audit_events": [
                _event(
                    turn_id,
                    existing_state.case_id,
                    "case_turn_conflict",
                    now,
                    {"expected_turn_count": request.expected_turn_count, "current_turn_count": existing_state.turn_count},
                )
            ],
            "dossier": harness.store.read_dossier(existing_state.case_id) or render_case_dossier(existing_state, review, patch),
            "conflict": True,
            "graph_steps": graph_steps,
        }

    return {
        **state,
        "now": now,
        "existing_state": existing_state,
        "case_state": case_state,
        "turn_id": turn_id,
        "contract": contract,
        "audit_events": [],
        "conflict": False,
        "graph_steps": graph_steps,
    }


def classify_turn_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    if state.get("conflict"):
        return {**state, "graph_steps": _steps(state, "classify_turn")}
    request = state["request"]
    intent = classify_case_turn(
        request.user_message,
        has_case=state.get("existing_state") is not None,
        has_evidence=bool(request.extra_evidence),
    )
    return {**state, "intent": intent, "graph_steps": _steps(state, "classify_turn")}


def assemble_case_context_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    if state.get("conflict"):
        return {**state, "graph_steps": _steps(state, "assemble_case_context")}
    harness = state["harness"]
    request = state["request"]
    case_state = state["case_state"]
    context_pack = harness.context_assembler.assemble(case_state, state["contract"], request.user_message)
    events = list(state.get("audit_events", []))
    events.append(
        _event(
            state["turn_id"],
            case_state.case_id,
            "turn_received",
            state["now"],
            {"intent": state["intent"], "context_pack": context_pack},
        )
    )
    return {
        **state,
        "context_pack": context_pack,
        "audit_events": events,
        "graph_steps": _steps(state, "assemble_case_context"),
    }


def review_submission_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    if state.get("conflict"):
        return {**state, "graph_steps": _steps(state, "review_submission")}
    harness = state["harness"]
    request = state["request"]
    candidates = harness._candidate_evidence(request, state["case_state"], state["turn_id"], state["intent"])
    provisional_review = harness._review(state["case_state"], request.user_message, candidates)
    model_decision, model_error = harness._review_with_stage_model(
        context_pack=state["context_pack"],
        candidates=candidates,
        review=provisional_review,
        deterministic_intent=state["intent"],
    )
    return {
        **state,
        "candidates": candidates,
        "provisional_review": provisional_review,
        "model_decision": model_decision,
        "model_error": model_error,
        "graph_steps": _steps(state, "review_submission"),
    }


def propose_patch_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    if state.get("conflict"):
        return {**state, "graph_steps": _steps(state, "propose_patch")}
    harness = state["harness"]
    intent = harness._intent_from_stage_model(state["intent"], state.get("model_decision"), state["contract"])
    accepted, rejected, warnings = harness._review_candidate_evidence(
        state.get("candidates", []),
        state["provisional_review"],
        state["now"],
    )
    accepted, rejected, warnings = harness._apply_stage_model_decision(
        candidates=state.get("candidates", []),
        accepted=accepted,
        rejected=rejected,
        warnings=warnings,
        decision=state.get("model_decision"),
        now=state["now"],
    )
    final_review = state["provisional_review"] if accepted else harness._review(state["case_state"], state["request"].user_message, [])
    patch = harness._build_patch(
        state=state["case_state"],
        turn_id=state["turn_id"],
        intent=intent,
        accepted=accepted,
        rejected=rejected,
        review=final_review,
        warnings=warnings,
        created_new=state.get("existing_state") is None,
        model_decision=state.get("model_decision"),
        model_error=state.get("model_error", ""),
    )
    return {
        **state,
        "intent": intent,
        "accepted": accepted,
        "rejected": rejected,
        "warnings": warnings,
        "review": final_review,
        "patch": patch,
        "graph_steps": _steps(state, "propose_patch"),
    }


def validate_patch_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    if state.get("conflict"):
        return {**state, "graph_steps": _steps(state, "validate_patch")}
    harness = state["harness"]
    patch = harness.validator.validate(state["case_state"], state["patch"], state["contract"], review=state["review"])
    return {**state, "patch": patch, "graph_steps": _steps(state, "validate_patch")}


def persist_case_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    request = state["request"]
    case_state = state["case_state"]
    patch = state["patch"]
    review = state["review"]
    now = state["now"]
    turn_id = state["turn_id"]
    events = list(state.get("audit_events", []))

    if state.get("conflict"):
        for event in events:
            harness.store.append_audit_event(event)
        return {**state, "graph_steps": _steps(state, "persist_case")}

    candidates = state.get("candidates", [])
    if state.get("existing_state") is None:
        events.append(_event(turn_id, case_state.case_id, "case_created", now, {"approval_type": case_state.approval_type, "approval_id": case_state.approval_id}))
    if candidates:
        events.append(_event(turn_id, case_state.case_id, "evidence_submitted", now, {"source_ids": [item.source_id for item in candidates]}))
    if patch.accepted_evidence:
        events.append(_event(turn_id, case_state.case_id, "evidence_accepted", now, {"source_ids": [item.source_id for item in patch.accepted_evidence]}))
    if patch.rejected_evidence:
        events.append(
            _event(
                turn_id,
                case_state.case_id,
                "evidence_rejected",
                now,
                {"source_ids": [item.source_id for item in patch.rejected_evidence], "reasons": patch.rejection_reasons},
            )
        )
    if state.get("intent") == "off_topic":
        events.append(_event(turn_id, case_state.case_id, "off_topic_rejected", now, {"message_preview": request.user_message[:240]}))
    if state.get("model_decision") is not None:
        model_decision = state["model_decision"]
        events.append(
            _event(
                turn_id,
                case_state.case_id,
                "case_stage_model_reviewed",
                now,
                {
                    "turn_intent": model_decision.turn_intent,
                    "patch_type": model_decision.patch_type,
                    "evidence_decision": model_decision.evidence_decision,
                    "confidence": model_decision.confidence,
                    "error": state.get("model_error", ""),
                },
            )
        )

    if patch.allowed_to_apply:
        case_state = harness._apply_patch(case_state, patch, review, now, turn_id, mutate_case=state.get("intent") != "off_topic")
        for evidence in patch.accepted_evidence:
            evidence_path = harness.store.write_evidence_text(case_state.case_id, evidence.source_id, evidence.content)
            for stored in case_state.accepted_evidence:
                if stored.source_id == evidence.source_id:
                    stored.metadata["local_evidence_file"] = evidence_path
        dossier = render_case_dossier(case_state, review, patch)
        harness.store.write_dossier(case_state.case_id, dossier)
        case_state = case_state.model_copy(update={"dossier_version": case_state.dossier_version + 1, "audit_event_count": case_state.audit_event_count + len(events)})
        harness.store.upsert(case_state)
        events.append(_event(turn_id, case_state.case_id, "case_state_persisted", now, {"stage": case_state.stage, "dossier_version": case_state.dossier_version}))
    else:
        dossier = harness.store.read_dossier(case_state.case_id) or render_case_dossier(case_state, review, patch)
        events.append(_event(turn_id, case_state.case_id, "case_patch_rejected", now, {"warnings": patch.warnings}))

    for event in events:
        harness.store.append_audit_event(event)
    return {
        **state,
        "case_state": case_state,
        "dossier": dossier,
        "audit_events": events,
        "graph_steps": _steps(state, "persist_case"),
    }


def respond_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    case_state = state["case_state"]
    response = CaseTurnResponse(
        case_state=case_state,
        contract=contract_for_state(case_state),
        patch=state["patch"],
        review=state["review"],
        dossier=state["dossier"],
        audit_events=state.get("audit_events", []),
        storage_paths=state["harness"].store.paths_for(case_state.case_id),
        operation_scope="persistent_case_turn_conflict" if state.get("conflict") else "persistent_case_turn",
        non_action_statement=CASE_HARNESS_NON_ACTION_STATEMENT,
    )
    return {**state, "response": response, "graph_steps": _steps(state, "respond")}


def _steps(state: CaseTurnGraphState, step: str) -> list[str]:
    return list(state.get("graph_steps", [])) + [step]
