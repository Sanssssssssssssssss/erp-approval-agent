# CODEX_HANDOFF

This repository is no longer a generic agent sandbox. Treat it as an RFP/security answer drafting product with a benchmarkable retrieval pipeline.

## First Read

- [README.md](README.md)
- [RUNBOOK.md](RUNBOOK.md)
- [docs/ops/benchmarking.md](docs/ops/benchmarking.md)
- [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
- [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)

## Architecture Invariants

Keep these intact unless a task explicitly changes them:

- `HarnessRuntime` is still the lifecycle owner
- canonical harness events remain the execution truth
- retrieval strategy abstraction lives in the knowledge layer, not the runtime layer
- the existing benchmark framework is the only benchmark framework
- evidence-first answer governance matters more than surface fluency

Do not add a second runtime.
Do not bypass evidence planning and verifier paths with hidden side channels.
Do not trade unsupported-claim safety for cosmetic completeness.

## Where To Look First

- domain logic: [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
- retrieval abstraction: [src/backend/knowledge/retrieval_strategy.py](src/backend/knowledge/retrieval_strategy.py)
- retrieval registry: [src/backend/knowledge/retrieval_registry.py](src/backend/knowledge/retrieval_registry.py)
- knowledge orchestrator: [src/backend/knowledge/orchestrator.py](src/backend/knowledge/orchestrator.py)
- benchmark suite: [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)
- benchmark runner: [backend/benchmarks/run_harness_benchmark.py](backend/benchmarks/run_harness_benchmark.py)
- live validation: [backend/benchmarks/run_harness_live_validation.py](backend/benchmarks/run_harness_live_validation.py)

## What Good Looks Like

- grounded answers with direct citations
- explicit `insufficient_evidence` or approval escalation when support is weak
- retrieval recall stays high without flooding the answer with loose citations
- benchmark artifacts stay reproducible and carry `execution_metadata`

## Local Commands

Focused tests:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

Smoke benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

Full benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --output artifacts\benchmarks\latest\rfp_security_full.json
```

## Secrets

Use your own local `backend/.env`.
Do not print or commit real keys.
Use [backend/.env.example](backend/.env.example) for variable names.
