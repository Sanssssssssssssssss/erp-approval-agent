from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from threading import Lock
from typing import Any

from src.backend.domains.erp_approval.analytics import summarize_trace_trends, summarize_traces
from src.backend.domains.erp_approval.trace_models import (
    ERP_TRACE_NON_ACTION_STATEMENT,
    ApprovalAnalyticsSummary,
    ApprovalTraceListResponse,
    ApprovalTraceQuery,
    ApprovalTraceRecord,
    ApprovalTraceWriteResult,
    ApprovalTrendSummary,
)


FINAL_ANSWER_PREVIEW_LIMIT = 800
CSV_EXPORT_FIELDS = [
    "trace_id",
    "created_at",
    "approval_id",
    "approval_type",
    "recommendation_status",
    "review_status",
    "human_review_required",
    "guard_downgraded",
    "proposal_action_types",
    "blocked_proposal_ids",
    "rejected_proposal_ids",
]


def default_trace_path(base_dir: Path) -> Path:
    resolved = Path(base_dir).resolve()
    if resolved.name.lower() == "backend":
        return resolved / "storage" / "erp_approval" / "approval_traces.jsonl"
    return resolved / "backend" / "storage" / "erp_approval" / "approval_traces.jsonl"


def build_trace_record_from_state(state: dict[str, Any], now: str) -> ApprovalTraceRecord:
    request = _dict(state.get("erp_request"))
    context = _dict(state.get("erp_context"))
    recommendation = _dict(state.get("erp_recommendation"))
    guard = _dict(state.get("erp_guard_result"))
    hitl_decision = _dict(state.get("erp_hitl_decision"))
    proposals_bundle = _dict(state.get("erp_action_proposals"))
    validation = _dict(state.get("erp_action_validation_result"))
    proposals = [item for item in proposals_bundle.get("proposals", []) or [] if isinstance(item, dict)]
    run_id = str(state.get("run_id", "") or "")
    turn_id = str(state.get("turn_id", "") or "")
    trace_id = f"erp-trace:{run_id}:{turn_id or '0'}"
    return ApprovalTraceRecord(
        trace_id=trace_id,
        run_id=run_id,
        session_id=str(state.get("session_id")) if state.get("session_id") is not None else None,
        thread_id=str(state.get("thread_id", "") or ""),
        turn_id=turn_id,
        created_at=now,
        updated_at=now,
        approval_id=str(request.get("approval_id", "") or context.get("request_id", "") or ""),
        approval_type=str(request.get("approval_type", "") or "unknown"),
        requester=str(request.get("requester", "") or ""),
        department=str(request.get("department", "") or ""),
        amount=_float_or_none(request.get("amount")),
        currency=str(request.get("currency", "") or ""),
        vendor=str(request.get("vendor", "") or ""),
        cost_center=str(request.get("cost_center", "") or ""),
        context_source_ids=_context_source_ids(context),
        recommendation_status=str(recommendation.get("status", "") or ""),
        recommendation_confidence=float(recommendation.get("confidence", 0.0) or 0.0),
        human_review_required=bool(recommendation.get("human_review_required", True)),
        missing_information=_list_of_strings(recommendation.get("missing_information")),
        risk_flags=_list_of_strings(recommendation.get("risk_flags")),
        citations=_list_of_strings(recommendation.get("citations")),
        guard_warnings=_list_of_strings(guard.get("warnings")),
        guard_downgraded=bool(guard.get("downgraded", False)),
        review_status=str(state.get("erp_review_status", "") or proposals_bundle.get("review_status", "") or ""),
        hitl_decision=str(hitl_decision.get("decision", "") or ""),
        proposal_ids=_proposal_strings(proposals, "proposal_id"),
        proposal_action_types=_proposal_strings(proposals, "action_type"),
        proposal_statuses=_proposal_strings(proposals, "status"),
        proposal_validation_warnings=_list_of_strings(validation.get("warnings")),
        blocked_proposal_ids=_list_of_strings(validation.get("blocked_proposal_ids")),
        rejected_proposal_ids=_list_of_strings(validation.get("rejected_proposal_ids")),
        final_answer_preview=str(state.get("final_answer", "") or "")[:FINAL_ANSWER_PREVIEW_LIMIT],
        non_action_statement=ERP_TRACE_NON_ACTION_STATEMENT,
    )


class ApprovalTraceRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def upsert(self, record: ApprovalTraceRecord) -> ApprovalTraceWriteResult:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                existing = self._read_all_unlocked()
                created = record.trace_id not in {item.trace_id for item in existing}
                merged: list[ApprovalTraceRecord] = []
                replaced = False
                for item in existing:
                    if item.trace_id == record.trace_id:
                        merged.append(record.model_copy(update={"created_at": item.created_at or record.created_at}))
                        replaced = True
                    else:
                        merged.append(item)
                if not replaced:
                    merged.append(record)
                tmp = self.path.with_suffix(self.path.suffix + ".tmp")
                tmp.write_text(
                    "".join(json.dumps(item.model_dump(), ensure_ascii=False, sort_keys=True) + "\n" for item in merged),
                    encoding="utf-8",
                )
                tmp.replace(self.path)
                return ApprovalTraceWriteResult(success=True, trace_id=record.trace_id, path=str(self.path), created=created)
            except Exception as exc:
                return ApprovalTraceWriteResult(success=False, trace_id=record.trace_id, path=str(self.path), error=str(exc))

    def list_recent(self, limit: int = 100) -> list[ApprovalTraceRecord]:
        with self._lock:
            records = self._read_all_unlocked()
        limit = max(0, int(limit or 0))
        if limit <= 0:
            return []
        return records[-limit:][::-1]

    def query(self, query: ApprovalTraceQuery) -> list[ApprovalTraceRecord]:
        with self._lock:
            records = self._read_all_unlocked()
        filtered = [record for record in records if _matches_query(record, query)]
        limit = max(0, int(query.limit or 0))
        if limit <= 0:
            return []
        return filtered[-limit:][::-1]

    def list_response(self, query: ApprovalTraceQuery) -> ApprovalTraceListResponse:
        records = self.query(query)
        return ApprovalTraceListResponse(traces=records, total=len(records), query=query)

    def get(self, trace_id: str) -> ApprovalTraceRecord | None:
        with self._lock:
            for record in self._read_all_unlocked():
                if record.trace_id == trace_id:
                    return record
        return None

    def summarize(self, limit: int = 500) -> ApprovalAnalyticsSummary:
        records = self.list_recent(limit=limit)
        return summarize_traces(records)

    def export_json(self, query: ApprovalTraceQuery) -> dict[str, Any]:
        records = self.query(query)
        return {
            "query": query.model_dump(),
            "total": len(records),
            "records": [record.model_dump() for record in records],
        }

    def export_csv(self, query: ApprovalTraceQuery) -> str:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=CSV_EXPORT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for record in self.query(query):
            writer.writerow(
                {
                    "trace_id": record.trace_id,
                    "created_at": record.created_at,
                    "approval_id": record.approval_id,
                    "approval_type": record.approval_type,
                    "recommendation_status": record.recommendation_status,
                    "review_status": record.review_status,
                    "human_review_required": str(record.human_review_required).lower(),
                    "guard_downgraded": str(record.guard_downgraded).lower(),
                    "proposal_action_types": ";".join(record.proposal_action_types),
                    "blocked_proposal_ids": ";".join(record.blocked_proposal_ids),
                    "rejected_proposal_ids": ";".join(record.rejected_proposal_ids),
                }
            )
        return output.getvalue()

    def trend_summary(self, query: ApprovalTraceQuery) -> ApprovalTrendSummary:
        return summarize_trace_trends(self.query(query))

    def _read_all_unlocked(self) -> list[ApprovalTraceRecord]:
        if not self.path.exists():
            return []
        records: list[ApprovalTraceRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(ApprovalTraceRecord.model_validate(json.loads(line)))
            except Exception:
                continue
        return records


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_strings(value: Any) -> list[str]:
    return [str(item) for item in value or [] if str(item or "").strip()] if isinstance(value, list) else []


def _context_source_ids(context: dict[str, Any]) -> list[str]:
    records = context.get("records", []) if isinstance(context, dict) else []
    return [str(item.get("source_id", "")) for item in records if isinstance(item, dict) and str(item.get("source_id", "") or "")]


def _proposal_strings(proposals: list[dict[str, Any]], key: str) -> list[str]:
    return [str(item.get(key, "")) for item in proposals if str(item.get(key, "") or "")]


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _matches_query(record: ApprovalTraceRecord, query: ApprovalTraceQuery) -> bool:
    if query.approval_type and record.approval_type != query.approval_type:
        return False
    if query.recommendation_status and record.recommendation_status != query.recommendation_status:
        return False
    if query.review_status and record.review_status != query.review_status:
        return False
    if query.proposal_action_type and query.proposal_action_type not in record.proposal_action_types:
        return False
    if query.human_review_required is not None and record.human_review_required != query.human_review_required:
        return False
    if query.guard_downgraded is not None and record.guard_downgraded != query.guard_downgraded:
        return False
    if query.high_risk_only and not _is_high_risk_trace(record):
        return False
    if query.text_query and not _matches_text_query(record, query.text_query):
        return False
    if query.date_from and not _created_at_gte(record.created_at, query.date_from):
        return False
    if query.date_to and not _created_at_lte(record.created_at, query.date_to):
        return False
    return True


def _is_high_risk_trace(record: ApprovalTraceRecord) -> bool:
    return bool(
        record.risk_flags
        or record.guard_warnings
        or record.blocked_proposal_ids
        or record.recommendation_status in {"blocked", "recommend_reject", "escalate"}
    )


def _matches_text_query(record: ApprovalTraceRecord, text_query: str) -> bool:
    needle = text_query.strip().lower()
    if not needle:
        return True
    fields = [
        record.approval_id,
        record.requester,
        record.department,
        record.vendor,
        record.cost_center,
        record.trace_id,
    ]
    return any(needle in str(value or "").lower() for value in fields)


def _created_at_gte(created_at: str, threshold: str) -> bool:
    if len(threshold) <= 10:
        return (created_at or "")[:10] >= threshold
    return (created_at or "") >= threshold


def _created_at_lte(created_at: str, threshold: str) -> bool:
    if len(threshold) <= 10:
        return (created_at or "")[:10] <= threshold
    return (created_at or "") <= threshold
