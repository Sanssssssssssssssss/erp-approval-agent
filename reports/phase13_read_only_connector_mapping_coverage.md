# Phase 13: Read-Only Connector Mapping Coverage Expansion + Replay Coverage Matrix

## What Changed

- Added representative local provider payload fixtures for seven additional read-only operations:
  - `vendor`
  - `budget`
  - `purchase_order`
  - `invoice`
  - `goods_receipt`
  - `contract`
  - `policy`
- Expanded fixture coverage to four provider profiles:
  - SAP S/4HANA OData
  - Microsoft Dynamics 365 Finance & Operations OData
  - Oracle Fusion REST
  - Custom HTTP JSON
- Extended fixture operation slug detection for purchase requisition, vendor, budget, PO, invoice, GRN, contract, and policy payloads.
- Enhanced provider payload mapper entity-id extraction for operation-specific representative fields.
- Added replay coverage models and service:
  - `ErpConnectorReplayCoverageItem`
  - `ErpConnectorReplayCoverageSummary`
  - `build_replay_coverage_matrix`
- Added GET-only coverage endpoint:
  - `GET /api/erp-approval/connectors/replay/coverage`
- Extended frontend connector diagnostics with replay coverage totals, by-provider counts, by-operation counts, warnings, and failed checks.
- Updated README, CODEX handoff, status, plan, and product direction docs.

## Fixture Coverage Scope

The fixture set now covers 4 providers x 8 read-only operations, for 32 local representative payload files:

- `approval_request`
- `vendor`
- `budget`
- `purchase_order`
- `invoice`
- `goods_receipt`
- `contract`
- `policy`

These fixtures are representative mapping examples only. They are not live ERP data and do not claim complete SAP, Dynamics, Oracle, or custom ERP schema coverage.

## Coverage Matrix

The coverage matrix replays every local provider fixture through the existing mapper and records:

- provider
- operation
- fixture name
- replay status
- validation status
- record count
- source ids
- warnings
- failed checks

It verifies mapper output completeness for `ApprovalContextRecord` fields and read-only metadata. It does not judge LLM quality, approval correctness, business policy correctness, or ERP integration readiness.

## Why Coverage Is Not A Benchmark

- It has no ground-truth approval decisions.
- It does not measure model accuracy.
- It does not compare vendors or ERP systems.
- It only checks local fixture mapping completeness.
- It is a mapper readiness diagnostic, not a production quality or benchmark claim.

## Why Replay Is Not A Live ERP Test

- It reads only JSON fixtures under `backend/fixtures/erp_approval/provider_payloads`.
- It does not call `HttpReadOnlyErpConnector._get`.
- It does not open network connections.
- It does not require credentials.
- It does not invoke tools or `capability_invoke`.
- It does not create, update, approve, reject, route, comment, pay, onboard, sign, or modify any ERP object.

## API Endpoints

New GET-only endpoint:

- `GET /api/erp-approval/connectors/replay/coverage`

Existing connector diagnostics endpoints remain:

- `GET /api/erp-approval/connectors/config`
- `GET /api/erp-approval/connectors/health`
- `GET /api/erp-approval/connectors/profiles`
- `GET /api/erp-approval/connectors/profiles/{provider}`
- `GET /api/erp-approval/connectors/replay/fixtures`
- `GET /api/erp-approval/connectors/replay`

No connect, test-live, execute, POST, PUT, PATCH, or DELETE connector endpoint was added.

## Frontend Diagnostics Update

The `Insights` tab connector diagnostics panel now shows:

- replay coverage totals
- passed and failed coverage item counts
- by-provider fixture counts
- by-operation fixture counts
- per-fixture replay status and validation result
- failed checks and warnings

The UI states that coverage is local fixture replay only and is not a live ERP integration test. It does not add real connect, test-live, execute, send, approve, reject, or route controls.

## Still Not Implemented

- no live SAP/Dynamics/Oracle/custom ERP integration
- no production ERP credentials
- no live connector network replay
- no ERP action execution API
- no action execution ledger
- no `approval.*` Harness events
- no benchmark suite or process-mining claim

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
  backend.tests.test_erp_approval_audit_package `
  backend.tests.test_erp_approval_audit_workspace `
  backend.tests.test_erp_approval_action_simulation `
  backend.tests.test_erp_approval_connectors `
  backend.tests.test_erp_approval_connector_config `
  backend.tests.test_erp_approval_connector_api `
  backend.tests.test_erp_approval_connector_replay `
  backend.tests.test_erp_approval_connector_coverage
```

Result: `Ran 101 tests ... OK`

Passed:

```powershell
backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Result: `Ran 11 tests ... OK`

Passed:

```powershell
backend\.venv\Scripts\python.exe -m py_compile ...
```

Result: `py_compile ok: 10 files`

Passed:

```powershell
# LangGraph compiler smoke
```

Result: `CompiledStateGraph`

Passed:

```powershell
cd src\frontend
npm run build
```

Result: Next.js production build completed successfully.

Passed:

```powershell
git diff --check
```

Result: exit code 0, with Windows LF/CRLF conversion warnings only.

## Phase 14 Recommendation

Add local-only connector profile notes or richer mapper diagnostics for reviewers, still using fixtures and fake transports only. Keep mock as the default connector, keep non-mock providers disabled/no-network by default, and do not add connector write operations or action execution.
