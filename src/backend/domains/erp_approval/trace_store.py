from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from src.backend.domains.erp_approval.analytics import summarize_traces
from src.backend.domains.erp_approval.trace_models import (
    ERP_TRACE_NON_ACTION_STATEMENT,
    ApprovalAnalyticsSummary,
    ApprovalTraceRecord,
    ApprovalTraceWriteResult,
)


FINAL_ANSWER_PREVIEW_LIMIT = 800


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

    def get(self, trace_id: str) -> ApprovalTraceRecord | None:
        with self._lock:
            for record in self._read_all_unlocked():
                if record.trace_id == trace_id:
                    return record
        return None

    def summarize(self, limit: int = 500) -> ApprovalAnalyticsSummary:
        records = self.list_recent(limit=limit)
        return summarize_traces(records)

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
