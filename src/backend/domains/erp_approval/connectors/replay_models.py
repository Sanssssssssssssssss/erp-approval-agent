from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.connectors.models import ErpConnectorProvider, ErpReadOperation
from src.backend.domains.erp_approval.schemas import ApprovalContextRecord


ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT = "Fixture replay only. No ERP network or write action was executed."
ErpConnectorReplayStatus = Literal["success", "warning", "failed", "blocked"]


class ErpConnectorReplayRequest(BaseModel):
    provider: ErpConnectorProvider
    operation: ErpReadOperation
    fixture_name: str
    approval_id: str = ""
    correlation_id: str = ""
    dry_run: bool = True
    confirm_no_network: bool = True


class ErpConnectorReplayValidation(BaseModel):
    passed: bool = False
    warnings: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    checked_fields: list[str] = Field(default_factory=list)
    non_action_statement: str = ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT


class ErpConnectorReplayRecord(BaseModel):
    replay_id: str
    provider: ErpConnectorProvider
    operation: ErpReadOperation
    fixture_name: str
    status: ErpConnectorReplayStatus = "blocked"
    records: list[ApprovalContextRecord] = Field(default_factory=list)
    record_count: int = 0
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validation: ErpConnectorReplayValidation = Field(default_factory=ErpConnectorReplayValidation)
    created_at: str = ""
    dry_run: bool = True
    network_accessed: bool = False
    non_action_statement: str = ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT


class ErpConnectorReplaySummary(BaseModel):
    total_fixtures: int = 0
    total_replays: int = 0
    by_provider: dict[str, int] = Field(default_factory=dict)
    non_action_statement: str = ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT


class ErpConnectorReplayFixtureInfo(BaseModel):
    provider: ErpConnectorProvider
    operation: ErpReadOperation
    fixture_name: str
    display_name: str = ""
    source_id_prefix: str = ""
    non_action_statement: str = ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT
