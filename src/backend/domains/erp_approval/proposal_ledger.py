from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any

from src.backend.domains.erp_approval.proposal_ledger_models import (
    PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
    ApprovalActionProposalListResponse,
    ApprovalActionProposalQuery,
    ApprovalActionProposalRecord,
    ApprovalActionProposalWriteResult,
    ApprovalAuditCompletenessCheck,
    ApprovalAuditPackage,
    ApprovalAuditPackageProposal,
    ApprovalAuditPackageTrace,
)
from src.backend.domains.erp_approval.trace_models import ApprovalTraceRecord
from src.backend.domains.erp_approval.trace_store import build_trace_record_from_state


def default_proposal_ledger_path(base_dir: Path) -> Path:
    resolved = Path(base_dir).resolve()
    if resolved.name.lower() == "backend":
        return resolved / "storage" / "erp_approval" / "action_proposals.jsonl"
    return resolved / "backend" / "storage" / "erp_approval" / "action_proposals.jsonl"


def build_proposal_records_from_state(state: dict[str, Any], trace_id: str, now: str) -> list[ApprovalActionProposalRecord]:
    request = _dict(state.get("erp_request"))
    recommendation = _dict(state.get("erp_recommendation"))
    bundle = _dict(state.get("erp_action_proposals"))
    validation = _dict(state.get("erp_action_validation_result"))
    proposals = [item for item in bundle.get("proposals", []) or [] if isinstance(item, dict)]
    warnings = _list_of_strings(validation.get("warnings"))
    blocked_ids = set(_list_of_strings(validation.get("blocked_proposal_ids")))
    rejected_ids = set(_list_of_strings(validation.get("rejected_proposal_ids")))
    records: list[ApprovalActionProposalRecord] = []
    for proposal in proposals:
        proposal_id = str(proposal.get("proposal_id", "") or "")
        if not proposal_id:
            continue
        record_id = f"erp-proposal-record:{proposal_id}:{trace_id}"
        status = str(proposal.get("status", "") or "")
        records.append(
            ApprovalActionProposalRecord(
                proposal_record_id=record_id,
                proposal_id=proposal_id,
                trace_id=trace_id,
                run_id=str(state.get("run_id", "") or ""),
                session_id=str(state.get("session_id")) if state.get("session_id") is not None else None,
                thread_id=str(state.get("thread_id", "") or ""),
                turn_id=str(state.get("turn_id", "") or ""),
                approval_id=str(request.get("approval_id", "") or bundle.get("request_id", "") or ""),
                approval_type=str(request.get("approval_type", "") or "unknown"),
                created_at=now,
                updated_at=now,
                review_status=str(state.get("erp_review_status", "") or bundle.get("review_status", "") or ""),
                recommendation_status=str(recommendation.get("status", "") or ""),
                action_type=str(proposal.get("action_type", "") or ""),
                status=status,
                title=str(proposal.get("title", "") or ""),
                summary=str(proposal.get("summary", "") or ""),
                target=str(proposal.get("target", "") or ""),
                payload_preview=_dict(proposal.get("payload_preview")),
                citations=_list_of_strings(proposal.get("citations")),
                idempotency_key=str(proposal.get("idempotency_key", "") or ""),
                idempotency_scope=str(proposal.get("idempotency_scope", "") or ""),
                idempotency_fingerprint=str(proposal.get("idempotency_fingerprint", "") or ""),
                risk_level=str(proposal.get("risk_level", "") or ""),
                requires_human_review=bool(proposal.get("requires_human_review", True)),
                executable=False,
                non_action_statement=PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
                validation_warnings=[warning for warning in warnings if proposal_id in warning] or warnings,
                blocked=proposal_id in blocked_ids or status == "blocked",
                rejected_by_validation=proposal_id in rejected_ids or status == "rejected_by_validation",
            )
        )
    return records


class ApprovalActionProposalRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def upsert_many(self, records: list[ApprovalActionProposalRecord]) -> list[ApprovalActionProposalWriteResult]:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                existing = self._read_all_unlocked()
                by_id = {record.proposal_record_id: record for record in existing}
                results: list[ApprovalActionProposalWriteResult] = []
                for record in records:
                    created = record.proposal_record_id not in by_id
                    previous = by_id.get(record.proposal_record_id)
                    by_id[record.proposal_record_id] = record.model_copy(
                        update={"created_at": previous.created_at if previous and previous.created_at else record.created_at}
                    )
                    results.append(
                        ApprovalActionProposalWriteResult(
                            success=True,
                            proposal_record_id=record.proposal_record_id,
                            path=str(self.path),
                            created=created,
                        )
                    )
                merged = list(by_id.values())
                tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                tmp.write_text(
                    "".join(json.dumps(item.model_dump(), ensure_ascii=False, sort_keys=True) + "\n" for item in merged),
                    encoding="utf-8",
                )
                tmp.replace(self.path)
                return results
            except Exception as exc:
                return [
                    ApprovalActionProposalWriteResult(
                        success=False,
                        proposal_record_id=record.proposal_record_id,
                        path=str(self.path),
                        error=str(exc),
                    )
                    for record in records
                ]

    def list_recent(self, limit: int = 100) -> list[ApprovalActionProposalRecord]:
        with self._lock:
            records = self._read_all_unlocked()
        limit = max(0, int(limit or 0))
        if limit <= 0:
            return []
        return records[-limit:][::-1]

    def get(self, proposal_record_id: str) -> ApprovalActionProposalRecord | None:
        with self._lock:
            for record in self._read_all_unlocked():
                if record.proposal_record_id == proposal_record_id:
                    return record
        return None

    def by_trace_id(self, trace_id: str) -> list[ApprovalActionProposalRecord]:
        return self.query(ApprovalActionProposalQuery(trace_id=trace_id, limit=5000))

    def query(self, query: ApprovalActionProposalQuery) -> list[ApprovalActionProposalRecord]:
        with self._lock:
            records = self._read_all_unlocked()
        filtered = [record for record in records if _matches_query(record, query)]
        limit = max(0, int(query.limit or 0))
        if limit <= 0:
            return []
        return filtered[-limit:][::-1]

    def list_response(self, query: ApprovalActionProposalQuery) -> ApprovalActionProposalListResponse:
        proposals = self.query(query)
        return ApprovalActionProposalListResponse(proposals=proposals, total=len(proposals), query=query)

    def _read_all_unlocked(self) -> list[ApprovalActionProposalRecord]:
        if not self.path.exists():
            return []
        records: list[ApprovalActionProposalRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(ApprovalActionProposalRecord.model_validate(json.loads(line)))
            except Exception:
                continue
        return records


def build_audit_package(
    traces: list[ApprovalTraceRecord],
    proposals: list[ApprovalActionProposalRecord],
    now: str,
) -> ApprovalAuditPackage:
    trace_ids = [trace.trace_id for trace in traces]
    proposal_ids = [proposal.proposal_record_id for proposal in proposals]
    package_source = {"trace_ids": trace_ids, "proposal_record_ids": proposal_ids}
    digest = hashlib.sha256(json.dumps(package_source, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    checks: list[ApprovalAuditCompletenessCheck] = []
    proposals_by_trace: dict[str, list[ApprovalActionProposalRecord]] = {}
    for proposal in proposals:
        proposals_by_trace.setdefault(proposal.trace_id, []).append(proposal)
    for trace in traces:
        checks.extend(run_completeness_checks(trace, proposals_by_trace.get(trace.trace_id, [])))
    summary = {
        "trace_count": len(traces),
        "proposal_count": len(proposals),
        "failed_check_count": len([check for check in checks if not check.passed]),
        "error_check_count": len([check for check in checks if not check.passed and check.severity == "error"]),
        "warning_check_count": len([check for check in checks if not check.passed and check.severity == "warning"]),
    }
    return ApprovalAuditPackage(
        package_id=f"erp-audit-package:{digest}",
        created_at=now,
        trace_ids=trace_ids,
        proposal_record_ids=proposal_ids,
        traces=[_audit_trace(trace) for trace in traces],
        proposals=[_audit_proposal(proposal) for proposal in proposals],
        completeness_checks=checks,
        summary=summary,
        non_action_statement=PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
    )


def run_completeness_checks(
    trace: ApprovalTraceRecord,
    proposals: list[ApprovalActionProposalRecord],
) -> list[ApprovalAuditCompletenessCheck]:
    context_sources = set(trace.context_source_ids)
    checks = [
        _check("has_approval_request", bool(trace.approval_id), "error", "Trace includes an approval request identifier."),
        _check("has_context_sources", bool(trace.context_source_ids), "warning", "Trace includes context source IDs."),
        _check("has_recommendation_status", bool(trace.recommendation_status), "error", "Trace includes a recommendation status."),
        _check("has_citations", bool(trace.citations), "warning", "Trace includes model citations."),
        _check("has_guard_result", bool(trace.guard_warnings or trace.guard_downgraded or trace.guard_warnings == []), "info", "Trace includes guard summary fields."),
        _check("has_review_status", bool(trace.review_status), "warning", "Trace includes human review status."),
        _check("has_action_proposals", bool(proposals), "warning", "Trace has action proposal records."),
    ]
    for proposal in proposals:
        prefix = f"{proposal.proposal_id}: "
        checks.extend(
            [
                _check(
                    "proposal_has_idempotency",
                    bool(proposal.idempotency_key and proposal.idempotency_fingerprint),
                    "error",
                    prefix + "Proposal includes idempotency key and fingerprint.",
                ),
                _check(
                    "proposal_executable_false",
                    proposal.executable is False,
                    "error",
                    prefix + "Proposal remains non-executable.",
                ),
                _check(
                    "proposal_has_non_action_statement",
                    "No ERP write action was executed" in proposal.non_action_statement,
                    "error",
                    prefix + "Proposal states that no ERP write action was executed.",
                ),
                _check(
                    "proposal_citations_present_in_trace_context",
                    all(citation in context_sources for citation in proposal.citations),
                    "warning",
                    prefix + "Proposal citations are present in trace context source IDs.",
                ),
            ]
        )
    return checks


def trace_id_from_state(state: dict[str, Any]) -> str:
    return build_trace_record_from_state(state, "").trace_id


def _matches_query(record: ApprovalActionProposalRecord, query: ApprovalActionProposalQuery) -> bool:
    if query.action_type and record.action_type != query.action_type:
        return False
    if query.status and record.status != query.status:
        return False
    if query.approval_id and record.approval_id != query.approval_id:
        return False
    if query.trace_id and record.trace_id != query.trace_id:
        return False
    if query.risk_level and record.risk_level != query.risk_level:
        return False
    if query.requires_human_review is not None and record.requires_human_review != query.requires_human_review:
        return False
    if query.blocked is not None and record.blocked != query.blocked:
        return False
    if query.rejected_by_validation is not None and record.rejected_by_validation != query.rejected_by_validation:
        return False
    return True


def _audit_trace(trace: ApprovalTraceRecord) -> ApprovalAuditPackageTrace:
    return ApprovalAuditPackageTrace(
        trace_id=trace.trace_id,
        approval_id=trace.approval_id,
        approval_type=trace.approval_type,
        created_at=trace.created_at,
        recommendation_status=trace.recommendation_status,
        review_status=trace.review_status,
        context_source_ids=list(trace.context_source_ids),
        citations=list(trace.citations),
        guard_warnings=list(trace.guard_warnings),
        proposal_ids=list(trace.proposal_ids),
        non_action_statement=PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
    )


def _audit_proposal(proposal: ApprovalActionProposalRecord) -> ApprovalAuditPackageProposal:
    return ApprovalAuditPackageProposal(
        proposal_record_id=proposal.proposal_record_id,
        proposal_id=proposal.proposal_id,
        trace_id=proposal.trace_id,
        approval_id=proposal.approval_id,
        action_type=proposal.action_type,
        status=proposal.status,
        title=proposal.title,
        summary=proposal.summary,
        target=proposal.target,
        citations=list(proposal.citations),
        idempotency_key=proposal.idempotency_key,
        idempotency_scope=proposal.idempotency_scope,
        idempotency_fingerprint=proposal.idempotency_fingerprint,
        risk_level=proposal.risk_level,
        requires_human_review=proposal.requires_human_review,
        executable=False,
        validation_warnings=list(proposal.validation_warnings),
        blocked=proposal.blocked,
        rejected_by_validation=proposal.rejected_by_validation,
        non_action_statement=PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
    )


def _check(check_name: str, passed: bool, severity: str, success_message: str) -> ApprovalAuditCompletenessCheck:
    status = "passed" if passed else "failed"
    return ApprovalAuditCompletenessCheck(
        check_name=check_name,
        passed=passed,
        severity=severity,  # type: ignore[arg-type]
        message=f"{status}: {success_message}",
    )


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_strings(value: Any) -> list[str]:
    return [str(item) for item in value or [] if str(item or "").strip()] if isinstance(value, list) else []
