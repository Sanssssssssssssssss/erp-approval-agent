# ERP Approval Agent Workbench Status

## Current Active Phase

Phase 5: ERP Approval Trace Ledger + Analytics Foundation.

Phase 0 product-semantic migration is complete. Phase 1 added the LLM-first ERP approval graph skeleton, Phase 2 added the read-only mock ERP context adapter, Phase 3 added durable recommendation review through the existing HITL checkpoint/resume mechanism, Phase 4 added proposed-only ERP action drafts, and Phase 5 adds a local structured trace ledger plus read-only analytics summary:

```text
bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_reasoning -> erp_guard -> erp_hitl_gate -> erp_action_proposal -> erp_finalize -> finalize
```

The current active capability is Phase 5: after finalization, the graph writes a local ERP approval trace record from structured state and exposes read-only analytics over those records. Analytics summarize recommendation status, review status, missing information, risk flags, guard warnings, and action proposal validation outcomes. They do not parse final answer text and do not call ERP systems.

## Active Product Direction

ERP Approval Agent Workbench is becoming a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows.

Current positioning:

- approval recommendation, not autonomous final execution.
- LLM-first approval reasoning, governed by graph nodes and HITL controls.
- existing ERP approval graph skeleton.
- mock ERP/policy context.
- durable ERP recommendation review HITL gate.
- guarded ERP action proposal drafts.
- local ERP approval trace ledger.
- read-only ERP approval analytics API.
- frontend management Insights panel.
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
- no SAP, Dynamics, Oracle, or custom ERP connector exists yet.
- no real approval write action exists yet.
- no real comment/request-more-info/routing action exists yet.
- no real ERP write-action approval card exists yet.
- current benchmark evidence is legacy RFP/security compatibility evidence, not ERP approval accuracy evidence.
- trace analytics are operational summaries only, not process mining or benchmark accuracy.
- model/provider credentials and network availability may affect live model validation.
- full production write actions require future idempotency, audit, and strict HITL design.

## Recommended Next Steps

1. start Phase 6 read-only analytics refinement: trend filters, export, and richer trace drill-down.
2. keep analytics grounded in structured trace records, evidence, review status, validation warnings, and proposal outcomes.
3. keep all real ERP writes out of scope until a separate guarded execution phase.
