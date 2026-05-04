from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field, ValidationError

from src.backend.domains.erp_approval import (
    ApprovalActionProposalQuery,
    ApprovalActionProposalRepository,
    ApprovalActionSimulationQuery,
    ApprovalActionSimulationRepository,
    ApprovalActionSimulationRequest,
    ERP_CONNECTOR_NON_ACTION_STATEMENT,
    PROVIDER_PROFILES,
    ErpConnectorProviderProfileSummary,
    ErpConnectorReplayRequest,
    ReviewerNoteRepository,
    SavedAuditPackageQuery,
    SavedAuditPackageRepository,
    ApprovalTraceQuery,
    ApprovalTraceRepository,
    append_reviewer_note,
    build_audit_package,
    build_connector_registry_from_env,
    build_replay_coverage_matrix,
    build_saved_audit_package_manifest,
    build_simulation_record,
    connector_selection_summary,
    default_action_simulation_path,
    default_proposal_ledger_path,
    default_reviewer_notes_path,
    default_saved_audit_package_path,
    default_trace_path,
    load_erp_connector_config_from_env,
    list_provider_fixtures,
    redacted_connector_config,
    replay_provider_fixture,
    validate_simulation_request,
)
from src.backend.domains.erp_approval.case_harness import CaseHarness
from src.backend.domains.erp_approval.case_state_models import CASE_HARNESS_NON_ACTION_STATEMENT, CaseTurnRequest
from src.backend.domains.erp_approval.case_stage_model import CaseStageModelReviewer
from src.backend.domains.erp_approval.case_turn_executor import CaseTurnExecutor
from src.backend.domains.erp_approval.case_turn_graph import CASE_TURN_GRAPH_NAME
from src.backend.runtime.agent_manager import agent_manager
from src.backend.runtime.config import get_settings

router = APIRouter()


class SaveAuditPackageRequest(BaseModel):
    title: str = ""
    description: str = ""
    created_by: str = ""
    trace_ids: list[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)


class CreateReviewerNoteRequest(BaseModel):
    author: str = ""
    note_type: str = "general"
    body: str = ""
    trace_id: str = ""
    proposal_record_id: str = ""


def _repository() -> ApprovalTraceRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return ApprovalTraceRepository(default_trace_path(base_dir))


def _proposal_repository() -> ApprovalActionProposalRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return ApprovalActionProposalRepository(default_proposal_ledger_path(base_dir))


def _saved_package_repository() -> SavedAuditPackageRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return SavedAuditPackageRepository(default_saved_audit_package_path(base_dir))


def _note_repository() -> ReviewerNoteRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return ReviewerNoteRepository(default_reviewer_notes_path(base_dir))


def _simulation_repository() -> ApprovalActionSimulationRepository:
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return ApprovalActionSimulationRepository(default_action_simulation_path(base_dir))


def _connector_registry():
    base_dir = agent_manager.base_dir or get_settings().backend_dir
    return build_connector_registry_from_env(base_dir)


def _connector_base_dir():
    return agent_manager.base_dir or get_settings().backend_dir


def _case_review_base_dir():
    return agent_manager.base_dir or get_settings().backend_dir


def _case_harness() -> CaseHarness:
    return CaseHarness(_case_review_base_dir(), stage_model=_case_stage_model_reviewer())


@lru_cache(maxsize=1)
def _case_stage_model_reviewer():
    enabled = os.getenv("ERP_CASE_STAGE_MODEL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None
    try:
        timeout = float(os.getenv("ERP_CASE_STAGE_MODEL_ROLE_TIMEOUT_SECONDS", "30.0"))
        timeout = max(0.2, min(timeout, 60.0))
        return CaseStageModelReviewer(agent_manager._build_chat_model(), role_timeout_seconds=timeout)
    except Exception:
        return None


def _harness_runtime():
    try:
        return agent_manager.get_harness_runtime()
    except RuntimeError:
        from src.backend.runtime.runtime import build_harness_runtime  # pylint: disable=import-outside-toplevel

        return build_harness_runtime(_case_review_base_dir())


def _case_turn_session_id(request: CaseTurnRequest) -> str:
    if request.case_id.strip():
        return request.case_id.strip()
    digest = hashlib.sha256(request.user_message.encode("utf-8")).hexdigest()[:16]
    return f"erp-case-draft:{digest}"


def _event_summary(event) -> dict:
    payload = dict(event.payload or {})
    if event.name == "answer.completed":
        content = str(payload.get("content", "") or "")
        payload = {
            "final": bool(payload.get("final", True)),
            "segment_index": payload.get("segment_index", 0),
            "content_preview": content[:320],
            "content_length": len(content),
        }
    return {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "name": event.name,
        "ts": event.ts,
        "payload": payload,
    }


@router.post("/erp-approval/cases/turn")
async def apply_erp_approval_case_turn(request: CaseTurnRequest) -> dict:
    if not request.user_message.strip() and not request.extra_evidence:
        raise HTTPException(status_code=400, detail="user_message or extra_evidence is required")
    executor = CaseTurnExecutor(_case_harness(), request)
    events = []
    runtime = _harness_runtime()
    async for event in runtime.run_with_executor(
        user_message=request.user_message,
        session_id=_case_turn_session_id(request),
        source="internal",
        executor=executor,
        history=[],
        orchestration_engine="langgraph_case_turn",
    ):
        events.append(event)
    if executor.response is None:
        raise HTTPException(status_code=500, detail="ERP approval case turn did not produce a response")
    payload = executor.response.model_dump()
    payload["operation_scope"] = executor.response.operation_scope
    payload["persistence"] = (
        "writes_local_audit_log_only"
        if executor.response.operation_scope == "read_only_case_turn"
        else "writes_local_case_state_dossier_and_audit_log_only"
    )
    payload["harness_run"] = {
        "run_id": events[0].run_id if events else "",
        "orchestration_engine": "langgraph_case_turn",
        "graph_name": CASE_TURN_GRAPH_NAME,
        "graph_steps": executor.graph_steps,
        "stage_model_used": bool((executor.response.patch.model_review or {}).get("used")),
        "stage_model_role_status": {
            role: (
                "skipped"
                if details.get("skipped")
                else "error"
                if details.get("error")
                else "executed"
            )
            for role, details in (executor.response.patch.model_review or {}).get("role_outputs", {}).items()
            if isinstance(details, dict)
        },
        "event_names": [event.name for event in events],
        "events": [_event_summary(event) for event in events],
        "non_action_statement": CASE_HARNESS_NON_ACTION_STATEMENT,
    }
    return payload


@router.get("/erp-approval/cases")
async def list_erp_approval_cases(limit: int = Query(default=50, ge=0, le=200)) -> list[dict]:
    return [state.model_dump() for state in _case_harness().list_cases(limit=limit)]


@router.get("/erp-approval/cases/{case_id}")
async def get_erp_approval_case(case_id: str) -> dict:
    state = _case_harness().get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="ERP approval case not found")
    return state.model_dump()


@router.get("/erp-approval/cases/{case_id}/dossier")
async def get_erp_approval_case_dossier(case_id: str) -> Response:
    state = _case_harness().get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="ERP approval case not found")
    dossier = _case_harness().get_dossier(case_id)
    return Response(content=dossier, media_type="text/markdown; charset=utf-8")


@router.get("/erp-approval/cases/{case_id}/conversation")
async def get_erp_approval_case_conversation(case_id: str, limit: int = Query(default=200, ge=0, le=1000)) -> list[dict]:
    state = _case_harness().get_case(case_id)
    if state is None:
        raise HTTPException(status_code=404, detail="ERP approval case not found")
    return _case_harness().get_conversation(case_id, limit=limit)


@router.get("/erp-approval/connectors/config")
async def get_erp_approval_connector_config() -> dict:
    config = load_erp_connector_config_from_env()
    return {
        "config": redacted_connector_config(config),
        "selection": connector_selection_summary(config),
        "non_action_statement": ERP_CONNECTOR_NON_ACTION_STATEMENT,
    }


@router.get("/erp-approval/connectors/health")
async def get_erp_approval_connector_health() -> dict:
    return _connector_registry().diagnostic_summary().model_dump()


@router.get("/erp-approval/connectors/profiles")
async def list_erp_approval_connector_profiles() -> list[dict]:
    return [_profile_summary(provider, profile).model_dump() for provider, profile in PROVIDER_PROFILES.items()]


@router.get("/erp-approval/connectors/profiles/{provider}")
async def get_erp_approval_connector_profile(provider: str) -> dict:
    profile = PROVIDER_PROFILES.get(provider)
    if profile is None:
        raise HTTPException(status_code=404, detail="ERP connector provider profile not found")
    return _profile_summary(provider, profile).model_dump()


@router.get("/erp-approval/connectors/replay/fixtures")
async def list_erp_approval_connector_replay_fixtures() -> list[dict]:
    return [fixture.model_dump() for fixture in list_provider_fixtures(_connector_base_dir())]


@router.get("/erp-approval/connectors/replay/coverage")
async def get_erp_approval_connector_replay_coverage() -> dict:
    return build_replay_coverage_matrix(_connector_base_dir(), _now()).model_dump()


@router.get("/erp-approval/connectors/replay")
async def replay_erp_approval_connector_fixture(
    provider: str,
    operation: str,
    fixture_name: str,
    approval_id: str = "PR-1001",
    correlation_id: str = "connector-replay",
) -> dict:
    fixtures = list_provider_fixtures(_connector_base_dir())
    if not any(fixture.fixture_name == fixture_name for fixture in fixtures):
        raise HTTPException(status_code=404, detail="ERP connector replay fixture not found")
    try:
        request = ErpConnectorReplayRequest(
            provider=provider,
            operation=operation,
            fixture_name=fixture_name,
            approval_id=approval_id,
            correlation_id=correlation_id,
            dry_run=True,
            confirm_no_network=True,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return replay_provider_fixture(_connector_base_dir(), request, _now()).model_dump()


@router.get("/erp-approval/traces")
async def list_erp_approval_traces(
    limit: int = Query(default=100, ge=0, le=1000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> list[dict]:
    query = _trace_query(
        limit=limit,
        approval_type=approval_type,
        recommendation_status=recommendation_status,
        review_status=review_status,
        proposal_action_type=proposal_action_type,
        human_review_required=human_review_required,
        guard_downgraded=guard_downgraded,
        high_risk_only=high_risk_only,
        text_query=text_query,
        date_from=date_from,
        date_to=date_to,
    )
    return [record.model_dump() for record in _repository().query(query)]


@router.get("/erp-approval/traces/{trace_id}")
async def get_erp_approval_trace(trace_id: str) -> dict:
    record = _repository().get(trace_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ERP approval trace not found")
    return record.model_dump()


@router.get("/erp-approval/traces/{trace_id}/proposals")
async def list_erp_approval_trace_proposals(trace_id: str) -> list[dict]:
    return [record.model_dump() for record in _proposal_repository().by_trace_id(trace_id)]


@router.get("/erp-approval/proposals")
async def list_erp_approval_proposals(
    limit: int = Query(default=100, ge=0, le=1000),
    action_type: str | None = None,
    status: str | None = None,
    approval_id: str | None = None,
    trace_id: str | None = None,
    risk_level: str | None = None,
    requires_human_review: bool | None = None,
    blocked: bool | None = None,
    rejected_by_validation: bool | None = None,
) -> list[dict]:
    query = _proposal_query(
        limit=limit,
        action_type=action_type,
        status=status,
        approval_id=approval_id,
        trace_id=trace_id,
        risk_level=risk_level,
        requires_human_review=requires_human_review,
        blocked=blocked,
        rejected_by_validation=rejected_by_validation,
    )
    return [record.model_dump() for record in _proposal_repository().query(query)]


@router.get("/erp-approval/proposals/{proposal_record_id}")
async def get_erp_approval_proposal(proposal_record_id: str) -> dict:
    record = _proposal_repository().get(proposal_record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ERP approval proposal record not found")
    return record.model_dump()


@router.get("/erp-approval/proposals/{proposal_record_id}/simulations")
async def list_erp_approval_proposal_simulations(proposal_record_id: str) -> list[dict]:
    return [record.model_dump() for record in _simulation_repository().by_proposal_record_id(proposal_record_id)]


@router.get("/erp-approval/action-simulations")
async def list_erp_approval_action_simulations(
    limit: int = Query(default=100, ge=0, le=1000),
    proposal_record_id: str | None = None,
    package_id: str | None = None,
    trace_id: str | None = None,
    approval_id: str | None = None,
    action_type: str | None = None,
    status: str | None = None,
    requested_by: str | None = None,
) -> list[dict]:
    query = ApprovalActionSimulationQuery(
        limit=limit,
        proposal_record_id=_clean_optional(proposal_record_id),
        package_id=_clean_optional(package_id),
        trace_id=_clean_optional(trace_id),
        approval_id=_clean_optional(approval_id),
        action_type=_clean_optional(action_type),
        status=_clean_optional(status),
        requested_by=_clean_optional(requested_by),
    )
    return [record.model_dump() for record in _simulation_repository().list_recent(query)]


@router.get("/erp-approval/action-simulations/{simulation_id}")
async def get_erp_approval_action_simulation(simulation_id: str) -> dict:
    record = _simulation_repository().get(simulation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ERP approval action simulation not found")
    return record.model_dump()


@router.post("/erp-approval/action-simulations")
async def create_erp_approval_action_simulation(request: ApprovalActionSimulationRequest) -> dict:
    if not request.confirm_no_erp_write:
        raise HTTPException(status_code=400, detail="confirm_no_erp_write must be true for local simulation")
    proposal = _proposal_repository().get(request.proposal_record_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="ERP approval proposal record not found")
    saved_package = _saved_package_repository().get(request.package_id)
    if saved_package is None:
        raise HTTPException(status_code=404, detail="Saved ERP approval audit package not found")
    if proposal.proposal_record_id not in saved_package.proposal_record_ids:
        raise HTTPException(status_code=400, detail="Proposal record does not belong to saved audit package")

    validation = validate_simulation_request(request, proposal, saved_package)
    record = build_simulation_record(request, proposal, saved_package, validation, _now())
    result = _simulation_repository().upsert(record)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Failed to save local action simulation")
    return (_simulation_repository().get(record.simulation_id) or record).model_dump()


@router.get("/erp-approval/analytics/summary")
async def get_erp_approval_analytics_summary(limit: int = Query(default=500, ge=0, le=5000)) -> dict:
    return _repository().summarize(limit=limit).model_dump()


@router.get("/erp-approval/audit-package")
async def get_erp_approval_audit_package(
    trace_ids: str = "",
    limit: int = Query(default=100, ge=0, le=1000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    trace_repository = _repository()
    proposal_repository = _proposal_repository()
    ids = [item.strip() for item in trace_ids.split(",") if item.strip()]
    if ids:
        traces = [record for trace_id in ids if (record := trace_repository.get(trace_id)) is not None]
    else:
        traces = trace_repository.query(
            _trace_query(
                limit=limit,
                approval_type=approval_type,
                recommendation_status=recommendation_status,
                review_status=review_status,
                proposal_action_type=proposal_action_type,
                human_review_required=human_review_required,
                guard_downgraded=guard_downgraded,
                high_risk_only=high_risk_only,
                text_query=text_query,
                date_from=date_from,
                date_to=date_to,
            )
        )
    proposals = []
    for trace in traces:
        proposals.extend(proposal_repository.by_trace_id(trace.trace_id))
    return build_audit_package(traces, proposals, _now()).model_dump()


@router.get("/erp-approval/audit-packages")
async def list_saved_erp_approval_audit_packages(
    limit: int = Query(default=100, ge=0, le=1000),
    created_by: str | None = None,
    trace_id: str | None = None,
    text_query: str = "",
) -> list[dict]:
    query = SavedAuditPackageQuery(
        limit=limit,
        created_by=_clean_optional(created_by),
        trace_id=_clean_optional(trace_id),
        text_query=text_query.strip(),
    )
    return [record.model_dump() for record in _saved_package_repository().list_recent(query)]


@router.post("/erp-approval/audit-packages")
async def save_erp_approval_audit_package(request: SaveAuditPackageRequest) -> dict:
    filters = dict(request.filters or {})
    package = _build_audit_package_from_inputs(trace_ids=request.trace_ids, filters=filters, limit=100)
    now = _now()
    manifest = build_saved_audit_package_manifest(
        package,
        title=request.title,
        description=request.description,
        created_by=request.created_by,
        source_filters=filters,
        now=now,
    )
    repository = _saved_package_repository()
    result = repository.upsert(manifest)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Failed to save audit package")
    return (repository.get(manifest.package_id) or manifest).model_dump()


@router.get("/erp-approval/audit-packages/{package_id}")
async def get_saved_erp_approval_audit_package(package_id: str) -> dict:
    manifest = _saved_package_repository().get(package_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Saved ERP approval audit package not found")
    return manifest.model_dump()


@router.get("/erp-approval/audit-packages/{package_id}/export.json")
async def export_saved_erp_approval_audit_package(package_id: str) -> dict:
    manifest_repository = _saved_package_repository()
    export = manifest_repository.export_package(package_id)
    if export is None:
        raise HTTPException(status_code=404, detail="Saved ERP approval audit package not found")
    notes = _note_repository().list_for_package(package_id)
    return export.model_copy(update={"notes": notes}).model_dump()


@router.get("/erp-approval/audit-packages/{package_id}/notes")
async def list_saved_erp_approval_audit_package_notes(package_id: str) -> list[dict]:
    if _saved_package_repository().get(package_id) is None:
        raise HTTPException(status_code=404, detail="Saved ERP approval audit package not found")
    return [note.model_dump() for note in _note_repository().list_for_package(package_id)]


@router.post("/erp-approval/audit-packages/{package_id}/notes")
async def append_saved_erp_approval_audit_package_note(package_id: str, request: CreateReviewerNoteRequest) -> dict:
    package_repository = _saved_package_repository()
    if package_repository.get(package_id) is None:
        raise HTTPException(status_code=404, detail="Saved ERP approval audit package not found")
    if not request.body.strip():
        raise HTTPException(status_code=400, detail="Reviewer note body is required")
    now = _now()
    note = append_reviewer_note(
        package_id=package_id,
        author=request.author,
        note_type=request.note_type,
        body=request.body,
        trace_id=request.trace_id,
        proposal_record_id=request.proposal_record_id,
        now=now,
    )
    note_repository = _note_repository()
    result = note_repository.append(note)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Failed to save reviewer note")
    package_repository.update_note_count(package_id, len(note_repository.list_for_package(package_id)), now)
    return note.model_dump()


@router.get("/erp-approval/analytics/trends")
async def get_erp_approval_analytics_trends(
    limit: int = Query(default=500, ge=0, le=5000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    return _repository().trend_summary(
        _trace_query(
            limit=limit,
            approval_type=approval_type,
            recommendation_status=recommendation_status,
            review_status=review_status,
            proposal_action_type=proposal_action_type,
            human_review_required=human_review_required,
            guard_downgraded=guard_downgraded,
            high_risk_only=high_risk_only,
            text_query=text_query,
            date_from=date_from,
            date_to=date_to,
        )
    ).model_dump()


@router.get("/erp-approval/export.json")
async def export_erp_approval_traces_json(
    limit: int = Query(default=500, ge=0, le=5000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict:
    return _repository().export_json(
        _trace_query(
            limit=limit,
            approval_type=approval_type,
            recommendation_status=recommendation_status,
            review_status=review_status,
            proposal_action_type=proposal_action_type,
            human_review_required=human_review_required,
            guard_downgraded=guard_downgraded,
            high_risk_only=high_risk_only,
            text_query=text_query,
            date_from=date_from,
            date_to=date_to,
        )
    )


@router.get("/erp-approval/export.csv")
async def export_erp_approval_traces_csv(
    limit: int = Query(default=500, ge=0, le=5000),
    approval_type: str | None = None,
    recommendation_status: str | None = None,
    review_status: str | None = None,
    proposal_action_type: str | None = None,
    human_review_required: bool | None = None,
    guard_downgraded: bool | None = None,
    high_risk_only: bool = False,
    text_query: str = "",
    date_from: str = "",
    date_to: str = "",
) -> Response:
    content = _repository().export_csv(
        _trace_query(
            limit=limit,
            approval_type=approval_type,
            recommendation_status=recommendation_status,
            review_status=review_status,
            proposal_action_type=proposal_action_type,
            human_review_required=human_review_required,
            guard_downgraded=guard_downgraded,
            high_risk_only=high_risk_only,
            text_query=text_query,
            date_from=date_from,
            date_to=date_to,
        )
    )
    return Response(content=content, media_type="text/csv")


def _trace_query(
    *,
    limit: int,
    approval_type: str | None,
    recommendation_status: str | None,
    review_status: str | None,
    proposal_action_type: str | None,
    human_review_required: bool | None,
    guard_downgraded: bool | None,
    high_risk_only: bool,
    text_query: str,
    date_from: str,
    date_to: str,
) -> ApprovalTraceQuery:
    return ApprovalTraceQuery(
        limit=limit,
        approval_type=_clean_optional(approval_type),
        recommendation_status=_clean_optional(recommendation_status),
        review_status=_clean_optional(review_status),
        proposal_action_type=_clean_optional(proposal_action_type),
        human_review_required=human_review_required,
        guard_downgraded=guard_downgraded,
        high_risk_only=high_risk_only,
        text_query=text_query.strip(),
        date_from=date_from.strip(),
        date_to=date_to.strip(),
    )


def _clean_optional(value: str | None) -> str | None:
    cleaned = value.strip() if isinstance(value, str) else ""
    return cleaned or None


def _proposal_query(
    *,
    limit: int,
    action_type: str | None,
    status: str | None,
    approval_id: str | None,
    trace_id: str | None,
    risk_level: str | None,
    requires_human_review: bool | None,
    blocked: bool | None,
    rejected_by_validation: bool | None,
) -> ApprovalActionProposalQuery:
    return ApprovalActionProposalQuery(
        limit=limit,
        action_type=_clean_optional(action_type),
        status=_clean_optional(status),
        approval_id=_clean_optional(approval_id),
        trace_id=_clean_optional(trace_id),
        risk_level=_clean_optional(risk_level),
        requires_human_review=requires_human_review,
        blocked=blocked,
        rejected_by_validation=rejected_by_validation,
    )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _profile_summary(provider: str, profile: dict) -> ErpConnectorProviderProfileSummary:
    return ErpConnectorProviderProfileSummary(
        provider=provider,
        display_name=str(profile.get("display_name") or ""),
        supported_read_operations=list(profile.get("supported_read_operations", []) or []),
        default_source_id_prefix=str(profile.get("default_source_id_prefix") or ""),
        endpoint_templates=dict(profile.get("endpoint_templates", {}) or {}),
        read_only_notes=str(profile.get("read_only_notes") or ""),
        forbidden_methods=list(profile.get("forbidden_methods", []) or []),
        documentation_notes=str(profile.get("documentation_notes") or ""),
        non_action_statement=ERP_CONNECTOR_NON_ACTION_STATEMENT,
    )


def _build_audit_package_from_inputs(*, trace_ids: list[str], filters: dict, limit: int):
    trace_repository = _repository()
    proposal_repository = _proposal_repository()
    cleaned_ids = [str(item).strip() for item in trace_ids if str(item).strip()]
    if cleaned_ids:
        traces = [record for trace_id in cleaned_ids if (record := trace_repository.get(trace_id)) is not None]
    else:
        traces = trace_repository.query(_trace_query_from_filter_dict(filters, limit=limit))
    proposals = []
    for trace in traces:
        proposals.extend(proposal_repository.by_trace_id(trace.trace_id))
    return build_audit_package(traces, proposals, _now())


def _trace_query_from_filter_dict(filters: dict, *, limit: int) -> ApprovalTraceQuery:
    return _trace_query(
        limit=int(filters.get("limit") or limit),
        approval_type=filters.get("approval_type"),
        recommendation_status=filters.get("recommendation_status"),
        review_status=filters.get("review_status"),
        proposal_action_type=filters.get("proposal_action_type"),
        human_review_required=filters.get("human_review_required"),
        guard_downgraded=filters.get("guard_downgraded"),
        high_risk_only=bool(filters.get("high_risk_only", False)),
        text_query=str(filters.get("text_query", "") or ""),
        date_from=str(filters.get("date_from", "") or ""),
        date_to=str(filters.get("date_to", "") or ""),
    )
