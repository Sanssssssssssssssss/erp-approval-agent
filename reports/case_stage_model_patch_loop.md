# Case Stage Model Patch Loop Report

## Summary

CaseHarness now supports an optional model-heavy approval review loop without giving the model write authority.

When `ERP_CASE_STAGE_MODEL_ENABLED=true`, `/api/erp-approval/cases/turn` asks the configured chat model to review the current case context, candidate evidence, claims, sufficiency result, contradictions, control matrix, and current recommendation. The model must return JSON only and propose a bounded `CasePatch`.

## Model Role

The model is allowed to:

- classify the turn intent within the allowed case-turn enum.
- decide whether candidate evidence should be accepted, rejected, or clarified.
- explain why material is weak or insufficient.
- identify requirements it believes are satisfied or still missing.
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

- `backend.tests.test_erp_approval_case_harness`: passed, 8 tests.
- `py_compile`: passed.

## Next Step

The next maturity step is to split the stage model into separate prompt roles:

- turn classifier
- evidence extractor
- policy interpreter
- contradiction reviewer
- final reviewer memo drafter

Each role should still output JSON patches only. The validator remains the only writer to local case state.
