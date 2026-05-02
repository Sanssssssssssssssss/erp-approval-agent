# Evidence-First Case Agent Refactor

## Why This Refactor Was Needed

The previous ERP approval flow was too recommendation-centric. A short user prompt could move quickly into an approval recommendation even when enterprise-grade evidence was incomplete. That made the agent feel like a toy approval recommender rather than an approval workbench.

The new core is evidence-first: a user prompt creates an approval case draft, then the graph builds required evidence, evidence artifacts, claims, sufficiency, contradiction checks, control checks, a case-grounded recommendation, and adversarial review before guard/HITL.

## New Graph

```text
bootstrap
-> route
-> skill
-> memory_retrieval
-> erp_intake
-> erp_context
-> erp_case_file
-> erp_evidence_requirements
-> erp_evidence_claims
-> erp_evidence_sufficiency
-> erp_control_matrix
-> erp_case_recommendation
-> erp_adversarial_review
-> erp_guard
-> erp_hitl_gate
-> erp_action_proposal
-> erp_finalize
-> finalize
```

The legacy `erp_reasoning_node` remains as a compatibility wrapper, but it now drafts from the case/control path instead of doing one-step model recommendation.

## Implemented

- Added `case_models.py` with `ApprovalCaseFile`, evidence, sufficiency, contradiction, control, risk, path, and adversarial review models.
- Added evidence requirement matrices for purchase requisition, expense, invoice/payment, supplier onboarding, contract exception, budget exception, and unknown approvals.
- Added deterministic evidence artifact and claim extraction from current ERP/policy/user-statement context.
- Added evidence sufficiency gate: blocking evidence gaps or conflicts prevent `recommend_approve`.
- Added control matrix evaluator for general and approval-type-specific controls.
- Added case review and recommendation drafting from the structured case file.
- Added adversarial review that downgrades unsupported or over-strong recommendations.
- Updated final answer rendering to show Required evidence checklist, Evidence claims, Evidence sufficiency, Contradictions, Control matrix checks, Risk assessment, Adversarial review, Recommendation, and Non-action boundary.
- Updated the ERP graph to run the evidence-case path before guard/HITL/action proposals/finalize.

## Evidence Rules

- One-sentence user input is only `user_statement` evidence and cannot satisfy blocking requirements by itself.
- Blocking required evidence must be satisfied by current context/artifacts with `source_id`.
- Missing evidence, partial evidence, or conflicts cause the sufficiency gate to fail.
- `recommend_approve` requires sufficiency passed, control matrix passed, supported citations, and no contradiction.

## Still Not Implemented

- Live ERP connectors.
- Real ERP approval/rejection/payment/comment/request-more-info/route/supplier/budget/contract writes.
- Real attachment parsing or OCR.
- Production policy engine.
- ERP benchmark suite or benchmark-proven accuracy claims.

## Validation Results

Passed:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_file backend.tests.test_erp_approval_evidence_requirements backend.tests.test_erp_approval_evidence_claims backend.tests.test_erp_approval_evidence_sufficiency backend.tests.test_erp_approval_control_matrix backend.tests.test_erp_approval_case_review backend.tests.test_erp_approval_case_graph
```

Result: 19 tests passed.

Passed:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate backend.tests.test_erp_approval_action_proposals backend.tests.test_erp_approval_trace_store backend.tests.test_erp_approval_analytics backend.tests.test_erp_approval_api backend.tests.test_erp_approval_proposal_ledger backend.tests.test_erp_approval_audit_package backend.tests.test_erp_approval_audit_workspace backend.tests.test_erp_approval_action_simulation backend.tests.test_erp_approval_connectors backend.tests.test_erp_approval_connector_config backend.tests.test_erp_approval_connector_api backend.tests.test_erp_approval_connector_replay backend.tests.test_erp_approval_connector_coverage backend.tests.test_erp_approval_release_boundary backend.tests.test_erp_approval_case_file backend.tests.test_erp_approval_evidence_requirements backend.tests.test_erp_approval_evidence_claims backend.tests.test_erp_approval_evidence_sufficiency backend.tests.test_erp_approval_control_matrix backend.tests.test_erp_approval_case_review backend.tests.test_erp_approval_case_graph
```

Result: 133 tests passed.

Passed:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
```

Result: 11 tests passed.

Passed:

```powershell
backend\.venv\Scripts\python.exe -m py_compile src/backend/domains/erp_approval/case_models.py src/backend/domains/erp_approval/evidence_requirements.py src/backend/domains/erp_approval/evidence_claims.py src/backend/domains/erp_approval/evidence_sufficiency.py src/backend/domains/erp_approval/control_matrix.py src/backend/domains/erp_approval/case_review.py src/backend/domains/erp_approval/__init__.py src/backend/orchestration/compiler.py src/backend/orchestration/executor.py src/backend/orchestration/nodes/__init__.py src/backend/orchestration/nodes/erp_approval.py src/backend/orchestration/state.py backend/tests/test_erp_approval_case_file.py backend/tests/test_erp_approval_evidence_requirements.py backend/tests/test_erp_approval_evidence_claims.py backend/tests/test_erp_approval_evidence_sufficiency.py backend/tests/test_erp_approval_control_matrix.py backend/tests/test_erp_approval_case_review.py backend/tests/test_erp_approval_case_graph.py backend/tests/test_erp_approval_graph_smoke.py
```

Result: py_compile passed.

Passed:

```powershell
powershell -ExecutionPolicy Bypass -File backend\scripts\dev\validate-phase14-mvp.ps1 -SkipFrontend
```

Result: ERP 133 tests passed, legacy 11 tests passed, py_compile passed, LangGraph compiler smoke passed, `git diff --check` passed. Git printed CRLF normalization warnings only; no whitespace errors were reported.

## Next Suggested Task

Run a toy-case audit prompt pass: define 10 realistic approval scenarios, manually score expected evidence gaps and control outcomes, then compare the agent output against that rubric without claiming benchmark accuracy.
