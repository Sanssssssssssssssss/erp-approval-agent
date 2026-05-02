# Evidence-first Case Review Workspace

## Summary

This change moves the primary user experience away from a chat-style approval recommender and into a local evidence-first case review workspace.

The default frontend view is now "案件审查". A user submits an approval case, optionally adds local text evidence, and then receives structured review output:

- 案件概览
- 必备证据清单
- 证据材料
- 证据 Claims
- 证据充分性
- 控制矩阵
- 冲突检测
- 建议 / Reviewer memo

The workflow keeps the non-action boundary explicit: No ERP write action was executed.

## Backend Changes

- Added `POST /api/erp-approval/case-review` as a local-only case review endpoint.
- Added `case_review_service.py` to run the evidence-first domain pipeline without real ERP, network, or tool execution.
- Tightened ERP intake and reasoning prompts so one-sentence input creates only a case draft, not an approval decision.
- Added case evidence summary into ERP HITL recommendation review payloads so reviewers see evidence gaps and control checks before accepting a recommendation.
- Localized case analysis rendering and contradiction messages for the reviewer-facing memo.

## Frontend Changes

- Added `CaseReviewPanel` and made it the default workspace tab.
- Added local text evidence input and re-review flow.
- Reworked HITL recommendation review copy to show evidence sufficiency, blocking gaps, control checks, citations, and the non-action boundary.
- Improved chat welcome and message summary so the product reads as an approval case workbench, not a generic chat sandbox.
- Kept Chat, Audit Trace, Evidence, and Insights as secondary tabs.

## Boundaries

- No real ERP connector was enabled.
- No network ERP access was added.
- No approve/reject/payment/comment/request-more-info/route/supplier/budget/contract action is executed.
- No capability invocation is used for case review.
- No `approval.*` Harness events were added.
- `POST /api/erp-approval/case-review` writes nothing to ERP; it only returns local structured analysis.

## Browser Verification

Playwright was run against the local app with backend on `127.0.0.1:8015` and frontend on `127.0.0.1:3000`.

Artifacts:

- `output/playwright/case-review-default.png`
- `output/playwright/case-review-result-top.png`
- `output/playwright/case-review-output-bottom.png`
- `output/playwright/case-review-extra-evidence.png`
- `output/playwright/chat-tab-after-refactor.png`
- `output/playwright/insights-tab-after-refactor.png`
- `output/playwright/case-review-mobile.png`

Checks performed:

- Default Case Review view loads.
- Local evidence-first review runs.
- Output panel scrolls to reviewer memo.
- Local text evidence can be added and re-reviewed.
- Chat and Insights tabs still open.
- Mobile viewport renders without console errors.

## Validation

Command:

```powershell
.\backend\scripts\dev\validate-phase14-mvp.ps1
```

Results:

- ERP approval test suite: 149 tests OK.
- Strict evidence-case toy audit: 82 cases, 82 passed, 0 failed, 0 critical, 0 major.
- Manual ERP evidence smoke: 9/9 passed.
- Legacy RFP/security compatibility tests: 11 tests OK.
- `py_compile`: 32 files OK.
- LangGraph compiler smoke: `CompiledStateGraph`.
- Frontend build: passed.
- `git diff --check`: passed.

## Remaining Risks

- Local mock evidence is still not a substitute for real ERP records or real attachments.
- Claim extraction is deterministic and conservative; future LLM-assisted document extraction should be added with strict citation grounding.
- Case Review is local-first and no-action by design; production approval automation remains out of scope.
