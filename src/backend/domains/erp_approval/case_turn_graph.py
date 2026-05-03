from __future__ import annotations

from functools import lru_cache
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
from src.backend.domains.erp_approval.p2p_process_models import P2PProcessReview
from src.backend.domains.erp_approval.p2p_process_review import (
    P2P_RECORD_TYPES,
    p2p_amount_consistency_reviewer,
    p2p_exception_reviewer,
    p2p_match_type_classifier,
    p2p_process_fact_extractor,
    p2p_sequence_anomaly_reviewer,
    render_p2p_review_notes,
    review_p2p_process_evidence,
)

CASE_TURN_GRAPH_NAME = "erp_approval_dynamic_case_turn_graph"
CASE_TURN_GRAPH_NODES: tuple[str, ...] = (
    "load_case_state",
    "version_conflict_gate",
    "classify_turn_intent",
    "build_turn_contract",
    "assemble_case_context",
    "route_turn_intent",
    "materials_guidance_node",
    "case_status_summary_node",
    "off_topic_reject_node",
    "correct_evidence_node",
    "withdraw_evidence_node",
    "recompute_case_analysis",
    "final_memo_gate",
    "build_candidate_evidence",
    "route_evidence_type",
    "p2p_process_fact_extractor",
    "p2p_match_type_classifier",
    "p2p_sequence_anomaly_reviewer",
    "p2p_amount_consistency_reviewer",
    "p2p_exception_reviewer",
    "p2p_patch_proposal",
    "p2p_process_patch_validator",
    "purchase_requisition_review_subgraph",
    "expense_review_subgraph",
    "supplier_onboarding_review_subgraph",
    "contract_exception_review_subgraph",
    "budget_exception_review_subgraph",
    "generic_evidence_review_subgraph",
    "merge_review_outputs",
    "evidence_sufficiency_gate",
    "contradiction_gate",
    "control_matrix_gate",
    "propose_case_patch",
    "validate_case_patch",
    "route_patch_validity",
    "persist_case_state_dossier_audit",
    "reject_patch_explain",
    "respond_to_user",
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
    branch: str
    evidence_branch: str
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
    p2p_review: P2PProcessReview
    branch_review_outputs: dict[str, Any]


@lru_cache(maxsize=1)
def compile_case_turn_graph():
    """Compile the Harness-owned dynamic LangGraph case-turn graph."""

    graph = StateGraph(CaseTurnGraphState)
    node_builders = {
        "load_case_state": load_case_state_node,
        "version_conflict_gate": version_conflict_gate_node,
        "classify_turn_intent": classify_turn_intent_node,
        "build_turn_contract": build_turn_contract_node,
        "assemble_case_context": assemble_case_context_node,
        "route_turn_intent": route_turn_intent_node,
        "materials_guidance_node": materials_guidance_node,
        "case_status_summary_node": case_status_summary_node,
        "off_topic_reject_node": off_topic_reject_node,
        "correct_evidence_node": correct_evidence_node,
        "withdraw_evidence_node": withdraw_evidence_node,
        "recompute_case_analysis": recompute_case_analysis_node,
        "final_memo_gate": final_memo_gate_node,
        "build_candidate_evidence": build_candidate_evidence_node,
        "route_evidence_type": route_evidence_type_node,
        "p2p_process_fact_extractor": p2p_process_fact_extractor_node,
        "p2p_match_type_classifier": p2p_match_type_classifier_node,
        "p2p_sequence_anomaly_reviewer": p2p_sequence_anomaly_reviewer_node,
        "p2p_amount_consistency_reviewer": p2p_amount_consistency_reviewer_node,
        "p2p_exception_reviewer": p2p_exception_reviewer_node,
        "p2p_patch_proposal": p2p_patch_proposal_node,
        "p2p_process_patch_validator": p2p_process_patch_validator_node,
        "purchase_requisition_review_subgraph": purchase_requisition_review_subgraph_node,
        "expense_review_subgraph": expense_review_subgraph_node,
        "supplier_onboarding_review_subgraph": supplier_onboarding_review_subgraph_node,
        "contract_exception_review_subgraph": contract_exception_review_subgraph_node,
        "budget_exception_review_subgraph": budget_exception_review_subgraph_node,
        "generic_evidence_review_subgraph": generic_evidence_review_subgraph_node,
        "merge_review_outputs": merge_review_outputs_node,
        "evidence_sufficiency_gate": evidence_sufficiency_gate_node,
        "contradiction_gate": contradiction_gate_node,
        "control_matrix_gate": control_matrix_gate_node,
        "propose_case_patch": propose_case_patch_node,
        "validate_case_patch": validate_case_patch_node,
        "route_patch_validity": route_patch_validity_node,
        "persist_case_state_dossier_audit": persist_case_state_dossier_audit_node,
        "reject_patch_explain": reject_patch_explain_node,
        "respond_to_user": respond_to_user_node,
    }
    for node_name in CASE_TURN_GRAPH_NODES:
        graph.add_node(node_name, node_builders[node_name])

    graph.set_entry_point("load_case_state")
    graph.add_edge("load_case_state", "version_conflict_gate")
    graph.add_conditional_edges(
        "version_conflict_gate",
        _route_version_conflict,
        {"conflict": "reject_patch_explain", "continue": "classify_turn_intent"},
    )
    graph.add_edge("classify_turn_intent", "build_turn_contract")
    graph.add_edge("build_turn_contract", "assemble_case_context")
    graph.add_edge("assemble_case_context", "route_turn_intent")
    graph.add_conditional_edges(
        "route_turn_intent",
        _route_turn_intent,
        {
            "ask_required_materials": "materials_guidance_node",
            "ask_status": "case_status_summary_node",
            "off_topic": "off_topic_reject_node",
            "correct_previous_evidence": "correct_evidence_node",
            "withdraw_evidence": "withdraw_evidence_node",
            "request_final_memo": "final_memo_gate",
            "submit_evidence": "build_candidate_evidence",
            "create_case": "materials_guidance_node",
        },
    )
    graph.add_edge("materials_guidance_node", "propose_case_patch")
    graph.add_edge("case_status_summary_node", "propose_case_patch")
    graph.add_edge("off_topic_reject_node", "validate_case_patch")
    graph.add_edge("correct_evidence_node", "recompute_case_analysis")
    graph.add_edge("withdraw_evidence_node", "recompute_case_analysis")
    graph.add_edge("recompute_case_analysis", "propose_case_patch")
    graph.add_edge("final_memo_gate", "propose_case_patch")
    graph.add_edge("build_candidate_evidence", "route_evidence_type")
    graph.add_conditional_edges(
        "route_evidence_type",
        _route_evidence_type,
        {
            "p2p": "p2p_process_fact_extractor",
            "purchase_requisition": "purchase_requisition_review_subgraph",
            "expense": "expense_review_subgraph",
            "supplier_onboarding": "supplier_onboarding_review_subgraph",
            "contract_exception": "contract_exception_review_subgraph",
            "budget_exception": "budget_exception_review_subgraph",
            "generic": "generic_evidence_review_subgraph",
        },
    )
    graph.add_edge("p2p_process_fact_extractor", "p2p_match_type_classifier")
    graph.add_edge("p2p_match_type_classifier", "p2p_sequence_anomaly_reviewer")
    graph.add_edge("p2p_sequence_anomaly_reviewer", "p2p_amount_consistency_reviewer")
    graph.add_edge("p2p_amount_consistency_reviewer", "p2p_exception_reviewer")
    graph.add_edge("p2p_exception_reviewer", "p2p_patch_proposal")
    graph.add_edge("p2p_patch_proposal", "p2p_process_patch_validator")
    graph.add_edge("p2p_process_patch_validator", "merge_review_outputs")
    for branch_node in (
        "purchase_requisition_review_subgraph",
        "expense_review_subgraph",
        "supplier_onboarding_review_subgraph",
        "contract_exception_review_subgraph",
        "budget_exception_review_subgraph",
        "generic_evidence_review_subgraph",
    ):
        graph.add_edge(branch_node, "merge_review_outputs")
    graph.add_edge("merge_review_outputs", "evidence_sufficiency_gate")
    graph.add_edge("evidence_sufficiency_gate", "contradiction_gate")
    graph.add_edge("contradiction_gate", "control_matrix_gate")
    graph.add_edge("control_matrix_gate", "propose_case_patch")
    graph.add_edge("propose_case_patch", "validate_case_patch")
    graph.add_edge("validate_case_patch", "route_patch_validity")
    graph.add_conditional_edges(
        "route_patch_validity",
        _route_patch_validity,
        {"valid": "persist_case_state_dossier_audit", "invalid": "reject_patch_explain"},
    )
    graph.add_edge("persist_case_state_dossier_audit", "respond_to_user")
    graph.add_edge("reject_patch_explain", "respond_to_user")
    graph.add_edge("respond_to_user", END)
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
                "warnings": [],
                "branch_review_outputs": {},
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
            "intent": "ask_status",
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


def version_conflict_gate_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**state, "graph_steps": _steps(state, "version_conflict_gate")}


def classify_turn_intent_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    request = state["request"]
    intent = classify_case_turn(
        request.user_message,
        has_case=state.get("existing_state") is not None,
        has_evidence=bool(request.extra_evidence),
    )
    return {**state, "intent": intent, "graph_steps": _steps(state, "classify_turn_intent")}


def build_turn_contract_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**state, "contract": contract_for_state(state["case_state"]), "graph_steps": _steps(state, "build_turn_contract")}


def assemble_case_context_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    request = state["request"]
    case_state = state["case_state"]
    branch = _context_branch_for_intent(state["intent"])
    context_pack = harness.context_assembler.assemble_for_branch(case_state, state["contract"], request.user_message, branch=branch)
    events = list(state.get("audit_events", []))
    events.append(
        _event(
            state["turn_id"],
            case_state.case_id,
            "turn_received",
            state["now"],
            {"intent": state["intent"], "context_branch": branch, "context_pack": context_pack},
        )
    )
    return {
        **state,
        "branch": branch,
        "context_pack": context_pack,
        "audit_events": events,
        "graph_steps": _steps(state, "assemble_case_context"),
    }


def route_turn_intent_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**state, "graph_steps": _steps(state, "route_turn_intent")}


def materials_guidance_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = _review_without_new_evidence(state, branch="ask_required_materials")
    return {**state, "review": review, "provisional_review": review, "graph_steps": _steps(state, "materials_guidance_node")}


def case_status_summary_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = _review_without_new_evidence(state, branch="ask_status")
    return {**state, "review": review, "provisional_review": review, "graph_steps": _steps(state, "case_status_summary_node")}


def off_topic_reject_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    review = _review_without_new_evidence(state, branch="ask_status")
    patch = harness._build_patch(
        state=state["case_state"],
        turn_id=state["turn_id"],
        intent="off_topic",
        accepted=[],
        rejected=[],
        review=review,
        warnings=["This turn is unrelated to the current approval case and will not add accepted evidence."],
        created_new=False,
        model_decision=None,
        model_error="",
    )
    return {**state, "review": review, "provisional_review": review, "patch": patch, "graph_steps": _steps(state, "off_topic_reject_node")}


def correct_evidence_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {
        **state,
        "warnings": _unique(list(state.get("warnings", [])) + ["Correction requests are recorded as case review updates; prior accepted evidence is not deleted in this phase."]),
        "graph_steps": _steps(state, "correct_evidence_node"),
    }


def withdraw_evidence_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {
        **state,
        "warnings": _unique(list(state.get("warnings", [])) + ["Withdraw requests are recorded for review; evidence removal requires an explicit future withdrawal patch."]),
        "graph_steps": _steps(state, "withdraw_evidence_node"),
    }


def recompute_case_analysis_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = _review_without_new_evidence(state, branch="ask_status")
    return {**state, "review": review, "provisional_review": review, "graph_steps": _steps(state, "recompute_case_analysis")}


def final_memo_gate_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = _review_without_new_evidence(state, branch="final_memo")
    warnings = list(state.get("warnings", []))
    if not review.evidence_sufficiency.get("passed"):
        warnings.append("Final memo gate blocked approve-style wording because blocking evidence is still missing.")
    if not review.control_matrix.get("passed"):
        warnings.append("Final memo gate found control matrix gaps; reviewer memo must stay non-executing and evidence-first.")
    return {**state, "review": review, "provisional_review": review, "warnings": _unique(warnings), "graph_steps": _steps(state, "final_memo_gate")}


def build_candidate_evidence_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    request = state["request"]
    candidates = harness._candidate_evidence(request, state["case_state"], state["turn_id"], "submit_evidence")
    events = list(state.get("audit_events", []))
    if candidates:
        events.append(_event(state["turn_id"], state["case_state"].case_id, "candidate_evidence_built", state["now"], {"source_ids": [item.source_id for item in candidates]}))
    return {**state, "candidates": candidates, "audit_events": events, "graph_steps": _steps(state, "build_candidate_evidence")}


def route_evidence_type_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    branch = _evidence_branch(state)
    return {**state, "evidence_branch": branch, "graph_steps": _steps(state, "route_evidence_type")}


def p2p_process_fact_extractor_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = review_p2p_process_evidence(state.get("candidates", []))
    outputs = _branch_outputs(state)
    outputs["p2p_process_fact_extractor"] = p2p_process_fact_extractor(state.get("candidates", []))
    return {**state, "p2p_review": review, "branch_review_outputs": outputs, "graph_steps": _steps(state, "p2p_process_fact_extractor")}


def p2p_match_type_classifier_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = state.get("p2p_review") or review_p2p_process_evidence(state.get("candidates", []))
    outputs = _branch_outputs(state)
    outputs["p2p_match_type_classifier"] = {"match_type": p2p_match_type_classifier(state.get("candidates", []))}
    return {**state, "p2p_review": review, "branch_review_outputs": outputs, "graph_steps": _steps(state, "p2p_match_type_classifier")}


def p2p_sequence_anomaly_reviewer_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = state.get("p2p_review") or review_p2p_process_evidence(state.get("candidates", []))
    outputs = _branch_outputs(state)
    outputs["p2p_sequence_anomaly_reviewer"] = {"sequence_anomalies": p2p_sequence_anomaly_reviewer(state.get("candidates", []))}
    return {**state, "p2p_review": review, "branch_review_outputs": outputs, "graph_steps": _steps(state, "p2p_sequence_anomaly_reviewer")}


def p2p_amount_consistency_reviewer_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = state.get("p2p_review") or review_p2p_process_evidence(state.get("candidates", []))
    outputs = _branch_outputs(state)
    outputs["p2p_amount_consistency_reviewer"] = {"amount_facts": p2p_amount_consistency_reviewer(state.get("candidates", [])).model_dump()}
    return {**state, "p2p_review": review, "branch_review_outputs": outputs, "graph_steps": _steps(state, "p2p_amount_consistency_reviewer")}


def p2p_exception_reviewer_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = state.get("p2p_review") or review_p2p_process_evidence(state.get("candidates", []))
    outputs = _branch_outputs(state)
    outputs["p2p_exception_reviewer"] = {"process_exceptions": p2p_exception_reviewer(state.get("candidates", []))}
    return {**state, "p2p_review": review, "branch_review_outputs": outputs, "graph_steps": _steps(state, "p2p_exception_reviewer")}


def p2p_patch_proposal_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review_state = _run_evidence_branch_review(state, branch="p2p_process_review")
    p2p_review = review_state.get("p2p_review") or review_p2p_process_evidence(review_state.get("candidates", []))
    warnings = _unique(list(review_state.get("warnings", [])) + p2p_review.p2p_reviewer_notes + p2p_review.p2p_next_questions)
    outputs = _branch_outputs(review_state)
    outputs["p2p_patch_proposal"] = {
        "p2p_review": p2p_review.model_dump(),
        "reviewer_notes": render_p2p_review_notes(p2p_review),
    }
    return {
        **review_state,
        "p2p_review": p2p_review,
        "warnings": warnings,
        "branch_review_outputs": outputs,
        "graph_steps": _steps(review_state, "p2p_patch_proposal"),
    }


def p2p_process_patch_validator_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    p2p_review = state.get("p2p_review") or review_p2p_process_evidence(state.get("candidates", []))
    warnings = list(state.get("warnings", []))
    if p2p_review.missing_process_evidence:
        warnings.append("P2P process evidence is incomplete: " + ", ".join(p2p_review.missing_process_evidence))
    if p2p_review.process_exceptions:
        warnings.append("P2P process exceptions require reviewer attention before any approve-style memo.")
    return {**state, "warnings": _unique(warnings), "p2p_review": p2p_review, "graph_steps": _steps(state, "p2p_process_patch_validator")}


def purchase_requisition_review_subgraph_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**_run_evidence_branch_review(state, branch="purchase_requisition_review"), "graph_steps": _steps(state, "purchase_requisition_review_subgraph")}


def expense_review_subgraph_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**_run_evidence_branch_review(state, branch="expense_review"), "graph_steps": _steps(state, "expense_review_subgraph")}


def supplier_onboarding_review_subgraph_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**_run_evidence_branch_review(state, branch="supplier_onboarding_review"), "graph_steps": _steps(state, "supplier_onboarding_review_subgraph")}


def contract_exception_review_subgraph_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**_run_evidence_branch_review(state, branch="contract_exception_review"), "graph_steps": _steps(state, "contract_exception_review_subgraph")}


def budget_exception_review_subgraph_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**_run_evidence_branch_review(state, branch="budget_exception_review"), "graph_steps": _steps(state, "budget_exception_review_subgraph")}


def generic_evidence_review_subgraph_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**_run_evidence_branch_review(state, branch="generic_evidence_review"), "graph_steps": _steps(state, "generic_evidence_review_subgraph")}


def merge_review_outputs_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    outputs = _branch_outputs(state)
    if state.get("model_decision") is not None:
        outputs["stage_model_roles"] = state["model_decision"].to_patch_metadata(used=True, error=state.get("model_error", ""))
    return {**state, "branch_review_outputs": outputs, "graph_steps": _steps(state, "merge_review_outputs")}


def evidence_sufficiency_gate_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = state.get("review") or state.get("provisional_review") or _review_without_new_evidence(state, branch="ask_status")
    warnings = list(state.get("warnings", []))
    if not review.evidence_sufficiency.get("passed"):
        warnings.extend(str(item) for item in review.evidence_sufficiency.get("blocking_gaps") or [])
    return {**state, "review": review, "warnings": _unique(warnings), "graph_steps": _steps(state, "evidence_sufficiency_gate")}


def contradiction_gate_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = state.get("review") or state.get("provisional_review") or _review_without_new_evidence(state, branch="ask_status")
    warnings = list(state.get("warnings", []))
    contradictions = review.contradictions or {}
    if contradictions.get("has_conflict"):
        warnings.append("Contradiction gate found conflicting evidence; approve-style recommendation is not allowed.")
    return {**state, "review": review, "warnings": _unique(warnings), "graph_steps": _steps(state, "contradiction_gate")}


def control_matrix_gate_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = state.get("review") or state.get("provisional_review") or _review_without_new_evidence(state, branch="ask_status")
    warnings = list(state.get("warnings", []))
    if not review.control_matrix.get("passed"):
        warnings.append("Control matrix gate found missing/failing controls; continue evidence collection or escalate.")
    return {**state, "review": review, "warnings": _unique(warnings), "graph_steps": _steps(state, "control_matrix_gate")}


def propose_case_patch_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    review = state.get("review") or state.get("provisional_review") or _review_without_new_evidence(state, branch=state.get("branch", "ask_status"))
    intent = harness._intent_from_stage_model(state["intent"], state.get("model_decision"), state["contract"])
    accepted, rejected, warnings = harness._review_candidate_evidence(state.get("candidates", []), review, state["now"])
    accepted, rejected, warnings = harness._apply_stage_model_decision(
        candidates=state.get("candidates", []),
        accepted=accepted,
        rejected=rejected,
        warnings=_unique(list(state.get("warnings", [])) + warnings),
        decision=state.get("model_decision"),
        now=state["now"],
    )
    final_review = review if accepted else harness._review(state["case_state"], state["request"].user_message, [])
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
    if state.get("branch_review_outputs"):
        model_review = dict(patch.model_review or {})
        model_review["branch_review_outputs"] = state["branch_review_outputs"]
        if state.get("p2p_review") is not None:
            model_review["p2p_review"] = state["p2p_review"].model_dump()
        patch = patch.model_copy(update={"model_review": model_review})
    return {
        **state,
        "intent": intent,
        "accepted": accepted,
        "rejected": rejected,
        "warnings": warnings,
        "review": final_review,
        "patch": patch,
        "graph_steps": _steps(state, "propose_case_patch"),
    }


def validate_case_patch_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    patch = harness.validator.validate(state["case_state"], state["patch"], state["contract"], review=state["review"])
    return {**state, "patch": patch, "graph_steps": _steps(state, "validate_case_patch")}


def route_patch_validity_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return {**state, "graph_steps": _steps(state, "route_patch_validity")}


def persist_case_state_dossier_audit_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    request = state["request"]
    case_state = state["case_state"]
    patch = state["patch"]
    review = state["review"]
    now = state["now"]
    turn_id = state["turn_id"]
    events = list(state.get("audit_events", []))
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
                    "role_outputs": list((model_decision.role_outputs or {}).keys()),
                    "error": state.get("model_error", ""),
                },
            )
        )

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
    for event in events:
        harness.store.append_audit_event(event)
    return {
        **state,
        "case_state": case_state,
        "dossier": dossier,
        "audit_events": events,
        "graph_steps": _steps(state, "persist_case_state_dossier_audit"),
    }


def reject_patch_explain_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    case_state = state["case_state"]
    review = state.get("review") or state.get("provisional_review") or _review_without_new_evidence(state, branch="ask_status")
    patch = state["patch"]
    events = list(state.get("audit_events", []))
    events.append(_event(state["turn_id"], case_state.case_id, "case_patch_rejected", state["now"], {"warnings": patch.warnings, "allowed_to_apply": patch.allowed_to_apply}))
    dossier = harness.store.read_dossier(case_state.case_id) or render_case_dossier(case_state, review, patch)
    for event in events:
        harness.store.append_audit_event(event)
    return {
        **state,
        "review": review,
        "dossier": dossier,
        "audit_events": events,
        "graph_steps": _steps(state, "reject_patch_explain"),
    }


def respond_to_user_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
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
    return {**state, "response": response, "graph_steps": _steps(state, "respond_to_user")}


def _route_version_conflict(state: CaseTurnGraphState) -> str:
    return "conflict" if state.get("conflict") else "continue"


def _route_turn_intent(state: CaseTurnGraphState) -> str:
    intent = state.get("intent", "ask_status")
    return intent if intent in {"ask_required_materials", "ask_status", "off_topic", "correct_previous_evidence", "withdraw_evidence", "request_final_memo", "submit_evidence", "create_case"} else "ask_status"


def _route_evidence_type(state: CaseTurnGraphState) -> str:
    branch = state.get("evidence_branch") or _evidence_branch(state)
    if branch == "p2p":
        return "p2p"
    if branch in {"purchase_requisition", "expense", "supplier_onboarding", "contract_exception", "budget_exception"}:
        return branch
    return "generic"


def _route_patch_validity(state: CaseTurnGraphState) -> str:
    return "valid" if state["patch"].allowed_to_apply else "invalid"


def _context_branch_for_intent(intent: str) -> str:
    if intent in {"ask_required_materials", "ask_status"}:
        return intent
    if intent == "request_final_memo":
        return "final_memo"
    if intent == "submit_evidence":
        return "submit_evidence"
    return "generic_case_turn"


def _evidence_branch(state: CaseTurnGraphState) -> str:
    record_types = {str(getattr(item, "record_type", "") or "").strip().lower() for item in state.get("candidates", [])}
    if record_types.intersection(P2P_RECORD_TYPES):
        return "p2p"
    approval_type = str(state["case_state"].approval_type or "").strip()
    if approval_type in {"purchase_requisition", "expense", "supplier_onboarding", "contract_exception", "budget_exception"}:
        return approval_type
    if record_types.intersection({"approval_request", "quote", "budget", "vendor"}):
        return "purchase_requisition"
    if record_types.intersection({"receipt", "expense_claim"}):
        return "expense"
    if record_types.intersection({"bank_info", "tax_info", "sanctions_check"}):
        return "supplier_onboarding"
    if record_types.intersection({"contract", "redline", "legal_policy"}):
        return "contract_exception"
    if record_types.intersection({"finance_policy", "budget_exception"}):
        return "budget_exception"
    return "generic"


def _review_without_new_evidence(state: CaseTurnGraphState, *, branch: str):
    state["harness"].context_assembler.assemble_for_branch(state["case_state"], state["contract"], state["request"].user_message, branch=branch)
    return state["harness"]._review(state["case_state"], state["request"].user_message, [])


def _run_evidence_branch_review(state: CaseTurnGraphState, *, branch: str) -> CaseTurnGraphState:
    harness = state["harness"]
    candidates = state.get("candidates", [])
    context_pack = harness.context_assembler.assemble_for_branch(state["case_state"], state["contract"], state["request"].user_message, branch=branch)
    provisional_review = harness._review(state["case_state"], state["request"].user_message, candidates)
    model_decision, model_error = harness._review_with_stage_model(
        context_pack=context_pack,
        candidates=candidates,
        review=provisional_review,
        deterministic_intent="submit_evidence",
    )
    outputs = _branch_outputs(state)
    outputs[branch] = {
        "candidate_source_ids": [item.source_id for item in candidates],
        "stage_model_used": model_decision is not None,
        "model_error": model_error,
    }
    return {
        **state,
        "branch": branch,
        "context_pack": context_pack,
        "provisional_review": provisional_review,
        "review": provisional_review,
        "model_decision": model_decision,
        "model_error": model_error,
        "branch_review_outputs": outputs,
    }


def _branch_outputs(state: CaseTurnGraphState) -> dict[str, Any]:
    return dict(state.get("branch_review_outputs", {}) or {})


def _steps(state: CaseTurnGraphState, step: str) -> list[str]:
    return list(state.get("graph_steps", [])) + [step]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
