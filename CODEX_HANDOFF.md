# CODEX_HANDOFF

Treat this repository as ERP Approval Agent Workbench. It is not a generic agent sandbox and is no longer primarily an RFP/security product.

Phase 0 semantic migration is complete. Phase 1 added the minimal LLM-first ERP approval graph skeleton. Current work should treat `erp_approval` as an implemented backend graph path, while still preserving mock-only/read-only boundaries.

## First Read

- [README.md](README.md)
- [docs/product/erp_approval_agent_plan.md](docs/product/erp_approval_agent_plan.md)
- [RUNBOOK.md](RUNBOOK.md)
- [LOCAL_DEV.md](LOCAL_DEV.md)
- [src/backend/runtime/runtime.py](src/backend/runtime/runtime.py)
- [src/backend/orchestration](src/backend/orchestration)
- [src/backend/knowledge](src/backend/knowledge)

## Architecture Invariants

Keep these intact unless a task explicitly changes them:

- `HarnessRuntime` is the lifecycle owner.
- LangGraph is the orchestration graph layer.
- canonical harness events remain the execution truth.
- HITL and checkpoint semantics remain durable and auditable.
- knowledge retrieval abstractions remain the context/evidence boundary.
- capability governance remains the boundary for tool execution.

Do not add a second runtime.
Do not add a second agent framework.
Do not bypass graph/HITL governance for tool execution or irreversible actions.
Do not over-engineer the migration.

## Product Direction

The intended product is an LLM-first approval reasoning workbench for ERP business approvals. The `erp_approval` domain now exists beside the legacy `rfp_security` module.

LLM-first is the intended approval reasoning strategy:

- prompts and structured LLM outputs should carry the approval analysis.
- graph nodes should define the execution boundary and audit stages.
- tools and external actions must remain graph/HITL governed.
- irreversible ERP actions must never bypass explicit approval controls.

Prefer small, reviewable changes that keep the current local workbench running.

## Implemented ERP Skeleton

Phase 1 implemented this skeleton:

```text
bootstrap
-> route
-> skill
-> memory_retrieval
-> erp_intake
-> erp_context
-> erp_reasoning
-> erp_guard
-> erp_finalize
-> finalize
```

It produces an approval recommendation, not autonomous final execution. Phase 2 adds read-only context adapter interfaces and mock records. Real ERP connectors, real HITL approval cards, and write actions remain future work.

Current capabilities:

- LLM-first ERP intake and reasoning prompts.
- mock ERP/policy context.
- soft human review gate via `human_review_required`.
- deterministic guard for weak evidence and unsafe next actions.

Still absent:

- real ERP connector.
- real approval write action.
- real ERP HITL approval card.
- ERP benchmark suite.

## Legacy Compatibility

Do not remove or aggressively rename these:

- [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
- [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)
- [backend/benchmarks/cases/rfp_security](backend/benchmarks/cases/rfp_security)
- [knowledge/RFP Security](knowledge/RFP%20Security)

Existing RFP/security tests and benchmarks are compatibility checks until ERP-specific suites are added.

## Local Commands

Focused backend compatibility tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Focused ERP approval tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_erp_approval_domain `
  backend.tests.test_erp_approval_routing `
  backend.tests.test_erp_approval_edges `
  backend.tests.test_erp_approval_context_adapter `
  backend.tests.test_erp_approval_graph_smoke
```

Legacy RFP/security compatibility smoke benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Frontend build:

```powershell
cd src\frontend
npm run build
```

## Secrets

Use your own local `backend/.env`.
Do not print or commit real keys.
Use [backend/.env.example](backend/.env.example) for variable names.
