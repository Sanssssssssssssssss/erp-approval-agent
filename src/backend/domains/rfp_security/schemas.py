from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


RfpQuestionKind = Literal[
    "section_draft",
    "questionnaire_field",
    "missing_evidence_check",
    "conflict_review",
    "approval_review",
]
AnswerTemplateKind = Literal[
    "yes_no_capability",
    "policy_process",
    "certification_compliance",
    "deployment_security_architecture",
    "sla_support",
    "general_rfp",
]


@dataclass(frozen=True)
class EvidencePlanItem:
    required_point: str
    mapped_evidence_ids: tuple[str, ...] = ()
    matched_aliases: tuple[str, ...] = ()
    missing: bool = False
    needs_approval: bool = False
    conflict_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mapped_evidence_ids"] = list(self.mapped_evidence_ids)
        payload["matched_aliases"] = list(self.matched_aliases)
        return payload


@dataclass(frozen=True)
class EvidencePlan:
    items: tuple[EvidencePlanItem, ...] = ()
    selected_evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "selected_evidence_ids": list(self.selected_evidence_ids),
        }


@dataclass(frozen=True)
class RfpSecurityQuestion:
    query: str
    normalized_query: str
    question_kind: RfpQuestionKind
    answer_template_kind: AnswerTemplateKind = "general_rfp"
    tags: tuple[str, ...] = ()
    risk_level: str = "medium"
    required_points: tuple[str, ...] = ()
    approval_terms: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = list(self.tags)
        payload["required_points"] = list(self.required_points)
        payload["approval_terms"] = list(self.approval_terms)
        payload["search_terms"] = list(self.search_terms)
        return payload


@dataclass(frozen=True)
class PolicyDecision:
    status: str
    requires_approval: bool = False
    has_conflict: bool = False
    supported_points: tuple[str, ...] = ()
    missing_points: tuple[str, ...] = ()
    approval_reasons: tuple[str, ...] = ()
    conflict_notes: tuple[str, ...] = ()
    evidence_plan: EvidencePlan = field(default_factory=EvidencePlan)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["supported_points"] = list(self.supported_points)
        payload["missing_points"] = list(self.missing_points)
        payload["approval_reasons"] = list(self.approval_reasons)
        payload["conflict_notes"] = list(self.conflict_notes)
        payload["evidence_plan"] = self.evidence_plan.to_dict()
        return payload


@dataclass(frozen=True)
class SectionDraft:
    status: str
    answer: str
    citations: tuple[str, ...] = ()
    supported_points: tuple[str, ...] = ()
    missing_points: tuple[str, ...] = ()
    approval_reasons: tuple[str, ...] = ()
    conflict_notes: tuple[str, ...] = ()
    groundedness: float = 0.0
    relevance: float = 0.0
    response_completeness: float = 0.0
    unsupported_claim_rate: float = 0.0
    selected_evidence_ids: tuple[str, ...] = ()
    evidence_plan: EvidencePlan = field(default_factory=EvidencePlan)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["citations"] = list(self.citations)
        payload["supported_points"] = list(self.supported_points)
        payload["missing_points"] = list(self.missing_points)
        payload["approval_reasons"] = list(self.approval_reasons)
        payload["conflict_notes"] = list(self.conflict_notes)
        payload["selected_evidence_ids"] = list(self.selected_evidence_ids)
        payload["evidence_plan"] = self.evidence_plan.to_dict()
        return payload
