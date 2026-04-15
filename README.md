# RFP Security RAG

RFP Security RAG is a local-first agent workbench for answering security questionnaires and drafting RFP sections with auditable evidence.

It keeps the proven Ragclaw runtime core, but this repository is scoped around one domain:

- normalize questionnaire fields and RFP prompts into a stable answer schema
- retrieve security evidence with a pluggable knowledge-layer retrieval strategy
- generate section-level draft answers with citations, approval guards, and explicit insufficiency handling
- benchmark the whole path with repeatable retrieval, groundedness, and completeness metrics

## What Is In This Repo

- [src/backend/domains/rfp_security](src/backend/domains/rfp_security)
  - domain schemas, normalizers, prompts, policies, evidence planning, verifier, and exports
- [src/backend/knowledge](src/backend/knowledge)
  - retrieval strategy interface, registry, orchestrator, evidence organization, hybrid retriever plumbing
- [knowledge/RFP Security](knowledge/RFP%20Security)
  - sample corpus for security docs, approval policy, historical proposal snippets, and legacy answers
- [backend/benchmarks/cases/rfp_security](backend/benchmarks/cases/rfp_security)
  - 20-case evaluation pack covering extraction, missing evidence, conflicts, and approval-gated answers
- [backend/benchmarks/rfp_security_suite.py](backend/benchmarks/rfp_security_suite.py)
  - suite runner for standalone RFP/security benchmark evaluation

## Headline Results

From the tuned full-suite run documented in [reports/rfp_security_quality_delta.md](reports/rfp_security_quality_delta.md):

| Metric | Tuned Result |
| --- | ---: |
| Overall pass rate | `1.0000` |
| Retrieval hit@k | `1.0000` |
| Retrieval recall@k | `0.9722` |
| Evidence coverage | `0.8889` |
| Citation precision | `0.4478` |
| Citation recall | `0.8889` |
| Groundedness | `0.7500` |
| Response completeness | `0.8750` |
| Unsupported claim rate | `0.0000` |

The quality-tuned branch reached the requested merge thresholds without changing the retrieval strategy interface or the canonical runtime event semantics.

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

3. Run the focused RFP/security validation.

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator
```

4. Run the benchmark smoke suite.

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
```

If you want the full local workbench UI, the repo still supports the existing full-stack startup path:

```powershell
.\backend\scripts\dev\start-dev.ps1 -InstallIfMissing
```

## Benchmark Commands

Full RFP/security suite:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --output artifacts\benchmarks\latest\rfp_security_full.json
```

Pressure matrix:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 2 `
  --pressure-matrix `
  --pressure-rounds 1 `
  --output artifacts\benchmarks\latest\rfp_security_pressure_matrix.json
```

Live validation smoke:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_live_validation.py `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_live_validation_smoke.json
```

## Safety And Governance

- every exported answer is evidence-first and audit-friendly
- unsupported claims are downgraded to explicit insufficiency instead of padded prose
- approval-gated fields stay approval-gated
- retrieval remains replaceable through the knowledge-layer strategy interface
- `HarnessRuntime` remains the lifecycle owner; this repo does not introduce a second runtime

## Key Docs

- [QUICKSTART.md](QUICKSTART.md)
- [RUNBOOK.md](RUNBOOK.md)
- [LOCAL_DEV.md](LOCAL_DEV.md)
- [CODEX_HANDOFF.md](CODEX_HANDOFF.md)
- [docs/ops/benchmarking.md](docs/ops/benchmarking.md)
- [reports/rfp_security_benchmark_report.md](reports/rfp_security_benchmark_report.md)
- [reports/rfp_security_quality_tuning_report.md](reports/rfp_security_quality_tuning_report.md)
- [reports/rfp_security_resume_metrics.md](reports/rfp_security_resume_metrics.md)
