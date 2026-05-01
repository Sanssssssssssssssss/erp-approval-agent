from __future__ import annotations

from src.backend.domains.erp_approval.connectors.coverage_models import (
    ErpConnectorReplayCoverageItem,
    ErpConnectorReplayCoverageSummary,
)
from src.backend.domains.erp_approval.connectors.replay import list_provider_fixtures, replay_provider_fixture
from src.backend.domains.erp_approval.connectors.replay_models import (
    ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    ErpConnectorReplayRequest,
)


def build_replay_coverage_matrix(base_dir, now: str) -> ErpConnectorReplayCoverageSummary:
    items: list[ErpConnectorReplayCoverageItem] = []
    by_provider: dict[str, int] = {}
    by_operation: dict[str, int] = {}
    for fixture in list_provider_fixtures(base_dir):
        replay = replay_provider_fixture(
            base_dir,
            ErpConnectorReplayRequest(
                provider=fixture.provider,
                operation=fixture.operation,
                fixture_name=fixture.fixture_name,
                approval_id="PR-1001",
                correlation_id="coverage-matrix",
                dry_run=True,
                confirm_no_network=True,
            ),
            now,
        )
        passed = replay.status == "success" and replay.validation.passed
        items.append(
            ErpConnectorReplayCoverageItem(
                provider=replay.provider,
                operation=replay.operation,
                fixture_name=replay.fixture_name,
                replay_status=replay.status,
                validation_passed=passed,
                record_count=replay.record_count,
                source_ids=list(replay.source_ids),
                warnings=[*replay.warnings, *replay.validation.warnings],
                failed_checks=list(replay.validation.failed_checks),
            )
        )
        by_provider[replay.provider] = by_provider.get(replay.provider, 0) + 1
        by_operation[replay.operation] = by_operation.get(replay.operation, 0) + 1

    passed_items = sum(1 for item in items if item.validation_passed)
    return ErpConnectorReplayCoverageSummary(
        total_items=len(items),
        passed_items=passed_items,
        failed_items=len(items) - passed_items,
        by_provider=by_provider,
        by_operation=by_operation,
        items=items,
        non_action_statement=ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    )
