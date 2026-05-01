# Phase 12: Read-Only Connector Fixture Replay + Diagnostics UX

## What Changed

- Added connector replay Pydantic models for local fixture replay requests, records, validation, summaries, and fixture info.
- Added a local fixture replay service that reads JSON fixtures from `backend/fixtures/erp_approval/provider_payloads`.
- Added replay validation for `ApprovalContextRecord` output completeness, provider source-id prefixes, read-only metadata, provider/operation metadata, no-network status, and non-action statements.
- Added GET-only replay APIs:
  - `GET /api/erp-approval/connectors/replay/fixtures`
  - `GET /api/erp-approval/connectors/replay`
- Enhanced connector redaction to redact sensitive URL query params: `token`, `access_token`, `api_key`, `apikey`, `key`, `password`, `secret`, `signature`, and `sig`.
- Added frontend `Connector diagnostics` panel under `Insights` showing redacted config, health, provider profiles, local fixture replay controls, and replay output.
- Updated README, CODEX handoff, status, plan, and product direction docs.

## Fixture Replay Data Boundary

Fixture replay only reads local representative JSON files committed under `backend/fixtures/erp_approval/provider_payloads`. It maps those payloads through the existing provider mapper into `ApprovalContextRecord` records. Replay output is connector readiness and mapping diagnostic data; it is not live ERP data.

Every replay record includes:

- `dry_run=true`
- `network_accessed=false`
- `Fixture replay only. No ERP network or write action was executed.`

## Why Replay Is Not A Live ERP Test

- It never calls `HttpReadOnlyErpConnector._get`.
- It never opens a network connection.
- It does not require credentials.
- It does not call tools or `capability_invoke`.
- It does not create, update, approve, reject, route, comment, pay, onboard, sign, or modify any ERP object.

## Redaction Enhancement

Phase 11 already redacted URL userinfo and auth secret values. Phase 12 also redacts sensitive query parameter values in redacted config output. Example:

```text
https://erp.example/path?token=abc&company=100
```

becomes:

```text
https://erp.example/path?token=<redacted>&company=100
```

The raw config is not mutated; only redacted output is changed.

## API Endpoints

New GET-only endpoints:

- `GET /api/erp-approval/connectors/replay/fixtures`
- `GET /api/erp-approval/connectors/replay?provider=...&operation=...&fixture_name=...&approval_id=...&correlation_id=...`

Existing connector diagnostics endpoints remain GET-only:

- `GET /api/erp-approval/connectors/config`
- `GET /api/erp-approval/connectors/health`
- `GET /api/erp-approval/connectors/profiles`
- `GET /api/erp-approval/connectors/profiles/{provider}`

## Frontend Diagnostics UX

The `Insights` tab now includes a `Connector diagnostics` panel. It shows:

- current redacted connector config
- connector health diagnostics
- provider profile metadata
- fixture replay selector
- replay result records, source ids, validation state, warnings, `network_accessed=false`, and non-action statement

The UI does not include connect, test-live, execute, send, approve, reject, or route buttons.

## Still Not Implemented

- no live SAP/Dynamics/Oracle/custom ERP integration
- no production ERP credentials
- no real network replay
- no ERP action execution API
- no action execution ledger
- no `approval.*` Harness events

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
  backend.tests.test_erp_approval_connector_replay
```

Result: `Ran 95 tests ... OK`

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

Passed:

```powershell
# LangGraph compiler smoke
# Output: CompiledStateGraph
```

Passed:

```powershell
cd src\frontend
npm run build
```

Passed:

```powershell
git diff --check
```

Result: exit code 0, with Windows LF/CRLF conversion warnings only.

## Phase 13 Recommendation

Expand read-only connector mapping coverage with more local fixture payloads for vendor, budget, purchase order, invoice, goods receipt, contract, and policy operations. Keep the harness fixture-only and no-network by default.
