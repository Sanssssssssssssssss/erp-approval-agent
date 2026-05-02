from __future__ import annotations

from src.backend.domains.erp_approval.case_state_models import ApprovalCaseState, CaseTurnContract


class CaseContextAssembler:
    """Builds the bounded case context a stage model is allowed to see."""

    def assemble(self, state: ApprovalCaseState, contract: CaseTurnContract, user_message: str) -> dict:
        relevant_requirements = _relevant_requirements(state, user_message, limit=18)
        relevant_claims = _relevant_claims(state, relevant_requirements, user_message, limit=24)
        relevant_rejections = _relevant_rejections(state, user_message, limit=10)
        return {
            "context_policy": {
                "selection": "case_state_snapshot_relevant_to_current_turn",
                "claim_limit": 24,
                "rejected_evidence_limit": 10,
                "requirement_limit": 18,
                "notes": "Do not rely on raw chat history. Use this bounded case-state snapshot and current submission.",
            },
            "immutable_instruction": (
                "你是审批案卷资料专员，只能审核材料、抽取证据、提出 CasePatch。"
                "不能直接审批，不能执行 ERP 写动作。用户陈述不能满足阻断性强证据。"
            ),
            "case_summary": {
                "case_id": state.case_id,
                "stage": state.stage,
                "approval_type": state.approval_type,
                "approval_id": state.approval_id,
                "turn_count": state.turn_count,
                "dossier_version": state.dossier_version,
                "missing_items": list(state.missing_items),
                "next_questions": list(state.next_questions),
            },
            "current_relevant_requirements": relevant_requirements,
            "evidence_ledger_summary": {
                "accepted_claims": [
                    {
                        "claim_id": claim.get("claim_id"),
                        "claim_type": claim.get("claim_type"),
                        "source_id": claim.get("source_id"),
                        "verification_status": claim.get("verification_status"),
                        "supports_requirement_ids": claim.get("supports_requirement_ids") or [],
                    }
                    for claim in relevant_claims
                ],
                "rejected_evidence": [
                    {
                        "source_id": item.source_id,
                        "title": item.title,
                        "record_type": item.record_type,
                        "reasons": item.reasons,
                    }
                    for item in relevant_rejections
                ],
                "contradictions": state.contradictions,
            },
            "current_user_submission": user_message,
            "output_contract": {
                "schema": contract.output_schema,
                "allowed_intents": contract.allowed_intents,
                "allowed_patch_types": contract.allowed_patch_types,
                "validation_rules": contract.validation_rules,
                "forbidden_actions": contract.forbidden_actions,
            },
        }


def _relevant_requirements(state: ApprovalCaseState, user_message: str, *, limit: int) -> list[dict]:
    terms = _terms(user_message)
    missing_text = " ".join(state.missing_items or []).lower()
    scored: list[tuple[int, int, dict]] = []
    for index, requirement in enumerate(state.evidence_requirements or []):
        requirement_id = str(requirement.get("requirement_id", "") or "")
        label = str(requirement.get("label", "") or "")
        status = str(requirement.get("status", "") or "")
        haystack = f"{requirement_id} {label} {requirement.get('description', '')}".lower()
        score = 0
        if status in {"missing", "partial", "conflict"}:
            score += 8
        if requirement_id.lower() in missing_text or label.lower() in missing_text:
            score += 5
        score += sum(1 for term in terms if term in haystack)
        scored.append((-score, index, requirement))
    scored.sort()
    return [item for _score, _index, item in scored[:limit]]


def _relevant_claims(state: ApprovalCaseState, requirements: list[dict], user_message: str, *, limit: int) -> list[dict]:
    terms = _terms(user_message)
    requirement_ids = {str(item.get("requirement_id", "") or "") for item in requirements}
    scored: list[tuple[int, int, dict]] = []
    for index, claim in enumerate(state.claims or []):
        supports = set(claim.get("supports_requirement_ids") or [])
        haystack = f"{claim.get('claim_type', '')} {claim.get('statement', '')} {claim.get('source_id', '')}".lower()
        score = 0
        if supports.intersection(requirement_ids):
            score += 10
        if claim.get("verification_status") in {"conflict", "needs_review"}:
            score += 5
        score += sum(1 for term in terms if term in haystack)
        scored.append((-score, index, claim))
    scored.sort()
    return [item for _score, _index, item in scored[:limit]]


def _relevant_rejections(state: ApprovalCaseState, user_message: str, *, limit: int):
    terms = _terms(user_message)
    scored = []
    for index, item in enumerate(state.rejected_evidence or []):
        haystack = f"{item.source_id} {item.title} {item.record_type} {' '.join(item.reasons)}".lower()
        score = sum(1 for term in terms if term in haystack)
        scored.append((-score, -index, item))
    scored.sort()
    return [item for _score, _index, item in scored[:limit]]


def _terms(text: str) -> set[str]:
    normalized = str(text or "").lower()
    raw_terms = normalized.replace("/", " ").replace("-", " ").replace("_", " ").split()
    return {term.strip(".,:;()[]{}") for term in raw_terms if len(term.strip(".,:;()[]{}")) >= 3}
