# CODEX_HANDOFF

Treat this repository as ERP Approval Agent Workbench. It is not a generic agent sandbox and is no longer primarily an RFP/security product.

Phase 0 is semantic migration only. Preserve the runnable architecture while aligning naming, documentation, and frontend copy with the ERP approval direction.

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
Do not over-engineer the Phase 0 migration.

## Product Direction

The intended product is an LLM-first approval reasoning workbench for ERP business approvals. Future work should introduce an `erp_approval` domain incrementally, next to the legacy `rfp_security` module.

LLM-first is the intended approval reasoning strategy:

- prompts and structured LLM outputs should carry the approval analysis.
- graph nodes should define the execution boundary and audit stages.
- tools and external actions must remain graph/HITL governed.
- irreversible ERP actions must never bypass explicit approval controls.

Prefer small, reviewable changes that keep the current local workbench running.

## Future Target Graph

This graph is a future plan, not implemented in Phase 0:

```text
bootstrap
-> route
-> erp_intake_llm
-> erp_context_retrieval
-> erp_policy_context
-> erp_approval_reasoning_llm
-> erp_recommendation_structuring
-> erp_self_check
-> erp_hitl_gate
-> erp_action_proposal
-> erp_finalize_audit
```

The target graph should produce an approval recommendation, not autonomous final execution. It should preserve an auditable approval trace and expose human-in-the-loop approval control before any guarded action.

## Legacy Compatibility

Do not remove or aggressively rename these in Phase 0:

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
