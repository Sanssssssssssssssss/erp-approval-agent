# ERP Approval Agent Workbench Status

## Current Active Phase

Phase 2: read-only ERP context adapter interface.

Phase 0 product-semantic migration is complete. Phase 1 added the LLM-first ERP approval graph skeleton:

```text
bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_reasoning -> erp_guard -> erp_finalize -> finalize
```

The current active task is Phase 2: add a read-only ERP context adapter interface with mock records. This phase does not implement real ERP connectors, approval write actions, real ERP HITL cards, ERP benchmark suites, or production ERP automation.

## Active Product Direction

ERP Approval Agent Workbench is becoming a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows.

Current positioning:

- approval recommendation, not autonomous final execution.
- LLM-first approval reasoning, governed by graph nodes and HITL controls.
- existing ERP approval graph skeleton.
- mock ERP/policy context.
- soft human review gate.
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

- ERP-specific approval logic is minimal and mock-only.
- no SAP, Dynamics, Oracle, or custom ERP connector exists yet.
- no real approval write action exists yet.
- no real ERP HITL approval card exists yet.
- current benchmark evidence is legacy RFP/security compatibility evidence, not ERP approval accuracy evidence.
- model/provider credentials and network availability may affect live model validation.
- full production write actions require future idempotency, audit, and strict HITL design.

## Recommended Next Steps

1. complete the read-only mock ERP context adapter interface.
2. normalize approval request, vendor, budget, PO, invoice, goods receipt, contract, and policy context records.
3. keep all ERP write actions out of scope until guarded action phases.
