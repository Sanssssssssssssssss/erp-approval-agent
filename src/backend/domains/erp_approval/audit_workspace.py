from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any

from src.backend.domains.erp_approval.audit_workspace_models import (
    AuditPackageExport,
    ReviewerNote,
    ReviewerNoteQuery,
    ReviewerNoteWriteResult,
    SavedAuditPackageManifest,
    SavedAuditPackageQuery,
    SavedAuditPackageWriteResult,
)
from src.backend.domains.erp_approval.proposal_ledger_models import (
    PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
    ApprovalAuditPackage,
)


def default_saved_audit_package_path(base_dir: Path) -> Path:
    resolved = Path(base_dir).resolve()
    if resolved.name.lower() == "backend":
        return resolved / "storage" / "erp_approval" / "audit_packages.jsonl"
    return resolved / "backend" / "storage" / "erp_approval" / "audit_packages.jsonl"


def default_reviewer_notes_path(base_dir: Path) -> Path:
    resolved = Path(base_dir).resolve()
    if resolved.name.lower() == "backend":
        return resolved / "storage" / "erp_approval" / "reviewer_notes.jsonl"
    return resolved / "backend" / "storage" / "erp_approval" / "reviewer_notes.jsonl"


def build_saved_audit_package_manifest(
    package: ApprovalAuditPackage,
    title: str,
    description: str,
    created_by: str,
    source_filters: dict[str, Any],
    now: str,
) -> SavedAuditPackageManifest:
    snapshot = package.model_dump()
    package_hash = _stable_hash(snapshot)
    package_id = package.package_id or f"erp-saved-audit-package:{package_hash[:16]}"
    return SavedAuditPackageManifest(
        package_id=package_id,
        title=title.strip() or package_id,
        description=description.strip(),
        created_at=now,
        updated_at=now,
        created_by=created_by.strip() or "local_reviewer",
        trace_ids=list(package.trace_ids),
        proposal_record_ids=list(package.proposal_record_ids),
        source_filters=dict(source_filters or {}),
        package_hash=package_hash,
        package_snapshot=snapshot,
        completeness_summary=dict(package.summary or {}),
        note_count=0,
        non_action_statement=PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
    )


def append_reviewer_note(
    *,
    package_id: str,
    author: str,
    note_type: str,
    body: str,
    now: str,
    trace_id: str = "",
    proposal_record_id: str = "",
) -> ReviewerNote:
    cleaned_body = body.strip()
    source = {
        "package_id": package_id,
        "trace_id": trace_id,
        "proposal_record_id": proposal_record_id,
        "author": author,
        "note_type": note_type,
        "body": cleaned_body,
        "created_at": now,
    }
    return ReviewerNote(
        note_id=f"erp-reviewer-note:{_stable_hash(source)[:16]}",
        package_id=package_id,
        trace_id=trace_id.strip(),
        proposal_record_id=proposal_record_id.strip(),
        author=author.strip() or "local_reviewer",
        note_type=note_type if note_type in _NOTE_TYPES else "general",  # type: ignore[arg-type]
        body=cleaned_body,
        created_at=now,
        non_action_statement=PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
    )


class SavedAuditPackageRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def upsert(self, manifest: SavedAuditPackageManifest) -> SavedAuditPackageWriteResult:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                existing = self._read_all_unlocked()
                created = manifest.package_id not in {item.package_id for item in existing}
                merged: list[SavedAuditPackageManifest] = []
                replaced = False
                for item in existing:
                    if item.package_id == manifest.package_id:
                        merged.append(manifest.model_copy(update={"created_at": item.created_at or manifest.created_at, "note_count": item.note_count}))
                        replaced = True
                    else:
                        merged.append(item)
                if not replaced:
                    merged.append(manifest)
                self._write_all_unlocked(merged)
                return SavedAuditPackageWriteResult(success=True, package_id=manifest.package_id, path=str(self.path), created=created)
            except Exception as exc:
                return SavedAuditPackageWriteResult(success=False, package_id=manifest.package_id, path=str(self.path), error=str(exc))

    def list_recent(self, query: SavedAuditPackageQuery | None = None) -> list[SavedAuditPackageManifest]:
        query = query or SavedAuditPackageQuery()
        with self._lock:
            records = self._read_all_unlocked()
        filtered = [record for record in records if _matches_package_query(record, query)]
        limit = max(0, int(query.limit or 0))
        if limit <= 0:
            return []
        return filtered[-limit:][::-1]

    def get(self, package_id: str) -> SavedAuditPackageManifest | None:
        with self._lock:
            for record in self._read_all_unlocked():
                if record.package_id == package_id:
                    return record
        return None

    def export_package(self, package_id: str) -> AuditPackageExport | None:
        manifest = self.get(package_id)
        if manifest is None:
            return None
        return AuditPackageExport(
            manifest=manifest,
            package_snapshot=dict(manifest.package_snapshot),
            notes=[],
            non_action_statement=PROPOSAL_LEDGER_NON_ACTION_STATEMENT,
        )

    def update_note_count(self, package_id: str, note_count: int, updated_at: str) -> None:
        with self._lock:
            records = self._read_all_unlocked()
            updated: list[SavedAuditPackageManifest] = []
            for record in records:
                if record.package_id == package_id:
                    updated.append(record.model_copy(update={"note_count": note_count, "updated_at": updated_at}))
                else:
                    updated.append(record)
            self._write_all_unlocked(updated)

    def _read_all_unlocked(self) -> list[SavedAuditPackageManifest]:
        if not self.path.exists():
            return []
        records: list[SavedAuditPackageManifest] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(SavedAuditPackageManifest.model_validate(json.loads(line)))
            except Exception:
                continue
        return records

    def _write_all_unlocked(self, records: list[SavedAuditPackageManifest]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            "".join(json.dumps(item.model_dump(), ensure_ascii=False, sort_keys=True) + "\n" for item in records),
            encoding="utf-8",
        )
        tmp.replace(self.path)


class ReviewerNoteRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def append(self, note: ReviewerNote) -> ReviewerNoteWriteResult:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(note.model_dump(), ensure_ascii=False, sort_keys=True) + "\n")
                return ReviewerNoteWriteResult(success=True, note_id=note.note_id, path=str(self.path))
            except Exception as exc:
                return ReviewerNoteWriteResult(success=False, note_id=note.note_id, path=str(self.path), error=str(exc))

    def list_for_package(self, package_id: str) -> list[ReviewerNote]:
        return self.query(ReviewerNoteQuery(package_id=package_id, limit=5000))

    def query(self, query: ReviewerNoteQuery) -> list[ReviewerNote]:
        with self._lock:
            records = self._read_all_unlocked()
        filtered = [record for record in records if _matches_note_query(record, query)]
        limit = max(0, int(query.limit or 0))
        if limit <= 0:
            return []
        return filtered[-limit:][::-1]

    def _read_all_unlocked(self) -> list[ReviewerNote]:
        if not self.path.exists():
            return []
        records: list[ReviewerNote] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(ReviewerNote.model_validate(json.loads(line)))
            except Exception:
                continue
        return records


_NOTE_TYPES = {"general", "risk", "missing_info", "policy_friction", "reviewer_decision", "follow_up"}


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _matches_package_query(record: SavedAuditPackageManifest, query: SavedAuditPackageQuery) -> bool:
    if query.created_by and record.created_by != query.created_by:
        return False
    if query.trace_id and query.trace_id not in record.trace_ids:
        return False
    if query.text_query:
        needle = query.text_query.strip().lower()
        haystack = " ".join([record.package_id, record.title, record.description, record.created_by]).lower()
        if needle and needle not in haystack:
            return False
    return True


def _matches_note_query(record: ReviewerNote, query: ReviewerNoteQuery) -> bool:
    if query.package_id and record.package_id != query.package_id:
        return False
    if query.trace_id and record.trace_id != query.trace_id:
        return False
    if query.proposal_record_id and record.proposal_record_id != query.proposal_record_id:
        return False
    if query.author and record.author != query.author:
        return False
    if query.note_type and record.note_type != query.note_type:
        return False
    return True
