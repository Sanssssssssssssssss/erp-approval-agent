from __future__ import annotations

SECTION_DRAFT_INSTRUCTIONS = """
Draft one grounded RFP or security-questionnaire answer from retrieved evidence only.
- Prefer short, auditable claims.
- Cite the supporting source path for every substantive point.
- If evidence is missing, say so explicitly.
- If evidence conflicts, surface the conflict instead of silently choosing one side.
- If the question needs customer approval, legal approval, or roadmap confirmation, state that clearly.
""".strip()

ANSWER_TEMPLATE_HEADERS = {
    "yes_no_capability": "Capability answer:",
    "policy_process": "Policy/process answer:",
    "certification_compliance": "Compliance answer:",
    "deployment_security_architecture": "Deployment/security answer:",
    "sla_support": "SLA/support answer:",
    "general_rfp": "Grounded answer:",
}

MISSING_EVIDENCE_TEMPLATE = "insufficient_evidence: {point}."
APPROVAL_TEMPLATE = "requires_approval: {reason}."
CONFLICT_TEMPLATE = "conflicting_evidence: {note}."
