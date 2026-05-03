from __future__ import annotations

from src.backend.domains.erp_approval.case_state_models import ApprovalCaseState, CaseTurnContract


class CaseContextAssembler:
    """Builds the bounded case context a stage model is allowed to see."""

    def assemble(self, state: ApprovalCaseState, contract: CaseTurnContract, user_message: str) -> dict:
        return self.assemble_for_branch(state, contract, user_message, branch="generic_case_turn")

    def assemble_for_branch(self, state: ApprovalCaseState, contract: CaseTurnContract, user_message: str, *, branch: str) -> dict:
        relevant_requirements = _relevant_requirements(state, user_message, limit=18)
        relevant_claims = _relevant_claims(state, relevant_requirements, user_message, limit=24)
        relevant_rejections = _relevant_rejections(state, user_message, limit=10)
        branch_policy = _branch_context_policy(branch)
        return {
            "context_policy": {
                "selection": branch_policy["selection"],
                "branch": branch,
                "claim_limit": branch_policy["claim_limit"],
                "rejected_evidence_limit": branch_policy["rejected_evidence_limit"],
                "requirement_limit": branch_policy["requirement_limit"],
                "notes": branch_policy["notes"],
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
                "policy_failures": [
                    {
                        "requirement_id": item.requirement_id,
                        "policy_clause_id": item.policy_clause_id,
                        "why_failed": item.why_failed,
                        "how_to_fix": item.how_to_fix,
                        "source_id": item.source_id,
                        "resolved": item.resolved,
                    }
                    for item in state.policy_failures[-12:]
                    if not item.resolved
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


def _branch_context_policy(branch: str) -> dict:
    policies = {
        "ask_how_to_prepare": {
            "selection": "policy_rag_requirement_matrix_materials_guidance",
            "claim_limit": 4,
            "rejected_evidence_limit": 4,
            "requirement_limit": 30,
            "notes": "Answer how to prepare from local policy guidance and the requirement matrix. Do not mutate case evidence.",
        },
        "ask_required_materials": {
            "selection": "case_summary_requirements_and_missing_items_only",
            "claim_limit": 8,
            "rejected_evidence_limit": 4,
            "requirement_limit": 24,
            "notes": "Answer required materials from the case state, evidence matrix, and current blocking gaps.",
        },
        "ask_missing_requirements": {
            "selection": "case_state_missing_requirements_policy_failures_recent_evidence",
            "claim_limit": 12,
            "rejected_evidence_limit": 8,
            "requirement_limit": 22,
            "notes": "Answer current missing requirements from persisted case state and policy_failures, not from raw chat guesses.",
        },
        "ask_status": {
            "selection": "compact_case_state_blocking_gaps_recent_evidence",
            "claim_limit": 12,
            "rejected_evidence_limit": 8,
            "requirement_limit": 18,
            "notes": "Summarize current status without re-reviewing unrelated materials.",
        },
        "ask_policy_failure": {
            "selection": "persisted_policy_failures_and_rejected_evidence_only",
            "claim_limit": 6,
            "rejected_evidence_limit": 12,
            "requirement_limit": 18,
            "notes": "Explain why materials failed by reading case_state.policy_failures and rejected_evidence. Do not re-guess.",
        },
        "submit_evidence": {
            "selection": "current_evidence_related_requirements_claims_and_controls",
            "claim_limit": 24,
            "rejected_evidence_limit": 10,
            "requirement_limit": 18,
            "notes": "Review only the current submission against related requirements and controls.",
        },
        "p2p_process_review": {
            "selection": "invoice_po_grn_process_log_payment_policy_and_historical_claims",
            "claim_limit": 30,
            "rejected_evidence_limit": 10,
            "requirement_limit": 22,
            "notes": "Focus on P2P process evidence: invoice, PO, goods receipt, payment terms, duplicate checks, Clear Invoice history, sequence risk, and amount consistency.",
        },
        "final_memo": {
            "selection": "evidence_summary_control_matrix_contradictions_unresolved_risks",
            "claim_limit": 36,
            "rejected_evidence_limit": 16,
            "requirement_limit": 28,
            "notes": "Draft a reviewer memo only from validated case state and unresolved controls.",
        },
    }
    return policies.get(
        branch,
        {
            "selection": "case_state_snapshot_relevant_to_current_turn",
            "claim_limit": 24,
            "rejected_evidence_limit": 10,
            "requirement_limit": 18,
            "notes": "Do not rely on raw chat history. Use this bounded case-state snapshot and current submission.",
        },
    )
