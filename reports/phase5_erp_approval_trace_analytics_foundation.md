# Phase 5: ERP Approval Trace Ledger + Analytics Foundation

## Summary

Phase 5 adds a local-first ERP approval trace ledger and read-only analytics foundation. Each ERP approval run can now write a structured trace record during finalization, and the backend exposes lightweight read-only endpoints for trace listing, trace lookup, and analytics summary.

This is not a benchmark, process-mining system, ERP connector, or action execution layer.

## Implemented

- Added structured trace models for ERP approval run summaries.
- Added a filesystem JSONL trace repository with `trace_id` upsert dedupe.
- Added analytics summarization over structured trace records.
- Updated `erp_finalize_node` to write trace records without blocking final answer delivery.
- Added read-only ERP approval API endpoints:
  - `GET /api/erp-approval/traces?limit=100`
  - `GET /api/erp-approval/traces/{trace_id}`
  - `GET /api/erp-approval/analytics/summary?limit=500`
- Added a frontend `Insights` tab that displays management summary counts from the analytics endpoint.
- Added tests for trace record construction, repository dedupe/listing, analytics, API endpoints, and graph smoke trace writes.

## Trace Ledger Data Boundary

Trace records are built from structured graph state:

- approval request fields
- context source IDs
- recommendation status and confidence
- missing information and risk flags
- citations
- guard warnings and downgrade state
- HITL review status and decision
- action proposal IDs, action types, statuses, and validation warnings
- a short final answer preview

The ledger does not store full raw prompts. The final answer preview is length-limited and is not used as an analytics source of truth.

## Why Structured Trace, Not Final Answer Parsing

Analytics must be stable and auditable. Final answers are user-facing prose and may change wording, formatting, or language. Phase 5 therefore summarizes only structured `ApprovalTraceRecord` fields and never reverse-parses the final answer text for recommendation status, warnings, proposal outcomes, or review state.

## Frontend

Implemented a minimal read-only `Insights` panel. It displays:

- total traces
- human review and guard downgrade counts
- blocked/rejected proposal counts
- recommendation status counts
- review status counts
- top missing information
- proposal action type counts

It does not add action buttons or write behavior.

## Still Not Implemented

- real ERP connectors.
- ERP approval/rejection/payment/comment/request-more-info/route/supplier/budget/contract writes.
- `approval.*` Harness events.
- production process mining.
- benchmark accuracy claims.
- frontend trace detail drill-down.

## Validation

Passed:

```powershell
backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_erp_approval_domain `
  backend.tests.test_erp_approval_routing `
  backend.tests.test_erp_approval_edges `
  backend.tests.test_erp_approval_context_adapter `
  backend.tests.test_erp_approval_graph_smoke `
  backend.tests.test_erp_approval_hitl_gate `
  backend.tests.test_erp_approval_action_proposals `
  backend.tests.test_erp_approval_trace_store `
  backend.tests.test_erp_approval_analytics `
  backend.tests.test_erp_approval_api
```

Result: `Ran 42 tests in 0.108s - OK`.

```powershell
backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Result: `Ran 11 tests in 0.006s - OK`.

```powershell
backend\.venv\Scripts\python.exe -m py_compile `
  src/backend/domains/erp_approval/trace_models.py `
  src/backend/domains/erp_approval/trace_store.py `
  src/backend/domains/erp_approval/analytics.py `
  src/backend/api/erp_approval.py `
  src/backend/api/app.py `
  src/backend/orchestration/executor.py `
  src/backend/orchestration/state.py `
  backend/tests/test_erp_approval_trace_store.py `
  backend/tests/test_erp_approval_analytics.py `
  backend/tests/test_erp_approval_api.py `
  backend/tests/test_erp_approval_graph_smoke.py
```

Result: passed with no output.

```powershell
@'
from src.backend.orchestration.compiler import compile_harness_orchestration_graph
class Dummy:
    pass
compiled = compile_harness_orchestration_graph(Dummy(), include_checkpointer=False)
print(type(compiled).__name__)
'@ | backend\.venv\Scripts\python.exe -
```

Result: `CompiledStateGraph`.

```powershell
cd src\frontend
npm run build
```

Result: Next.js production build completed successfully.

```powershell
git diff --check
```

Result: no whitespace errors. Git reported LF-to-CRLF working-copy warnings on Windows.

## Phase 6 Recommendation

Add read-only analytics refinement: filters, export, trace detail drill-down, and trend summaries for missing-document patterns, policy friction, escalation drivers, and high-risk clusters. Keep the work grounded in structured trace records and keep all ERP writes out of scope.
