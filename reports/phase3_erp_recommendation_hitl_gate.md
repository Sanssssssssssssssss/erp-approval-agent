# Phase 3 ERP Recommendation HITL Gate

## Summary

Phase 3 adds a durable human-in-the-loop review gate for ERP approval recommendations. The ERP approval graph now routes through:

```text
bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_reasoning -> erp_guard -> erp_hitl_gate -> erp_finalize -> finalize
```

The gate uses the existing LangGraph interrupt/checkpoint/resume mechanism. No new runtime, agent framework, API protocol, or `approval.*` Harness events were added.

## Implemented

- Added `erp_hitl_gate` graph node and compiler edge.
- Added ERP HITL state fields:
  - `erp_hitl_request`
  - `erp_hitl_decision`
  - `erp_review_status`
- Added durable HITL request payloads for `erp_approval_recommendation_review`.
- Reused existing HITL decision enum: `approve`, `reject`, `edit`.
- Added review statuses:
  - `not_required`
  - `requested`
  - `accepted_by_human`
  - `rejected_by_human`
  - `edited_by_human`
- Added edit handling that parses an edited recommendation and reruns the deterministic approval validation gate.
- Updated final answers to display review status and always include:
  `No ERP approval, rejection, payment, supplier, contract, or budget action was executed.`
- Added minimal frontend copy for ERP recommendation review in the existing HITL UI.
- Updated Phase 3 docs/status.

## HITL Review Boundary

This HITL gate reviews the agent recommendation only. It does not approve, reject, pay, onboard, sign, update budgets, update contracts, or change any ERP object.

The HITL request `proposed_input` includes:

- `review_type: "erp_recommendation_review"`
- `approval_request`
- `context_source_ids`
- `recommendation`
- `guard_result`
- `explicit_non_action_statement`

## Why HITL Approve Is Not ERP Approve

The existing HITL decision value `approve` is reused to avoid changing the frontend/API protocol. In this path, `approve` means "accept the agent's recommendation as reviewed." It does not invoke `capability_invoke`, does not call a connector, and does not execute any ERP write action.

The backend stores the result as `erp_review_status="accepted_by_human"` to avoid mixing recommendation review with ERP approval execution.

## Still Not Implemented

- No SAP, Dynamics, Oracle, or custom ERP connector.
- No real approve/reject/payment/supplier/budget/contract write action.
- No ERP write-action approval card.
- No request-more-info or escalation workflow action.
- No ERP benchmark suite.
- No `approval.*` Harness events.

## Validation

Focused ERP approval tests:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke backend.tests.test_erp_approval_hitl_gate
```

Result:

```text
Ran 27 tests in 0.047s
OK
```

Legacy RFP/security compatibility:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
```

Result:

```text
Ran 11 tests in 0.006s
OK
```

Frontend build:

```text
cd src\frontend
npm run build
```

Result:

```text
Compiled successfully
Linting and checking validity of types passed
Generated static pages successfully
```

Syntax/import check:

```text
backend\.venv\Scripts\python.exe -m py_compile src/backend/orchestration/executor.py src/backend/orchestration/compiler.py src/backend/orchestration/nodes/erp_approval.py src/backend/orchestration/state.py backend/tests/test_erp_approval_hitl_gate.py
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

## Phase 4 Recommendation

Add guarded action proposal support without executing real ERP writes. Start with comments or request-more-info proposals, then require strict HITL, idempotency keys, audit records, and connector mocks before any future approve/reject action path is considered.
