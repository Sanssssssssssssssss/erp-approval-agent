# Phase 6: ERP Approval Trace Explorer + Read-only Analytics Refinement

## Summary

Phase 6 turns the Phase 5 trace ledger into a usable read-only management view. It adds structured trace filters, trace detail lookup, JSON/CSV export, date-bucket trend summaries, and a frontend trace explorer inside the existing `Insights` tab.

This remains a local-first analytics refinement. It is not a benchmark, process-mining system, ERP connector, ERP write-action layer, or action execution audit.

## Implemented

- Added trace query/filter models:
  - `ApprovalTraceQuery`
  - `ApprovalTraceListResponse`
  - `ApprovalTraceExportFormat`
  - `ApprovalTrendBucket`
  - `ApprovalTrendSummary`
- Added repository query support for:
  - approval type
  - recommendation status
  - review status
  - proposal action type
  - human review required
  - guard downgraded
  - high-risk traces
  - structured text fields
  - ISO-string date range
- Added read-only export:
  - JSON structured export
  - CSV stable-header export
- Added trend summary bucketed by `created_at[:10]`.
- Added API endpoints for trace filters, trends, and export.
- Expanded the frontend `Insights` tab with filters, trace list, trace detail, export buttons, and trend buckets.

## Filters, Export, And Trend Summary

Trace filters operate only on structured `ApprovalTraceRecord` fields. `text_query` matches:

- approval ID
- requester
- department
- vendor
- cost center
- trace ID

It intentionally does not match `final_answer_preview`.

CSV export uses a stable header:

```text
trace_id,created_at,approval_id,approval_type,recommendation_status,review_status,human_review_required,guard_downgraded,proposal_action_types,blocked_proposal_ids,rejected_proposal_ids
```

Trend summary groups records by `created_at` date prefix (`YYYY-MM-DD`) and reports counts for total traces, human review, guard downgrades, blocked/rejected proposals, recommendation status, and review status.

## API Endpoints

- `GET /api/erp-approval/traces`
- `GET /api/erp-approval/traces/{trace_id}`
- `GET /api/erp-approval/analytics/summary`
- `GET /api/erp-approval/analytics/trends`
- `GET /api/erp-approval/export.json`
- `GET /api/erp-approval/export.csv`

All endpoints are read-only. No POST, PUT, PATCH, DELETE, action, connector, or ERP execution endpoint was added.

## Frontend Trace Explorer

The `Insights` tab now includes:

- approval type, recommendation status, review status, high-risk, and text filters
- trace list
- trace detail card
- JSON and CSV export buttons
- trend bucket cards

It does not add any approve, reject, comment, request-more-info, route, payment, supplier, budget, or contract action button.

## Still Not Implemented

- real ERP connectors.
- ERP approval/rejection/payment/comment/request-more-info/route/supplier/budget/contract writes.
- `approval.*` Harness events.
- production process mining.
- benchmark accuracy claims.
- saved analytics views or audit handoff packages.

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

Result: `Ran 50 tests in 0.176s - OK`.

```powershell
backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Result: `Ran 11 tests in 0.005s - OK`.

```powershell
backend\.venv\Scripts\python.exe -m py_compile `
  src/backend/domains/erp_approval/trace_models.py `
  src/backend/domains/erp_approval/trace_store.py `
  src/backend/domains/erp_approval/analytics.py `
  src/backend/domains/erp_approval/__init__.py `
  src/backend/api/erp_approval.py `
  backend/tests/test_erp_approval_trace_store.py `
  backend/tests/test_erp_approval_analytics.py `
  backend/tests/test_erp_approval_api.py
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

## Phase 7 Recommendation

Add read-only audit packaging: saved views, export metadata, trace bundle pages, and trace completeness checks. Keep the work grounded in `ApprovalTraceRecord` and keep all ERP writes out of scope.
