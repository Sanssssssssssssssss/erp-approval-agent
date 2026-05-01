from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.backend.domains.erp_approval.action_simulation_models import (
    ACTION_SIMULATION_NON_ACTION_STATEMENT,
    ApprovalActionSimulationRecord,
    ApprovalActionSimulationRequest,
    ApprovalActionSimulationValidationResult,
)
from src.backend.domains.erp_approval.audit_workspace_models import SavedAuditPackageManifest
from src.backend.domains.erp_approval.proposal_ledger_models import ApprovalActionProposalRecord


ALLOWED_SIMULATION_ACTION_TYPES = {
    "request_more_info",
    "add_internal_comment",
    "route_to_manager",
    "route_to_finance",
    "route_to_procurement",
    "route_to_legal",
    "manual_review",
}

_EXECUTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bexecute\b",
        r"\bapprove[d]?\b",
        r"\breject(?:ed)?\b",
        r"\bpaid\b",
        r"\bpayment\b",
        r"\bsupplier\s+activation\b",
        r"\bactivate\s+supplier\b",
        r"\bbudget\s+update\b",
        r"\bupdate\s+budget\b",
        r"\bcontract\s+sign\b",
        r"\bsign\s+contract\b",
        r"\bsent\b",
        r"\bposted\b",
        r"\brouted\b",
        r"\bexecuted\b",
    ]
]

_OUTPUT_PREVIEWS = {
    "request_more_info": "would_prepare_local_request_more_info_draft",
    "add_internal_comment": "would_prepare_local_internal_comment_draft",
    "route_to_manager": "would_prepare_local_routing_draft",
    "route_to_finance": "would_prepare_local_routing_draft",
    "route_to_procurement": "would_prepare_local_routing_draft",
    "route_to_legal": "would_prepare_local_routing_draft",
    "manual_review": "would_prepare_local_manual_review_entry",
}


def validate_simulation_request(
    request: ApprovalActionSimulationRequest,
    proposal_record: ApprovalActionProposalRecord | None,
    saved_package: SavedAuditPackageManifest | None,
) -> ApprovalActionSimulationValidationResult:
    warnings: list[str] = []
    blocked_reasons: list[str] = []

    if not request.confirm_no_erp_write:
        blocked_reasons.append("confirm_no_erp_write must be true before a local simulation can be recorded.")
    if proposal_record is None:
        blocked_reasons.append("proposal_record must exist.")
    if saved_package is None:
        blocked_reasons.append("saved audit package must exist.")
    if saved_package is not None and request.package_id != saved_package.package_id:
        blocked_reasons.append("request package_id must match the saved audit package.")
    if proposal_record is not None and request.proposal_record_id != proposal_record.proposal_record_id:
        blocked_reasons.append("request proposal_record_id must match the proposal record.")
    if proposal_record is not None and saved_package is not None and proposal_record.proposal_record_id not in saved_package.proposal_record_ids:
        blocked_reasons.append("proposal_record_id must belong to the saved audit package.")

    if proposal_record is not None:
        if proposal_record.executable is not False:
            blocked_reasons.append("proposal executable must remain false for simulation.")
        if proposal_record.blocked:
            blocked_reasons.append("proposal is blocked and cannot be simulated as an available future path.")
        if proposal_record.rejected_by_validation:
            blocked_reasons.append("proposal was rejected by validation and cannot be simulated as an available future path.")
        if proposal_record.action_type not in ALLOWED_SIMULATION_ACTION_TYPES:
            blocked_reasons.append(f"action_type {proposal_record.action_type!r} is not allowed for local simulation.")
        if _has_execution_semantics(proposal_record.payload_preview):
            blocked_reasons.append("proposal payload contains ERP execution semantics and cannot be simulated.")
        if "No ERP write action was executed" not in proposal_record.non_action_statement:
            warnings.append("proposal non_action_statement does not explicitly state that no ERP write action was executed.")

    return ApprovalActionSimulationValidationResult(
        passed=not blocked_reasons,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
        non_action_statement=ACTION_SIMULATION_NON_ACTION_STATEMENT,
    )


def build_simulation_record(
    request: ApprovalActionSimulationRequest,
    proposal_record: ApprovalActionProposalRecord,
    saved_package: SavedAuditPackageManifest,
    validation: ApprovalActionSimulationValidationResult,
    now: str,
) -> ApprovalActionSimulationRecord:
    fingerprint_source = {
        "proposal_record_id": request.proposal_record_id,
        "package_id": request.package_id,
        "requested_by": request.requested_by.strip() or "local_reviewer",
        "simulation_mode": request.simulation_mode,
        "note": request.note.strip(),
        "proposal_idempotency_fingerprint": proposal_record.idempotency_fingerprint,
    }
    fingerprint = _stable_hash(fingerprint_source)
    status = _simulation_status(proposal_record, validation)
    output_preview = _output_preview(proposal_record) if status == "simulated" else _blocked_preview(proposal_record, status)
    return ApprovalActionSimulationRecord(
        simulation_id=f"erp-action-simulation:{proposal_record.proposal_record_id}:{saved_package.package_id}:{fingerprint[:16]}",
        proposal_record_id=proposal_record.proposal_record_id,
        package_id=saved_package.package_id,
        trace_id=proposal_record.trace_id,
        approval_id=proposal_record.approval_id,
        action_type=proposal_record.action_type,
        requested_by=request.requested_by.strip() or "local_reviewer",
        simulation_mode=request.simulation_mode,
        status=status,
        created_at=now,
        idempotency_key=f"erp-action-simulation:{proposal_record.proposal_record_id}:{saved_package.package_id}:{fingerprint[:16]}",
        idempotency_fingerprint=fingerprint,
        proposal_idempotency_key=proposal_record.idempotency_key,
        input_snapshot={
            "request": request.model_dump(),
            "proposal_record_id": proposal_record.proposal_record_id,
            "package_id": saved_package.package_id,
            "proposal_executable": proposal_record.executable,
            "proposal_status": proposal_record.status,
        },
        output_preview=output_preview,
        validation_warnings=list(validation.warnings),
        blocked_reasons=list(validation.blocked_reasons),
        simulated_only=True,
        erp_write_executed=False,
        non_action_statement=ACTION_SIMULATION_NON_ACTION_STATEMENT,
    )


def render_simulation_preview(record: ApprovalActionSimulationRecord) -> str:
    lines = [
        "Local action simulation",
        f"- simulation_id: {record.simulation_id}",
        f"- proposal_record_id: {record.proposal_record_id}",
        f"- status: {record.status}",
        f"- simulated_only: {str(record.simulated_only).lower()}",
        f"- erp_write_executed: {str(record.erp_write_executed).lower()}",
        f"- output_preview: {json.dumps(record.output_preview, ensure_ascii=False, sort_keys=True)}",
    ]
    if record.validation_warnings:
        lines.append(f"- validation_warnings: {'; '.join(record.validation_warnings)}")
    if record.blocked_reasons:
        lines.append(f"- blocked_reasons: {'; '.join(record.blocked_reasons)}")
    lines.append(f"- {record.non_action_statement}")
    return "\n".join(lines)


def _simulation_status(
    proposal_record: ApprovalActionProposalRecord,
    validation: ApprovalActionSimulationValidationResult,
):
    if proposal_record.rejected_by_validation:
        return "rejected_by_validation"
    if proposal_record.blocked or not validation.passed:
        return "blocked"
    return "simulated"


def _output_preview(proposal_record: ApprovalActionProposalRecord) -> dict[str, Any]:
    return {
        "preview_type": _OUTPUT_PREVIEWS.get(proposal_record.action_type, "would_prepare_local_manual_review_entry"),
        "action_type": proposal_record.action_type,
        "simulated_only": True,
    }


def _blocked_preview(proposal_record: ApprovalActionProposalRecord, status: str) -> dict[str, Any]:
    return {
        "preview_type": "would_prepare_local_blocked_simulation_notice",
        "action_type": proposal_record.action_type,
        "simulation_availability": "not_available_for_local_simulation",
        "simulated_only": True,
    }


def _has_execution_semantics(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value or "")
    return any(pattern.search(text) for pattern in _EXECUTION_PATTERNS)


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
