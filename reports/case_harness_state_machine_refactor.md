# CaseHarness State Machine Refactor

## Summary

This refactor changes the default user experience from a chat-style approval suggestion flow into a Harness-governed approval case workspace.

The key product correction is:

- Chat is only the interface.
- `ApprovalCase` is the business object.
- Every user turn is treated as a controlled case-state patch.
- Only validated patches can update local case state, dossier, audit log, or evidence files.

No ERP write action was executed.

## What Changed

- Added a local CaseHarness state-machine layer:
  - `case_state.json` is the machine-readable case truth.
  - `dossier.md` is the human-readable approval case file.
  - `audit_log.jsonl` records every case turn and patch decision.
  - `evidence/` stores local submitted evidence text.
- Added turn contracts and patch validation:
  - allowed intents
  - allowed patch types
  - forbidden action wording checks
  - local evidence source checks
  - off-topic turn rejection
- Added bounded context assembly for case turns:
  - immutable case instruction
  - case-state summary
  - accepted/rejected evidence summary
  - current user submission
  - output contract
- Added local API:
  - `POST /api/erp-approval/cases/turn`
  - `GET /api/erp-approval/cases`
  - `GET /api/erp-approval/cases/{case_id}`
  - `GET /api/erp-approval/cases/{case_id}/dossier`
- Updated the default frontend Case Review view to show:
  - case state machine
  - current stage
  - current patch
  - accepted evidence
  - rejected evidence
  - patch warnings

## What Intentionally Did Not Change

- No live ERP connector was enabled.
- No ERP approve/reject/payment/comment/request-more-info/route/supplier/budget/contract action was added.
- No action execution endpoint or ledger was added.
- No `approval.*` Harness events were added.
- No `capability_invoke` path was used.
- Existing LangGraph ERP evidence path remains intact.
- Existing trace, proposal, audit, simulation, connector diagnostics, replay, and coverage features remain local/read-only/proposed-only.

## Validation

Backend focused validation:

```powershell
backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_erp_approval_case_harness `
  backend.tests.test_erp_approval_case_review_api `
  backend.tests.test_erp_approval_api `
  backend.tests.test_erp_approval_release_boundary
```

Result: 21 tests passed.

Full MVP validation:

```powershell
.\backend\scripts\dev\validate-phase14-mvp.ps1
```

Result:

- 155 ERP tests passed.
- 11 legacy RFP/security compatibility tests passed.
- strict evidence-case toy audit regenerated 82 cases and passed with 0 critical and 0 major failures.
- manual ERP evidence smoke passed 9/9.
- `py_compile` passed.
- LangGraph compiler smoke passed.
- frontend production build passed.
- `git diff --check` passed.

Frontend/browser verification:

- Playwright created a case from the default PR-1001 prompt.
- Playwright submitted local quote evidence into the same case.
- Playwright verified the page contained:
  - `审批案卷状态机`
  - `必备证据清单`
  - `证据 Claims`
  - `控制矩阵`
  - `No ERP write action was executed`
- Playwright verified the one-sentence direct-approval prompt did not render `建议通过`.

Screenshots:

- `output/playwright/case-harness/01-default-case-workspace.png`
- `output/playwright/case-harness/02-created-case.png`
- `output/playwright/case-harness/03-added-quote-evidence.png`
- `output/playwright/case-harness/04-scrolled-control-matrix.png`
- `output/playwright/case-harness/05-one-sentence-blocked.png`

## Remaining Risks

- The current CaseHarness evidence review is still deterministic/local and mock-context based.
- Local text evidence is not a real document parser yet.
- The UI now exposes the right case-state structure, but future work should add a more polished dossier timeline and source preview.
- The default mock context can still make sample cases look more complete than a real blank enterprise case; future samples should separate empty-case onboarding from mock PR fixtures.

## Recommended Next Task

Build a dedicated dossier workspace with a left-side case lifecycle, middle evidence submission/review stream, and right-side dossier board. Keep the same CaseHarness contract: every UI interaction must become a validated local case patch, not free-form chat.
