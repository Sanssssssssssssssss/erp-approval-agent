# CaseHarness Runtime Integration Report

## Summary

`POST /api/erp-approval/cases/turn` is now HarnessRuntime-owned. The endpoint no longer calls `CaseHarness.handle_turn` as a bare local state-machine operation. It runs a `CaseTurnExecutor` through `HarnessRuntime.run_with_executor` with `orchestration_engine=case_harness`.

This keeps `HarnessRuntime` as the canonical lifecycle owner while preserving the local evidence-first case-state behavior.

## What Changed

- Added canonical non-action harness events:
  - `case.turn.started`
  - `case.patch.validated`
  - `case.state.persisted`
- Added `src/backend/domains/erp_approval/case_turn_executor.py`.
- Updated `/api/erp-approval/cases/turn` to run through `HarnessRuntime.run_with_executor`.
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

- `POST /api/erp-approval/case-review`
- `POST /api/erp-approval/cases/turn`

as local case-state writes, not ERP write actions.

## Validation

Commands run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_review_api
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_release_boundary
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_harness_types
```

Results:

- `backend.tests.test_erp_approval_case_review_api`: passed, 6 tests.
- `backend.tests.test_erp_approval_release_boundary`: passed, 5 tests.
- `backend.tests.test_harness_types`: passed, 11 tests.

## Remaining Architecture Work

The runtime lifecycle is now integrated, but the next maturity step is still separate:

- introduce stage-limited LLM `CasePatch` proposal inside CaseHarness.
- keep deterministic `CasePatchValidator` as the only writer to case state.
- merge `CaseContextAssembler` output with the global `ContextAssembler` budget/memory policy instead of relying on chat history.

That future work should keep the same rule: model output proposes patches; HarnessRuntime owns the run; CaseHarness validates and persists only safe local case-state updates.
