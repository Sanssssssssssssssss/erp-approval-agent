# CaseHarness P0/P1 Test Hardening

## Summary

This pass turns the strict reviewer test plan into executable P0/P1 regression coverage for the evidence-first approval case workspace.

The focus is not benchmark scoring. It is to catch state pollution, weak evidence acceptance, case drift, model patch overreach, and same-case concurrent turn loss.

## Implemented Coverage

- Long case lifecycle:
  - create case
  - add budget evidence
  - add vendor evidence
  - add quote evidence
  - reject off-topic turn
  - request current reviewer memo
  - assert `case_state.json`, `dossier.md`, `audit_log.jsonl`, turn count, dossier version, accepted evidence, and non-action statement
- Same-case concurrency:
  - submit 10 evidence turns concurrently
  - assert JSON remains valid, no accepted evidence is lost, audit events are appended, and dossier version advances
- CasePatch validator adversarial checks:
  - missing `source_id`
  - missing `claim_ids`
  - unknown claim
  - unknown requirement
  - disallowed intent / patch type
  - execution-like wording in dossier text and stage-model output metadata
- Evidence acceptance boundary:
  - verbal/user statements are rejected as weak evidence
  - structured budget and vendor records are accepted only when they produce supported claims
  - accepted evidence must have `source_id`, `claim_ids`, and `requirement_ids`
- Context assembly drift:
  - synthetic 100+ claim/rejection case state
  - context pack remains bounded and keeps the current budget-related requirement/claim
  - context does not dump full raw history
- Fake LLM stage-model guardrails:
  - invalid JSON falls back to deterministic evidence gate
  - classifier `off_topic` result dominates later reviewer memo role output
  - model output that tries to say "approve/execute/payment" is surfaced as a validator warning and does not write evidence

## Bugs Found And Fixed

1. `po` was matched as a raw substring, so words like `poem` and `laptop` could make an off-topic request look like purchase-order evidence.
   - Fixed by requiring standalone `po`, `po123`, or `po-123` style patterns.

2. Stage-model aggregation let the reviewer memo role override the turn-classifier role.
   - Fixed so `turn_classifier=off_topic` becomes `no_case_change` and clears accepted source IDs.

3. Patch validation did not inspect model role metadata for execution-like wording.
   - Fixed by scanning serialized `model_review` content for forbidden execution semantics.

## Remaining Gaps

- The concurrency coverage is in-process and verifies the current per-case lock. It does not yet prove cross-process safety if multiple backend worker processes write the same case folder.
- Existing frontend verification scripts still need a dedicated Case Workspace E2E flow that starts from the default case tab, submits evidence, scrolls the dossier/checklist/control matrix, and captures screenshots.
- CaseContextAssembler is now bounded and relevance-based, but it does not yet have a formal token budget estimator.
- Fake model tests cover bad JSON and overreach, but they do not yet simulate long multi-role hallucination sequences across 50+ turns.

## Validation Commands

Targeted commands run:

```powershell
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_harness_p0_p1
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_case_harness backend.tests.test_erp_approval_case_review_api backend.tests.test_erp_approval_release_boundary
```

Results:

- `test_erp_approval_case_harness_p0_p1`: 7 tests OK after fixes.
- `test_erp_approval_case_harness + test_erp_approval_case_review_api + test_erp_approval_release_boundary`: 25 tests OK.
- `backend\scripts\dev\validate-phase14-mvp.ps1 -SkipFrontend`: ERP suite 173 tests OK, strict toy audit 82/82, manual smoke 9/9, stress 66/66, maturity benchmark 321 cases average 99.85, legacy 11 tests OK, py_compile OK, compiler smoke OK, `git diff --check` OK.
- `npm run build` under `src\frontend`: Next.js production build OK.
