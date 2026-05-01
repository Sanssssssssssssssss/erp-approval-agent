from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from src.backend.domains.erp_approval.action_simulation_models import (
    ApprovalActionSimulationListResponse,
    ApprovalActionSimulationQuery,
    ApprovalActionSimulationRecord,
    ApprovalActionSimulationWriteResult,
)


def default_action_simulation_path(base_dir: Path) -> Path:
    resolved = Path(base_dir).resolve()
    if resolved.name.lower() == "backend":
        return resolved / "storage" / "erp_approval" / "action_simulations.jsonl"
    return resolved / "backend" / "storage" / "erp_approval" / "action_simulations.jsonl"


class ApprovalActionSimulationRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def upsert(self, record: ApprovalActionSimulationRecord) -> ApprovalActionSimulationWriteResult:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                existing = self._read_all_unlocked()
                by_id = {item.simulation_id: item for item in existing}
                created = record.simulation_id not in by_id
                previous = by_id.get(record.simulation_id)
                by_id[record.simulation_id] = record.model_copy(
                    update={"created_at": previous.created_at if previous and previous.created_at else record.created_at}
                )
                self._write_all_unlocked(list(by_id.values()))
                return ApprovalActionSimulationWriteResult(
                    success=True,
                    simulation_id=record.simulation_id,
                    path=str(self.path),
                    created=created,
                )
            except Exception as exc:
                return ApprovalActionSimulationWriteResult(
                    success=False,
                    simulation_id=record.simulation_id,
                    path=str(self.path),
                    error=str(exc),
                )

    def list_recent(self, query: ApprovalActionSimulationQuery | None = None) -> list[ApprovalActionSimulationRecord]:
        query = query or ApprovalActionSimulationQuery()
        with self._lock:
            records = self._read_all_unlocked()
        filtered = [record for record in records if _matches_query(record, query)]
        limit = max(0, int(query.limit or 0))
        if limit <= 0:
            return []
        return filtered[-limit:][::-1]

    def get(self, simulation_id: str) -> ApprovalActionSimulationRecord | None:
        with self._lock:
            for record in self._read_all_unlocked():
                if record.simulation_id == simulation_id:
                    return record
        return None

    def by_proposal_record_id(self, proposal_record_id: str) -> list[ApprovalActionSimulationRecord]:
        return self.list_recent(ApprovalActionSimulationQuery(proposal_record_id=proposal_record_id, limit=5000))

    def list_response(self, query: ApprovalActionSimulationQuery) -> ApprovalActionSimulationListResponse:
        simulations = self.list_recent(query)
        return ApprovalActionSimulationListResponse(simulations=simulations, total=len(simulations), query=query)

    def _read_all_unlocked(self) -> list[ApprovalActionSimulationRecord]:
        if not self.path.exists():
            return []
        records: list[ApprovalActionSimulationRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(ApprovalActionSimulationRecord.model_validate(json.loads(line)))
            except Exception:
                continue
        return records

    def _write_all_unlocked(self, records: list[ApprovalActionSimulationRecord]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            "".join(json.dumps(item.model_dump(), ensure_ascii=False, sort_keys=True) + "\n" for item in records),
            encoding="utf-8",
        )
        tmp.replace(self.path)


def _matches_query(record: ApprovalActionSimulationRecord, query: ApprovalActionSimulationQuery) -> bool:
    if query.proposal_record_id and record.proposal_record_id != query.proposal_record_id:
        return False
    if query.package_id and record.package_id != query.package_id:
        return False
    if query.trace_id and record.trace_id != query.trace_id:
        return False
    if query.approval_id and record.approval_id != query.approval_id:
        return False
    if query.action_type and record.action_type != query.action_type:
        return False
    if query.status and record.status != query.status:
        return False
    if query.requested_by and record.requested_by != query.requested_by:
        return False
    return True
