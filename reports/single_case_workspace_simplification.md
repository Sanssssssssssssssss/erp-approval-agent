# Single Case Workspace Simplification

## What changed

- Removed the user-facing chat workspace tab and its unused chat input/message components.
- Kept the default product experience focused on the evidence-first Case Workspace.
- Removed the temporary `POST /api/erp-approval/case-review` preview endpoint from the public API surface.
- Kept `POST /api/erp-approval/cases/turn` as the single local case-state update endpoint.
- Removed the `ERP_CASE_STAGE_MODEL_ENABLED` product toggle from active docs and `.env.example`.
- CaseHarness now attempts the configured LLM stage reviewer by default when local model settings are available.
- Deterministic code remains a validator, source/claim gate, no-action boundary, and test fallback; it is not a second user-facing review path.
- Added per-role timeout protection for the LLM stage reviewer so file/evidence review cannot freeze the frontend.
- Updated frontend verification scripts to test the Case Workspace path with local file evidence, scrolling, Trace tab navigation, screenshots, and mobile layout.

## Boundaries

- No live ERP connector was enabled.
- No ERP approve/reject/payment/comment/route/supplier/budget/contract action was added.
- No `approval.*` events were added.
- No `capability_invoke` path was introduced.
- `No ERP write action was executed` remains the product boundary.

## Validation

- `backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_harness backend.tests.test_erp_approval_case_harness_p0_p1 backend.tests.test_erp_approval_case_review_api backend.tests.test_erp_approval_api backend.tests.test_erp_approval_release_boundary`
  - Passed: 38 tests.
- `backend\scripts\dev\validate-phase14-mvp.ps1 -SkipFrontend`
  - Passed: 174 ERP tests, strict 82-case audit, manual smoke, 66-scenario stress suite, 321-case maturity benchmark, legacy compatibility tests, py_compile, LangGraph compiler smoke, and `git diff --check`.
- `npm run build`
  - Passed.
- `npm run verify:case-workspace`
  - Passed with desktop, scrolled, Trace, and mobile screenshots.

## Screenshot notes

Generated local screenshots under `src/frontend/output/playwright/`:

- `case-workspace-desktop.png`
- `case-workspace-scrolled.png`
- `case-workspace-trace.png`
- `case-workspace-mobile.png`

These are local validation artifacts and are not intended to be committed.

## Follow-up

The next useful product pass is not another parallel route. It should make the Case Workspace evidence intake stronger: OCR/PDF extraction, file authenticity metadata, structured attachment parsing, and better Chinese reviewer memo wording while keeping all writes local and non-ERP.
