from __future__ import annotations

from pydantic import BaseModel, Field

from src.backend.domains.erp_approval.connectors.replay_models import ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT


class ErpConnectorReplayCoverageItem(BaseModel):
    provider: str
    operation: str
    fixture_name: str
    replay_status: str
    validation_passed: bool = False
    record_count: int = 0
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)


class ErpConnectorReplayCoverageSummary(BaseModel):
    total_items: int = 0
    passed_items: int = 0
    failed_items: int = 0
    by_provider: dict[str, int] = Field(default_factory=dict)
    by_operation: dict[str, int] = Field(default_factory=dict)
    items: list[ErpConnectorReplayCoverageItem] = Field(default_factory=list)
    non_action_statement: str = ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT
