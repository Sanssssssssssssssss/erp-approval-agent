# Phase 7: ERP Action Proposal Ledger + Read-only Audit Package

## Summary

Phase 7 persists Phase 4 action proposals as independent local ledger records and adds read-only audit packages for internal review. This phase still does not execute real or mock ERP actions.

## Implemented

- Added proposal ledger models:
  - `ApprovalActionProposalRecord`
  - `ApprovalActionProposalWriteResult`
  - `ApprovalActionProposalQuery`
  - `ApprovalActionProposalListResponse`
  - `ApprovalAuditPackage`
  - `ApprovalAuditPackageTrace`
  - `ApprovalAuditPackageProposal`
  - `ApprovalAuditCompletenessCheck`
- Added local JSONL repository at `backend/storage/erp_approval/action_proposals.jsonl`.
- Added `build_proposal_records_from_state` for structured graph-state persistence.
- Added audit package builder and completeness checks.
- Updated `erp_finalize_node` to write both trace ledger and proposal ledger records.
- Added read-only proposal and audit package API endpoints.
- Extended the frontend `Insights` trace detail with action proposal records and audit package JSON download.

## Action Proposal Ledger vs Action Execution Ledger

The action proposal ledger stores proposed-only drafts. It is not an action execution ledger.

Proposal records preserve:

- proposal ID and trace ID
- approval ID and approval type
- action type and status
- payload preview
- citations
- idempotency key, scope, and fingerprint
- risk level
- validation warnings
- `executable=false`
- non-action statement

No connector, tool call, capability invocation, mock action, or ERP write is executed.

## Audit Package Data Boundary

Audit packages are built from structured trace records and structured proposal records. They are temporary read-only packages returned by API; they are not persisted as a new write artifact in this phase.

Audit packages do not parse final answers, prompts, or model prose. They do not evaluate whether the model was correct and do not claim approval accuracy.

## Completeness Checks

Completeness checks are auditability checks only:

- `has_approval_request`
- `has_context_sources`
- `has_recommendation_status`
- `has_citations`
- `has_guard_result`
- `has_review_status`
- `has_action_proposals`
- `proposal_has_idempotency`
- `proposal_executable_false`
- `proposal_has_non_action_statement`
- `proposal_citations_present_in_trace_context`

They do not judge LLM quality, approval correctness, business policy correctness, or benchmark accuracy.

## API Endpoints

- `GET /api/erp-approval/proposals?limit=100`
- `GET /api/erp-approval/proposals/{proposal_record_id}`
- `GET /api/erp-approval/traces/{trace_id}/proposals`
- `GET /api/erp-approval/audit-package?trace_ids=...&limit=100`

All endpoints are read-only. No POST, PUT, PATCH, DELETE, action, connector, or ERP execution endpoint was added.

## Frontend

The `Insights` trace detail now shows:

- action proposal records
- idempotency key
- risk level
- validation warnings
- `executable=false`
- audit package JSON download

No action button was added.

## Still Not Implemented

- real ERP connectors.
- real or mock ERP action execution.
- approval/rejection/payment/comment/request-more-info/route/supplier/budget/contract writes.
- `approval.*` Harness events.
- production action execution audit.
- process mining.
- benchmark accuracy claims.
- persisted audit package manifests.

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
  backend.tests.test_erp_approval_api `
  backend.tests.test_erp_approval_proposal_ledger `
  backend.tests.test_erp_approval_audit_package
```

Result: `Ran 57 tests in 0.405s - OK`.

```powershell
backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Result: `Ran 11 tests in 0.015s - OK`.

```powershell
backend\.venv\Scripts\python.exe -m py_compile `
  src/backend/domains/erp_approval/proposal_ledger_models.py `
  src/backend/domains/erp_approval/proposal_ledger.py `
  src/backend/domains/erp_approval/__init__.py `
  src/backend/api/erp_approval.py `
  src/backend/orchestration/executor.py `
  src/backend/orchestration/state.py `
  backend/tests/test_erp_approval_proposal_ledger.py `
  backend/tests/test_erp_approval_audit_package.py `
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

## Phase 8 Recommendation

Add read-only saved audit package manifests, package metadata, reviewer notes, and internal review export views. Keep everything local-first and keep all real or mock ERP writes out of scope.
