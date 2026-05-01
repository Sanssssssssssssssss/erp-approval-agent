# Phase 9: Mock Action Simulation Sandbox + Local Simulation Ledger

## Summary

Phase 9 adds a local mock action simulation sandbox for ERP approval action proposals. A simulation is a local dry-run record that previews what kind of local draft would be prepared from an existing action proposal and saved audit package.

This phase does not execute real or mock ERP actions.

## Implemented

- Added action simulation models:
  - `ApprovalActionSimulationRequest`
  - `ApprovalActionSimulationRecord`
  - `ApprovalActionSimulationValidationResult`
  - `ApprovalActionSimulationWriteResult`
  - `ApprovalActionSimulationQuery`
  - `ApprovalActionSimulationListResponse`
- Added simulation service helpers:
  - `validate_simulation_request`
  - `build_simulation_record`
  - `render_simulation_preview`
- Added local JSONL repository:
  - `backend/storage/erp_approval/action_simulations.jsonl`
- Added local simulation APIs.
- Extended the frontend `Insights` audit workspace with a local simulation panel.
- Added tests for validation, stable ids, repository dedupe, API errors, blocked simulations, and route safety.

## Simulation vs Execution

Simulation is a local dry-run preview. It writes a local JSONL record only.

Execution would mean sending a message, posting a comment, routing an approval, approving, rejecting, paying, onboarding, signing, updating, or changing an ERP object. Phase 9 does none of those things.

Every simulation record includes:

- `simulated_only=true`
- `erp_write_executed=false`
- `non_action_statement="This is a local simulation only. No ERP write action was executed."`

## Why POST /action-simulations Is Not ERP Write

`POST /api/erp-approval/action-simulations` writes only to the local simulation ledger. It does not call ERP systems, connectors, tools, capabilities, `capability_invoke`, LangGraph action nodes, or any approval execution path.

It requires `confirm_no_erp_write=true` before recording a dry-run result.

## Validation Rules

The simulation validator requires:

- `confirm_no_erp_write=true`.
- proposal record exists.
- saved audit package exists.
- proposal belongs to the saved package.
- proposal remains `executable=false`.
- action type is one of:
  - `request_more_info`
  - `add_internal_comment`
  - `route_to_manager`
  - `route_to_finance`
  - `route_to_procurement`
  - `route_to_legal`
  - `manual_review`
- blocked or validation-rejected proposals create blocked/rejected simulation records, not simulated records.
- payloads with execution semantics are blocked.

Simulation `output_preview` uses local draft wording such as `would_prepare_local_request_more_info_draft` and avoids execution language.

## Simulation Ledger

The repository is local filesystem JSONL only:

- path: `backend/storage/erp_approval/action_simulations.jsonl`
- upsert key: `simulation_id`
- duplicate request fingerprints return the same stable `simulation_id`
- no database
- no ERP connector
- no tool or capability call
- no graph runtime change

## API Endpoints

- `GET /api/erp-approval/action-simulations`
- `GET /api/erp-approval/action-simulations/{simulation_id}`
- `GET /api/erp-approval/proposals/{proposal_record_id}/simulations`
- `POST /api/erp-approval/action-simulations`

No PUT, PATCH, DELETE, `/execute`, action execution endpoint, or ERP connector endpoint was added.

## Frontend

The `Insights` tab saved audit package detail now includes a local simulation sandbox:

- select a proposal record from the saved package.
- enter `requested_by` and a local note.
- explicitly confirm no ERP write.
- run local simulation.
- view status, `simulated_only`, `erp_write_executed`, output preview, validation warnings, blocked reasons, and non-action statement.

The UI states: "This is a local simulation only. It does not execute an ERP action."

## Still Not Implemented

- real ERP connectors.
- real or mock ERP action execution.
- approve/reject/payment/comment/request-more-info/route/supplier/budget/contract writes.
- action execution ledger.
- `approval.*` Harness events.
- simulation analytics or package-level simulation summaries.
- production process mining.
- benchmark accuracy claims.

## Validation

Passed:

- `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate backend.tests.test_erp_approval_action_proposals backend.tests.test_erp_approval_trace_store backend.tests.test_erp_approval_analytics backend.tests.test_erp_approval_api backend.tests.test_erp_approval_proposal_ledger backend.tests.test_erp_approval_audit_package backend.tests.test_erp_approval_audit_workspace backend.tests.test_erp_approval_action_simulation`
  - `Ran 67 tests in 0.490s`
  - `OK`
- `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator`
  - `Ran 11 tests in 0.006s`
  - `OK`
- `backend\.venv\Scripts\python.exe -m py_compile src\backend\domains\erp_approval\action_simulation_models.py src\backend\domains\erp_approval\action_simulation.py src\backend\domains\erp_approval\action_simulation_ledger.py src\backend\domains\erp_approval\__init__.py src\backend\api\erp_approval.py backend\tests\test_erp_approval_action_simulation.py backend\tests\test_erp_approval_api`
  - passed
- LangGraph compiler smoke:
  - `CompiledStateGraph`
- `cd src\frontend && npm run build`
  - passed
- `git diff --check`
  - passed; Git only reported expected LF-to-CRLF working-copy warnings on Windows.

## Phase 10 Recommendation

Add local simulation review refinement: simulation filters, package-level simulation summaries, proposal-vs-simulation validation comparison, and optional local reviewer-note links to simulation records. Keep every simulation local and keep all ERP writes out of scope.
