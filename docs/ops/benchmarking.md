# RFP Security Benchmarking

## Benchmark Principles

- baseline first
- compare runs with the same Git SHA and backend config when possible
- keep raw JSON artifacts
- keep human-readable markdown summaries
- never silently skip missing infrastructure
- prefer evidence-grounded quality gains over prompt-only cosmetics

## Primary Entry Points

Focused RFP/security benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --output artifacts\benchmarks\latest\rfp_security_full.json
```

Smoke benchmark:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_smoke.json
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

Live validation:

```powershell
.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_live_validation.py `
  --limit 3 `
  --output artifacts\benchmarks\latest\rfp_security_live_validation_smoke.json
```

## Execution Metadata

Benchmark outputs include `execution_metadata` with:

- capture time
- Git SHA
- Python version
- platform
- working directory
- benchmark selection config
- retrieval strategy and suite config

## Current RFP Suite Shape

The `rfp_security` suite covers at least these scenarios:

- RFP section extraction
- security questionnaire field answering
- missing evidence handling
- conflicting evidence handling
- approval-required answers

Current pressure-matrix dimensions:

- concurrency: `1 / 2 / 4 / 8`
- rewrite: `on / off`
- reranker: `on / off`
- top_k: `5 / 10`
- strategy: `baseline_hybrid`

## Current Tuned Snapshot

From [reports/rfp_security_quality_delta.md](../../reports/rfp_security_quality_delta.md):

- overall pass rate: `1.0000`
- retrieval hit@k: `1.0000`
- retrieval recall@k: `0.9722`
- evidence coverage: `0.8889`
- citation precision: `0.4478`
- citation recall: `0.8889`
- groundedness: `0.7500`
- response completeness: `0.8750`
- unsupported claim rate: `0.0000`

## Interpretation Notes

- `unsupported_claim_rate = 0.0` is a hard guardrail, not a nice-to-have
- `citation_precision` improved because the tuned branch prunes weak citations instead of spraying every retrieved document
- `groundedness` and `response_completeness` should rise together through stronger evidence mapping, not evaluator loopholes
- if a future change boosts completeness while harming support quality, treat that as a regression
