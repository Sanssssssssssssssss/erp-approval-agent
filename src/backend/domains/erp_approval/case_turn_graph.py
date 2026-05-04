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
from src.backend.domains.erp_approval.policy_guidance import (
    build_policy_guidance,
    render_materials_guidance,
    render_policy_failures,
)

CASE_TURN_GRAPH_NAME = "erp_approval_dynamic_case_turn_graph"
CASE_TURN_GRAPH_NODES: tuple[str, ...] = (
    "load_case_state",
    "version_conflict_gate",
    "classify_turn_intent",
    "build_turn_contract",
    "assemble_case_context",
    "llm_turn_classifier",
    "deterministic_classifier_guard",
    "route_turn_intent",
    "materials_guidance_node",
    "case_status_summary_node",
    "policy_failure_explain_node",
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
    "p2p_process_fact_explanation",
    "p2p_sequence_risk_explanation",
    "p2p_amount_reconciliation_explanation",
    "p2p_missing_evidence_questions",
    "p2p_patch_proposal",
    "p2p_process_patch_validator",
    "purchase_requisition_review_subgraph",
    "expense_review_subgraph",
    "supplier_onboarding_review_subgraph",
    "contract_exception_review_subgraph",
    "budget_exception_review_subgraph",
    "generic_evidence_review_subgraph",
    "llm_evidence_extractor",
    "llm_policy_interpreter",
    "llm_contradiction_reviewer",
    "llm_reviewer_memo",
    "aggregate_llm_stage_outputs",
    "merge_review_outputs",
    "evidence_sufficiency_gate",
    "contradiction_gate",
    "control_matrix_gate",
    "propose_case_patch",
    "validate_case_patch",
    "route_patch_validity",
    "read_only_case_response",
    "append_audit_only",
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
    read_only_turn: bool
    deterministic_intent: str
    client_intent: str
    classifier_guard_intent: str
    p2p_review: P2PProcessReview
    branch_review_outputs: dict[str, Any]
    stage_model_payload: dict[str, Any]
    stage_model_role_outputs: dict[str, dict[str, Any]]
    stage_model_role_errors: dict[str, str]
    p2p_llm_explanations: dict[str, Any]


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
        "llm_turn_classifier": llm_turn_classifier_node,
        "deterministic_classifier_guard": deterministic_classifier_guard_node,
        "route_turn_intent": route_turn_intent_node,
        "materials_guidance_node": materials_guidance_node,
        "case_status_summary_node": case_status_summary_node,
        "policy_failure_explain_node": policy_failure_explain_node,
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
        "p2p_process_fact_explanation": p2p_process_fact_explanation_node,
        "p2p_sequence_risk_explanation": p2p_sequence_risk_explanation_node,
        "p2p_amount_reconciliation_explanation": p2p_amount_reconciliation_explanation_node,
        "p2p_missing_evidence_questions": p2p_missing_evidence_questions_node,
        "p2p_patch_proposal": p2p_patch_proposal_node,
        "p2p_process_patch_validator": p2p_process_patch_validator_node,
        "purchase_requisition_review_subgraph": purchase_requisition_review_subgraph_node,
        "expense_review_subgraph": expense_review_subgraph_node,
        "supplier_onboarding_review_subgraph": supplier_onboarding_review_subgraph_node,
        "contract_exception_review_subgraph": contract_exception_review_subgraph_node,
        "budget_exception_review_subgraph": budget_exception_review_subgraph_node,
        "generic_evidence_review_subgraph": generic_evidence_review_subgraph_node,
        "llm_evidence_extractor": llm_evidence_extractor_node,
        "llm_policy_interpreter": llm_policy_interpreter_node,
        "llm_contradiction_reviewer": llm_contradiction_reviewer_node,
        "llm_reviewer_memo": llm_reviewer_memo_node,
        "aggregate_llm_stage_outputs": aggregate_llm_stage_outputs_node,
        "merge_review_outputs": merge_review_outputs_node,
        "evidence_sufficiency_gate": evidence_sufficiency_gate_node,
        "contradiction_gate": contradiction_gate_node,
        "control_matrix_gate": control_matrix_gate_node,
        "propose_case_patch": propose_case_patch_node,
        "validate_case_patch": validate_case_patch_node,
        "route_patch_validity": route_patch_validity_node,
        "read_only_case_response": read_only_case_response_node,
        "append_audit_only": append_audit_only_node,
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
    graph.add_edge("assemble_case_context", "llm_turn_classifier")
    graph.add_edge("llm_turn_classifier", "deterministic_classifier_guard")
    graph.add_edge("deterministic_classifier_guard", "route_turn_intent")
    graph.add_conditional_edges(
        "route_turn_intent",
        _route_turn_intent,
        {
            "ask_how_to_prepare": "materials_guidance_node",
            "ask_missing_requirements": "case_status_summary_node",
            "ask_policy_failure": "policy_failure_explain_node",
            "ask_required_materials": "materials_guidance_node",
            "ask_status": "case_status_summary_node",
            "off_topic": "off_topic_reject_node",
            "correct_previous_evidence": "correct_evidence_node",
            "withdraw_evidence": "withdraw_evidence_node",
            "request_final_memo": "final_memo_gate",
            "request_final_review": "final_memo_gate",
            "submit_evidence": "build_candidate_evidence",
            "create_case": "materials_guidance_node",
        },
    )
    graph.add_conditional_edges(
        "materials_guidance_node",
        _route_guidance_persistence,
        {"mutable": "propose_case_patch", "read_only": "read_only_case_response"},
    )
    graph.add_edge("case_status_summary_node", "read_only_case_response")
    graph.add_edge("policy_failure_explain_node", "read_only_case_response")
    graph.add_edge("off_topic_reject_node", "read_only_case_response")
    graph.add_edge("correct_evidence_node", "recompute_case_analysis")
    graph.add_edge("withdraw_evidence_node", "recompute_case_analysis")
    graph.add_edge("recompute_case_analysis", "read_only_case_response")
    graph.add_edge("final_memo_gate", "merge_review_outputs")
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
    graph.add_edge("p2p_exception_reviewer", "p2p_process_fact_explanation")
    graph.add_edge("p2p_process_fact_explanation", "p2p_sequence_risk_explanation")
    graph.add_edge("p2p_sequence_risk_explanation", "p2p_amount_reconciliation_explanation")
    graph.add_edge("p2p_amount_reconciliation_explanation", "p2p_missing_evidence_questions")
    graph.add_edge("p2p_missing_evidence_questions", "p2p_patch_proposal")
    graph.add_edge("p2p_patch_proposal", "p2p_process_patch_validator")
    graph.add_edge("p2p_process_patch_validator", "llm_evidence_extractor")
    for branch_node in (
        "purchase_requisition_review_subgraph",
        "expense_review_subgraph",
        "supplier_onboarding_review_subgraph",
        "contract_exception_review_subgraph",
        "budget_exception_review_subgraph",
        "generic_evidence_review_subgraph",
    ):
        graph.add_edge(branch_node, "llm_evidence_extractor")
    graph.add_edge("llm_evidence_extractor", "llm_policy_interpreter")
    graph.add_edge("llm_policy_interpreter", "llm_contradiction_reviewer")
    graph.add_edge("llm_contradiction_reviewer", "llm_reviewer_memo")
    graph.add_edge("llm_reviewer_memo", "aggregate_llm_stage_outputs")
    graph.add_edge("aggregate_llm_stage_outputs", "merge_review_outputs")
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
    graph.add_edge("read_only_case_response", "append_audit_only")
    graph.add_edge("append_audit_only", "respond_to_user")
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
                "stage_model_role_outputs": {},
                "stage_model_role_errors": {},
                "p2p_llm_explanations": {},
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
    deterministic_intent = classify_case_turn(
        request.user_message,
        has_case=state.get("existing_state") is not None,
        has_evidence=bool(request.extra_evidence),
    )
    client_intent, client_warnings = _guarded_client_intent(state, deterministic_intent)
    intent = client_intent or deterministic_intent
    return {
        **state,
        "intent": intent,
        "deterministic_intent": deterministic_intent,
        "client_intent": client_intent,
        "warnings": _unique(list(state.get("warnings", [])) + client_warnings),
        "graph_steps": _steps(state, "classify_turn_intent"),
    }


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
            {
                "intent": state["intent"],
                "deterministic_intent": state.get("deterministic_intent", state["intent"]),
                "client_intent": state.get("client_intent", ""),
                "context_branch": branch,
                "context_summary": _context_pack_summary(context_pack),
            },
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
    review = _review_without_new_evidence(state, branch="ask_how_to_prepare")
    guidance = build_policy_guidance(state["case_state"])
    model_output = _run_custom_stage_model_role(
        state,
        role_name="policy_guidance",
        system_prompt=(
            "Role: policy/RAG materials guidance specialist. Use the local requirement matrix and policy guidance payload "
            "to decide what materials the user must prepare. Return JSON only: "
            '{"rendered_guidance":"中文材料清单，逐项包含材料、blocking、制度条款、可接受证据、不接受证据、下一步",'
            '"warnings":[],"confidence":0.0,"non_action_statement":"This is a local approval case state update. No ERP write action was executed."} '
            "Do not create a case, do not make an approval recommendation, and do not execute ERP actions."
        ),
        payload={
            "turn_intent": state.get("intent", "ask_how_to_prepare"),
            "user_message": state["request"].user_message,
            "case_summary": (state.get("context_pack") or {}).get("case_summary", {}),
            "policy_guidance": guidance,
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        },
    )
    rendered_guidance = str(model_output.get("rendered_guidance") or "").strip() or render_materials_guidance(guidance)
    patch = state["harness"]._build_patch(
        state=state["case_state"],
        turn_id=state["turn_id"],
        intent=state.get("intent", "ask_how_to_prepare"),
        accepted=[],
        rejected=[],
        review=review,
        warnings=list(state.get("warnings", [])),
        created_new=state.get("existing_state") is None and state.get("intent") == "create_case",
        model_decision=None,
        model_error="",
    )
    model_review = dict(patch.model_review or {})
    model_review["used"] = bool(model_output.get("used"))
    model_review["policy_rag"] = {
        "used": bool(model_output.get("used")),
        "model_status": model_output.get("status", "executed" if model_output.get("used") else "skipped"),
        "guidance": guidance,
        "role_output": model_output,
        "rendered_guidance": rendered_guidance,
    }
    patch = patch.model_copy(update={"model_review": model_review})
    return {
        **state,
        "review": review,
        "provisional_review": review,
        "patch": patch,
        "graph_steps": _steps(state, "materials_guidance_node"),
    }


def case_status_summary_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = _review_without_new_evidence(state, branch="ask_missing_requirements")
    model_output = _run_custom_stage_model_role(
        state,
        role_name="missing_requirements_answer",
        system_prompt=(
            "Role: missing requirements explainer. Read only persisted case_state, evidence_sufficiency, control_matrix, "
            "and policy_failures. Return JSON only: "
            '{"rendered":"中文当前缺口说明，必须区分blocking缺口、policy failure、下一步补证问题",'
            '"warnings":[],"confidence":0.0,"non_action_statement":"This is a local approval case state update. No ERP write action was executed."}'
        ),
        payload={
            "case_state": state["case_state"].model_dump(),
            "evidence_sufficiency": review.evidence_sufficiency,
            "control_matrix": review.control_matrix,
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        },
    )
    patch = state["harness"]._build_patch(
        state=state["case_state"],
        turn_id=state["turn_id"],
        intent="ask_missing_requirements",
        accepted=[],
        rejected=[],
        review=review,
        warnings=list(state.get("warnings", [])),
        created_new=False,
        model_decision=None,
        model_error="",
    )
    fallback_rendered = _render_missing_requirements_answer(state, review)
    model_review = dict(patch.model_review or {})
    model_review["used"] = bool(model_output.get("used"))
    model_review["missing_requirements_answer"] = {
        "used": bool(model_output.get("used")),
        "model_status": model_output.get("status", "executed" if model_output.get("used") else "skipped"),
        "role_output": model_output,
        "rendered": str(model_output.get("rendered") or "").strip() or fallback_rendered,
    }
    patch = patch.model_copy(update={"model_review": model_review})
    return {**state, "review": review, "provisional_review": review, "patch": patch, "graph_steps": _steps(state, "case_status_summary_node")}


def policy_failure_explain_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review = _review_without_new_evidence(state, branch="ask_policy_failure")
    fallback_rendered = render_policy_failures(state["case_state"].policy_failures)
    model_output = _run_custom_stage_model_role(
        state,
        role_name="policy_failure_explainer",
        system_prompt=(
            "Role: policy failure explainer. Use only case_state.policy_failures and rejected_evidence. "
            "Do not invent new failures. Return JSON only: "
            '{"rendered":"中文解释材料为什么不符合制度、对应条款、如何修正",'
            '"warnings":[],"confidence":0.0,"non_action_statement":"This is a local approval case state update. No ERP write action was executed."}'
        ),
        payload={
            "policy_failures": [item.model_dump() for item in state["case_state"].policy_failures],
            "rejected_evidence": [item.model_dump() for item in state["case_state"].rejected_evidence],
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        },
    )
    patch = state["harness"]._build_patch(
        state=state["case_state"],
        turn_id=state["turn_id"],
        intent="ask_policy_failure",
        accepted=[],
        rejected=[],
        review=review,
        warnings=list(state.get("warnings", [])),
        created_new=False,
        model_decision=None,
        model_error="",
    )
    model_review = dict(patch.model_review or {})
    model_review["used"] = bool(model_output.get("used"))
    model_review["policy_failures_answer"] = {
        "used": bool(model_output.get("used")),
        "model_status": model_output.get("status", "executed" if model_output.get("used") else "skipped"),
        "source": "case_state.policy_failures",
        "role_output": model_output,
        "rendered": str(model_output.get("rendered") or "").strip() or fallback_rendered,
    }
    patch = patch.model_copy(update={"model_review": model_review})
    return {
        **state,
        "review": review,
        "provisional_review": review,
        "patch": patch,
        "graph_steps": _steps(state, "policy_failure_explain_node"),
    }


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


def p2p_process_fact_explanation_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _p2p_explanation_node(
        state,
        "p2p_process_fact_explanation",
        "Explain the P2P process facts from the candidate evidence. Return JSON with explanation, source_ids, warnings, and non_action_statement. Do not infer facts without source_id.",
    )


def p2p_sequence_risk_explanation_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _p2p_explanation_node(
        state,
        "p2p_sequence_risk_explanation",
        "Explain sequence risk for invoice/PO/GRN/process-log evidence. Clear Invoice must be described as a historical event only, not an executable payment authorization. Return JSON.",
    )


def p2p_amount_reconciliation_explanation_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _p2p_explanation_node(
        state,
        "p2p_amount_reconciliation_explanation",
        "Explain PO, invoice, goods receipt, and cumulative amount reconciliation risks. Return JSON with amount_explanation, source_ids, warnings, and non_action_statement.",
    )


def p2p_missing_evidence_questions_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _p2p_explanation_node(
        state,
        "p2p_missing_evidence_questions",
        "Draft missing P2P evidence questions from the current deterministic P2P review. Return JSON with questions, source_ids, warnings, and non_action_statement.",
    )


def p2p_patch_proposal_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    review_state = _run_evidence_branch_review(state, branch="p2p_process_review")
    p2p_review = review_state.get("p2p_review") or review_p2p_process_evidence(review_state.get("candidates", []))
    llm_explanations = dict(review_state.get("p2p_llm_explanations", {}) or {})
    llm_warnings = [
        warning
        for output in llm_explanations.values()
        if isinstance(output, dict)
        for warning in output.get("warnings", []) or []
    ]
    warnings = _unique(list(review_state.get("warnings", [])) + p2p_review.p2p_reviewer_notes + p2p_review.p2p_next_questions + llm_warnings)
    outputs = _branch_outputs(review_state)
    outputs["p2p_patch_proposal"] = {
        "p2p_review": p2p_review.model_dump(),
        "llm_explanations": llm_explanations,
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
    valid_match_types = {"three_way_invoice_after_gr", "three_way_invoice_before_gr", "two_way", "consignment", "unknown"}
    if p2p_review.match_type not in valid_match_types:
        warnings.append(f"P2P match_type {p2p_review.match_type} is outside the allowed enum.")
    if p2p_review.missing_process_evidence:
        warnings.append("P2P process evidence is incomplete: " + ", ".join(p2p_review.missing_process_evidence))
    if p2p_review.process_exceptions:
        warnings.append("P2P process exceptions require reviewer attention before any approve-style memo.")
    if "clear_invoice_historical_only" in p2p_review.sequence_anomalies:
        warnings.append("Clear Invoice is a historical event only; it cannot authorize payment or any ERP write action.")
    if p2p_review.amount_facts.amount_variation_risk in {"medium", "high", "needs_reconciliation", "unknown"}:
        warnings.append(f"P2P amount facts require reconciliation; risk={p2p_review.amount_facts.amount_variation_risk}.")
    known_source_ids = {str(getattr(item, "source_id", "") or "") for item in state.get("candidates", [])}
    if any(source_id and source_id not in known_source_ids for source_id in p2p_review.source_ids):
        warnings.append("P2P review referenced a source_id outside current candidate evidence.")
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


def llm_turn_classifier_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _llm_stage_role_node(state, "turn_classifier", "llm_turn_classifier")


def deterministic_classifier_guard_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    deterministic_intent = state.get("deterministic_intent", state.get("intent", "ask_status"))
    baseline_intent = state.get("intent", deterministic_intent)
    outputs = dict(state.get("stage_model_role_outputs", {}) or {})
    role_output = outputs.get("turn_classifier", {}) or {}
    warnings = list(state.get("warnings", []))
    guarded_intent = baseline_intent
    candidate_intent = _canonical_intent(str(role_output.get("turn_intent") or "").strip())

    if candidate_intent and not role_output.get("skipped"):
        allowed = set(getattr(state["contract"], "allowed_intents", []) or [])
        if candidate_intent in allowed and _classifier_override_allowed(state, baseline_intent, candidate_intent):
            guarded_intent = candidate_intent
        elif candidate_intent != baseline_intent:
            warnings.append(
                f"LLM turn classifier proposed {candidate_intent}, but deterministic guard kept {baseline_intent}."
            )

    if guarded_intent != baseline_intent:
        state = {**state, "intent": guarded_intent, "branch": _context_branch_for_intent(guarded_intent)}
    return {
        **state,
        "deterministic_intent": deterministic_intent,
        "classifier_guard_intent": guarded_intent,
        "warnings": _unique(warnings),
        "graph_steps": _steps(state, "deterministic_classifier_guard"),
    }


def llm_evidence_extractor_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _llm_stage_role_node(state, "evidence_extractor", "llm_evidence_extractor")


def llm_policy_interpreter_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _llm_stage_role_node(state, "policy_interpreter", "llm_policy_interpreter")


def llm_contradiction_reviewer_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _llm_stage_role_node(state, "contradiction_reviewer", "llm_contradiction_reviewer")


def llm_reviewer_memo_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    return _llm_stage_role_node(state, "reviewer_memo", "llm_reviewer_memo")


def aggregate_llm_stage_outputs_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    outputs = dict(state.get("stage_model_role_outputs", {}) or {})
    errors = dict(state.get("stage_model_role_errors", {}) or {})
    if harness.stage_model is None:
        return {
            **state,
            "model_decision": None,
            "model_error": "",
            "graph_steps": _steps(state, "aggregate_llm_stage_outputs"),
        }
    decision = harness.stage_model.aggregate_role_outputs(
        outputs,
        deterministic_intent=state.get("intent", "submit_evidence"),
        warnings=[f"{role} 未返回可用结构化结果：{error}" for role, error in errors.items() if error],
    )
    return {
        **state,
        "model_decision": decision,
        "model_error": "; ".join(f"{role}: {error}" for role, error in errors.items() if error),
        "graph_steps": _steps(state, "aggregate_llm_stage_outputs"),
    }


def merge_review_outputs_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    outputs = _branch_outputs(state)
    if state.get("model_decision") is not None:
        outputs["stage_model_roles"] = state["model_decision"].to_patch_metadata(used=True, error=state.get("model_error", ""))
    elif state.get("stage_model_role_outputs"):
        outputs["stage_model_roles"] = {
            "used": False,
            "role_outputs": state.get("stage_model_role_outputs", {}),
            "role_errors": state.get("stage_model_role_errors", {}),
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        }
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


def read_only_case_response_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    review = state.get("review") or state.get("provisional_review") or _review_without_new_evidence(state, branch=state.get("branch", "ask_status"))
    patch = state.get("patch")
    if patch is None:
        patch = harness._build_patch(
            state=state["case_state"],
            turn_id=state["turn_id"],
            intent=state.get("intent", "ask_status"),
            accepted=[],
            rejected=[],
            review=review,
            warnings=list(state.get("warnings", [])),
            created_new=False,
            model_decision=None,
            model_error=state.get("model_error", ""),
        )
    patch = harness.validator.validate(state["case_state"], patch, state["contract"], review=review)
    dossier = harness.store.read_dossier(state["case_state"].case_id) or render_case_dossier(state["case_state"], review, patch)
    return {
        **state,
        "review": review,
        "patch": patch,
        "dossier": dossier,
        "read_only_turn": True,
        "graph_steps": _steps(state, "read_only_case_response"),
    }


def append_audit_only_node(state: CaseTurnGraphState) -> CaseTurnGraphState:
    harness = state["harness"]
    case_state = state["case_state"]
    event_name = "case_read_only_turn"
    if state.get("intent") == "off_topic":
        event_name = "off_topic_rejected"
    elif state.get("intent") in {"correct_previous_evidence", "withdraw_evidence"}:
        event_name = "case_revision_request_recorded"
    events = list(state.get("audit_events", []))
    events.append(
        _event(
            state["turn_id"],
            case_state.case_id,
            event_name,
            state["now"],
            {
                "intent": state.get("intent", "ask_status"),
                "patch_type": state["patch"].patch_type,
                "state_mutated": False,
                "dossier_mutated": False,
            },
        )
    )
    if not (state.get("existing_state") is None and state.get("intent") in {"ask_how_to_prepare", "ask_required_materials"}):
        for event in events:
            harness.store.append_audit_event(event)
    return {
        **state,
        "audit_events": events,
        "graph_steps": _steps(state, "append_audit_only"),
    }


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
    operation_scope = "read_only_case_turn" if state.get("read_only_turn") else "persistent_case_turn"
    if state.get("conflict"):
        operation_scope = "persistent_case_turn_conflict"
    response = CaseTurnResponse(
        case_state=case_state,
        contract=contract_for_state(case_state),
        patch=state["patch"],
        review=state["review"],
        dossier=state["dossier"],
        audit_events=state.get("audit_events", []),
        storage_paths=state["harness"].store.paths_for(case_state.case_id),
        operation_scope=operation_scope,
        non_action_statement=CASE_HARNESS_NON_ACTION_STATEMENT,
    )
    return {**state, "response": response, "graph_steps": _steps(state, "respond_to_user")}


def _route_version_conflict(state: CaseTurnGraphState) -> str:
    return "conflict" if state.get("conflict") else "continue"


def _route_turn_intent(state: CaseTurnGraphState) -> str:
    intent = state.get("intent", "ask_status")
    return intent if intent in {
        "ask_how_to_prepare",
        "ask_missing_requirements",
        "ask_policy_failure",
        "ask_required_materials",
        "ask_status",
        "off_topic",
        "correct_previous_evidence",
        "withdraw_evidence",
        "request_final_memo",
        "request_final_review",
        "submit_evidence",
        "create_case",
    } else "ask_missing_requirements"


def _route_guidance_persistence(state: CaseTurnGraphState) -> str:
    if state.get("intent") == "create_case":
        return "mutable"
    return "read_only"


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
    if intent in {"ask_how_to_prepare", "ask_required_materials"}:
        return "ask_how_to_prepare"
    if intent in {"ask_missing_requirements", "ask_status"}:
        return "ask_missing_requirements"
    if intent == "ask_policy_failure":
        return "ask_policy_failure"
    if intent in {"request_final_memo", "request_final_review"}:
        return "final_memo"
    if intent == "submit_evidence":
        return "submit_evidence"
    return "generic_case_turn"


def _guarded_client_intent(state: CaseTurnGraphState, deterministic_intent: str) -> tuple[str, list[str]]:
    request = state["request"]
    requested = _canonical_intent(str(getattr(request, "client_intent", "") or "").strip())
    if not requested:
        return "", []
    allowed_intents = {
        "create_case",
        "ask_how_to_prepare",
        "ask_missing_requirements",
        "ask_policy_failure",
        "ask_required_materials",
        "submit_evidence",
        "correct_previous_evidence",
        "withdraw_evidence",
        "ask_status",
        "request_final_memo",
        "request_final_review",
        "off_topic",
    }
    warnings: list[str] = []
    if requested not in allowed_intents:
        return "", [f"Client intent {requested} is not recognized and was ignored."]
    if request.extra_evidence:
        if requested != "submit_evidence":
            warnings.append(f"Client intent {requested} was ignored because this turn includes evidence.")
        return "submit_evidence", warnings
    if requested == "submit_evidence":
        if deterministic_intent == "submit_evidence":
            return "submit_evidence", warnings
        return "", ["Client intent submit_evidence was ignored because no evidence payload was provided."]
    if requested == "request_final_review" and state.get("existing_state") is None:
        return "", ["Client intent request_final_review was ignored because no approval case exists yet."]
    if requested in {"ask_missing_requirements", "ask_policy_failure"} and state.get("existing_state") is None:
        return "", [f"Client intent {requested} was ignored because no approval case exists yet."]
    if requested == "create_case" and state.get("existing_state") is not None:
        return "", ["Client intent create_case was ignored because the current turn is already bound to a case."]
    if requested in {"ask_missing_requirements", "ask_how_to_prepare", "ask_policy_failure", "request_final_review"}:
        return requested, warnings
    if requested in {"correct_previous_evidence", "withdraw_evidence"} and state.get("existing_state") is not None:
        return requested, warnings
    if requested == "off_topic" and deterministic_intent == "off_topic":
        return requested, warnings
    return "", [f"Client intent {requested} was not safe for this case state and was ignored."]


def _context_pack_summary(context_pack: dict[str, Any]) -> dict[str, Any]:
    case_summary = dict(context_pack.get("case_summary") or {})
    policy = dict(context_pack.get("context_policy") or {})
    ledger = dict(context_pack.get("evidence_ledger_summary") or {})
    current_submission = str(context_pack.get("current_user_submission") or "")
    return {
        "case_id": case_summary.get("case_id", ""),
        "stage": case_summary.get("stage", ""),
        "approval_type": case_summary.get("approval_type", ""),
        "branch": policy.get("branch", ""),
        "selection": policy.get("selection", ""),
        "requirement_count": len(context_pack.get("current_relevant_requirements") or []),
        "accepted_claim_count": len(ledger.get("accepted_claims") or []),
        "rejected_evidence_count": len(ledger.get("rejected_evidence") or []),
        "contradiction_count": len(ledger.get("contradictions") or []),
        "has_current_submission": bool(current_submission.strip()),
        "current_submission_chars": len(current_submission),
    }


def _classifier_override_allowed(state: CaseTurnGraphState, deterministic_intent: str, candidate_intent: str) -> bool:
    deterministic_intent = _canonical_intent(deterministic_intent)
    candidate_intent = _canonical_intent(candidate_intent)
    request = state["request"]
    if candidate_intent == deterministic_intent:
        return True
    if deterministic_intent in {"off_topic", "request_final_review"}:
        return False
    if request.extra_evidence:
        return candidate_intent == "submit_evidence"
    if candidate_intent == "submit_evidence":
        return deterministic_intent == "submit_evidence"
    if candidate_intent == "create_case":
        return state.get("existing_state") is None
    if candidate_intent in {"ask_missing_requirements", "ask_how_to_prepare", "ask_policy_failure", "off_topic"}:
        return True
    return False


def _canonical_intent(intent: str) -> str:
    aliases = {
        "ask_required_materials": "ask_how_to_prepare",
        "ask_status": "ask_missing_requirements",
        "request_final_memo": "request_final_review",
    }
    return aliases.get(intent, intent)


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
    stage_model_payload = {}
    if harness.stage_model is not None:
        stage_model_payload = harness.stage_model.build_payload(
            context_pack=context_pack,
            candidates=candidates,
            review=provisional_review,
            deterministic_intent="submit_evidence",
        )
    outputs = _branch_outputs(state)
    outputs[branch] = {
        "candidate_source_ids": [item.source_id for item in candidates],
        "stage_model_payload_ready": bool(stage_model_payload),
    }
    return {
        **state,
        "branch": branch,
        "context_pack": context_pack,
        "provisional_review": provisional_review,
        "review": provisional_review,
        "stage_model_payload": stage_model_payload,
        "branch_review_outputs": outputs,
    }


def _branch_outputs(state: CaseTurnGraphState) -> dict[str, Any]:
    return dict(state.get("branch_review_outputs", {}) or {})


def _llm_stage_role_node(state: CaseTurnGraphState, role: str, step: str) -> CaseTurnGraphState:
    harness = state["harness"]
    outputs = dict(state.get("stage_model_role_outputs", {}) or {})
    errors = dict(state.get("stage_model_role_errors", {}) or {})
    if harness.stage_model is None:
        outputs[role] = {
            "skipped": True,
            "reason": "stage_model_not_configured",
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        }
        return {**state, "stage_model_role_outputs": outputs, "stage_model_role_errors": errors, "graph_steps": _steps(state, step)}
    payload = dict(state.get("stage_model_payload", {}) or {})
    if not payload:
        review = state.get("review") or state.get("provisional_review") or _review_without_new_evidence(state, branch="submit_evidence")
        payload = harness.stage_model.build_payload(
            context_pack=state.get("context_pack", {}),
            candidates=state.get("candidates", []),
            review=review,
            deterministic_intent=state.get("intent", "submit_evidence"),
        )
    output, error = harness.stage_model.review_role(role, payload=payload, role_outputs=outputs)
    outputs[role] = output or {"skipped": bool(error), "error": error, "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT}
    if error:
        errors[role] = error
    return {
        **state,
        "stage_model_payload": payload,
        "stage_model_role_outputs": outputs,
        "stage_model_role_errors": errors,
        "graph_steps": _steps(state, step),
    }


def _p2p_explanation_node(state: CaseTurnGraphState, step: str, prompt: str) -> CaseTurnGraphState:
    harness = state["harness"]
    p2p_review = state.get("p2p_review") or review_p2p_process_evidence(state.get("candidates", []))
    explanations = dict(state.get("p2p_llm_explanations", {}) or {})
    outputs = _branch_outputs(state)
    if harness.stage_model is None:
        explanation = {
            "skipped": True,
            "reason": "stage_model_not_configured",
            "deterministic_fallback": render_p2p_review_notes(p2p_review),
            "non_action_statement": p2p_review.non_action_statement,
        }
    else:
        payload = {
            "p2p_review": p2p_review.model_dump(),
            "candidate_evidence": [
                {
                    "source_id": getattr(item, "source_id", ""),
                    "title": getattr(item, "title", ""),
                    "record_type": getattr(item, "record_type", ""),
                    "content_preview": getattr(item, "content", "")[:1600],
                }
                for item in state.get("candidates", [])
            ],
            "allowed_match_types": ["three_way_invoice_after_gr", "three_way_invoice_before_gr", "two_way", "consignment", "unknown"],
            "non_action_statement": p2p_review.non_action_statement,
        }
        explanation, error = harness.stage_model.review_custom_json_role(role_name=step, system_prompt=prompt, payload=payload)
        if error:
            explanation = {
                "error": error,
                "deterministic_fallback": render_p2p_review_notes(p2p_review),
                "non_action_statement": p2p_review.non_action_statement,
            }
    explanations[step] = explanation
    outputs[step] = explanation
    return {
        **state,
        "p2p_review": p2p_review,
        "p2p_llm_explanations": explanations,
        "branch_review_outputs": outputs,
        "graph_steps": _steps(state, step),
    }


def _run_custom_stage_model_role(
    state: CaseTurnGraphState,
    *,
    role_name: str,
    system_prompt: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    harness = state["harness"]
    if harness.stage_model is None:
        return {
            "used": False,
            "status": "skipped",
            "reason": "stage_model_not_configured",
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        }
    output, error = harness.stage_model.review_custom_json_role(
        role_name=role_name,
        system_prompt=system_prompt,
        payload=payload,
    )
    if error:
        return {
            "used": False,
            "status": "error",
            "error": error,
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        }
    return {
        **(output or {}),
        "used": True,
        "status": "executed",
        "non_action_statement": output.get("non_action_statement", CASE_HARNESS_NON_ACTION_STATEMENT) if isinstance(output, dict) else CASE_HARNESS_NON_ACTION_STATEMENT,
    }


def _render_missing_requirements_answer(state: CaseTurnGraphState, review: Any) -> str:
    case_state = state["case_state"]
    gaps = list(review.evidence_sufficiency.get("blocking_gaps") or []) or list(case_state.missing_items or [])
    questions = list(review.evidence_sufficiency.get("next_questions") or []) or list(case_state.next_questions or [])
    failures = [item for item in case_state.policy_failures if not item.resolved]
    lines = ["当前缺口（来自案卷状态、证据充分性和控制矩阵）："]
    if gaps:
        lines.append("Blocking 缺口：")
        lines.extend(f"- {item}" for item in gaps[:12])
    else:
        lines.append("- 暂无新的 blocking gap，但仍需 human reviewer 查看完整案卷。")
    if failures:
        lines.append("未解决 policy failure：")
        lines.extend(f"- {item.requirement_id}: {item.how_to_fix}" for item in failures[:8])
    if questions:
        lines.append("下一步补证问题：")
        lines.extend(f"- {item}" for item in questions[:8])
    lines.append("No ERP write action was executed.")
    return "\n".join(lines)


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
