# Case Stage Model Patch Loop Report

## Summary

CaseHarness now supports an optional model-heavy approval review loop without giving the model write authority.

When `ERP_CASE_STAGE_MODEL_ENABLED=true`, `/api/erp-approval/cases/turn` asks the configured chat model to review the current case context, candidate evidence, claims, sufficiency result, contradictions, control matrix, and current recommendation through five bounded roles. Each role returns JSON only. The role outputs are aggregated into a bounded `CasePatch`.

Roles:

- `turn_classifier`
- `evidence_extractor`
- `policy_interpreter`
- `contradiction_reviewer`
- `reviewer_memo`

## Model Roles

The model roles are allowed to:

- classify the turn intent within the allowed case-turn enum.
- decide whether candidate evidence should be accepted, rejected, or clarified.
- explain why material is weak or insufficient.
- identify requirements it believes are satisfied or still missing.
- interpret policy/control gaps.
- challenge contradictions, prompt injection, and execution-like wording.
- generate Chinese reviewer notes and next questions.
- be stricter than deterministic extraction.

The model is not allowed to:

- write `case_state.json` directly.
- satisfy blocking evidence without `source_id` and supported claims.
- execute or imply ERP approve/reject/payment/comment/route/supplier/budget/contract actions.
- bypass `CasePatchValidator`.

## Hard Constraints

The deterministic layer still enforces:

- allowed turn intents.
- allowed patch types.
- accepted evidence must have `source_id`.
- accepted evidence must have supported claims.
- user statements cannot satisfy blocking evidence.
- execution-like wording is retained only as non-action review text.
- no ERP write action is executed.

The model can downgrade deterministic evidence, but it cannot upgrade weak evidence past the source/claim gates.

## Files Changed

- `src/backend/domains/erp_approval/case_stage_model.py`
- `src/backend/domains/erp_approval/case_harness.py`
- `src/backend/domains/erp_approval/case_state_models.py`
- `src/backend/domains/erp_approval/case_turn_executor.py`
- `src/backend/api/erp_approval.py`
- `backend/tests/test_erp_approval_case_harness.py`
- `backend/.env.example`
- docs/status files

## Validation

Commands run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_harness
backend\.venv\Scripts\python.exe -m py_compile src\backend\domains\erp_approval\case_stage_model.py src\backend\domains\erp_approval\case_harness.py src\backend\domains\erp_approval\case_state_models.py src\backend\api\erp_approval.py backend\tests\test_erp_approval_case_harness.py
```

Results:

- `backend.tests.test_erp_approval_case_harness`: passed, 9 tests.
- `py_compile`: passed.

Full Phase 14 backend validation also passed after the role split:

- ERP MVP tests: 160 tests passed.
- strict toy audit: 82/82 passed, 0 critical, 0 major.
- manual smoke: 9/9 passed.
- CaseHarness stress: 66/66 scenarios passed.
- maturity benchmark: 321 cases, average 99.85.
- legacy RFP/security compatibility: 11 tests passed.

## Next Step

The next maturity step is to run this role split against real configured model calls locally and compare model-produced patches against the deterministic fallback on difficult case submissions. Keep the validator as the only writer to local case state.
