from __future__ import annotations

from src.backend.domains.erp_approval.case_state_models import ApprovalCaseState, CaseTurnContract


class CaseContextAssembler:
    """Builds the compact case context a stage model is allowed to see."""

    def assemble(self, state: ApprovalCaseState, contract: CaseTurnContract, user_message: str) -> dict:
        return {
            "immutable_instruction": (
                "你是审批案卷资料专员。你只能审核材料、抽取证据、更新案卷；"
                "不能直接审批，不能执行 ERP 写动作。用户陈述不能满足阻断性强证据。"
            ),
            "case_summary": {
                "case_id": state.case_id,
                "stage": state.stage,
                "approval_type": state.approval_type,
                "approval_id": state.approval_id,
                "missing_items": list(state.missing_items),
                "next_questions": list(state.next_questions),
            },
            "evidence_ledger_summary": {
                "accepted_claims": [
                    {
                        "claim_id": claim.get("claim_id"),
                        "claim_type": claim.get("claim_type"),
                        "source_id": claim.get("source_id"),
                        "supports_requirement_ids": claim.get("supports_requirement_ids") or [],
                    }
                    for claim in state.claims[:30]
                ],
                "rejected_evidence": [
                    {
                        "source_id": item.source_id,
                        "title": item.title,
                        "reasons": item.reasons,
                    }
                    for item in state.rejected_evidence[-12:]
                ],
                "contradictions": state.contradictions,
            },
            "current_user_submission": user_message,
            "output_contract": {
                "schema": contract.output_schema,
                "allowed_intents": contract.allowed_intents,
                "allowed_patch_types": contract.allowed_patch_types,
                "validation_rules": contract.validation_rules,
            },
        }
