# CODEX_HANDOFF

Treat this repository as ERP Approval Agent Workbench. It is not a generic agent sandbox and is no longer primarily an RFP/security product.

Phase 0 semantic migration is complete. Phase 1 added the minimal LLM-first ERP approval graph skeleton. Phase 2 added read-only mock ERP context adapters. Phase 3 added a durable ERP recommendation review HITL gate. Phase 4 added guarded ERP action proposal drafts. Phase 5 added a local ERP approval trace ledger and read-only analytics foundation. Phase 6 added read-only trace explorer filters, detail lookup, JSON/CSV export, and trend summaries. Phase 7 added a proposed-only action proposal ledger and read-only audit packages. Phase 8 added a local audit package workspace with saved manifests and append-only reviewer notes. Current work should treat `erp_approval` as an implemented backend graph path, while still preserving mock-only/read-only/proposed-only/read-only-analytics/local-audit boundaries.

## First Read

- [README.md](README.md)
- [docs/product/erp_approval_agent_plan.md](docs/product/erp_approval_agent_plan.md)
- [RUNBOOK.md](RUNBOOK.md)
- [LOCAL_DEV.md](LOCAL_DEV.md)
- [src/backend/runtime/runtime.py](src/backend/runtime/runtime.py)
- [src/backend/orchestration](src/backend/orchestration)
- [src/backend/knowledge](src/backend/knowledge)

## Architecture Invariants

Keep these intact unless a task explicitly changes them:

- `HarnessRuntime` is the lifecycle owner.
- LangGraph is the orchestration graph layer.
- canonical harness events remain the execution truth.
- HITL and checkpoint semantics remain durable and auditable.
- knowledge retrieval abstractions remain the context/evidence boundary.
- capability governance remains the boundary for tool execution.

Do not add a second runtime.
Do not add a second agent framework.
Do not bypass graph/HITL governance for tool execution or irreversible actions.
Do not over-engineer the migration.

## Product Direction

The intended product is an LLM-first approval reasoning workbench for ERP business approvals. The `erp_approval` domain now exists beside the legacy `rfp_security` module.

LLM-first is the intended approval reasoning strategy:

- prompts and structured LLM outputs should carry the approval analysis.
- graph nodes should define the execution boundary and audit stages.
- tools and external actions must remain graph/HITL governed.
- irreversible ERP actions must never bypass explicit approval controls.

Prefer small, reviewable changes that keep the current local workbench running.

## Implemented ERP Skeleton

Current ERP graph:

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

It produces an approval recommendation, not autonomous final execution. Phase 2 added read-only context adapter interfaces and mock records. Phase 3 added a durable HITL review gate for accepting, rejecting, or editing the agent recommendation. Phase 4 added proposed-only action drafts with validation and idempotency fields. Phase 5 writes local trace records from structured graph state and exposes read-only analytics summaries. Phase 6 turns those records into a read-only trace explorer. Phase 7 persists action proposal records and builds temporary audit packages for internal review. Phase 8 lets reviewers save local package manifests and append local reviewer notes. HITL approve in this path means "accept the agent recommendation"; it never means "approve the ERP object."

Current capabilities:

- LLM-first ERP intake and reasoning prompts.
- mock ERP/policy context.
- deterministic recommendation guard via `human_review_required`.
- durable ERP recommendation HITL review using existing checkpoint/resume semantics.
- deterministic guard for weak evidence and unsafe next actions.
- guarded action proposals that are always `executable=false`.
- local JSONL trace ledger at `backend/storage/erp_approval/approval_traces.jsonl`.
- local JSONL action proposal ledger at `backend/storage/erp_approval/action_proposals.jsonl`.
- local JSONL saved audit packages and reviewer notes.
- read-only trace/proposal/audit APIs plus local audit workspace POST endpoints under `/api/erp-approval/*`.
- frontend `Insights` tab for trace-based summary counts, filters, drill-down, proposal records, audit package download, saved package workspace, reviewer notes, export, and trend buckets.

Still absent:

- real ERP connector.
- real approval write action.
- real comment/request-more-info/routing write action.
- real ERP approval/rejection/payment/supplier/contract/budget execution.
- ERP benchmark suite.

Trace analytics rules:

- build analytics from `ApprovalTraceRecord` fields only.
- do not reverse-parse `final_answer`.
- do not filter search text against `final_answer_preview`.
- do not treat analytics as a benchmark or process-mining system.
- do not add write endpoints under the ERP approval analytics router.
- action proposal ledger is not an execution ledger.
- audit package completeness checks judge structured-record completeness only, not approval correctness.
- reviewer notes are local notes, not ERP comments.
- local audit workspace POST endpoints must not be reused for ERP writes.

## Legacy Compatibility

Do not remove or aggressively rename these:

- [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
- [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)
- [backend/benchmarks/cases/rfp_security](backend/benchmarks/cases/rfp_security)
- [knowledge/RFP Security](knowledge/RFP%20Security)

Existing RFP/security tests and benchmarks are compatibility checks until ERP-specific suites are added.

## Local Commands

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

Legacy RFP/security compatibility smoke benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Frontend build:

```powershell
cd src\frontend
npm run build
```

## Secrets

Use your own local `backend/.env`.
Do not print or commit real keys.
Use [backend/.env.example](backend/.env.example) for variable names.
