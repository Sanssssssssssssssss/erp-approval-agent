# Phase 4 ERP Action Proposal Skeleton

## Summary

Phase 4 adds guarded ERP action proposal drafts after the ERP recommendation HITL gate. The current ERP graph is:

```text
bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_reasoning -> erp_guard -> erp_hitl_gate -> erp_action_proposal -> erp_finalize -> finalize
```

Action proposals are structured drafts for a possible next step. They are not tool calls, capability invocations, connector calls, or ERP writes.

## Implemented

- Added action proposal schemas:
  - `ApprovalActionProposal`
  - `ApprovalActionProposalBundle`
  - `ApprovalActionValidationResult`
- Added `src/backend/domains/erp_approval/action_proposals.py`.
- Added proposal builders for:
  - `request_more_info`
  - `add_internal_comment`
  - `route_to_manager`
  - `route_to_finance`
  - `route_to_procurement`
  - `route_to_legal`
  - `manual_review`
- Added `erp_action_proposal` graph node.
- Updated final answers to include Action proposals and validation warnings.
- Added focused proposal tests and updated graph smoke/HITL tests.

## Boundary: Proposal vs ERP Action

Every proposal is `executable=false` and includes:

```text
This is a proposed action only. No ERP write action was executed.
```

The node does not call external tools, does not call ERP connectors, does not create `capability_results`, does not enter `capability_invoke`, and does not emit `approval.*` Harness events.

No approve, reject, payment, supplier, budget, contract, comment, request-more-info, or routing action is executed in Phase 4.

## Idempotency Design

Each proposal gets:

- `idempotency_scope`: `approval_action_proposal:<approval_id>:<action_type>:<target>`
- `idempotency_fingerprint`: SHA-256 over approval id, action type, target, and payload preview
- `idempotency_key`: `<scope>:<fingerprint-prefix>`

The same input produces the same fingerprint and idempotency key. These are preparatory audit fields only; there is no write execution path yet.

## Validation Rules

`validate_action_proposals` blocks or rejects:

- action types outside the Phase 4 whitelist.
- citations that are not present in the current `ApprovalContextBundle.records.source_id`.
- missing idempotency fields.
- payload previews containing execution-like ERP semantics such as approve/reject execution, payment release, supplier activation, budget update, or contract signing.

Validation also forces `executable=false` and preserves the non-action statement on every proposal.

## Still Not Implemented

- No real ERP connector.
- No real ERP write actions.
- No real comment/request-more-info/routing action.
- No approval/rejection/payment/supplier/budget/contract execution.
- No `approval.*` events.
- No ERP benchmark suite.

## Validation

Focused ERP approval tests:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate backend.tests.test_erp_approval_action_proposals
```

Result:

```text
Ran 34 tests in 0.058s
OK
```

Legacy RFP/security compatibility:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
```

Result:

```text
Ran 11 tests in 0.008s
OK
```

Python compile:

```text
backend\.venv\Scripts\python.exe -m py_compile src/backend/domains/erp_approval/schemas.py src/backend/domains/erp_approval/action_proposals.py src/backend/domains/erp_approval/__init__.py src/backend/orchestration/executor.py src/backend/orchestration/compiler.py src/backend/orchestration/nodes/erp_approval.py src/backend/orchestration/state.py backend/tests/test_erp_approval_action_proposals.py backend/tests/test_erp_approval_graph_smoke.py backend/tests/test_erp_approval_hitl_gate.py
```

Result: OK.

LangGraph compiler smoke:

```text
compile_harness_orchestration_graph(Dummy(), include_checkpointer=False)
```

Result:

```text
CompiledStateGraph
```

Frontend build: not run, because no frontend files were changed in Phase 4. Existing chat and trace components already render the final answer as markdown/text.

## Phase 5 Recommendation

Build management efficiency analytics over stored ERP approval traces: bottlenecks, missing-information patterns, review delay, policy friction, and high-risk proposal clusters. Keep analytics read-only and grounded in existing recommendation, review, validation, and proposal records.
