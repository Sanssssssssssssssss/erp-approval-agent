# ERP Approval Agent Workbench

ERP Approval Agent Workbench is a local-first, LLM-first, graph-driven approval agent workbench for ERP business workflows. It helps review approval requests with retrieved business context, policy context, auditable reasoning traces, and human-in-the-loop approval controls.

The repository target identity is `erp-approval-agent`. Phase 0 aligned the public product language, and Phase 1 added the first minimal ERP approval graph skeleton.

## Product Direction

This project is becoming an enterprise approval assistant for ERP workflows such as:

- purchase requisitions
- expense approvals
- invoice and payment review
- supplier onboarding
- contract exception review
- budget exception review

The intended future product posture is approval recommendation, not autonomous final execution. LLM-first approval reasoning is the primary direction, but graph nodes, HarnessRuntime events, checkpoints, HITL gates, and capability governance remain the execution boundary.

## Current Architecture Anchors

These anchors stay intact across the migration:

- `HarnessRuntime` remains the HarnessRuntime-owned execution lifecycle.
- LangGraph remains the graph-driven approval workflow orchestration layer.
- existing harness event semantics remain the execution truth.
- checkpoint and human-in-the-loop approval control concepts remain in place.
- knowledge retrieval abstractions remain the path for ERP policy and business context retrieval.
- no second runtime, second agent framework, or parallel lifecycle owner is introduced.

## Legacy Compatibility

The previous implementation focused on RFP/security answer drafting and security questionnaire validation. That code remains available as legacy compatibility while ERP-specific domains are introduced later:

- [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
  - legacy domain schemas, prompts, policies, evidence planning, verifier, and exports
- [knowledge/RFP Security](knowledge/RFP%20Security)
  - legacy corpus still used by existing tests and benchmark smoke checks
- [backend/benchmarks/cases/rfp_security](backend/benchmarks/cases/rfp_security)
  - legacy 20-case compatibility evaluation pack
- [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)
  - legacy suite runner used until ERP-specific benchmark suites exist

These legacy paths are not the new product identity. They are retained to avoid unnecessary breakage during the semantic migration.

## Current Phase Status

Completed:

- Phase 0 product-semantic migration.
- Phase 1 LLM-first ERP approval graph skeleton:
  `bootstrap -> route -> skill -> memory_retrieval -> erp_intake -> erp_context -> erp_reasoning -> erp_guard -> erp_finalize -> finalize`.
- mock ERP/policy context for approval reasoning.
- soft human review gate through structured recommendations and deterministic guard checks.

Current Phase 2 target:

- read-only ERP context adapter interface.
- normalized mock ERP records for approval request, vendor, budget, purchase order, invoice, goods receipt, contract, and policy context.

Still not implemented:

- real ERP connectors.
- approval write actions.
- production ERP automation.
- real HITL approval cards for ERP decisions.
- ERP benchmark accuracy claims.

## Future ERP Approval Direction

The current implemented skeleton flow is:

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

It produces a structured approval recommendation with confidence, missing information, risk flags, citations, and proposed next action. Phase 2 keeps context read-only and mock-only.

## Quick Start

1. Create the backend environment.

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

2. Copy local environment variables.

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

3. Install frontend dependencies.

```powershell
cd src\frontend
npm install
cd ..\..
```

4. Start the local workbench UI and API.

```powershell
.\backend\scripts\dev\start-dev.ps1 -InstallIfMissing
```

Default URLs:

- Frontend: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- Backend: [http://127.0.0.1:8015](http://127.0.0.1:8015)
- Health: [http://127.0.0.1:8015/health](http://127.0.0.1:8015/health)
- Metrics: [http://127.0.0.1:8015/metrics](http://127.0.0.1:8015/metrics)

## Validation Commands

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

Legacy RFP/security compatibility benchmark smoke:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Frontend production build:

```powershell
cd src\frontend
npm run build
```

## Safety And Governance

- every approval recommendation should be evidence-first and audit-friendly.
- unsupported claims should be surfaced as missing context or insufficient evidence.
- human-in-the-loop approval control remains required before irreversible actions.
- retrieval remains replaceable through the knowledge-layer strategy interface.
- `HarnessRuntime` remains the lifecycle owner.
- future ERP write actions must be idempotent, auditable, and guarded by explicit HITL.

## Non-Claims

This repository does not currently claim to:

- integrate with SAP, Dynamics, Oracle, or any other live ERP system.
- automatically approve ERP requests.
- provide production-ready ERP automation.
- benchmark-prove ERP approval accuracy.

Current ERP work includes a graph skeleton and mock read-only context. Legacy RFP/security validation remains only a compatibility signal until ERP-specific suites are added.

## Key Docs

- [QUICKSTART.md](QUICKSTART.md)
- [RUNBOOK.md](RUNBOOK.md)
- [LOCAL_DEV.md](LOCAL_DEV.md)
- [CODEX_HANDOFF.md](CODEX_HANDOFF.md)
- [docs/product/erp_approval_agent_plan.md](docs/product/erp_approval_agent_plan.md)
- [docs/ops/benchmarking.md](docs/ops/benchmarking.md)
