# Phase 8: Local Audit Package Workspace + Reviewer Notes

## Summary

Phase 8 upgrades temporary read-only audit packages into a local audit workspace. Reviewers can save audit package manifests, preserve package snapshots, append local reviewer notes, list saved packages, and export saved package JSON.

This phase still does not execute real or mock ERP actions.

## Implemented

- Added audit workspace models:
  - `SavedAuditPackageManifest`
  - `SavedAuditPackageWriteResult`
  - `SavedAuditPackageQuery`
  - `SavedAuditPackageListResponse`
  - `ReviewerNote`
  - `ReviewerNoteWriteResult`
  - `ReviewerNoteQuery`
  - `AuditPackageExport`
- Added local JSONL repositories:
  - `backend/storage/erp_approval/audit_packages.jsonl`
  - `backend/storage/erp_approval/reviewer_notes.jsonl`
- Added saved package manifest builder with stable package hash.
- Added append-only reviewer notes.
- Added local audit workspace APIs.
- Extended the frontend `Insights` tab with a local audit workspace for saving packages, listing packages, appending notes, and exporting saved package JSON.

## Why Local POST Is Not ERP Write

Phase 8 introduces POST endpoints only for local audit workspace artifacts. They write JSONL files inside the local workbench storage directory. They do not call ERP systems, connectors, tools, capabilities, or action execution code.

Saving an audit package is local application persistence. It is not approve, reject, payment, ERP comment, request-more-info, route, supplier, budget, or contract execution.

## Manifest vs Temporary Audit Package

The Phase 7 temporary audit package is built on demand from current trace and proposal records.

The Phase 8 saved manifest stores:

- package metadata
- trace IDs
- proposal record IDs
- source filters
- stable package hash
- full package snapshot
- completeness summary

The snapshot prevents saved audit packages from drifting if underlying trace or proposal records change later.

## Reviewer Notes vs ERP Comments

Reviewer notes are local review notes. They are append-only JSONL artifacts in the workbench and are not sent to an ERP system. A reviewer note must not be interpreted as an ERP comment or as an approval action.

## API Endpoints

- `GET /api/erp-approval/audit-packages`
- `GET /api/erp-approval/audit-packages/{package_id}`
- `GET /api/erp-approval/audit-packages/{package_id}/export.json`
- `GET /api/erp-approval/audit-packages/{package_id}/notes`
- `POST /api/erp-approval/audit-packages`
- `POST /api/erp-approval/audit-packages/{package_id}/notes`

No PUT, PATCH, DELETE, ERP action, connector, or execution endpoint was added.

## Frontend

The `Insights` tab now includes a local audit workspace:

- save selected trace as an audit package
- save current filtered traces as an audit package
- list saved audit packages
- view package details
- append reviewer notes
- download saved package export JSON

The UI text states that saved packages and reviewer notes are local review artifacts and do not execute ERP actions.

## Still Not Implemented

- real ERP connectors.
- real or mock ERP action execution.
- approval/rejection/payment/comment/request-more-info/route/supplier/budget/contract writes.
- `approval.*` Harness events.
- action execution ledger.
- production process mining.
- benchmark accuracy claims.
- package detail pages or saved filter presets.

## Validation

Passed:

- `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate backend.tests.test_erp_approval_action_proposals backend.tests.test_erp_approval_trace_store backend.tests.test_erp_approval_analytics backend.tests.test_erp_approval_api backend.tests.test_erp_approval_proposal_ledger backend.tests.test_erp_approval_audit_package backend.tests.test_erp_approval_audit_workspace`
  - `Ran 62 tests in 0.409s`
  - `OK`
- `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator`
  - `Ran 11 tests in 0.006s`
  - `OK`
- `backend\.venv\Scripts\python.exe -m py_compile src\backend\domains\erp_approval\audit_workspace_models.py src\backend\domains\erp_approval\audit_workspace.py src\backend\domains\erp_approval\__init__.py src\backend\api\erp_approval.py backend\tests\test_erp_approval_audit_workspace.py backend\tests\test_erp_approval_api`
  - passed
- LangGraph compiler smoke:
  - `CompiledStateGraph`
- `cd src\frontend && npm run build`
  - passed
- `git diff --check`
  - passed; Git only reported expected LF-to-CRLF working-copy warnings on Windows.

## Phase 9 Recommendation

Add read-only local audit workspace refinement: saved filter presets, package detail pages, note search, package comparison, and completeness summary grouping. Keep all reviewer notes local and keep every ERP write action out of scope.
