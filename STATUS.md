# ERP Approval Agent Workbench Status

## Current Active Phase

Phase 14: Final MVP Closure plus strict evidence-case toy audit.

Phase 0 product-semantic migration is complete. Phase 1 added the LLM-first ERP approval graph skeleton, Phase 2 added the read-only mock ERP context adapter, Phase 3 added durable recommendation review through the existing HITL checkpoint/resume mechanism, Phase 4 added proposed-only ERP action drafts, Phase 5 added a local structured trace ledger plus read-only analytics summary, Phase 6 added trace explorer filters, detail lookup, export, and trend summaries, Phase 7 added a proposed-only action proposal ledger plus read-only audit packages, Phase 8 added saved audit package manifests plus append-only reviewer notes, Phase 9 added a local mock action simulation sandbox, Phase 10 added a read-only ERP connector interface plus connector registry, Phase 11 hardened connector configuration, Phase 12 added local connector replay diagnostics, Phase 13 added multi-entity replay coverage, and Phase 14 closes the MVP boundary:

```text
bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_case_file -> erp_evidence_requirements -> erp_evidence_claims -> erp_evidence_sufficiency -> erp_control_matrix -> erp_case_recommendation -> erp_adversarial_review -> erp_guard -> erp_hitl_gate -> erp_action_proposal -> erp_finalize -> finalize
```

The current active capability is Phase 14 plus an evidence-first case-agent refactor. No connector, simulation, audit workspace, mapper diagnostic, profile note, benchmark, live ERP, or ERP write-action scope is added. ERP context retrieval still goes through a read-only connector interface and registry with typed env loading, explicit read-only opt-in gates, redacted diagnostics, healthcheck/profile APIs, representative provider payload fixtures, local fixture replay, and local replay coverage. The default connector remains mock, disabled, and no-network. SAP S/4HANA OData, Dynamics 365 F&O OData, Oracle Fusion REST, and custom HTTP JSON profiles are disabled metadata/skeletons only.

The latest local strict toy audit generated 82 fictional approval cases and passed with 0 critical and 0 major failures. Reports:

- `reports/evaluations/evidence_case_audit_latest.md`
- `reports/evaluations/evidence_case_audit_latest.json`
- `reports/evidence_case_toy_audit_self_critique.md`

This audit is local regression/self-critique only. It is not a production benchmark, process-mining result, or ERP integration proof.

The latest CaseHarness pressure/usability stress suite generated 66 deliberately messy local scenarios and 74 turns, including one-sentence approvals, prompt injection, mixed off-topic requests, weak user assertions, incomplete evidence, complete mock context, execution-boundary probes, and multi-turn evidence submission. Latest reports:

- `reports/evaluations/case_harness_stress_latest.md`
- `reports/evaluations/case_harness_stress_latest.json`

The stress suite found and fixed weak oral evidence acceptance, overly broad ERP ID parsing, first-turn memo intent misclassification, and mixed off-topic turn handling. It is a local usability/regression stress test, not a production benchmark.

The latest scored CaseHarness maturity benchmark generated 321 local cases and 417 turns. Every case is scored on a 100-point rubric covering case lifecycle, evidence handling, recommendation boundary, human-review/non-action boundary, guidance, dossier, and control matrix. Latest reports:

- `reports/evaluations/case_harness_maturity_benchmark_latest.md`
- `reports/evaluations/case_harness_maturity_benchmark_latest.json`
- `backend/benchmarks/cases/erp_approval/case_harness_maturity_benchmark.json`

Latest score: average 99.85, p10 100.00, 321 A grades, 0 critical failures, and 0 major failures. This remains a local maturity benchmark over fictional/mock cases, not production approval accuracy.

After manual real-path review, the mock ERP context now includes a visible fictional evidence pack under `knowledge/ERP Approval/sample_evidence`. The latest manual smoke report is `reports/evaluations/manual_agent_smoke_latest.md` and covers:

- one-sentence direct-approval prompts: must not recommend approve.
- PR-1001: has approval form, budget, and vendor evidence, but is still blocked because quote/price-basis evidence is missing.
- PR-1002: complete purchase evidence chain can form a non-executing approve recommendation.
- INV-3001: invoice, PO, GRN, vendor, payment terms, duplicate payment check, and policy evidence are displayed before recommendation.
- prompt injection: "ignore policy / no citations / directly approve" is downgraded and requires human review.

Evidence-first behavior:

- one-sentence input creates a case draft only.
- each user turn can now be processed through a local CaseHarness state machine: the turn loads `case_state.json`, classifies intent, assembles a bounded case context, validates a `CasePatch`, updates `dossier.md`, appends `audit_log.jsonl`, and then responds.
- `POST /api/erp-approval/cases/turn` is HarnessRuntime-owned: it runs through `run_with_executor`, emits `case.turn.started`, `case.patch.validated`, and `case.state.persisted`, and completes as a canonical harness run.
- the configured LLM is the single product review path when local model settings are available. It runs bounded roles for turn classification, evidence extraction, policy interpretation, contradiction review, and reviewer memo drafting; the aggregated structured `CasePatch` still goes through source/claim/action validation before persistence.
- deterministic code remains the validator, boundary guard, and test fallback; it is no longer presented as a second user-facing review path.
- case turns are serialized per case id, write local JSON/Markdown artifacts atomically, and can reject stale `expected_turn_count` submissions without mutating the dossier.
- chat is treated as the interface to an `ApprovalCase`; it is not the source of truth.
- off-topic turns and invalid patches are rejected without changing accepted evidence.
- blocking ERP/policy/attachment evidence gaps prevent `recommend_approve`.
- deterministic evidence sufficiency and control-matrix checks run before recommendation drafting.
- adversarial review downgrades unsupported or over-strong recommendations.
- final answers render required evidence, evidence claims, sufficiency, contradictions, control checks, risk, adversarial review, recommendation, and the non-action boundary.
- default frontend experience is now `Case Review`, not chat: users submit a case, add local text/file evidence, rerun review, and inspect required evidence, claims, sufficiency, control matrix, contradictions, recommendation, and reviewer memo.
- local `POST /api/erp-approval/cases/turn` updates an approval case state machine; it writes only local dossier artifacts and never writes to ERP.
- release boundary tests explicitly allow `/api/erp-approval/cases/turn` as a local case-state write, not an ERP action write.

## Active Product Direction

ERP Approval Agent Workbench is becoming a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows.

Current positioning:

- approval recommendation, not autonomous final execution.
- evidence-first approval case analysis, with LLM used for intake/explanation and deterministic gates used for sufficiency/control boundaries.
- existing ERP approval graph skeleton.
- mock ERP/policy context.
- durable ERP recommendation review HITL gate.
- guarded ERP action proposal drafts.
- local ERP approval trace ledger.
- read-only ERP approval analytics API.
- frontend management Insights panel with trace filtering and drill-down.
- action proposal ledger and read-only audit package.
- local saved audit package workspace and reviewer notes.
- local action simulation sandbox and simulation ledger.
- read-only ERP connector registry with mock default.
- hardened connector env loading, redaction, diagnostics, provider profiles, and mapping fixtures.
- local connector fixture replay harness and frontend diagnostics UX.
- local connector replay coverage matrix.
- final MVP acceptance checklist and release boundary tests.
- `GRAPH_VERSION=phase14`.
- HarnessRuntime-owned execution lifecycle.
- LangGraph orchestration.
- auditable approval trace.
- ERP policy and business context retrieval through existing knowledge abstractions.

## Completed Phase 1 Capabilities

- `erp_approval` domain package.
- ERP approval routing intent.
- ERP graph path in LangGraph.
- LLM-first intake and reasoning prompts.
- mock context bundle.
- deterministic guard for recommendations.
- unit tests for domain, routing, and graph edge behavior.

## Completed Phase 2 Capabilities

- read-only ERP context adapter interface.
- local mock ERP context fixture.
- normalized approval request, vendor, budget, PO, invoice, goods receipt, contract, and policy records.
- routing hardening for no-retrieval/no-knowledge constraints.
- stricter validation gate for weak evidence, missing citations, unknown citations, and unsafe next actions.

## Completed Phase 3 Capabilities

- `erp_hitl_gate` node between `erp_guard` and `erp_finalize`.
- durable HITL recommendation review requests using existing checkpoint/resume mechanics.
- review statuses: `not_required`, `requested`, `accepted_by_human`, `rejected_by_human`, `edited_by_human`.
- frontend copy clarifying that HITL approve accepts the recommendation only.
- final answers continue to state that no ERP action was executed.

## Completed Phase 4 Capabilities

- `erp_action_proposal` node between `erp_hitl_gate` and `erp_finalize`.
- action proposal schemas and validation result models.
- deterministic idempotency key and fingerprint generation.
- validation blocks unknown citation sources, invalid action types, and payloads with ERP execution semantics.
- final answers render Action proposals and explicitly state that no ERP write action was executed.

## Completed Phase 5 Capabilities

- structured `ApprovalTraceRecord` model for ERP approval run summaries.
- local JSONL trace repository with trace-id upsert dedupe.
- `erp_finalize` trace write that does not block final answers if storage fails.
- read-only endpoints for traces, trace detail, and analytics summary:
  - `GET /api/erp-approval/traces`
  - `GET /api/erp-approval/traces/{trace_id}`
  - `GET /api/erp-approval/analytics/summary`
- frontend `Insights` tab with trace-based management summary counts.

## Completed Phase 6 Capabilities

- `ApprovalTraceQuery`, trace list response, export format, and trend models.
- repository filters for approval type, recommendation status, review status, proposal action type, human review, guard downgrade, high-risk traces, structured text fields, and ISO date strings.
- read-only JSON and CSV export.
- read-only trend summary bucketed by `created_at` date.
- frontend trace explorer with filters, list, detail card, export buttons, and trend buckets.

## Completed Phase 7 Capabilities

- `ApprovalActionProposalRecord` ledger model with idempotency fields, payload preview, validation warnings, and `executable=false`.
- local JSONL proposal repository at `backend/storage/erp_approval/action_proposals.jsonl`.
- `erp_finalize` writes proposal ledger records without blocking final answer delivery.
- read-only proposal APIs and per-trace proposal lookup.
- temporary read-only audit package endpoint with completeness checks.
- frontend trace detail displays action proposal records and can download an audit package JSON.

## Completed Phase 8 Capabilities

- saved audit package manifest model with package snapshot and stable hash.
- local package repository at `backend/storage/erp_approval/audit_packages.jsonl`.
- append-only reviewer notes at `backend/storage/erp_approval/reviewer_notes.jsonl`.
- local-only POST endpoints for saving audit packages and notes.
- frontend workspace for saving packages, listing saved packages, adding local notes, and exporting saved package JSON.

## Completed Phase 9 Capabilities

- local action simulation request, validation, record, query, and write-result models.
- deterministic simulation id and idempotency fingerprint.
- local simulation repository at `backend/storage/erp_approval/action_simulations.jsonl`.
- local-only `POST /api/erp-approval/action-simulations` endpoint for dry-run records.
- read-only simulation list/detail/by-proposal endpoints.
- frontend local simulation panel in the `Insights` audit workspace.
- `simulated_only=true` and `erp_write_executed=false` on every simulation record.

## Completed Phase 10 Capabilities

- connector models for provider, config, read request, operation, and read result.
- connector protocol and registry.
- `MockErpReadOnlyConnector` backed by the existing mock fixture.
- provider profile metadata for SAP S/4HANA OData, Dynamics 365 F&O OData, Oracle Fusion REST, and custom HTTP JSON.
- `HttpReadOnlyErpConnector` skeleton that is disabled and network-blocked by default.
- `erp_context_node` now fetches context through the default connector registry.
- state captures `erp_connector_result` and `erp_connector_warnings`.

## Completed Phase 11 Capabilities

- typed connector environment loader with safe defaults: `provider=mock`, `enabled=false`, and `allow_network=false`.
- explicit read-only opt-in and use-as-default gates for non-mock connector candidates.
- redacted connector config summaries that expose only auth env var names and presence booleans.
- connector diagnostics and read-only health/profile APIs:
  - `GET /api/erp-approval/connectors/config`
  - `GET /api/erp-approval/connectors/health`
  - `GET /api/erp-approval/connectors/profiles`
  - `GET /api/erp-approval/connectors/profiles/{provider}`
- provider payload mapping fixtures for SAP S/4HANA OData, Dynamics 365 F&O OData, Oracle Fusion REST, and custom HTTP JSON.
- HTTP read-only connector now maps provider payload shapes through a shared mapper.
- `GRAPH_VERSION` was first centralized in Phase 11; current MVP graph version is `phase14`.

## Completed Phase 12 Capabilities

- connector replay models and local fixture replay service.
- replay validation for source ids, titles, record types, content, read-only metadata, provider metadata, operation metadata, no-network status, and non-action statements.
- GET-only replay APIs:
  - `GET /api/erp-approval/connectors/replay/fixtures`
  - `GET /api/erp-approval/connectors/replay`
- enhanced redaction for sensitive URL query parameters such as `token`, `api_key`, `password`, `secret`, and `signature`.
- frontend `Connector diagnostics` panel under `Insights` with redacted config, health, provider profiles, fixture selector, local replay result, and `network_accessed=false` visibility.

## Completed Phase 13 Capabilities

- representative provider payload fixtures now cover four providers across eight read-only operations.
- operation slug detection covers approval request, vendor, budget, purchase order, invoice, goods receipt, contract, and policy fixtures.
- provider payload mapper extracts operation-specific entity ids while preserving read-only metadata.
- replay coverage matrix reports total, passed, failed, by-provider, and by-operation counts.
- GET-only coverage API:
  - `GET /api/erp-approval/connectors/replay/coverage`
- frontend `Connector diagnostics` panel shows the coverage summary, grouped counts, warnings, and failed checks.
- coverage remains local fixture replay only, not a benchmark and not a live ERP integration test.

## Completed Phase 14 Capabilities

- final MVP acceptance checklist:
  - `docs/product/mvp_acceptance_checklist.md`
- final validation script:
  - `backend/scripts/dev/validate-phase14-mvp.ps1`
- release boundary tests:
  - `backend/tests/test_erp_approval_release_boundary.py`
- final MVP report:
  - `reports/phase14_final_mvp_closure.md`
- graph version updated to `phase14`.
- STOP rules documented: no further connector, simulation, audit workspace, mapper diagnostics, profile notes, benchmark, live ERP, or ERP write-action expansion in this MVP closure.

## Historical Infrastructure Context

The previous infrastructure closeout remains useful historical context. It documented capabilities that future ERP approval work should preserve:

- local sessions persisted as filesystem JSON.
- run traces persisted as JSONL plus summary JSON.
- HITL/checkpoints backed by local SQLite paths.
- in-process per-session FIFO queueing.
- runtime backend abstractions:
  - `SessionRepository`
  - `RunTraceRepository`
  - `QueueBackend`
  - `HitlRepository`
- optional Redis-backed queueing and Postgres-backed run/event storage.
- runs explorer APIs:
  - `GET /api/runs`
  - `GET /api/runs/stats`
  - `GET /api/runs/{run_id}`
  - `GET /api/runs/{run_id}/events`
  - `GET /api/hitl/pending`
- Prometheus metrics and `/metrics`.
- OTel tracing middleware.
- benchmark and live-validation metadata.

These are infrastructure capabilities, not the active product identity.

## Legacy Compatibility

Still intentionally present:

- [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
- [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)
- [backend/benchmarks/cases/rfp_security](backend/benchmarks/cases/rfp_security)
- [knowledge/RFP Security](knowledge/RFP%20Security)

These paths support existing tests and compatibility benchmarks until ERP-specific validation suites can replace legacy compatibility checks.

## Known Risks / Blockers

- ERP-specific approval logic is minimal and mock-only.
- no SAP, Dynamics, Oracle, or custom ERP connector is enabled by default.
- no real approval write action exists yet.
- no real comment/request-more-info/routing action exists yet.
- no real ERP write-action approval card exists yet.
- current benchmark evidence is legacy RFP/security compatibility evidence, not ERP approval accuracy evidence.
- trace analytics are operational summaries only, not process mining, benchmark accuracy, or production ERP action audit.
- action proposal ledger is proposed-only storage, not an action execution ledger.
- reviewer notes are local artifacts, not ERP comments.
- action simulation ledger is local dry-run storage, not an action execution ledger.
- connector profiles are read-only interface metadata, not production ERP integrations.
- connector diagnostics and APIs must never expose secret values.
- fixture replay and replay coverage are local mapping diagnostics only, not live ERP testing.
- model/provider credentials and network availability may affect live model validation.
- full production write actions require future idempotency, audit, and strict HITL design.

## Recommended Next Steps

1. stop MVP expansion at Phase 14 unless a future task explicitly opens a new phase.
2. keep connector outputs normalized into `ApprovalContextRecord` and never add write operations.
3. keep all real and mock ERP writes out of scope until a separate guarded execution phase.
