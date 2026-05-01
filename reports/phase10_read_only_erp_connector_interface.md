# Phase 10: Read-only ERP Connector Interface + Connector Registry

## Summary

Phase 10 adds a read-only ERP connector interface and registry for ERP approval context retrieval. The default connector remains the existing mock connector. Non-mock providers are represented as disabled profiles or skeletons only.

This phase is not a live ERP integration and does not execute any ERP write action.

## Implemented

- Added connector models:
  - `ErpConnectorConfig`
  - `ErpReadRequest`
  - `ErpReadResult`
  - provider, mode, operation, auth, and status type aliases.
- Added connector protocol:
  - `ErpReadOnlyConnector`
- Added connector registry:
  - `ErpConnectorRegistry`
  - `build_default_connector_registry`
- Added `MockErpReadOnlyConnector` using the existing mock fixture.
- Added provider profile metadata.
- Added disabled `HttpReadOnlyErpConnector` skeleton.
- Updated `erp_context_node` to fetch context through the default connector registry.
- Added state fields:
  - `erp_connector_result`
  - `erp_connector_warnings`
- Added connector environment variable examples to `backend/.env.example`.

## Why This Is Interface, Not ERP Integration

The connector layer is a context provider boundary. It only returns `ApprovalContextRecord` values inside `ErpReadResult`.

It does not:

- connect to production ERP by default.
- execute approve/reject/payment/comment/request-more-info/route/supplier/budget/contract actions.
- call tools or `capability_invoke`.
- create ERP action records.
- add `approval.*` Harness events.

## Provider Profiles

Provider profiles are metadata only:

- SAP S/4HANA OData
- Microsoft Dynamics 365 Finance & Operations OData
- Oracle Fusion Procurement REST
- Custom HTTP JSON

Each profile declares read operations, source id prefix, endpoint templates, read-only notes, and forbidden methods.

The profiles do not claim live SAP/Dynamics/Oracle/custom ERP integration.

## Read-only Method Boundary

The only allowed HTTP method in the skeleton is `GET`.

Forbidden methods:

- `POST`
- `PUT`
- `PATCH`
- `DELETE`
- `MERGE`

No write operation model was added.

## Network Disabled Default

`HttpReadOnlyErpConnector` defaults to blocked behavior because `enabled=false` and `allow_network=false`.

If `allow_network=false`, `fetch_context` returns `status="blocked"` and records a warning.

The default connector registry registers mock as the default connector. Non-mock HTTP skeletons can be registered for future explicit tests, but they are not the default.

## Secret Handling

Connector config references an `auth_env_var` name only. It does not store or print secret values.

When auth is configured but the environment variable is missing, the connector returns a blocked result or warning without exposing secret material.

## Validation

Passed:

- `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate backend.tests.test_erp_approval_action_proposals backend.tests.test_erp_approval_trace_store backend.tests.test_erp_approval_analytics backend.tests.test_erp_approval_api backend.tests.test_erp_approval_proposal_ledger backend.tests.test_erp_approval_audit_package backend.tests.test_erp_approval_audit_workspace backend.tests.test_erp_approval_action_simulation backend.tests.test_erp_approval_connectors`
  - `Ran 74 tests in 0.481s`
  - `OK`
- `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator`
  - `Ran 11 tests in 0.006s`
  - `OK`
- `backend\.venv\Scripts\python.exe -m py_compile src\backend\domains\erp_approval\connectors\models.py src\backend\domains\erp_approval\connectors\base.py src\backend\domains\erp_approval\connectors\provider_profiles.py src\backend\domains\erp_approval\connectors\http_readonly.py src\backend\domains\erp_approval\connectors\registry.py src\backend\domains\erp_approval\connectors\__init__.py src\backend\domains\erp_approval\context_adapter.py src\backend\domains\erp_approval\__init__.py src\backend\orchestration\executor.py src\backend\orchestration\state.py backend\tests\test_erp_approval_connectors.py`
  - passed
- LangGraph compiler smoke:
  - `CompiledStateGraph`
- `git diff --check`
  - passed; Git only reported expected LF-to-CRLF working-copy warnings on Windows.
- Frontend build:
  - not run because Phase 10 did not change frontend files.

## Phase 11 Recommendation

Add read-only connector configuration hardening: typed environment loading, explicit connector selection tests, redacted diagnostics, connector healthcheck API, and fixture-driven schema mapping examples. Keep all connector methods read-only and keep every ERP write action out of scope.
