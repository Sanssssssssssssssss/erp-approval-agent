# Phase 1 ERP Approval Graph Skeleton

## Summary

Phase 1 adds a minimal real ERP approval graph path to ERP Approval Agent Workbench while preserving the existing HarnessRuntime-owned lifecycle and LangGraph orchestration layer.

Implemented target path:

```text
bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_reasoning -> erp_guard -> erp_finalize -> finalize
```

## Files Changed

- `src/backend/domains/erp_approval/__init__.py`
- `src/backend/domains/erp_approval/schemas.py`
- `src/backend/domains/erp_approval/prompts.py`
- `src/backend/domains/erp_approval/mock_context.py`
- `src/backend/domains/erp_approval/service.py`
- `src/backend/decision/lightweight_router.py`
- `src/backend/orchestration/state.py`
- `src/backend/context/models.py`
- `src/backend/context/budget.py`
- `src/backend/context/assembler.py`
- `src/backend/orchestration/nodes/erp_approval.py`
- `src/backend/orchestration/nodes/__init__.py`
- `src/backend/orchestration/compiler.py`
- `src/backend/orchestration/edges.py`
- `src/backend/orchestration/executor.py`
- `backend/tests/test_erp_approval_domain.py`
- `backend/tests/test_erp_approval_routing.py`
- `backend/tests/test_erp_approval_edges.py`
- `reports/phase1_erp_approval_graph_skeleton.md`

## Implemented

- Added `erp_approval` domain models for approval request intake, mock context, recommendation, and guard result.
- Added JSON-only intake and reasoning prompts for LLM-first approval reasoning.
- Added static mock ERP/policy context records only. These do not read external files or connect to ERP systems.
- Added service helpers for JSON extraction, safe fallback parsing, recommendation guarding, and final answer rendering.
- Extended deterministic and LLM router semantics with `erp_approval`.
- Added graph state and context path kind for `erp_approval`.
- Added ERP-specific context budget and system context block.
- Added LangGraph nodes and edges for the ERP approval skeleton path.
- Added executor methods for intake, mock context assembly, reasoning, guard, and final answer emission through existing answer events.
- Added unit tests for domain parsing/guard behavior, routing, and graph branching.

## Mock-Only Boundaries

- ERP context is static mock context from `build_mock_context`.
- There are no SAP, Dynamics, Oracle, or custom ERP adapters.
- No approval action is executed.
- Recommendations are rendered as approval recommendations only.

## Intentionally Not Implemented

- No real ERP connectors.
- No approval-specific Harness events such as `approval.*`.
- No LangGraph interrupt or `PendingHitlRequest` for ERP approval.
- No approve/reject/payment/supplier/contract/budget write action.
- No benchmark suite.
- No rename or deletion of legacy `rfp_security` modules.
- No frontend store or API semantics changes.

## Validation

Initial command with the system Python failed because that interpreter did not have project dependencies:

```text
python -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges
```

Result:

```text
FAILED (errors=3)
ModuleNotFoundError: No module named 'pydantic'
ModuleNotFoundError: No module named 'dotenv'
```

Rerun with the repository virtual environment:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_domain backend.tests.test_erp_approval_routing backend.tests.test_erp_approval_edges
```

Result:

```text
Ran 8 tests in 0.001s
OK
```

Lightweight syntax/import compilation check:

```text
backend\.venv\Scripts\python.exe -m py_compile src/backend/orchestration/executor.py src/backend/orchestration/compiler.py src/backend/orchestration/nodes/erp_approval.py src/backend/decision/lightweight_router.py src/backend/domains/erp_approval/service.py
```

Result: OK.

LangGraph compiler smoke check:

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

Legacy RFP/security compatibility validation:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
```

Result:

```text
Ran 11 tests in 0.006s
OK
```

## Phase 2 Recommendation

Add read-only ERP context adapter interfaces next, starting with a mock adapter that normalizes approval request, vendor, budget, invoice, PO, and policy evidence into context records. Keep all write actions out of scope until guarded ERP action phases.
