from __future__ import annotations

import json
from typing import Any

from src.backend.domains.erp_approval.case_state_models import ApprovalCaseState, CasePatch, CaseTurnContract


EXECUTION_TERMS = (
    "approve",
    "reject",
    "payment",
    "pay",
    "supplier activation",
    "activate supplier",
    "budget update",
    "contract sign",
    "execute",
    "执行",
    "付款",
    "批准",
    "驳回",
    "供应商激活",
    "预算写入",
    "合同签署",
)


class CasePatchValidator:
    def validate(self, state: ApprovalCaseState, patch: CasePatch, contract: CaseTurnContract, *, review: Any | None = None) -> CasePatch:
        warnings = list(patch.warnings)
        allowed = True
        if patch.turn_intent not in contract.allowed_intents:
            allowed = False
            warnings.append(f"turn_intent {patch.turn_intent} is not allowed in stage {state.stage}.")
        if patch.patch_type not in contract.allowed_patch_types:
            allowed = False
            warnings.append(f"patch_type {patch.patch_type} is not allowed in stage {state.stage}.")
        text = " ".join(
            [
                patch.dossier_patch,
                " ".join(patch.rejection_reasons),
                " ".join(patch.next_questions),
                _stringify_model_review(patch.model_review),
            ]
        ).lower()
        if any(term in text for term in EXECUTION_TERMS):
            warnings.append("本轮 patch 文本含有类似执行动作的措辞，已按非执行审查文本保留，不会触发任何 ERP 写入。")
        claims_by_id = _claims_by_id(review)
        requirement_ids = _requirement_ids(review)
        for evidence in patch.accepted_evidence:
            if not evidence.source_id:
                allowed = False
                warnings.append("accepted evidence must have source_id.")
            if not evidence.claim_ids:
                allowed = False
                warnings.append(f"accepted evidence {evidence.source_id} has no supported claims.")
            if evidence.record_type in {"local_note", "user_statement"}:
                allowed = False
                warnings.append(f"accepted evidence {evidence.source_id} is a user statement/local note and cannot satisfy blocking evidence.")
            for requirement_id in evidence.requirement_ids:
                if requirement_ids and requirement_id not in requirement_ids:
                    allowed = False
                    warnings.append(f"accepted evidence {evidence.source_id} references unknown requirement {requirement_id}.")
            supported_requirements_for_evidence: set[str] = set()
            for claim_id in evidence.claim_ids:
                claim = claims_by_id.get(claim_id)
                if claims_by_id and claim is None:
                    allowed = False
                    warnings.append(f"accepted evidence {evidence.source_id} references unknown claim {claim_id}.")
                    continue
                if claim is None:
                    continue
                if str(claim.get("source_id", "") or "") != evidence.source_id:
                    allowed = False
                    warnings.append(f"claim {claim_id} source_id does not match accepted evidence {evidence.source_id}.")
                if str(claim.get("verification_status", "") or "") == "unsupported":
                    allowed = False
                    warnings.append(f"claim {claim_id} is unsupported and cannot satisfy accepted evidence.")
                supported_requirements_for_evidence.update(str(item) for item in claim.get("supports_requirement_ids") or [])
            missing_requirement_links = [
                requirement_id
                for requirement_id in evidence.requirement_ids
                if requirement_id not in supported_requirements_for_evidence
            ]
            if missing_requirement_links:
                allowed = False
                warnings.append(
                    f"accepted evidence {evidence.source_id} has no same-source claim support for requirements: {', '.join(missing_requirement_links)}."
                )
        if patch.patch_type == "final_memo":
            unresolved_policy_failures = [failure for failure in state.policy_failures if not getattr(failure, "resolved", False)]
            if unresolved_policy_failures:
                allowed = False
                warnings.append("final_memo is blocked because unresolved policy_failures remain in case_state.")
            if review is not None:
                sufficiency = getattr(review, "evidence_sufficiency", None) or (review.get("evidence_sufficiency") if isinstance(review, dict) else {})
                control_matrix = getattr(review, "control_matrix", None) or (review.get("control_matrix") if isinstance(review, dict) else {})
                contradictions = getattr(review, "contradictions", None) or (review.get("contradictions") if isinstance(review, dict) else {})
                if not dict(sufficiency or {}).get("passed"):
                    allowed = False
                    warnings.append("final_memo is blocked because evidence_sufficiency has not passed.")
                if not dict(control_matrix or {}).get("passed"):
                    allowed = False
                    warnings.append("final_memo is blocked because control_matrix has not passed.")
                if dict(contradictions or {}).get("has_conflict"):
                    allowed = False
                    warnings.append("final_memo is blocked because unresolved contradictions exist.")
        return patch.model_copy(update={"allowed_to_apply": allowed, "warnings": _unique(warnings)})


def _claims_by_id(review: Any | None) -> dict[str, dict[str, Any]]:
    if review is None:
        return {}
    claims = getattr(review, "evidence_claims", None)
    if claims is None and isinstance(review, dict):
        claims = review.get("evidence_claims")
    output: dict[str, dict[str, Any]] = {}
    for item in claims or []:
        if isinstance(item, dict):
            claim_id = str(item.get("claim_id", "") or "")
            if claim_id:
                output[claim_id] = item
    return output


def _requirement_ids(review: Any | None) -> set[str]:
    if review is None:
        return set()
    requirements = getattr(review, "evidence_requirements", None)
    if requirements is None and isinstance(review, dict):
        requirements = review.get("evidence_requirements")
    output: set[str] = set()
    for item in requirements or []:
        if isinstance(item, dict):
            requirement_id = str(item.get("requirement_id", "") or "")
            if requirement_id:
                output.add(requirement_id)
    return output


def _stringify_model_review(model_review: dict[str, Any] | None) -> str:
    if not model_review:
        return ""
    redacted = _drop_non_action_statements(model_review)
    try:
        return json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(redacted)


def _drop_non_action_statements(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_non_action_statements(item)
            for key, item in value.items()
            if key != "non_action_statement"
        }
    if isinstance(value, list):
        return [_drop_non_action_statements(item) for item in value]
    if isinstance(value, str) and "No ERP write action was executed" in value:
        return ""
    return value


def contract_for_state(state: ApprovalCaseState) -> CaseTurnContract:
    if state.stage in {"ready_for_final_review", "final_memo_ready"}:
        allowed_intents = [
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
        ]
    elif state.stage == "blocked":
        allowed_intents = [
            "ask_missing_requirements",
            "ask_policy_failure",
            "ask_status",
            "submit_evidence",
            "request_final_memo",
            "request_final_review",
            "off_topic",
        ]
    else:
        allowed_intents = [
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
        ]
    return CaseTurnContract(
        case_id=state.case_id,
        stage=state.stage,
        allowed_intents=allowed_intents,
        allowed_patch_types=["create_case", "accept_evidence", "reject_evidence", "answer_status", "final_memo", "no_case_change"],
        required_context_blocks=[
            "immutable_instruction",
            "case_summary",
            "evidence_ledger_summary",
            "current_user_submission",
            "output_contract",
        ],
        forbidden_actions=[
            "approve_erp",
            "reject_erp",
            "pay_invoice",
            "route_live_workflow",
            "post_comment",
            "activate_supplier",
            "update_budget",
            "sign_contract",
        ],
        validation_rules=[
            "模型只能输出 CasePatch，不能直接写 case_state。",
            "accepted_evidence 必须有 source_id 和 supported claims。",
            "用户陈述不能满足 blocking evidence。",
            "任何执行 ERP 写动作的语义都只能作为被拒绝的用户请求记录。",
        ],
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
