from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.proposal_ledger_models import PROPOSAL_LEDGER_NON_ACTION_STATEMENT


ReviewerNoteType = Literal[
    "general",
    "risk",
    "missing_info",
    "policy_friction",
    "reviewer_decision",
    "follow_up",
]


class SavedAuditPackageManifest(BaseModel):
    package_id: str = ""
    title: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    created_by: str = ""
    trace_ids: list[str] = Field(default_factory=list)
    proposal_record_ids: list[str] = Field(default_factory=list)
    source_filters: dict[str, Any] = Field(default_factory=dict)
    package_hash: str = ""
    package_snapshot: dict[str, Any] = Field(default_factory=dict)
    completeness_summary: dict[str, Any] = Field(default_factory=dict)
    note_count: int = 0
    non_action_statement: str = PROPOSAL_LEDGER_NON_ACTION_STATEMENT


class SavedAuditPackageWriteResult(BaseModel):
    success: bool = False
    package_id: str = ""
    path: str = ""
    created: bool = False
    error: str = ""


class SavedAuditPackageQuery(BaseModel):
    limit: int = Field(default=100, ge=0, le=5000)
    created_by: str | None = None
    trace_id: str | None = None
    text_query: str = ""


class SavedAuditPackageListResponse(BaseModel):
    packages: list[SavedAuditPackageManifest] = Field(default_factory=list)
    total: int = 0
    query: SavedAuditPackageQuery = Field(default_factory=SavedAuditPackageQuery)


class ReviewerNote(BaseModel):
    note_id: str = ""
    package_id: str = ""
    trace_id: str = ""
    proposal_record_id: str = ""
    author: str = ""
    note_type: ReviewerNoteType = "general"
    body: str = ""
    created_at: str = ""
    non_action_statement: str = PROPOSAL_LEDGER_NON_ACTION_STATEMENT


class ReviewerNoteWriteResult(BaseModel):
    success: bool = False
    note_id: str = ""
    path: str = ""
    error: str = ""


class ReviewerNoteQuery(BaseModel):
    limit: int = Field(default=100, ge=0, le=5000)
    package_id: str | None = None
    trace_id: str | None = None
    proposal_record_id: str | None = None
    author: str | None = None
    note_type: ReviewerNoteType | None = None


class AuditPackageExport(BaseModel):
    manifest: SavedAuditPackageManifest
    package_snapshot: dict[str, Any] = Field(default_factory=dict)
    notes: list[ReviewerNote] = Field(default_factory=list)
    non_action_statement: str = PROPOSAL_LEDGER_NON_ACTION_STATEMENT
