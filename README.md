# ERP Approval Agent Workbench

ERP Approval Agent Workbench is a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows. It helps review approval requests with retrieved business context, policy context, auditable reasoning traces, and human-in-the-loop approval controls.

The repository target identity is `erp-approval-agent`. Phase 0 aligned the public product language, Phase 1 added the first minimal ERP approval graph skeleton, Phase 2 added read-only mock ERP context adapters, Phase 3 added a durable recommendation review HITL gate, Phase 4 added guarded ERP action proposal drafts, Phase 5 added a local ERP approval trace ledger plus read-only analytics foundation, Phase 6 added a read-only trace explorer with filters, export, drill-down, and trend summaries, Phase 7 added a proposed-only action proposal ledger plus read-only audit packages, and Phase 8 adds a local audit package workspace with reviewer notes.

## Product Direction

This project is becoming an enterprise approval assistant for ERP workflows such as:

- purchase requisitions
- expense approvals
- invoice and payment review
- supplier onboarding
- contract exception review
- budget exception review

The intended future product posture is approval recommendation, not autonomous final execution. LLM-first approval reasoning is the primary direction, but graph nodes, HarnessRuntime events, checkpoints, HITL gates, and capability governance remain the execution boundary.

## Current Architecture Anchors

These anchors stay intact across the migration:

- `HarnessRuntime` remains the HarnessRuntime-owned execution lifecycle.
- LangGraph remains the graph-driven approval workflow orchestration layer.
- existing harness event semantics remain the execution truth.
- checkpoint and human-in-the-loop approval control concepts remain in place.
- knowledge retrieval abstractions remain the path for ERP policy and business context retrieval.
- no second runtime, second agent framework, or parallel lifecycle owner is introduced.

## Legacy Compatibility

The previous implementation focused on RFP/security answer drafting and security questionnaire validation. That code remains available as legacy compatibility while ERP-specific domains are introduced later:

- [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
  - legacy domain schemas, prompts, policies, evidence planning, verifier, and exports
- [knowledge/RFP Security](knowledge/RFP%20Security)
  - legacy corpus still used by existing tests and benchmark smoke checks
- [backend/benchmarks/cases/rfp_security](backend/benchmarks/cases/rfp_security)
  - legacy 20-case compatibility evaluation pack
- [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)
  - legacy suite runner used until ERP-specific benchmark suites exist

These legacy paths are not the new product identity. They are retained to avoid unnecessary breakage during the semantic migration.

## Current Phase Status

Completed:

- Phase 0 product-semantic migration.
- current LLM-first ERP approval graph:
  `bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_reasoning -> erp_guard -> erp_hitl_gate -> erp_action_proposal -> erp_finalize -> finalize`.
- Phase 2 read-only ERP context adapter interface.
- normalized mock ERP records for approval request, vendor, budget, purchase order, invoice, goods receipt, contract, and policy context.
- Phase 3 ERP recommendation review HITL gate using the existing checkpoint/resume mechanism.
- Phase 4 guarded ERP action proposal skeleton with deterministic validation, idempotency keys, and `executable=false`.
- Phase 5 local ERP approval trace ledger written from structured graph state.
- read-only ERP approval analytics API for trace summaries.
- Phase 6 trace filtering, detail lookup, JSON/CSV export, and date-bucket trend summaries.
- Phase 7 action proposal ledger and read-only audit packages with completeness checks.
- Phase 8 saved audit package manifests and append-only reviewer notes.
- frontend `Insights` tab for management-efficiency summary counts and trace drill-down.
- frontend copy for ERP recommendation review where approve means accepting the agent recommendation only; no real action buttons are introduced.

Still not implemented:

- real ERP connectors.
- approval write actions.
- production ERP automation.
- real ERP approval/rejection/payment/supplier/contract/budget execution.
- real ERP comment/request-more-info/route execution.
- ERP benchmark accuracy claims.

## Future ERP Approval Direction

The current implemented skeleton flow is:

```text
bootstrap
-> route
-> skill
-> memory_retrieval
-> erp_intake
-> erp_context
-> erp_reasoning
-> erp_guard
-> erp_hitl_gate
-> erp_action_proposal
-> erp_finalize
-> finalize
```

It produces a structured approval recommendation with confidence, missing information, risk flags, citations, proposed next action, and guarded action proposal drafts. If `human_review_required=true`, the graph creates a durable HITL review request. That review accepts, rejects, or edits the agent recommendation only; it does not execute an ERP approval.

Action proposals are proposed-only drafts. They include idempotency fields and validation warnings, but they are not tool calls, capability invocations, connector calls, or ERP writes.

Phase 5 records each completed ERP approval run as a local JSONL trace at `backend/storage/erp_approval/approval_traces.jsonl`. The trace is built from structured graph state, not by parsing final answer text. Phase 6 adds read-only trace filtering, trace detail lookup, JSON/CSV export, and date-bucket trend summaries. Phase 7 persists action proposals separately at `backend/storage/erp_approval/action_proposals.jsonl` and can build temporary read-only audit packages. Phase 8 saves local audit package manifests at `backend/storage/erp_approval/audit_packages.jsonl` and append-only reviewer notes at `backend/storage/erp_approval/reviewer_notes.jsonl`. Analytics summarize recommendation status, review status, missing information, guard warnings, and action proposal validation outcomes.

ERP approval APIs include read-only trace/proposal/audit lookups plus local audit workspace writes:

- `GET /api/erp-approval/traces?limit=100`
- `GET /api/erp-approval/traces/{trace_id}`
- `GET /api/erp-approval/analytics/summary?limit=500`
- `GET /api/erp-approval/analytics/trends?limit=500`
- `GET /api/erp-approval/export.json`
- `GET /api/erp-approval/export.csv`
- `GET /api/erp-approval/proposals?limit=100`
- `GET /api/erp-approval/proposals/{proposal_record_id}`
- `GET /api/erp-approval/traces/{trace_id}/proposals`
- `GET /api/erp-approval/audit-package?trace_ids=...&limit=100`
- `GET /api/erp-approval/audit-packages`
- `GET /api/erp-approval/audit-packages/{package_id}`
- `GET /api/erp-approval/audit-packages/{package_id}/export.json`
- `GET /api/erp-approval/audit-packages/{package_id}/notes`
- `POST /api/erp-approval/audit-packages`
- `POST /api/erp-approval/audit-packages/{package_id}/notes`

The two POST endpoints write only local audit workspace artifacts. They are not ERP writes and do not execute action proposals.

## Quick Start

1. Create the backend environment.

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

2. Copy local environment variables.

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

3. Install frontend dependencies.

```powershell
cd src\frontend
npm install
cd ..\..
```

4. Start the local workbench UI and API.

```powershell
.\backend\scripts\dev\start-dev.ps1 -InstallIfMissing
```

Default URLs:

- Frontend: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- Backend: [http://127.0.0.1:8015](http://127.0.0.1:8015)
- Health: [http://127.0.0.1:8015/health](http://127.0.0.1:8015/health)
- Metrics: [http://127.0.0.1:8015/metrics](http://127.0.0.1:8015/metrics)

## Validation Commands

Focused backend compatibility tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Focused ERP approval tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_erp_approval_domain `
  backend.tests.test_erp_approval_routing `
  backend.tests.test_erp_approval_edges `
  backend.tests.test_erp_approval_context_adapter `
  backend.tests.test_erp_approval_graph_smoke `
  backend.tests.test_erp_approval_hitl_gate `
  backend.tests.test_erp_approval_action_proposals `
  backend.tests.test_erp_approval_trace_store `
  backend.tests.test_erp_approval_analytics `
  backend.tests.test_erp_approval_api `
  backend.tests.test_erp_approval_proposal_ledger `
  backend.tests.test_erp_approval_audit_package `
  backend.tests.test_erp_approval_audit_workspace
```

Legacy RFP/security compatibility benchmark smoke:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Frontend production build:

```powershell
cd src\frontend
npm run build
```

## Safety And Governance

- every approval recommendation should be evidence-first and audit-friendly.
- unsupported claims should be surfaced as missing context or insufficient evidence.
- human-in-the-loop recommendation review does not equal ERP action execution.
- human-in-the-loop approval control remains required before any future irreversible ERP action.
- action proposals are always `executable=false` in the current phase.
- retrieval remains replaceable through the knowledge-layer strategy interface.
- `HarnessRuntime` remains the lifecycle owner.
- future ERP write actions must be idempotent, auditable, and guarded by explicit HITL.
- analytics are based on structured trace records, not final-answer text parsing.
- trace explorer filters only structured fields such as approval id, requester, vendor, cost center, status, date, and risk markers.
- action proposal ledger is not an execution ledger; it stores proposed-only drafts with `executable=false`.
- audit packages are completeness review artifacts, not model-quality benchmarks.
- saved audit packages and reviewer notes are local review artifacts, not ERP comments or ERP writes.

## Non-Claims

This repository does not currently claim to:

- integrate with SAP, Dynamics, Oracle, or any other live ERP system.
- automatically approve ERP requests.
- provide production-ready ERP automation.
- benchmark-prove ERP approval accuracy.
- provide production process mining or execution audit.

Current ERP work includes a graph skeleton, mock read-only context, durable recommendation review HITL, proposed-only action drafts, a local trace explorer/analytics foundation, read-only audit packages, and a local audit package workspace. Legacy RFP/security validation remains only a compatibility signal until ERP-specific suites are added.

## Key Docs

- [QUICKSTART.md](QUICKSTART.md)
- [RUNBOOK.md](RUNBOOK.md)
- [LOCAL_DEV.md](LOCAL_DEV.md)
- [CODEX_HANDOFF.md](CODEX_HANDOFF.md)
- [docs/product/erp_approval_agent_plan.md](docs/product/erp_approval_agent_plan.md)
- [docs/ops/benchmarking.md](docs/ops/benchmarking.md)
