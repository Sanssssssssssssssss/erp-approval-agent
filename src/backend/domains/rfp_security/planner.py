from __future__ import annotations

import re
import unicodedata

from src.backend.domains.rfp_security.schemas import EvidencePlan, EvidencePlanItem, RfpSecurityQuestion
from src.backend.knowledge.types import Evidence


_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "to",
    "of",
    "is",
    "are",
    "be",
    "before",
    "after",
    "any",
    "request",
    "requires",
    "require",
    "current",
    "currently",
    "available",
    "provide",
    "state",
    "that",
    "this",
    "with",
    "within",
    "than",
    "later",
    "do",
    "not",
    "the",
}

_POINT_ALIAS_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "SAML 2.0": (("saml 2.0",),),
    "OpenID Connect": (("openid connect",),),
    "SCIM 2.0": (("scim 2.0",),),
    "administrative access requires phishing-resistant MFA": (
        ("administrative access",),
        ("phishing resistant mfa",),
    ),
    "role-based access control": (("role based access control", "least privilege"),),
    "24 hours": (("24 hours",),),
    "4 hours": (("4 hours",),),
    "15 minutes": (("15 minutes",),),
    "tabletop exercise every year": (("tabletop exercise every year", "tabletop exercise"),),
    "data processing agreement": (("data processing agreement",),),
    "public subprocessor list": (("public subprocessor list",),),
    "United States, the European Union, and Singapore": (
        ("united states",),
        ("european union",),
        ("singapore",),
    ),
    "standard contractual clauses": (("standard contractual clauses",),),
    "authentication events": (("authentication events",),),
    "configuration changes": (("configuration changes",),),
    "export events": (("export events",),),
    "365 days": (("365 days",),),
    "TLS 1.2 or newer": (("tls 1.2", "tls 1.2 or newer"),),
    "AES-256": (("aes 256", "aes-256"),),
    "customer references require customer approval": (
        ("customer references", "named customer references"),
        ("customer approval", "approval before disclosure"),
    ),
    "named customer references require customer approval": (
        ("named customer references",),
        ("customer approval", "approval before disclosure"),
    ),
    "Do not claim FedRAMP Moderate authorization": (
        ("do not claim fedramp moderate authorization",),
    ),
    "under assessment planning and not currently authorized": (
        ("under assessment planning",),
        ("not currently authorized",),
    ),
    "penetration test reports require security approval": (
        ("penetration test reports",),
        ("security approval", "approval before disclosure"),
    ),
    "Any request to change contractual notification timing requires legal approval": (
        ("change contractual notification timing", "contractual notification timing"),
        ("legal approval",),
    ),
}


def canonical_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    normalized = normalized.replace("\\", "/")
    normalized = re.sub(r"[`'\"“”‘’]+", "", normalized)
    normalized = re.sub(r"[\(\)\[\]\{\}:,.;!?/_-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def evidence_id(evidence: Evidence) -> str:
    locator = str(evidence.locator or "").strip()
    if locator:
        return f"{evidence.source_path}|{locator}"
    return evidence.source_path


def _evidence_corpus(evidence: Evidence) -> str:
    return canonical_text(" ".join([evidence.source_path, str(evidence.locator or ""), str(evidence.snippet or "")]))


def _point_alias_groups(point: str) -> tuple[tuple[str, ...], ...]:
    if point in _POINT_ALIAS_GROUPS:
        return _POINT_ALIAS_GROUPS[point]
    return ((str(point),),)


def _tokens(value: str) -> list[str]:
    return [token for token in canonical_text(value).split() if token and token not in _STOPWORDS]


def _token_overlap_match(point: str, corpus: str) -> bool:
    point_tokens = _tokens(point)
    if not point_tokens:
        return False
    matched = sum(1 for token in point_tokens if token in corpus)
    if len(point_tokens) <= 2:
        return matched == len(point_tokens)
    return matched >= max(2, int(len(point_tokens) * 0.75))


def _match_alias_groups(point: str, corpus: str) -> tuple[bool, tuple[str, ...]]:
    matched_aliases: list[str] = []
    for group in _point_alias_groups(point):
        group_match = next((alias for alias in group if canonical_text(alias) and canonical_text(alias) in corpus), "")
        if not group_match:
            return False, ()
        matched_aliases.append(group_match)
    return True, tuple(matched_aliases)


def _authority_rank(evidence: Evidence) -> int:
    source_path = str(evidence.source_path or "").lower()
    if any(token in source_path for token in ("security_controls", "incident_response", "approval_policy", "privacy_and_subprocessors")):
        return 3
    if "sample_customer_rfp" in source_path:
        return 2
    if "historical_proposal_snippets" in source_path:
        return 1
    if "legacy_answers" in source_path:
        return 0
    return 1


def _point_match_score(point: str, evidence: Evidence, matched_aliases: tuple[str, ...]) -> tuple[int, int, int, float]:
    corpus = _evidence_corpus(evidence)
    exact = int(canonical_text(point) in corpus)
    alias_count = len(matched_aliases)
    authority = _authority_rank(evidence)
    score = float(evidence.score or 0.0)
    return (exact, alias_count, authority, score)


def match_point_to_evidences(point: str, evidences: list[Evidence]) -> list[tuple[Evidence, tuple[str, ...]]]:
    matches: list[tuple[Evidence, tuple[str, ...]]] = []
    for evidence in evidences:
        corpus = _evidence_corpus(evidence)
        direct_match, matched_aliases = _match_alias_groups(point, corpus)
        if direct_match or _token_overlap_match(point, corpus):
            aliases = matched_aliases or (point,)
            matches.append((evidence, aliases))
    return sorted(
        matches,
        key=lambda item: _point_match_score(point, item[0], item[1]),
        reverse=True,
    )


def build_evidence_plan(
    question: RfpSecurityQuestion,
    evidences: list[Evidence],
    *,
    approval_reasons: tuple[str, ...] = (),
    conflict_notes: tuple[str, ...] = (),
) -> EvidencePlan:
    items: list[EvidencePlanItem] = []
    selected_evidence_ids: list[str] = []
    max_citations_per_point = 2 if question.question_kind == "section_draft" else 1

    for point in question.required_points:
        matches = match_point_to_evidences(point, evidences)[:max_citations_per_point]
        evidence_ids = tuple(evidence_id(evidence) for evidence, _aliases in matches)
        matched_aliases = tuple(alias for _evidence, aliases in matches for alias in aliases)
        items.append(
            EvidencePlanItem(
                required_point=point,
                mapped_evidence_ids=evidence_ids,
                matched_aliases=matched_aliases,
                missing=not evidence_ids,
                needs_approval=bool(approval_reasons),
                conflict_note="; ".join(conflict_notes[:1]) if conflict_notes else "",
            )
        )
        for item in evidence_ids:
            if item not in selected_evidence_ids:
                selected_evidence_ids.append(item)

    return EvidencePlan(
        items=tuple(items),
        selected_evidence_ids=tuple(selected_evidence_ids),
    )


def select_evidences_for_plan(plan: EvidencePlan, evidences: list[Evidence]) -> list[Evidence]:
    selected: list[Evidence] = []
    selected_ids = set(plan.selected_evidence_ids)
    for evidence in evidences:
        if evidence_id(evidence) in selected_ids:
            selected.append(evidence)
    return selected
