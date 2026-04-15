from __future__ import annotations

import re

from src.backend.domains.rfp_security.schemas import RfpSecurityQuestion


_APPROVAL_TERMS = (
    "customer reference",
    "named customer",
    "penetration test",
    "fedramp",
    "contract commit",
    "legal commitment",
    "breach count",
)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        candidate = str(value or "").strip()
        lowered = candidate.lower()
        if candidate and lowered not in seen:
            seen.add(lowered)
            ordered.append(candidate)
    return tuple(ordered)


def _question_kind(query: str, tags: tuple[str, ...], risk_level: str) -> str:
    lowered = query.lower()
    if risk_level in {"high", "critical"} or any("approval" in tag for tag in tags):
        return "approval_review"
    if any(tag.startswith("conflict") for tag in tags) or "conflict" in lowered:
        return "conflict_review"
    if any(tag.startswith("missing") for tag in tags) or "missing evidence" in lowered:
        return "missing_evidence_check"
    if "section" in lowered or "rfp" in lowered:
        return "section_draft"
    return "questionnaire_field"


def _answer_template_kind(query: str, tags: tuple[str, ...], required_points: tuple[str, ...]) -> str:
    lowered = query.lower()
    joined_points = " ".join(required_points).lower()
    if any(token in lowered or token in joined_points for token in ("sso", "scim", "mfa", "supported", "available", "protocol")):
        return "yes_no_capability"
    if any(token in lowered or token in joined_points for token in ("fedramp", "soc 2", "pci", "iso", "attestation", "authorization", "compliance")):
        return "certification_compliance"
    if any(token in lowered or token in joined_points for token in ("timeline", "rto", "rpo", "sla", "support", "24 hours", "15 minutes", "4 hours")):
        return "sla_support"
    if any(token in lowered or token in joined_points for token in ("hosting", "region", "residency", "subprocessor", "encryption", "architecture", "deployment")):
        return "deployment_security_architecture"
    if any(token in lowered or token in joined_points for token in ("approval", "policy", "procedure", "reference", "report", "contract")) or any(
        "approval" in tag or "conflict" in tag for tag in tags
    ):
        return "policy_process"
    if lowered.startswith(("is ", "can ", "does ", "which ", "what ")) or any(
        token in lowered for token in ("supported", "available", "provide", "confirm")
    ):
        return "yes_no_capability"
    return "general_rfp"


def _search_terms(query: str, required_points: tuple[str, ...]) -> tuple[str, ...]:
    tokens = re.split(r"[^a-zA-Z0-9]+", query)
    keywords = [token for token in tokens if len(token) >= 4]
    return _dedupe(list(required_points) + keywords[:10])


def _normalized_query(query: str, required_points: tuple[str, ...], search_terms: tuple[str, ...]) -> str:
    normalized_query = " ".join(str(query or "").split())
    clauses = [normalized_query]
    if required_points:
        clauses.append("Focus points: " + "; ".join(required_points[:5]))
    extra_terms = [term for term in search_terms if term.lower() not in normalized_query.lower()]
    if extra_terms:
        clauses.append("Keywords: " + ", ".join(extra_terms[:8]))
    return " ".join(clause.strip() for clause in clauses if clause.strip())


def normalize_rfp_security_query(
    query: str,
    *,
    tags: list[str] | tuple[str, ...] | None = None,
    risk_level: str = "medium",
    required_points: list[str] | tuple[str, ...] | None = None,
) -> RfpSecurityQuestion:
    normalized_tags = _dedupe([str(item).strip().lower() for item in list(tags or []) if str(item).strip()])
    normalized_points = _dedupe([str(item) for item in list(required_points or []) if str(item).strip()])
    clean_query = " ".join(str(query or "").split())
    search_terms = _search_terms(clean_query, normalized_points)
    approval_terms = tuple(
        term for term in _APPROVAL_TERMS if term in query.lower() or term.replace(" ", "_") in " ".join(normalized_tags)
    )
    kind = _question_kind(query, normalized_tags, str(risk_level or "medium").strip().lower())
    return RfpSecurityQuestion(
        query=query,
        normalized_query=_normalized_query(clean_query, normalized_points, search_terms),
        question_kind=kind,  # type: ignore[arg-type]
        answer_template_kind=_answer_template_kind(clean_query, normalized_tags, normalized_points),  # type: ignore[arg-type]
        tags=normalized_tags,
        risk_level=str(risk_level or "medium").strip().lower() or "medium",
        required_points=normalized_points,
        approval_terms=approval_terms,
        search_terms=search_terms,
    )
