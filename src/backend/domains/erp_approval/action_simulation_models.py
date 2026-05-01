from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ACTION_SIMULATION_NON_ACTION_STATEMENT = "This is a local simulation only. No ERP write action was executed."
ApprovalActionSimulationMode = Literal["dry_run"]
ApprovalActionSimulationStatus = Literal["simulated", "blocked", "rejected_by_validation"]


class ApprovalActionSimulationRequest(BaseModel):
    proposal_record_id: str = ""
    package_id: str = ""
    requested_by: str = ""
    simulation_mode: ApprovalActionSimulationMode = "dry_run"
    confirm_no_erp_write: bool = False
    note: str = ""


class ApprovalActionSimulationValidationResult(BaseModel):
    passed: bool = False
    warnings: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    non_action_statement: str = ACTION_SIMULATION_NON_ACTION_STATEMENT


class ApprovalActionSimulationRecord(BaseModel):
    simulation_id: str = ""
    proposal_record_id: str = ""
    package_id: str = ""
    trace_id: str = ""
    approval_id: str = ""
    action_type: str = ""
    requested_by: str = ""
    simulation_mode: ApprovalActionSimulationMode = "dry_run"
    status: ApprovalActionSimulationStatus = "blocked"
    created_at: str = ""
    idempotency_key: str = ""
    idempotency_fingerprint: str = ""
    proposal_idempotency_key: str = ""
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    output_preview: dict[str, Any] = Field(default_factory=dict)
    validation_warnings: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    simulated_only: bool = True
    erp_write_executed: bool = False
    non_action_statement: str = ACTION_SIMULATION_NON_ACTION_STATEMENT


class ApprovalActionSimulationWriteResult(BaseModel):
    success: bool = False
    simulation_id: str = ""
    path: str = ""
    created: bool = False
    error: str = ""


class ApprovalActionSimulationQuery(BaseModel):
    limit: int = Field(default=100, ge=0, le=5000)
    proposal_record_id: str | None = None
    package_id: str | None = None
    trace_id: str | None = None
    approval_id: str | None = None
    action_type: str | None = None
    status: str | None = None
    requested_by: str | None = None


class ApprovalActionSimulationListResponse(BaseModel):
    simulations: list[ApprovalActionSimulationRecord] = Field(default_factory=list)
    total: int = 0
    query: ApprovalActionSimulationQuery = Field(default_factory=ApprovalActionSimulationQuery)
