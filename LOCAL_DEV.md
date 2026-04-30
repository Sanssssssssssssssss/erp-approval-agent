# LOCAL_DEV

## Verified Local Baseline

- Windows
- Python `3.13`
- Node.js `v24.14.0`
- npm `11.9.0`

## Product Context

The local app is ERP Approval Agent Workbench. Phase 0 is a product-semantic migration, so the workbench can run while legacy RFP/security compatibility tests remain in place.

## Backend Setup

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

## Frontend Setup

```powershell
cd src/frontend
npm install
cd ../..
```

## VS Code Shortcuts

- [.vscode/settings.json](.vscode/settings.json)
- [.vscode/tasks.json](.vscode/tasks.json)
- [.vscode/launch.json](.vscode/launch.json)
- [.vscode/extensions.json](.vscode/extensions.json)

## Start Commands

Full stack:

```powershell
.\backend\scripts\dev\start-dev.ps1
```

Forced restart:

```powershell
.\backend\scripts\dev\start-dev.ps1 -Restart
```

Backend only:

```powershell
powershell -ExecutionPolicy Bypass -File .\backend\scripts\dev\start-backend-dev.ps1
```

Frontend only:

```powershell
powershell -ExecutionPolicy Bypass -File .\backend\scripts\dev\start-frontend-dev.ps1
```

## Core Validation Commands

Focused backend compatibility tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Full backend regression:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover backend/tests
```

Legacy RFP/security compatibility smoke benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Live validation smoke for the existing harness:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_live_validation.py `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_live_validation_smoke.json
```

Frontend build:

```powershell
cd src/frontend
npm run build
```

Frontend UI verification, if browser dependencies are available:

```powershell
cd src/frontend
npm run verify:chat-ui
```

## Main Config Entrypoints

- `backend/.env`
- [src/backend/runtime/config.py](src/backend/runtime/config.py)
- [langgraph.json](langgraph.json)

## Notes

- benchmark and live-validation artifacts are written under `artifacts/`
- [knowledge/ERP Approval](knowledge/ERP%20Approval) is the future ERP approval context placeholder
- [knowledge/RFP Security](knowledge/RFP%20Security) remains for legacy compatibility
- keep this repo local-first by default; external infra and observability are optional
