from __future__ import annotations

from src.backend.domains.rfp_security.planner import build_evidence_plan
from src.backend.domains.rfp_security.schemas import PolicyDecision, RfpSecurityQuestion
from src.backend.knowledge.types import Evidence


_APPROVAL_SIGNAL_TERMS = (
    "customer reference",
    "named customer",
    "penetration test",
    "fedramp",
    "contract commit",
    "guarantee",
    "legal",
)

_CONFLICT_RULES = (
    ("24 hours", "72 hours", "Incident notification SLA differs between current and legacy material."),
    ("requires approval", "available on request", "Reference-sharing guidance differs between policy and legacy material."),
    ("not currently supported", "supported", "Capability support differs between sources."),
)


def _contains(text: str, term: str) -> bool:
    return term.lower() in str(text or "").lower()


def evaluate_policy_decision(
    question: RfpSecurityQuestion,
    evidences: list[Evidence],
) -> PolicyDecision:
    joined_text = "\n".join(
        " ".join(
            [
                evidence.source_path,
                evidence.locator,
                evidence.snippet,
            ]
        )
        for evidence in evidences
    ).lower()

    approval_reasons: list[str] = []
    if question.risk_level in {"high", "critical"}:
        approval_reasons.append(f"{question.risk_level} risk question")
    for term in question.approval_terms:
        approval_reasons.append(f"approval-sensitive term: {term}")
    if any(term in question.normalized_query.lower() for term in _APPROVAL_SIGNAL_TERMS):
        approval_reasons.append("query requests approval-sensitive disclosure")

    conflict_notes: list[str] = []
    for left, right, note in _CONFLICT_RULES:
        if left in joined_text and right in joined_text:
            conflict_notes.append(note)

    evidence_plan = build_evidence_plan(
        question,
        evidences,
        approval_reasons=tuple(approval_reasons),
        conflict_notes=tuple(conflict_notes),
    )
    supported_points = [
        item.required_point
        for item in evidence_plan.items
        if item.mapped_evidence_ids
    ]
    missing_points = [item.required_point for item in evidence_plan.items if item.missing]

    status = "supported"
    if missing_points:
        status = "partial"
    if approval_reasons:
        status = "needs_approval"
    if conflict_notes:
        status = "conflict"

    return PolicyDecision(
        status=status,
        requires_approval=bool(approval_reasons),
        has_conflict=bool(conflict_notes),
        supported_points=tuple(supported_points),
        missing_points=tuple(missing_points),
        approval_reasons=tuple(approval_reasons),
        conflict_notes=tuple(conflict_notes),
        evidence_plan=evidence_plan,
    )
