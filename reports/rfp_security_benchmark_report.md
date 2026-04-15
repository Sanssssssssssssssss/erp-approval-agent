# RFP Security Benchmark Report

## Scope

This repository packages the RFP/security baseline and tuned quality path as a standalone project.

The benchmark scope is:

- domain pack for RFP section drafting and security questionnaire answering
- pluggable retrieval strategy interface in the knowledge layer
- `baseline_hybrid` retrieval strategy built on the existing hybrid RAG stack
- 20-case `rfp_security` benchmark suite
- pressure matrix across concurrency, rewrite, reranker, and top-k settings

## Canonical Commands

Smoke:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\<timestamp>\rfp_security_smoke.json
```

Full suite:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --output artifacts\benchmarks\<timestamp>\rfp_security_full.json
```

Pressure matrix:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 2 `
  --pressure-matrix `
  --pressure-rounds 1 `
  --output artifacts\benchmarks\<timestamp>\rfp_security_pressure_matrix.json
```

Live validation smoke:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_live_validation.py `
  --limit 3 `
  --output artifacts\benchmarks\<timestamp>\rfp_security_live_validation_smoke.json
```

## Tuned Headline Metrics

These are the current reference numbers for the standalone repository:

- total cases: `20`
- overall pass rate: `1.0000`
- retrieval hit@k: `1.0000`
- retrieval recall@k: `0.9722`
- evidence coverage: `0.8889`
- citation precision: `0.4478`
- citation recall: `0.8889`
- groundedness: `0.7500`
- relevance: `0.9558`
- response completeness: `0.8750`
- unsupported claim rate: `0.0000`
- error rate: `0.0000`

## Pressure-Matrix Snapshot

- concurrency grid: `1 / 2 / 4 / 8`
- rewrite: `on / off`
- reranker: `on / off`
- top_k: `5 / 10`
- strategy: `baseline_hybrid`

Observed tuned summary:

- pass rate: `1.0000`
- error rate: `0.0000`
- p50 latency: `8122.5 ms`
- p95 latency: `19592.1 ms`
- retrieval recall@k: `1.0000`
- groundedness: `0.8875`
- response completeness: `1.0000`
- unsupported claim rate: `0.0000`

## Live Validation Guardrail

The RFP/security extraction and tuning work did not break the existing runtime path:

- total smoke cases: `3`
- passed: `3`
- failed: `0`
- trace completeness: `1.0000`
- retrieval trace presence: `1.0000`
- tool trace presence: `1.0000`
- completion integrity: `1.0000`
- session persistence integrity: `1.0000`
- SSE order integrity: `1.0000`

## Notes

- This project keeps the existing benchmark framework; it does not introduce a second runner.
- `execution_metadata` is still attached to benchmark artifacts.
- If you need fresh JSON outputs, re-run the canonical commands above and keep the generated files under `artifacts/benchmarks/<timestamp>/`.
