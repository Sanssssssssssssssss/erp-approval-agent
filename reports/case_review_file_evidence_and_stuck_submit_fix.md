# Case Review Stuck Submit And File Evidence Pass

## What Was Wrong

- `/api/erp-approval/cases/turn` could hang on the first case creation turn when `ERP_CASE_STAGE_MODEL_ENABLED=true`.
- The first turn has no submitted evidence yet, so calling the multi-role stage model there only slowed or blocked case creation.
- The Case Review UI waited for that API response, so the right panel stayed at "waiting to create approval case".
- A validator warning also falsely appeared because it scanned the fixed non-action statement `No ERP write action was executed` and treated the word `executed` as execution intent.

## Fixes

- CaseHarness now skips the stage model for no-evidence create/materials/status/off-topic turns.
- Evidence turns can still use the stage model; the fast path is only for turns where there is no material to review.
- The frontend case-turn request now has a 60 second timeout with a clear error instead of spinning forever.
- The validator ignores fixed non-action statements when scanning model metadata for execution-like language.
- The old chat tab label was clarified to "聊天流（不写案卷）" so users know it does not create or update the case dossier.

## File Evidence UX

- Added a local file evidence picker in Case Review.
- Text-like files (`.txt`, `.md`, `.json`, `.csv`, `.tsv`, `.xml`, `.log`) are read in the browser and added as evidence text.
- PDF/image files are registered as metadata-only evidence with file name, type, size, and SHA-256.
- PDF/image OCR and full forgery detection are not implemented yet and are not claimed.
- Metadata-only files should not satisfy blocking evidence until text/OCR/signature validation is added.

## Boundary

- No real ERP connector was enabled.
- No ERP approve/reject/payment/comment/route/supplier/budget/contract action was executed.
- File evidence is local browser-side evidence intake, not production document forensics.

## Validation

- Direct backend `/api/erp-approval/cases/turn` first-case creation returned successfully in about 4.2s with `model_used=false`.
- Targeted backend tests: 33 tests OK.
- Phase 14 backend validation: 174 ERP tests OK, strict audit 82/82, manual smoke 9/9, stress 66/66, maturity benchmark 321 cases average 99.85, legacy 11 tests OK, py_compile OK, compiler smoke OK, `git diff --check` OK.
- Frontend build: `npm run build` OK.
- Playwright browser verification:
  - opened Case Review
  - submitted a new PR case
  - confirmed the right panel left the waiting state and displayed `erp-case:PR-PW-NOWARN`
  - uploaded a local `budget-evidence.txt`
  - confirmed the file evidence appeared in the pending evidence list
  - confirmed no console errors and no false execution-like warning
- Screenshots:
  - `output/playwright/case-review-after-create-nowarn.png`
  - `output/playwright/case-review-file-evidence-nowarn.png`
