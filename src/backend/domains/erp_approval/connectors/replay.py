from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.backend.domains.erp_approval.connectors.mappers import map_provider_payload_to_records
from src.backend.domains.erp_approval.connectors.models import ErpConnectorProvider, ErpReadOperation, ErpReadRequest
from src.backend.domains.erp_approval.connectors.provider_profiles import PROVIDER_PROFILES, profile_for
from src.backend.domains.erp_approval.connectors.replay_models import (
    ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    ErpConnectorReplayFixtureInfo,
    ErpConnectorReplayRecord,
    ErpConnectorReplayRequest,
    ErpConnectorReplayValidation,
)


_KNOWN_PROVIDERS = sorted(PROVIDER_PROFILES.keys(), key=len, reverse=True)
_FIXTURE_OPERATION_ALIASES = {"purchase_requisition": "approval_request"}


def list_provider_fixtures(base_dir) -> list[ErpConnectorReplayFixtureInfo]:
    fixture_dir = _fixture_dir(base_dir)
    if not fixture_dir.exists():
        return []
    fixtures: list[ErpConnectorReplayFixtureInfo] = []
    for path in sorted(fixture_dir.glob("*.json")):
        info = _fixture_info(path.name)
        if info is not None:
            fixtures.append(info)
    return fixtures


def load_provider_fixture(base_dir, fixture_name: str) -> dict:
    safe_name = Path(str(fixture_name or "")).name
    if not safe_name or safe_name != fixture_name:
        raise FileNotFoundError("Fixture name must be a local fixture filename.")
    path = _fixture_dir(base_dir) / safe_name
    if not path.exists() or path.suffix.lower() != ".json":
        raise FileNotFoundError(f"Connector replay fixture not found: {safe_name}")
    return json.loads(path.read_text(encoding="utf-8"))


def replay_provider_fixture(base_dir, request: ErpConnectorReplayRequest, now: str) -> ErpConnectorReplayRecord:
    warnings: list[str] = []
    fixture_name = Path(str(request.fixture_name or "")).name
    records = []
    status = "success"
    if not request.dry_run:
        warnings.append("Fixture replay requires dry_run=true.")
        status = "blocked"
    if not request.confirm_no_network:
        warnings.append("Fixture replay requires confirm_no_network=true.")
        status = "blocked"

    info = _fixture_info(fixture_name)
    if info is None:
        warnings.append("Fixture name does not match a known provider replay fixture.")
        status = "failed" if status != "blocked" else "blocked"
    elif info.provider != request.provider:
        warnings.append("Fixture provider does not match replay request provider.")
        status = "blocked"
    elif info.operation != request.operation:
        warnings.append("Fixture operation does not match replay request operation.")
        status = "blocked"

    if status == "success":
        try:
            payload = load_provider_fixture(base_dir, fixture_name)
            records = map_provider_payload_to_records(
                request.provider,
                request.operation,
                payload,
                ErpReadRequest(
                    approval_id=request.approval_id,
                    requested_operations=[request.operation],
                    correlation_id=request.correlation_id,
                ),
            )
        except Exception as exc:
            warnings.append(f"Fixture replay failed: {exc}")
            status = "failed"

    record = ErpConnectorReplayRecord(
        replay_id=_replay_id(request),
        provider=request.provider,
        operation=request.operation,
        fixture_name=fixture_name,
        status=status,
        records=records,
        record_count=len(records),
        source_ids=[record.source_id for record in records],
        warnings=warnings,
        created_at=now,
        dry_run=True,
        network_accessed=False,
        non_action_statement=ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    )
    validation = validate_replay_record(record)
    if status == "success" and not validation.passed:
        status = "warning" if records else "failed"
    return record.model_copy(update={"status": status, "validation": validation})


def validate_replay_record(record: ErpConnectorReplayRecord) -> ErpConnectorReplayValidation:
    checked_fields = [
        "records",
        "source_id",
        "title",
        "record_type",
        "content",
        "source_id_prefix",
        "metadata.read_only",
        "metadata.provider",
        "metadata.operation",
        "network_accessed",
        "non_action_statement",
    ]
    warnings: list[str] = []
    failed_checks: list[str] = []
    if not record.records:
        failed_checks.append("records")
    prefix = str(profile_for(record.provider).get("default_source_id_prefix") or f"{record.provider}://")
    for index, context_record in enumerate(record.records):
        label = f"records[{index}]"
        if not context_record.source_id:
            failed_checks.append(f"{label}.source_id")
        if not context_record.title:
            failed_checks.append(f"{label}.title")
        if not context_record.record_type:
            failed_checks.append(f"{label}.record_type")
        if not context_record.content:
            failed_checks.append(f"{label}.content")
        if not context_record.source_id.startswith(prefix):
            failed_checks.append(f"{label}.source_id_prefix")
        if context_record.metadata.get("read_only") is not True:
            failed_checks.append(f"{label}.metadata.read_only")
        if not context_record.metadata.get("provider"):
            failed_checks.append(f"{label}.metadata.provider")
        if not context_record.metadata.get("operation"):
            failed_checks.append(f"{label}.metadata.operation")
    if record.network_accessed:
        failed_checks.append("network_accessed")
    if not record.non_action_statement:
        failed_checks.append("non_action_statement")
    if record.warnings:
        warnings.extend(record.warnings)
    return ErpConnectorReplayValidation(
        passed=not failed_checks,
        warnings=warnings,
        failed_checks=failed_checks,
        checked_fields=checked_fields,
        non_action_statement=ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
    )


def _fixture_dir(base_dir) -> Path:
    base = Path(base_dir or ".").resolve()
    candidates = [
        base / "fixtures" / "erp_approval" / "provider_payloads",
        base / "backend" / "fixtures" / "erp_approval" / "provider_payloads",
        base.parent / "fixtures" / "erp_approval" / "provider_payloads",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _fixture_info(fixture_name: str) -> ErpConnectorReplayFixtureInfo | None:
    name = Path(str(fixture_name or "")).name
    if not name.endswith(".json"):
        return None
    stem = name[:-5]
    for provider in _KNOWN_PROVIDERS:
        prefix = f"{provider}_"
        if stem.startswith(prefix):
            operation_slug = stem[len(prefix) :]
            operation = _FIXTURE_OPERATION_ALIASES.get(operation_slug, operation_slug)
            profile = profile_for(provider)
            supported = set(profile.get("supported_read_operations", []) or [])
            if operation not in supported:
                return None
            return ErpConnectorReplayFixtureInfo(
                provider=provider,
                operation=operation,
                fixture_name=name,
                display_name=str(profile.get("display_name") or provider),
                source_id_prefix=str(profile.get("default_source_id_prefix") or f"{provider}://"),
                non_action_statement=ERP_CONNECTOR_REPLAY_NON_ACTION_STATEMENT,
            )
    return None


def _replay_id(request: ErpConnectorReplayRequest) -> str:
    payload: dict[str, Any] = {
        "provider": request.provider,
        "operation": request.operation,
        "fixture_name": Path(str(request.fixture_name or "")).name,
        "approval_id": request.approval_id,
        "correlation_id": request.correlation_id,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"erp-connector-replay:{request.provider}:{request.operation}:{Path(request.fixture_name).name}:{digest}"
