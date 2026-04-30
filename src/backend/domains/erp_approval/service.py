from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from src.backend.domains.erp_approval.schemas import (
    ApprovalContextBundle,
    ApprovalGuardResult,
    ApprovalRecommendation,
    ApprovalRequest,
)


FINAL_ACTION_TERMS = {
    "approve",
    "reject",
    "final_approve",
    "final_reject",
    "execute_approve",
    "execute_reject",
    "approve_request",
    "reject_request",
    "issue_payment",
    "execute_payment",
    "release_payment",
    "onboard_supplier",
    "activate_supplier",
    "update_budget",
    "execute_budget",
    "execute_contract",
    "sign_contract",
}
FINAL_ACTION_KEYWORDS = ("approve", "reject", "payment", "supplier", "vendor", "budget", "contract")


def extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "")
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("No JSON object found")


def parse_approval_request(text: str, raw_user_message: str) -> ApprovalRequest:
    try:
        payload = extract_json_object(text)
        request = ApprovalRequest.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        request = ApprovalRequest(raw_request=str(raw_user_message or text or ""), business_purpose=str(raw_user_message or text or "")[:500])
    if not request.raw_request:
        request = request.model_copy(update={"raw_request": str(raw_user_message or text or "")})
    return request


def parse_recommendation(text: str) -> ApprovalRecommendation:
    try:
        payload = extract_json_object(text)
        return ApprovalRecommendation.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        return ApprovalRecommendation(
            status="request_more_info",
            confidence=0.0,
            summary="The approval recommendation could not be parsed into the required JSON schema.",
            rationale=["Fallback recommendation created because the model output was not valid JSON for the ERP approval schema."],
            missing_information=["valid structured approval recommendation"],
            risk_flags=["unparsed_model_output"],
            citations=[],
            proposed_next_action="request_more_info",
            human_review_required=True,
        )


def guard_recommendation(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
) -> tuple[ApprovalRecommendation, ApprovalGuardResult]:
    del request
    warnings: list[str] = []
    updates: dict[str, Any] = {}
    original_status = recommendation.status
    context_source_ids = {record.source_id for record in context.records}

    if recommendation.status == "recommend_approve" and recommendation.missing_information:
        updates["status"] = "request_more_info"
        updates["proposed_next_action"] = "request_more_info"
        updates["human_review_required"] = True
        warnings.append("recommend_approve downgraded because missing_information is present.")

    effective_status = str(updates.get("status", recommendation.status))
    if effective_status == "recommend_approve" and recommendation.confidence < 0.72:
        updates["status"] = "escalate"
        updates["proposed_next_action"] = "manual_review"
        updates["human_review_required"] = True
        warnings.append("recommend_approve downgraded because confidence is below 0.72.")

    proposed_action = str(updates.get("proposed_next_action", recommendation.proposed_next_action) or "")
    normalized_action = proposed_action.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_action in FINAL_ACTION_TERMS or normalized_action.startswith("execute_"):
        updates["proposed_next_action"] = "manual_review"
        updates["human_review_required"] = True
        warnings.append("Proposed irreversible ERP execution action replaced with manual_review.")
    elif normalized_action not in {
        "none",
        "request_more_info",
        "route_to_manager",
        "route_to_finance",
        "route_to_procurement",
        "route_to_legal",
        "manual_review",
    } and any(keyword in normalized_action for keyword in FINAL_ACTION_KEYWORDS):
        updates["proposed_next_action"] = "manual_review"
        updates["human_review_required"] = True
        warnings.append("Proposed ERP write-like action replaced with manual_review.")

    if not recommendation.citations:
        updates["human_review_required"] = True
        warnings.append("No citations were provided; human review is required.")
        if str(updates.get("status", recommendation.status)) == "recommend_approve":
            updates["status"] = "escalate"
            updates["proposed_next_action"] = "manual_review"
            warnings.append("recommend_approve downgraded because no citations were provided.")
    else:
        invalid_citations = [citation for citation in recommendation.citations if citation not in context_source_ids]
        if invalid_citations:
            updates["human_review_required"] = True
            warnings.append("Unknown citation source_id values: " + ", ".join(invalid_citations))
            if str(updates.get("status", recommendation.status)) == "recommend_approve":
                updates["status"] = "escalate"
                updates["proposed_next_action"] = "manual_review"
                warnings.append("recommend_approve downgraded because citations are outside the current context bundle.")

    final_status = str(updates.get("status", recommendation.status))
    if final_status in {"blocked", "recommend_reject", "escalate", "request_more_info"} or recommendation.missing_information:
        updates["human_review_required"] = True

    guarded = recommendation.model_copy(update=updates) if updates else recommendation
    guard = ApprovalGuardResult(
        passed=not warnings,
        downgraded=guarded.status != original_status,
        original_status=original_status,
        final_status=guarded.status,
        warnings=warnings,
        human_review_required=guarded.human_review_required,
    )
    return guarded, guard


def validate_approval_recommendation(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
) -> tuple[ApprovalRecommendation, ApprovalGuardResult]:
    return guard_recommendation(request, context, recommendation)


def render_recommendation(
    request: ApprovalRequest,
    context: ApprovalContextBundle,
    recommendation: ApprovalRecommendation,
    guard: ApprovalGuardResult,
) -> str:
    model_citations = list(recommendation.citations)
    fallback_sources = [] if model_citations else [record.source_id for record in context.records[:2]]
    lines = [
        "ERP approval recommendation",
        "",
        f"Status: {recommendation.status}",
        f"Confidence: {recommendation.confidence:.2f}",
        f"Next action: {recommendation.proposed_next_action}",
        f"Human review required: {'yes' if recommendation.human_review_required else 'no'}",
        "",
        f"Summary: {recommendation.summary or 'No summary provided.'}",
    ]
    if recommendation.rationale:
        lines.extend(["", "Rationale:"])
        lines.extend(f"- {item}" for item in recommendation.rationale)
    if recommendation.missing_information:
        lines.extend(["", "Missing information:"])
        lines.extend(f"- {item}" for item in recommendation.missing_information)
    if recommendation.risk_flags:
        lines.extend(["", "Risk flags:"])
        lines.extend(f"- {item}" for item in recommendation.risk_flags)
    if guard.warnings:
        lines.extend(["", "Guard notes:"])
        lines.extend(f"- {item}" for item in guard.warnings)
    lines.extend(["", "Model citations:"])
    if model_citations:
        lines.extend(f"- {item}" for item in model_citations)
    else:
        lines.append("- none provided by model")
    if fallback_sources:
        lines.extend(["", "Fallback context sources (not model citations):"])
        lines.extend(f"- {item}" for item in fallback_sources)
    lines.extend(
        [
            "",
            f"Approval request: {request.approval_type} / {request.approval_id or 'unidentified'}",
            "No ERP approval, rejection, payment, supplier, contract, or budget action was executed.",
        ]
    )
    return "\n".join(lines).strip()
