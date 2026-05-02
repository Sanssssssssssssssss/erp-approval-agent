# CaseHarness Hardening Review

## Summary

This hardening pass addressed the strict review concerns around long-lived case turns, local case-state consistency, patch validation depth, bounded model context, and API scope clarity.

## Addressed Findings

### HarnessRuntime Ownership

`POST /api/erp-approval/cases/turn` was already wrapped by `HarnessRuntime.run_with_executor` in the current branch. It uses `CaseTurnExecutor` and emits canonical events:

- `run.started`
- `case.turn.started`
- `case.patch.validated`
- `case.state.persisted`
- `run.completed`

No `approval.*` events are emitted.

### Case-State Consistency

`CaseMemoryStore` now provides per-case in-process locks. `CaseHarness.handle_turn` serializes work by case id before reading or writing state.

Local state files are written through atomic temp-file replacement for:

- `case_state.json`
- `dossier.md`
- local evidence text files

`CaseTurnRequest.expected_turn_count` can now detect stale-window submissions. If the expected turn count does not match current state, the turn returns a conflict response and does not mutate the case.

### Deeper Patch Validation

`CasePatchValidator` now accepts the structured review and verifies:

- accepted evidence source id exists.
- accepted evidence has claim ids.
- accepted evidence is not `user_statement` / `local_note`.
- accepted evidence requirement ids exist in the current requirement set.
- claim ids exist in current `evidence_claims`.
- each accepted claim source id matches the accepted evidence source id.
- unsupported claims cannot satisfy accepted evidence.
- claim requirement links actually support the evidence requirement ids.

### Bounded Case Context

`CaseContextAssembler` no longer uses fixed `claims[:30]` and `rejected_evidence[-12:]` selection. It now selects a bounded case-state snapshot around:

- current missing/partial/conflict requirements.
- current user submission terms.
- relevant accepted claims.
- relevant rejected evidence.
- current contradictions.
- current stage contract.

This is still lightweight and deterministic, but it is closer to the intended case-context pack.

### API Scope Clarity

The two local POST endpoints now explicitly report scope:

- `POST /api/erp-approval/case-review`
  - `operation_scope=temporary_case_review_preview`
  - `persistence=does_not_write_case_state`

- `POST /api/erp-approval/cases/turn`
  - `operation_scope=persistent_case_turn`
  - `persistence=writes_local_case_state_dossier_and_audit_log_only`

### Product Model Path

`backend/scripts/dev/start-dev.ps1` enables `ERP_CASE_STAGE_MODEL_ENABLED=true` by default for local product runs unless explicitly overridden. Test and benchmark commands still remain deterministic unless intentionally configured for live model evaluation.

## Tests Added

- stale `expected_turn_count` does not mutate case state.
- parallel turns for the same case are serialized without losing accepted evidence.
- validator rejects claim/source mismatch.
- validator allows multiple same-source claims to jointly support one accepted evidence item.
- context assembler prioritizes relevant missing requirements and keeps bounded claim selection.
- API distinguishes temporary preview from persistent case turn.

## Validation

Commands run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_harness backend.tests.test_erp_approval_case_review_api backend.tests.test_erp_approval_release_boundary
backend\.venv\Scripts\python.exe -m py_compile src\backend\domains\erp_approval\case_memory_store.py src\backend\domains\erp_approval\case_harness.py src\backend\domains\erp_approval\case_patch_validator.py src\backend\domains\erp_approval\case_context.py src\backend\domains\erp_approval\case_state_models.py src\backend\api\erp_approval.py backend\tests\test_erp_approval_case_harness.py backend\tests\test_erp_approval_case_review_api.py
```

Results:

- targeted tests: passed, 25 tests.
- py_compile: passed.

Full validation:

```powershell
backend\scripts\dev\validate-phase14-mvp.ps1 -SkipFrontend
```

Results:

- ERP MVP tests: passed, 166 tests.
- strict evidence-case toy audit: 82/82 passed, 0 critical, 0 major.
- manual ERP smoke: 9/9 passed.
- CaseHarness stress suite: 66/66 scenarios passed, 0 critical, 0 major.
- maturity benchmark: 321 cases, average 99.85, 321 A grades.
- legacy RFP/security compatibility: 11 tests passed.
- py_compile: passed.
- LangGraph compiler smoke: passed.
- git diff --check: passed.

## Remaining Risks

- The per-case lock is in-process. Multi-process deployment would still need a filesystem or database-backed lock.
- The stage model path is enabled for local product startup, but broad live-model shadow evaluation is still needed.
- The maturity benchmark still has a ceiling effect and should be made harsher with long-lived, messy, multi-document cases.
- Frontend should surface `expected_turn_count` and stale-turn conflicts to users to avoid confusing double submissions.
