# ERP Agent Quality Hardening Report

Date: 2026-05-02

## What Was Validated

This pass focused on whether the ERP approval path is actually using the model and whether the result is reasonable for approval work.

- Confirmed `erp_intake_node` and `erp_reasoning_node` call the shared Harness model path through `_stream_model_answer`.
- Confirmed the runtime still uses HarnessRuntime and LangGraph; no new runtime, agent framework, connector, or ERP write action was added.
- Added repeatable local quality evaluation: `npm run evaluate:erp-agent`.
- Ran 9 manual-style API cases through the local app:
  - complete purchase requisition
  - unknown purchase requisition
  - expense reimbursement
  - invoice three-way match
  - supplier onboarding with pending sanctions check
  - contract exception
  - budget exception
  - ambiguous approval request
  - workspace file search that must not be hijacked by ERP approval routing

## External Sanity Sources

I checked official ERP documentation to calibrate the expected approval reasoning:

- Microsoft Dynamics 365 Finance documents invoice matching as comparing invoice, purchase order, and product receipt evidence for three-way matching: https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/three-way-matching-policies
- SAP S/4HANA Cloud documents flexible workflow for purchase requisitions as one-step or multi-step approval processes: https://help.sap.com/docs/SAP_S4HANA_CLOUD/0e602d466b99490187fcbb30d1dc897c/8536fac83ec045d796cb6f12a5f21bf1.html
- Oracle Fusion Payables documents matching invoices to purchase orders and receipts: https://docs.oracle.com/en/cloud/saas/financials/24c/fappp/matching-invoice-lines.html
- Oracle Fusion Procurement documents requisition approval as a workflow submission/action concept, reinforcing that this workbench must not treat advice as final ERP execution: https://docs.oracle.com/en/cloud/saas/procurement/26a/fapra/op-purchaserequisitions-purchaserequisitionsuniqid-action-submitrequisition-post.html

These sources were used only for sanity-checking expected reasoning patterns. No live ERP integration was added.

## Problems Found

- The model was being called, but the output contract was too loose.
- The model sometimes shortened object IDs, for example `PR-1001` to `PR-100`.
- The model sometimes drifted citation source IDs, for example typoed vendor source IDs.
- Some non-blocking details were treated as blocking missing information, causing overly conservative `request_more_info`.
- Workspace search requests containing approval words could still be routed into ERP approval.
- The quality evaluator incorrectly treated a no-HITL final ERP answer as "not ERP"; it now recognizes final ERP answers too.
- The Playwright UX check initially exposed a local dev-server issue: Next static chunks were returning 404, causing unstyled HTML. Restarting the frontend dev server fixed the loaded UI, and the UX script now verifies the styled flow.

## Changes Made

- Strengthened ERP intake and reasoning prompts for exact IDs, exact citations, Chinese explanation, and ERP evidence grounding.
- Added deterministic request repair for IDs, amounts, vendor extraction, purpose extraction, and raw request preservation.
- Added context-aware recommendation repair before guard validation:
  - fixes truncated IDs where context supports an exact source ID
  - repairs near-match citation typos against the current `ApprovalContextBundle`
  - moves non-blocking follow-up details out of `missing_information` for approve recommendations
  - enriches summaries with request fields and Chinese business terms
- Added a contextual fallback recommendation when model output is not parseable JSON, so users see a conservative business recommendation instead of a generic parse failure.
- Hardened router rules so explicit project/workspace search requests are not hijacked by ERP approval.
- Added `npm run evaluate:erp-agent` as a repeatable local scorecard.
- Hardened `npm run verify:ux` to verify the current UI without assuming a preselected session and to use a HITL-triggering supplier onboarding case.

## Quality Score

Latest local API score:

- Command: `npm run evaluate:erp-agent`
- Result: pass
- Average score: 98
- Cases passing threshold: 9/9

Notable outcomes:

- Complete purchase requisition now preserves `PR-1001`, `Acme Supplies`, `OPS-CC-10`, and exact citations.
- Invoice payment now handles PO/GRN/invoice three-way evidence.
- Supplier onboarding correctly blocks on pending sanctions/legal/procurement checks.
- Contract exception now escalates to legal review instead of showing a generic parse failure.
- Budget exception now escalates to finance with insufficient-funds language.
- Workspace search no longer enters the ERP approval graph.

## Validation Commands

Passed:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate backend.tests.test_erp_approval_action_proposals backend.tests.test_erp_approval_trace_store backend.tests.test_erp_approval_analytics backend.tests.test_erp_approval_api backend.tests.test_erp_approval_proposal_ledger backend.tests.test_erp_approval_audit_package backend.tests.test_erp_approval_audit_workspace backend.tests.test_erp_approval_action_simulation backend.tests.test_erp_approval_connectors backend.tests.test_erp_approval_connector_config backend.tests.test_erp_approval_connector_api backend.tests.test_erp_approval_connector_replay backend.tests.test_erp_approval_connector_coverage
```

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
```

```powershell
backend\.venv\Scripts\python.exe -m py_compile src/backend/decision/lightweight_router.py src/backend/domains/erp_approval/service.py src/backend/domains/erp_approval/prompts.py src/backend/domains/erp_approval/__init__.py src/backend/orchestration/executor.py backend/tests/test_erp_approval_domain.py backend/tests/test_erp_approval_routing.py
```

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\dev\validate-phase14-mvp.ps1
```

```powershell
npm run evaluate:erp-agent
npm run verify:ux
npm run build
git diff --check
```

Notes:

- `git diff --check` passed with line-ending warnings only.
- Playwright screenshots were written under `src/frontend/output/playwright/`.
- During visual verification, an already-running Next dev server served stale `_next/static` assets after `next build`, causing 404s and an unstyled page. Restarting the frontend dev server restored the styled UI; a follow-up Playwright static-asset check reported no `_next/static` failures.

## Boundaries Preserved

- No real ERP connector was enabled.
- No ERP approve/reject/payment/comment/route action was executed.
- No `approval.*` Harness events were added.
- No benchmark accuracy claim was made.
- Legacy RFP/security tests remain green.

## Next Recommendation

The next useful task is not another backend ledger. It should be a model-facing quality pass:

- add a compact golden-case prompt pack for ERP approvals
- keep `evaluate:erp-agent` in CI/local validation
- tune HITL copy and final answer rendering around what a business reviewer needs first: recommendation, evidence, missing blockers, risk, and exact safe next step
- only after this is stable, consider a real read-only connector pilot behind explicit opt-in
