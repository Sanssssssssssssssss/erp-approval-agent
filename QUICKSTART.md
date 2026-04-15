# QUICKSTART

This is the fastest path to a working RFP/security benchmark and draft-generation setup.

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

Edit `backend/.env` and fill in your own model and provider keys.

## 3. Run the focused RFP/security tests

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

## 4. Run a smoke benchmark

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

## 5. Optional full-stack local run

If you want the UI and API together:

```powershell
.\backend\scripts\dev\start-dev.ps1 -InstallIfMissing
```

Default URLs:

- Frontend: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- Backend: [http://127.0.0.1:8015](http://127.0.0.1:8015)
- Health: [http://127.0.0.1:8015/health](http://127.0.0.1:8015/health)
- Metrics: [http://127.0.0.1:8015/metrics](http://127.0.0.1:8015/metrics)

## If You Want More Detail

- ops and benchmark commands: [docs/ops/benchmarking.md](docs/ops/benchmarking.md)
- local run guide: [LOCAL_DEV.md](LOCAL_DEV.md)
- architecture handoff: [CODEX_HANDOFF.md](CODEX_HANDOFF.md)
