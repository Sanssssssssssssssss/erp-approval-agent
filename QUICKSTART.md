# QUICKSTART

This is the fastest path to a working local ERP Approval Agent Workbench. Phase 14 is the MVP closure point: the local workbench runs with ERP approval graph, trace, audit, simulation, and connector diagnostics features, while still keeping legacy RFP/security compatibility checks.

## 1. Create the backend venv

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

## 2. Configure local environment variables

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

Edit `backend/.env` and fill in your own model and provider keys. Do not commit real keys.

## 3. Install frontend dependencies

```powershell
cd src\frontend
npm install
cd ..\..
```

## 4. Run final MVP validation

```powershell
.\backend\scripts\dev\validate-phase14-mvp.ps1
```

For backend-only validation:

```powershell
.\backend\scripts\dev\validate-phase14-mvp.ps1 -SkipFrontend
```

## 5. Run focused backend compatibility tests

These tests still exercise the legacy RFP/security compatibility path until ERP-specific tests are added.

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

## 6. Run a legacy compatibility smoke benchmark

This command validates the existing benchmark harness and retrieval path. It is not an ERP approval benchmark.

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

## 7. Start the local workbench

```powershell
.\backend\scripts\dev\start-dev.ps1 -InstallIfMissing
```

Default URLs:

- Frontend: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- Backend: [http://127.0.0.1:8015](http://127.0.0.1:8015)
- Health: [http://127.0.0.1:8015/health](http://127.0.0.1:8015/health)
- Metrics: [http://127.0.0.1:8015/metrics](http://127.0.0.1:8015/metrics)

## More Detail

- local run guide: [LOCAL_DEV.md](LOCAL_DEV.md)
- operator runbook: [RUNBOOK.md](RUNBOOK.md)
- future product plan: [docs/product/erp_approval_agent_plan.md](docs/product/erp_approval_agent_plan.md)
- MVP acceptance checklist: [docs/product/mvp_acceptance_checklist.md](docs/product/mvp_acceptance_checklist.md)
- architecture handoff: [CODEX_HANDOFF.md](CODEX_HANDOFF.md)
