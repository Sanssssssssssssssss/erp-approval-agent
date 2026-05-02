# Case Workspace Click Test Hardening

## Summary

Added a stricter Playwright click-flow verification for the evidence-first Case Workspace.

This test is meant to catch user-facing regressions: stuck submit buttons, old chat paths reappearing, case ID leakage between cases, evidence add/remove failures, file-evidence upload failures, tab switching regressions, mobile overflow, and missing no-ERP-write boundaries.

## What Changed

- Added `src/frontend/scripts/verify-case-workspace-clicks.mjs`.
- Added npm script `verify:case-clicks`.
- Added a `新建案卷` button in the Case Workspace so users can explicitly reset the current local case workspace before starting a different approval case.

## Click Coverage

The new script exercises:

- default empty state
- one-sentence bypass prompt
- case creation
- manual evidence add
- manual evidence remove
- local file evidence upload
- second evidence-submission turn
- scroll behavior
- `Audit Trace` tab
- `证据` tab
- `管理洞察` tab
- `Workflow tools` menu
- mobile viewport overflow check

The script also inspects the `/api/erp-approval/cases/turn` response and fails if:

- a one-sentence bypass produces `recommend_approve`
- evidence sufficiency incorrectly passes on the bypass case
- a new case leaks the previous case id
- partial evidence produces `recommend_approve`
- the no-ERP-write boundary is missing
- the submit button remains disabled after a turn
- browser page errors, console errors, failed requests, or horizontal overflow are detected

## Validation Results

Commands run:

```powershell
cd src\frontend
npm run verify:case-clicks
npm run build
npm run verify:case-workspace
```

Results:

- `verify:case-clicks`: passed
- `npm run build`: passed
- `verify:case-workspace`: passed

Latest screenshots are written under:

```text
src/frontend/output/playwright/case-clicks/
```

## Finding

The first click-test run exposed a real UX problem: after running the one-sentence bypass test, the next PR submission reused the previous `case_id`. The new `新建案卷` button fixes the user path, and the click test now asserts that the next case becomes `erp-case:PR-CLICK-001`.

## Boundary

No ERP write action was executed.

## Grouping Follow-up

The Case Workspace now has explicit visual grouping instead of one long mixed panel.

Left-side input groups:

- case request
- supplemental evidence
- current turn submission

Right-side review groups:

- case status
- evidence review
- controls and conclusion

`src/frontend/scripts/verify-frontend-ux.mjs` was refreshed to match the current Case Workspace. It now waits for the real `/api/erp-approval/cases/turn` response, verifies grouped layout selectors, captures desktop/mobile screenshots, checks scroll and tab behavior, and fails on console errors, page errors, failed requests, or horizontal overflow.

Additional screenshot output:

```text
src/frontend/output/playwright/case-workspace/
```
