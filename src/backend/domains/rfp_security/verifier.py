from __future__ import annotations

from src.backend.domains.rfp_security.prompts import APPROVAL_TEMPLATE, CONFLICT_TEMPLATE, MISSING_EVIDENCE_TEMPLATE
from src.backend.domains.rfp_security.schemas import EvidencePlan, PolicyDecision, RfpSecurityQuestion


def revise_answer_lines(
    question: RfpSecurityQuestion,
    policy: PolicyDecision,
    plan: EvidencePlan,
    lines: list[str],
) -> list[str]:
    revised: list[str] = []
    seen: set[str] = set()
    supported_points = {item.required_point for item in plan.items if item.mapped_evidence_ids}
    missing_points = {item.required_point for item in plan.items if item.missing}

    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line or line in seen:
            continue
        if any(point in line for point in missing_points) and "[" in line and "]" in line:
            point = next(point for point in missing_points if point in line)
            line = f"- {MISSING_EVIDENCE_TEMPLATE.format(point=point)}"
        if any(point in line for point in supported_points) and "insufficient_evidence" in line:
            point = next(point for point in supported_points if point in line)
            line = f"- {point}."
        seen.add(line)
        revised.append(line)

    if not revised:
        revised.append("- insufficient_evidence: no grounded answer can be drafted from the retrieved material.")

    for reason in policy.approval_reasons:
        approval_line = f"- {APPROVAL_TEMPLATE.format(reason=reason)}"
        if approval_line not in seen:
            revised.append(approval_line)
            seen.add(approval_line)

    for note in policy.conflict_notes:
        conflict_line = f"- {CONFLICT_TEMPLATE.format(note=note)}"
        if conflict_line not in seen:
            revised.append(conflict_line)
            seen.add(conflict_line)

    return revised

