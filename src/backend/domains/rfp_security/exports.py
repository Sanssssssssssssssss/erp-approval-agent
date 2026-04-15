from __future__ import annotations

from src.backend.domains.rfp_security.prompts import (
    APPROVAL_TEMPLATE,
    ANSWER_TEMPLATE_HEADERS,
    CONFLICT_TEMPLATE,
    MISSING_EVIDENCE_TEMPLATE,
)
from src.backend.domains.rfp_security.planner import build_evidence_plan, select_evidences_for_plan
from src.backend.domains.rfp_security.schemas import PolicyDecision, RfpSecurityQuestion, SectionDraft
from src.backend.domains.rfp_security.verifier import revise_answer_lines
from src.backend.knowledge.types import Evidence


def _citation(evidence: Evidence) -> str:
    locator = str(evidence.locator or "").strip()
    if locator:
        return f"{evidence.source_path}|{locator}"
    return evidence.source_path


def _render_supported_line(point: str, citations: tuple[str, ...]) -> str:
    citation_block = " ".join(f"[{citation}]" for citation in citations[:2])
    return f"- {point}.{(' ' + citation_block) if citation_block else ''}".rstrip()


def build_section_level_draft(
    question: RfpSecurityQuestion,
    evidences: list[Evidence],
    policy: PolicyDecision,
) -> SectionDraft:
    plan = policy.evidence_plan or build_evidence_plan(
        question,
        evidences,
        approval_reasons=policy.approval_reasons,
        conflict_notes=policy.conflict_notes,
    )
    lines: list[str] = [ANSWER_TEMPLATE_HEADERS.get(question.answer_template_kind, "Grounded answer:")]
    citations: list[str] = []
    for item in plan.items:
        if item.mapped_evidence_ids:
            citations.extend(item.mapped_evidence_ids[:2])
            lines.append(_render_supported_line(item.required_point, item.mapped_evidence_ids))
        else:
            lines.append(f"- {MISSING_EVIDENCE_TEMPLATE.format(point=item.required_point)}")
    if not plan.items:
        if evidences:
            lines.append("- insufficient_evidence: retrieved related materials, but none directly support the requested answer.")
        else:
            lines.append("- insufficient_evidence: no supporting evidence was retrieved.")

    lines = revise_answer_lines(question, policy, plan, lines)
    selected_evidences = select_evidences_for_plan(plan, evidences)
    selected_citations = tuple(dict.fromkeys(citations))

    supported_points = tuple(item.required_point for item in plan.items if item.mapped_evidence_ids)
    missing_points = tuple(item.required_point for item in plan.items if item.missing)
    response_completeness = (
        len(supported_points) / len(question.required_points)
        if question.required_points
        else (1.0 if selected_evidences else 0.0)
    )
    unsupported_claim_rate = 0.0
    groundedness = max(0.0, response_completeness - (0.15 if policy.has_conflict else 0.0))
    if policy.requires_approval and supported_points:
        groundedness = max(0.0, groundedness - 0.1)
    relevance = min(
        1.0,
        (
            (1.0 if selected_evidences or evidences else 0.0)
            + response_completeness
            + (1.0 if question.answer_template_kind != "general_rfp" else 0.85)
        )
        / 3.0,
    )

    return SectionDraft(
        status=policy.status,
        answer="\n".join(lines).strip(),
        citations=selected_citations,
        supported_points=supported_points,
        missing_points=missing_points,
        approval_reasons=policy.approval_reasons,
        conflict_notes=policy.conflict_notes,
        groundedness=round(groundedness, 4),
        relevance=round(relevance, 4),
        response_completeness=round(response_completeness, 4),
        unsupported_claim_rate=round(unsupported_claim_rate, 4),
        selected_evidence_ids=plan.selected_evidence_ids,
        evidence_plan=plan,
    )
