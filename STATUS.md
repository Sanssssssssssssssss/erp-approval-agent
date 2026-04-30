# ERP Approval Agent Workbench Status

## Current Active Phase

Phase 0: ERP Approval Agent product-semantic migration.

The current task is to align product language, documentation, frontend copy, and high-level repository direction with ERP Approval Agent Workbench. This phase does not implement real ERP connectors, approval business rules, ERP benchmark suites, or production ERP automation.

## Active Product Direction

ERP Approval Agent Workbench is becoming a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows.

Current positioning:

- approval recommendation, not autonomous final execution.
- LLM-first approval reasoning, governed by graph nodes and HITL controls.
- HarnessRuntime-owned execution lifecycle.
- LangGraph orchestration.
- auditable approval trace.
- ERP policy and business context retrieval through existing knowledge abstractions.

## Phase 0 Done Criteria

- public docs present ERP Approval Agent Workbench as the product identity.
- legacy RFP/security modules are labeled compatibility assets.
- frontend copy uses approval assistant, audit trace, evidence, approval threads, workflow tools, and policy/evidence index language.
- API title is updated without route changes.
- existing focused backend compatibility tests still pass.
- frontend build remains green.

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

These paths support existing tests and compatibility benchmarks until an `erp_approval` domain and ERP-specific validation suite are added.

## Known Risks / Blockers

- ERP-specific approval logic is not implemented yet.
- no SAP, Dynamics, Oracle, or custom ERP connector exists yet.
- current benchmark evidence is legacy RFP/security compatibility evidence, not ERP approval accuracy evidence.
- model/provider credentials and network availability may affect live model validation.
- full production write actions require future idempotency, audit, and strict HITL design.

## Recommended Next Steps

1. add an `erp_approval` domain skeleton beside the legacy `rfp_security` domain.
2. define a minimal mock approval request schema and structured LLM output.
3. add graph nodes for ERP intake, context retrieval, policy context, reasoning, self-check, HITL gate, action proposal, and audit finalization.
4. keep mock context read-only until Phase 2 adapters exist.
