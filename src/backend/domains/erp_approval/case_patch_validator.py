from __future__ import annotations

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
    def validate(self, state: ApprovalCaseState, patch: CasePatch, contract: CaseTurnContract) -> CasePatch:
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
            ]
        ).lower()
        if any(term in text for term in EXECUTION_TERMS):
            warnings.append("patch text contains execution-like wording; retained as non-action review text only.")
        for evidence in patch.accepted_evidence:
            if not evidence.source_id:
                allowed = False
                warnings.append("accepted evidence must have source_id.")
            if not evidence.claim_ids:
                allowed = False
                warnings.append(f"accepted evidence {evidence.source_id} has no supported claims.")
        return patch.model_copy(update={"allowed_to_apply": allowed, "warnings": _unique(warnings)})


def contract_for_state(state: ApprovalCaseState) -> CaseTurnContract:
    if state.stage in {"ready_for_final_review", "final_memo_ready"}:
        allowed_intents = [
            "ask_required_materials",
            "submit_evidence",
            "correct_previous_evidence",
            "withdraw_evidence",
            "ask_status",
            "request_final_memo",
            "off_topic",
        ]
    elif state.stage == "blocked":
        allowed_intents = ["ask_status", "submit_evidence", "request_final_memo", "off_topic"]
    else:
        allowed_intents = [
            "create_case",
            "ask_required_materials",
            "submit_evidence",
            "correct_previous_evidence",
            "withdraw_evidence",
            "ask_status",
            "request_final_memo",
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
