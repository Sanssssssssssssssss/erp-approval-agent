# Phase 11: Read-Only Connector Configuration Hardening

## What Changed

- Added typed ERP connector env loading with safe defaults:
  - `ERP_CONNECTOR_PROVIDER=mock`
  - `ERP_CONNECTOR_ENABLED=false`
  - `ERP_CONNECTOR_ALLOW_NETWORK=false`
  - `ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN=false`
- Added connector selection summaries and redacted connector config output.
- Added connector diagnostics models and GET-only connector config/health/profile APIs.
- Added representative provider payload fixtures for SAP S/4HANA OData, Dynamics 365 F&O OData, Oracle Fusion REST, and custom HTTP JSON.
- Added provider payload mappers for `records`, `value`, `d.results`, and single-object payload shapes.
- Updated the HTTP read-only connector to use the shared mapper and continue allowing only GET.
- Updated `GRAPH_VERSION` to `phase11`.
- Updated docs and `.env.example` to clarify mock/default-disabled/no-network behavior.

## Config / Env Loading Rules

- Provider defaults to `mock`.
- Connector `enabled` defaults to `false`.
- Connector `allow_network` defaults to `false`.
- Connector mode remains `read_only`.
- Non-mock providers are blocked unless `ERP_CONNECTOR_EXPLICIT_READ_ONLY_OPT_IN=true`.
- Explicit read-only opt-in does not enable network access; `ERP_CONNECTOR_ALLOW_NETWORK=true` is still required.
- Non-mock connectors are not selected as default unless `ERP_CONNECTOR_USE_AS_DEFAULT=true`, `enabled=true`, `allow_network=true`, and explicit read-only opt-in is true.
- Invalid provider/auth/timeout values fall back to safe defaults with warnings instead of crashing startup.

## Redaction Rules

- `auth_env_var` stores only the environment variable name.
- Redacted config returns `auth_env_var_present=true/false`; it never returns the secret value.
- Redacted config removes userinfo from `base_url` if a URL accidentally contains embedded credentials.
- Connector diagnostics and health output do not include auth header values.
- HTTP connector auth headers use redacted placeholder values only for test transport calls.

## Healthcheck API

Added read-only endpoints:

- `GET /api/erp-approval/connectors/config`
- `GET /api/erp-approval/connectors/health`
- `GET /api/erp-approval/connectors/profiles`
- `GET /api/erp-approval/connectors/profiles/{provider}`

These endpoints do not call ERP systems, do not call tools, and do not invoke capabilities. Provider profile endpoints return metadata only.

## Provider Mapping Fixtures

Added representative fixture payloads under `backend/fixtures/erp_approval/provider_payloads/`:

- `sap_s4_odata_purchase_requisition.json`
- `dynamics_fo_odata_purchase_requisition.json`
- `oracle_fusion_rest_purchase_requisition.json`
- `custom_http_json_purchase_requisition.json`

The mapper normalizes these into `ApprovalContextRecord` records with provider source-id prefixes and read-only metadata. These are mapping examples, not production ERP schema coverage.

## Why Phase 11 Is Still Not Live ERP Integration

- Default connector remains mock.
- Default network access remains disabled.
- SAP/Dynamics/Oracle/custom profiles are metadata and skeletons only.
- Tests use fake transport and fixture payloads only.
- No production credentials are required or committed.

## Why Connector Is Not An Action Executor

- Connectors only provide read-only context records.
- No connector defines write operations.
- No connector is wired to `capability_invoke`.
- No approve/reject/payment/comment/request-more-info/route/supplier/budget/contract action is executed.
- Every connector result/diagnostic includes: `Read-only connector. No ERP write action was executed.`

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
  backend.tests.test_erp_approval_connector_api
```

Result: `Ran 88 tests ... OK`

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
backend\.venv\Scripts\python.exe -m py_compile `
  src/backend/domains/erp_approval/connectors/config.py `
  src/backend/domains/erp_approval/connectors/diagnostics.py `
  src/backend/domains/erp_approval/connectors/mappers.py `
  src/backend/domains/erp_approval/connectors/registry.py `
  src/backend/domains/erp_approval/connectors/http_readonly.py `
  src/backend/domains/erp_approval/connectors/__init__.py `
  src/backend/domains/erp_approval/__init__.py `
  src/backend/api/erp_approval.py `
  src/backend/orchestration/executor.py `
  src/backend/orchestration/state.py `
  backend/tests/test_erp_approval_connectors.py `
  backend/tests/test_erp_approval_connector_config.py `
  backend/tests/test_erp_approval_connector_api.py
```

Passed:

```powershell
# LangGraph compiler smoke
# Output: CompiledStateGraph
```

Passed:

```powershell
git diff --check
```

Result: exit code 0, with Windows LF/CRLF conversion warnings only.

Frontend build was not run because Phase 11 did not modify frontend files.

## Phase 12 Recommendation

Add a read-only connector fixture replay or connector diagnostics UX that lets reviewers inspect provider mapping behavior locally. Keep fake transports and fixture payloads only, keep diagnostics redacted, and continue treating connectors as context providers rather than action executors.
