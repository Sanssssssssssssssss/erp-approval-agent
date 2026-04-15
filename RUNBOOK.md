# RUNBOOK

## Repository Map

- [src/backend](src/backend): backend product code
- [src/frontend](src/frontend): frontend workbench
- [src/backend/domains/rfp_security](src/backend/domains/rfp_security): RFP/security domain logic
- [backend/benchmarks](backend/benchmarks): benchmark runners, suites, evaluators, and case files
- [backend/tests](backend/tests): backend tests
- [backend/scripts/dev](backend/scripts/dev): local startup and validation scripts
- [knowledge/RFP Security](knowledge/RFP%20Security): sample corpus for this domain

## Common Tasks

Install backend dependencies:

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..
```

Start the app:

```powershell
.\backend\scripts\dev\start-dev.ps1 -InstallIfMissing
```

Run the focused RFP suite:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --output artifacts\benchmarks\latest\rfp_security_full.json
```

Run pressure mode:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 2 `
  --pressure-matrix `
  --pressure-rounds 1 `
  --output artifacts\benchmarks\latest\rfp_security_pressure_matrix.json
```

Run live validation:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_live_validation.py `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_live_validation_smoke.json
```

## Environment Variables

Use [backend/.env.example](backend/.env.example).

The most common local variables are:

- model/provider API keys
- backend host and port overrides
- LangSmith and OTel settings if you want tracing

## Benchmarks And Reports

- benchmark commands and methodology: [docs/ops/benchmarking.md](docs/ops/benchmarking.md)
- headline RFP results: [reports/rfp_security_benchmark_report.md](reports/rfp_security_benchmark_report.md)
- tuned quality analysis: [reports/rfp_security_quality_tuning_report.md](reports/rfp_security_quality_tuning_report.md)
- baseline vs tuned delta: [reports/rfp_security_quality_delta.md](reports/rfp_security_quality_delta.md)
