# Phase 2 ERP Read-Only Context Adapter

## Summary

Phase 2 adds a small read-only ERP context adapter interface for ERP Approval Agent Workbench. The ERP approval graph remains LLM-first and HarnessRuntime/LangGraph-owned. The adapter uses local mock fixture data only and never connects to a real ERP system.

## Implemented

- Added `src/backend/domains/erp_approval/context_adapter.py`.
- Added `ErpContextQuery`, `ErpContextAdapter`, `MockErpContextAdapter`, and `build_context_bundle_from_records`.
- Added mock fixture records in `backend/fixtures/erp_approval/mock_context_records.json`.
- Updated `erp_context_node` to use `MockErpContextAdapter` instead of direct hard-coded mock context.
- Kept `build_mock_context` as a compatibility wrapper over the adapter.
- Strengthened ERP routing constraints so `erp_approval` respects no retrieval / no knowledge instructions.
- Strengthened `branch_after_memory` so ERP graph entry requires retrieval and knowledge to be allowed.
- Strengthened the approval validation gate:
  - `recommend_approve` with missing information downgrades to `request_more_info`.
  - low-confidence `recommend_approve` downgrades to `escalate`.
  - `recommend_approve` without citations downgrades to `escalate`.
  - unknown citation `source_id` values trigger warnings and downgrade approve recommendations.
  - proposed irreversible ERP actions are replaced with `manual_review`.
  - blocked, reject, escalate, and request-more-info statuses require human review.
- Updated reasoning prompt/input formatting with clear sections:
  - Approval request
  - ERP records
  - Policy records
  - Missing context hints
  - Output JSON schema
- Updated documentation to reflect that Phase 1 is complete and Phase 2 is the active read-only adapter phase.

## Adapter Interface

The adapter normalizes read-only records into existing domain models:

- `ApprovalContextRecord`
- `ApprovalContextBundle`

Supported mock record types:

- `approval_request`
- `vendor`
- `budget`
- `purchase_order`
- `invoice`
- `goods_receipt`
- `contract`
- `policy`

Source IDs follow the mock-only scheme:

- `mock_erp://approval_request/<id>`
- `mock_erp://vendor/<id-or-name>`
- `mock_erp://budget/<cost_center>`
- `mock_erp://purchase_order/<id>`
- `mock_erp://invoice/<id>`
- `mock_erp://goods_receipt/<id>`
- `mock_erp://contract/<id>`
- `mock_policy://...`

## Mock-Only Boundary

- No SAP, Dynamics, Oracle, custom ERP, or live vendor system is connected.
- No tools are called by the context adapter.
- No approval, rejection, payment, supplier, budget, or contract write action is executed.
- No `approval.*` Harness events were added.
- No second runtime or agent framework was introduced.

If the fixture is missing or invalid, `MockErpContextAdapter` falls back to static mock policy records instead of failing the run.

## Still Not Implemented

- Real ERP connector.
- Real ERP HITL approval card.
- Real approve/reject/payment/supplier/budget/contract write action.
- ERP benchmark suite.
- Production approval automation.

## Validation

Focused ERP approval tests:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges backend.tests.test_erp_approval_context_adapter backend.tests.test_erp_approval_graph_smoke
```

Result:

```text
Ran 20 tests in 0.126s
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

Syntax/import check:

```text
backend\.venv\Scripts\python.exe -m py_compile src/backend/domains/erp_approval/context_adapter.py src/backend/domains/erp_approval/service.py src/backend/domains/erp_approval/prompts.py src/backend/orchestration/executor.py src/backend/decision/lightweight_router.py src/backend/decision/execution_strategy.py src/backend/runtime/agent_manager.py src/backend/orchestration/edges.py
```

Result: OK.

LangGraph compiler smoke:

```text
@'
from src.backend.orchestration.compiler import compile_harness_orchestration_graph
class Dummy:
    pass
compiled = compile_harness_orchestration_graph(Dummy(), include_checkpointer=False)
print(type(compiled).__name__)
'@ | backend\.venv\Scripts\python.exe -
```

Result:

```text
CompiledStateGraph
```

## Phase 3 Recommendation

Build the HITL approval workbench layer next: approval review cards, request-more-info/escalate/reject/recommend-approve controls, durable resume behavior, and explicit audit rendering. Keep ERP write actions out of scope until the guarded action phase.
