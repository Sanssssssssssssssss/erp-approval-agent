# RFP Security Quality Tuning Report

## Scope

The tuning pass stays inside the answer-quality boundary:

- [src/backend/domains/rfp_security/prompts.py](../src/backend/domains/rfp_security/prompts.py)
- [src/backend/domains/rfp_security/policies.py](../src/backend/domains/rfp_security/policies.py)
- [src/backend/domains/rfp_security/normalizers.py](../src/backend/domains/rfp_security/normalizers.py)
- [src/backend/domains/rfp_security/planner.py](../src/backend/domains/rfp_security/planner.py)
- [src/backend/domains/rfp_security/verifier.py](../src/backend/domains/rfp_security/verifier.py)
- [src/backend/domains/rfp_security/exports.py](../src/backend/domains/rfp_security/exports.py)
- [backend/benchmarks/rfp_security_suite.py](../backend/benchmarks/rfp_security_suite.py)

It does not change:

- retrieval strategy interface shape
- canonical harness event semantics
- benchmark framework architecture

## What Changed

### 1. Evidence plan before answer generation

The draft path now builds a point-by-point evidence plan before rendering the answer:

- `required_point`
- `mapped_evidence_ids`
- `missing`
- `needs_approval`
- `conflict_note`

### 2. Citation pruning and authoritative evidence preference

The tuned path:

- prefers authoritative evidence families such as `security_controls.md`, `incident_response.md`, `approval_policy.md`, and `privacy_and_subprocessors.json`
- prunes weak fallback citations from historical proposal snippets unless they are the best available direct support
- records only answer-used evidence in the final trace payload

### 3. Question-type templates

The normalizer now classifies questions into template kinds:

- `yes_no_capability`
- `policy_process`
- `certification_compliance`
- `deployment_security_architecture`
- `sla_support`
- `general_rfp`

### 4. Verifier/reviser pass

A deterministic verifier removes or downgrades weak lines instead of letting loosely related evidence appear as direct support.

### 5. Retrieval-side quality help without interface drift

The suite feeds `query_hints=normalized.search_terms` into the existing retrieval request and builds the planning pool from the richer retrieval bundle, while leaving the retrieval strategy interface intact.

## Reference Result

Current tuned full-suite metrics:

- overall pass rate: `1.0000`
- retrieval hit@k: `1.0000`
- retrieval recall@k: `0.9722`
- evidence coverage: `0.8889`
- citation precision: `0.4478`
- citation recall: `0.8889`
- groundedness: `0.7500`
- response completeness: `0.8750`
- unsupported claim rate: `0.0000`
- error rate: `0.0000`

Acceptance check:

- `groundedness >= 0.75`: passed
- `response_completeness >= 0.80`: passed
- `citation_precision >= 0.40`: passed
- `citation_recall >= 0.80`: passed
- `unsupported_claim_rate = 0.0`: passed
- `retrieval_recall_at_k >= 0.85`: passed
- `error_rate = 0.0`: passed

## Reproduce

```powershell
.\backend\.venv\Scripts\python.exe -m unittest `
  backend.tests.test_retrieval_strategy `
  backend.tests.test_rfp_security_domain `
  backend.tests.test_rfp_security_benchmark `
  backend.tests.test_benchmark_evaluator

.\backend\.venv\Scripts\python.exe backend\benchmarks\run_harness_benchmark.py `
  --suite rfp_security `
  --output artifacts\benchmarks\<timestamp>\rfp_security_full.json
```

## Recommendation

Keep the tuned logic as the default path for this repository.

Reason:

- it clears every requested quality threshold
- it keeps `unsupported_claim_rate = 0`
- it improves evidence discipline instead of gaming the evaluator
