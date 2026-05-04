from __future__ import annotations

import json
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.backend.domains.erp_approval.case_state_models import (
    ApprovalCaseState,
    CaseAuditEvent,
    CASE_HARNESS_NON_ACTION_STATEMENT,
)


def default_case_workspace_path(base_dir: Path | str) -> Path:
    resolved = Path(base_dir).resolve()
    if resolved.name.lower() == "backend":
        return resolved / "storage" / "erp_approval" / "cases"
    return resolved / "backend" / "storage" / "erp_approval" / "cases"


class CaseMemoryStore:
    _locks_guard = threading.Lock()
    _case_locks: dict[str, threading.RLock] = {}

    def __init__(self, base_dir: Path | str) -> None:
        self.root = default_case_workspace_path(base_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def case_lock(self, case_id: str) -> Iterator[None]:
        lock = self._lock_for(case_id)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    @classmethod
    def _lock_for(cls, case_id: str) -> threading.RLock:
        safe_id = _safe_case_id(case_id)
        with cls._locks_guard:
            lock = cls._case_locks.get(safe_id)
            if lock is None:
                lock = threading.RLock()
                cls._case_locks[safe_id] = lock
            return lock

    def case_dir(self, case_id: str) -> Path:
        safe_id = _safe_case_id(case_id)
        path = (self.root / safe_id).resolve()
        root = self.root.resolve()
        if not str(path).startswith(str(root)):
            raise ValueError(f"Unsafe case_id path: {case_id}")
        path.mkdir(parents=True, exist_ok=True)
        (path / "evidence").mkdir(parents=True, exist_ok=True)
        return path

    def get(self, case_id: str) -> ApprovalCaseState | None:
        path = self.case_dir(case_id) / "case_state.json"
        if not path.exists():
            return None
        return ApprovalCaseState.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def upsert(self, state: ApprovalCaseState) -> ApprovalCaseState:
        path = self.case_dir(state.case_id) / "case_state.json"
        _atomic_write_text(path, json.dumps(state.model_dump(), ensure_ascii=False, indent=2, sort_keys=True))
        return state

    def append_audit_event(self, event: CaseAuditEvent) -> None:
        path = self.case_dir(event.case_id) / "audit_log.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(), ensure_ascii=False, sort_keys=True) + "\n")

    def read_audit_events(self, case_id: str, limit: int = 100) -> list[CaseAuditEvent]:
        path = self.case_dir(case_id) / "audit_log.jsonl"
        if not path.exists():
            return []
        events: list[CaseAuditEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(CaseAuditEvent.model_validate(json.loads(line)))
            except Exception:
                continue
        return events[-limit:]

    def append_conversation_message(self, case_id: str, message: dict) -> None:
        path = self.case_dir(case_id) / "conversation.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message, ensure_ascii=False, sort_keys=True) + "\n")

    def read_conversation_messages(self, case_id: str, limit: int = 200) -> list[dict]:
        path = self.case_dir(case_id) / "conversation.jsonl"
        if not path.exists():
            return []
        messages: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    messages.append(parsed)
            except Exception:
                continue
        return messages[-limit:]

    def write_dossier(self, case_id: str, dossier: str) -> None:
        _atomic_write_text(self.case_dir(case_id).joinpath("dossier.md"), dossier)

    def read_dossier(self, case_id: str) -> str:
        path = self.case_dir(case_id) / "dossier.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_evidence_text(self, case_id: str, source_id: str, content: str) -> str:
        filename = _safe_case_id(source_id).replace("local_evidence-", "evidence-", 1) + ".md"
        path = self.case_dir(case_id) / "evidence" / filename
        _atomic_write_text(path, content.rstrip() + "\n")
        return str(path)

    def list_recent(self, limit: int = 50) -> list[ApprovalCaseState]:
        states: list[ApprovalCaseState] = []
        for path in self.root.glob("*/case_state.json"):
            try:
                states.append(ApprovalCaseState.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
        states.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return states[:limit]

    def paths_for(self, case_id: str) -> dict[str, str]:
        case_dir = self.case_dir(case_id)
        return {
            "case_dir": str(case_dir),
            "case_state": str(case_dir / "case_state.json"),
            "dossier": str(case_dir / "dossier.md"),
            "audit_log": str(case_dir / "audit_log.jsonl"),
            "conversation": str(case_dir / "conversation.jsonl"),
            "evidence_dir": str(case_dir / "evidence"),
            "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
        }


def _safe_case_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "unidentified").strip()).strip("-")
    return cleaned[:120] or "unidentified"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{threading.get_ident()}")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)
