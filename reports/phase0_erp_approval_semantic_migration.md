# Phase 0 ERP Approval Semantic Migration Report

## Summary

Phase 0 changed the public product direction from the previous RFP/security workbench language to ERP Approval Agent Workbench.

The migration was intentionally semantic and documentation-oriented. It did not add ERP connectors, ERP business rules, ERP benchmark suites, or a new runtime.

## What Changed

- Rewrote top-level product docs around ERP Approval Agent Workbench.
- Added a future ERP approval product plan.
- Added an ERP approval knowledge placeholder.
- Updated local development and runbook language.
- Labeled existing `rfp_security` tests and benchmarks as legacy RFP/security compatibility validation.
- Updated frontend user-facing copy:
  - approval assistant
  - audit trace
  - evidence
  - approval threads
  - workflow tools
  - policy / evidence index
  - ERP approval review prompt copy
- Updated frontend package metadata to `erp-approval-agent-frontend`.
- Updated FastAPI title to `ERP Approval Agent API`.
- Updated the frontend UI verification script to follow the new button names.

## What Intentionally Did Not Change

- No new ERP connector was added.
- No SAP, Dynamics, Oracle, or custom ERP integration was added.
- No ERP approval business rules were implemented.
- No ERP benchmark suite was added.
- No API routes were renamed.
- No runtime ownership changed.
- No second runtime or second agent framework was introduced.
- No legacy RFP/security domain module was renamed or removed.
- No `.env` values or secrets were changed.

## Legacy Compatibility Notes

The following paths remain intentionally in place:

- `src/backend/domains/rfp_security`
- `backend/benchmarks/rfp_security_suite.py`
- `backend/benchmarks/cases/rfp_security`
- `knowledge/RFP Security`

The `rfp_security` suite is still useful as a compatibility signal for retrieval, grounding, HITL, and benchmark plumbing. It is not an ERP approval benchmark.

Legacy `ragclaw_*` metric and config names also remain in Phase 0 for compatibility with existing observability artifacts.

## Files Touched

- `README.md`
- `CODEX_HANDOFF.md`
- `PLANS.md`
- `STATUS.md`
- `QUICKSTART.md`
- `LOCAL_DEV.md`
- `RUNBOOK.md`
- `docs/ops/benchmarking.md`
- `docs/ops/observability.md`
- `docs/ops/runbook.md`
- `docs/product/erp_approval_agent_plan.md`
- `knowledge/ERP Approval/README.md`
- `src/backend/api/__init__.py`
- `src/backend/api/app.py`
- `src/frontend/package.json`
- `src/frontend/package-lock.json`
- `src/frontend/scripts/verify-chat-ui.mjs`
- `src/frontend/src/app/layout.tsx`
- `src/frontend/src/app/page.tsx`
- `src/frontend/src/components/chat/AssetsPanel.tsx`
- `src/frontend/src/components/chat/ChatInput.tsx`
- `src/frontend/src/components/chat/ChatPanel.tsx`
- `src/frontend/src/components/chat/ContextTracePanel.tsx`
- `src/frontend/src/components/chat/RetrievalCard.tsx`
- `src/frontend/src/components/chat/TracePanel.tsx`
- `src/frontend/src/components/layout/Navbar.tsx`
- `src/frontend/src/components/layout/Sidebar.tsx`

## Validation Commands Run

Backend focused compatibility tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
```

Result: passed, `Ran 11 tests`, `OK`.

Legacy RFP/security compatibility smoke benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py --suite rfp_security --limit 3 --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Result: passed, `executed_cases = 3`, `overall_pass_rate = 1.0`. A known Pydantic `UnsupportedFieldAttributeWarning` was emitted.

Frontend production build:

```powershell
cd src\frontend
npm run build
```

Result: passed.

Playwright browser installation:

```powershell
cd src\frontend
npm run playwright:install
```

Result: passed. Chromium and related Playwright browser assets were installed locally.

Frontend UI verification:

```powershell
cd src\frontend
npm run verify:chat-ui
```

Result: failed on the final scroll-distance assertion after the script successfully opened the app, submitted an approval-review prompt, reached the audit trace view, and opened the evidence/files drawer.

Observed failure payload:

```json
{
  "maxDistance": 1291,
  "finalDistance": 904,
  "thresholds": {
    "maxSampleDistance": 180,
    "finalDistanceThreshold": 80
  },
  "traceVisible": true,
  "filesVisible": true
}
```

Reason: the UI verification script still enforces a strict chat-scroll threshold. After the semantic copy and current session state, the chat scroll area remained far from the bottom during sampling. This was not hidden or bypassed.

Service smoke after restart:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8015/openapi.json -UseBasicParsing
Invoke-WebRequest -Uri http://127.0.0.1:3000 -UseBasicParsing
```

Result: passed. Backend OpenAPI title is `ERP Approval Agent API`; frontend returned `200` and contained ERP Approval Agent Workbench copy.

## Recommended Phase 1 Next Steps

1. Add `src/backend/domains/erp_approval` next to the legacy `rfp_security` domain.
2. Define a minimal mock approval request schema.
3. Add an ERP approval path kind and graph skeleton.
4. Implement LLM-first structured output for approval recommendation.
5. Keep mock ERP context read-only.
6. Add self-check fields for unsupported claims, missing context, escalation, and irreversible action risk.
7. Introduce HITL approval cards only after the graph skeleton is stable.
