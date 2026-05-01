# RUNBOOK

## Repository Map

- [src/backend](src/backend): backend product code
- [src/frontend](src/frontend): frontend approval workbench
- [src/backend/knowledge](src/backend/knowledge): retrieval abstractions for policy and business context
- [src/backend/orchestration](src/backend/orchestration): LangGraph orchestration and execution paths
- [src/backend/runtime](src/backend/runtime): HarnessRuntime-owned lifecycle wiring
- [src/backend/domains/rfp_security](src/backend/domains/rfp_security): legacy RFP/security compatibility domain
- [backend/benchmarks](backend/benchmarks): benchmark runners, suites, evaluators, and case files
- [backend/tests](backend/tests): backend tests
- [backend/scripts/dev](backend/scripts/dev): local startup and validation scripts
- [knowledge/ERP Approval](knowledge/ERP%20Approval): future ERP approval policy/context placeholder
- [knowledge/RFP Security](knowledge/RFP%20Security): legacy sample corpus still used by compatibility checks

## Common Tasks

Install backend dependencies:

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

Install frontend dependencies:

```powershell
cd src\frontend
npm install
cd ..\..
```

Start the app:

```powershell
.\backend\scripts\dev\start-dev.ps1 -InstallIfMissing
```

Run focused backend compatibility tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Run final Phase 14 MVP validation:

```powershell
.\backend\scripts\dev\validate-phase14-mvp.ps1
```

Run the legacy RFP/security compatibility suite:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --output artifacts\benchmarks\latest\rfp_security_full.json
```

Run legacy pressure mode:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 2 `
  --pressure-matrix `
  --pressure-rounds 1 `
  --output artifacts\benchmarks\latest\rfp_security_pressure_matrix.json
```

Run live validation for the existing harness:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_live_validation.py `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_live_validation_smoke.json
```

Build the frontend:

```powershell
cd src\frontend
npm run build
```

## Environment Variables

Use [backend/.env.example](backend/.env.example).

The most common local variables are:

- model/provider API keys
- backend host and port overrides
- LangSmith and OTel settings if you want tracing

Do not commit real keys.

## Benchmarks And Reports

- legacy compatibility benchmark commands and methodology: [docs/ops/benchmarking.md](docs/ops/benchmarking.md)
- future ERP approval product plan: [docs/product/erp_approval_agent_plan.md](docs/product/erp_approval_agent_plan.md)
- MVP acceptance checklist: [docs/product/mvp_acceptance_checklist.md](docs/product/mvp_acceptance_checklist.md)
- historical RFP/security reports remain under [reports](reports)

## Operating Posture

ERP Approval Agent Workbench should provide approval recommendation, not autonomous final execution. Phase 14 is the MVP closure boundary: do not add connector expansion, simulation expansion, audit workspace expansion, mapper diagnostics, profile notes, benchmarks, live ERP connections, or ERP write actions inside this closed MVP. Future ERP write actions must be guarded by explicit HITL, idempotency, and auditable approval trace requirements in a new explicit phase.
