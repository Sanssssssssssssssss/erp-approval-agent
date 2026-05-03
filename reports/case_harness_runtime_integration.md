# CaseHarness Runtime Integration Report

## Summary

`POST /api/erp-approval/cases/turn` is now HarnessRuntime-owned and LangGraph-orchestrated. The endpoint no longer treats `CaseHarness` as a bare local state-machine operation or a parallel orchestrator. It runs a `CaseTurnExecutor` through `HarnessRuntime.run_with_executor` with `orchestration_engine=langgraph_case_turn`, and the executor drives the LangGraph case-turn graph.

This keeps `HarnessRuntime` as the canonical lifecycle owner, LangGraph as the orchestration layer, and `CaseHarness` as a graph-node domain module for local case state, context, validation, dossier, and audit helpers.

## What Changed

- Added canonical non-action harness events:
  - `case.turn.started`
  - `case.patch.validated`
  - `case.state.persisted`
- Added `src/backend/domains/erp_approval/case_turn_executor.py`.
- Added `src/backend/domains/erp_approval/case_turn_graph.py`.
- Updated `/api/erp-approval/cases/turn` to run through `HarnessRuntime.run_with_executor`.
- The case-turn graph now executes:
  `load_case_state -> classify_turn -> assemble_case_context -> review_submission -> propose_patch -> validate_patch -> persist_case -> respond`.
- `case_state.json`, `dossier.md`, `audit_log.jsonl`, and local evidence files are still written locally, but the write now happens in the graph `persist_case` node.
- The case turn API response now includes a `harness_run` summary with run id, event names, event payload summaries, and the non-action boundary.
- Updated release/API tests to assert that a case turn emits canonical harness lifecycle events and no `approval.*` events.

## Boundary

This integration does not add ERP action execution. Case turns may write local case artifacts only:

- `case_state.json`
- `dossier.md`
- `audit_log.jsonl`
- local evidence text files

No ERP approval, rejection, payment, supplier, contract, budget, comment, or routing action is executed.

## Release Boundary Result

The release boundary test already recognizes:

- `POST /api/erp-approval/cases/turn`

as local case-state writes, not ERP write actions.

## Validation

Commands run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_review_api
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_release_boundary
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_harness backend.tests.test_erp_approval_case_review_api backend.tests.test_erp_approval_release_boundary
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_harness_p0_p1 backend.tests.test_erp_approval_case_graph backend.tests.test_erp_approval_case_review backend.tests.test_erp_approval_case_file backend.tests.test_erp_approval_evidence_requirements backend.tests.test_erp_approval_evidence_claims backend.tests.test_erp_approval_evidence_sufficiency backend.tests.test_erp_approval_control_matrix
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate backend.tests.test_erp_approval_action_proposals backend.tests.test_erp_approval_trace_store backend.tests.test_erp_approval_analytics backend.tests.test_erp_approval_api backend.tests.test_erp_approval_proposal_ledger backend.tests.test_erp_approval_audit_package backend.tests.test_erp_approval_audit_workspace backend.tests.test_erp_approval_action_simulation backend.tests.test_erp_approval_connectors backend.tests.test_erp_approval_connector_config backend.tests.test_erp_approval_connector_api backend.tests.test_erp_approval_connector_replay backend.tests.test_erp_approval_connector_coverage backend.tests.test_erp_approval_release_boundary backend.tests.test_erp_approval_case_file backend.tests.test_erp_approval_evidence_requirements backend.tests.test_erp_approval_evidence_claims backend.tests.test_erp_approval_evidence_sufficiency backend.tests.test_erp_approval_control_matrix backend.tests.test_erp_approval_case_review backend.tests.test_erp_approval_case_graph backend.tests.test_erp_approval_case_harness backend.tests.test_erp_approval_case_harness_p0_p1 backend.tests.test_erp_approval_case_review_api
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
backend\.venv\Scripts\python.exe -m py_compile src/backend/domains/erp_approval/case_turn_graph.py src/backend/domains/erp_approval/case_turn_executor.py src/backend/domains/erp_approval/case_harness.py src/backend/api/erp_approval.py
```

Results:

- focused case/API/boundary tests: passed, 25 tests.
- case evidence graph/domain tests: passed, 27 tests.
- broader ERP regression command: passed, 161 tests.
- legacy RFP/security compatibility command: passed, 11 tests.
- `py_compile`: passed.

## Remaining Architecture Work

The lifecycle and graph ownership are now integrated. Remaining maturity work is product quality work, not a second runtime:

- continue hardening the stage-limited LLM `CasePatch` proposal roles used by the graph nodes.
- keep deterministic `CasePatchValidator` as the only writer to case state.
- merge `CaseContextAssembler` output with the global `ContextAssembler` budget/memory policy instead of relying on chat history.

That future work should keep the same rule: model output proposes patches; HarnessRuntime owns the run; LangGraph owns the case-turn orchestration; CaseHarness/CaseMemoryStore/CasePatchValidator/DossierWriter-style helpers are used inside graph nodes only.
