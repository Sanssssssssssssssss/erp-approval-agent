# ERP Approval Agent Workbench MVP Acceptance Checklist

This checklist defines the Phase 14 MVP acceptance boundary. It is a release-readiness checklist, not a new feature plan.

## MVP Scope Accepted

- [x] Product identity is ERP Approval Agent Workbench.
- [x] HarnessRuntime remains the only lifecycle owner.
- [x] LangGraph remains the only orchestration graph layer.
- [x] Current ERP graph is stable:

```text
bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_case_file -> erp_evidence_requirements -> erp_evidence_claims -> erp_evidence_sufficiency -> erp_control_matrix -> erp_case_recommendation -> erp_adversarial_review -> erp_guard -> erp_hitl_gate -> erp_action_proposal -> erp_finalize -> finalize
```

- [x] `GRAPH_VERSION` is `phase14`.
- [x] ERP approval path is evidence-first, LLM-assisted, and graph-governed.
- [x] One-sentence input creates a case draft only; missing blocking evidence prevents `recommend_approve`.
- [x] Evidence sufficiency, contradiction detection, control matrix, and adversarial review run before guard/HITL.
- [x] Strict local evidence-case toy audit covers at least 80 fictional cases and reports 0 critical/major failures in the latest run.
- [x] Local sample evidence pack exists under `knowledge/ERP Approval/sample_evidence` so approval forms, invoice/PO/GRN, receipts, quotes, budget, vendor, and policy evidence can be shown in the answer.
- [x] Manual real-path smoke report verifies one-sentence prompts do not pass and complete sample cases cite visible local evidence paths.
- [x] ERP context is read-only and defaults to mock.
- [x] Recommendation HITL gate reviews the agent recommendation only.
- [x] Action proposals remain proposed-only and `executable=false`.
- [x] Trace ledger, proposal ledger, audit package workspace, reviewer notes, simulation ledger, connector diagnostics, fixture replay, and replay coverage are local-first artifacts.
- [x] Frontend has read-only trace, analytics, audit, simulation, connector diagnostics, and replay coverage views.
- [x] Legacy RFP/security modules remain compatibility paths.

## Release Boundary Accepted

- [x] No live ERP connector is enabled by default.
- [x] No real ERP network call is required for tests.
- [x] No ERP write action is implemented.
- [x] No approve/reject/payment/comment/request-more-info/route/supplier/budget/contract execution endpoint exists.
- [x] No action execution ledger exists.
- [x] No `approval.*` Harness event namespace is introduced.
- [x] No `capability_invoke` path is used by ERP action proposals, simulation, replay, or connector diagnostics.
- [x] No HITL decision enum expansion is required.
- [x] HITL approve means accepting the agent recommendation only, not approving an ERP object.
- [x] Analytics are based on structured trace records, not final-answer parsing.
- [x] Fixture replay and coverage are local mapper diagnostics, not live ERP tests.
- [x] No benchmark or process-mining claim is made.

## Final Validation

Use the Phase 14 validation script from repo root:

```powershell
.\backend\scripts\dev\validate-phase14-mvp.ps1
```

For backend-only validation:

```powershell
.\backend\scripts\dev\validate-phase14-mvp.ps1 -SkipFrontend
```

The script runs:

- ERP approval unit and release boundary tests.
- strict evidence-case toy audit generation and execution.
- manual real-path ERP evidence smoke generation and execution.
- legacy RFP/security compatibility tests.
- `py_compile` over Phase 14 touched Python files.
- LangGraph compiler smoke.
- frontend production build unless `-SkipFrontend` is passed.
- `git diff --check`.

## STOP Rules

Stop the current MVP here unless a future task explicitly opens a new phase.

Do not extend this MVP closure by adding:

- connector expansion
- simulation expansion
- audit workspace expansion
- mapper diagnostics expansion
- connector profile notes
- ERP benchmark suites
- live ERP connections
- ERP write actions
- action execution APIs
- action execution ledgers
- new `approval.*` Harness events
- another runtime or agent framework

Any future work should start as a new phase with its own scope, tests, report, and explicit boundary review.
