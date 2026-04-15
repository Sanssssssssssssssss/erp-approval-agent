# LOCAL_DEV

## Verified Local Baseline

- Windows
- Python `3.13`
- Node.js `v24.14.0`
- npm `11.9.0`

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

Focused RFP/security tests:

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

RFP/security smoke benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Live validation smoke:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_live_validation.py `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_live_validation_smoke.json
```

## Main Config Entrypoints

- `backend/.env`
- [src/backend/runtime/config.py](src/backend/runtime/config.py)
- [langgraph.json](langgraph.json)

## Notes

- the benchmark and live-validation artifacts are written under `artifacts/`
- the RFP/security corpus lives under [knowledge/RFP Security](knowledge/RFP%20Security)
- keep this repo local-first by default; external infra and observability are optional, not mandatory to run the RFP suite
