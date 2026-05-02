# Manual Evidence Fixture Agent Repair

## Summary

The previous evidence-first refactor hardened the structured domain pipeline, but the real user path still felt immature because mock ERP context mostly exposed summary records instead of visible approval materials. A reviewer could see a recommendation without seeing the approval form, invoice, PO, GRN, receipt, quote, budget support, vendor support, or policy excerpt that justified it.

This repair adds a local fictional evidence pack and makes the final case analysis render evidence materials and paths before recommendation text.

## What Changed

- Added local fictional evidence files under `knowledge/ERP Approval/sample_evidence`.
- Expanded `backend/fixtures/erp_approval/mock_context_records.json` with evidence-backed records for:
  - PR-1001 approval form, budget, vendor evidence; quote intentionally missing.
  - PR-1002 complete purchase evidence chain with quote.
  - EXP-2001 receipt, duplicate check, and limit check.
  - INV-3001 invoice, PO, GRN, vendor, payment terms, duplicate payment check, and policy excerpt.
  - VEND-4001 supplier onboarding checks with sanctions pending.
- Allowed local evidence record types such as `quote`, `receipt`, `duplicate_check`, `limit_check`, and `payment_terms` to enter the approval context bundle without changing live connector operations.
- Updated case rendering to show `证据材料与链接 / Evidence artifacts and links`.
- Added deterministic prompt-boundary detection for instructions such as ignore policy, skip citations, directly approve, or execute payment.
- Added manual smoke runner:
  - `backend.benchmarks.erp_approval_manual_agent_smoke`
  - latest outputs:
    - `reports/evaluations/manual_agent_smoke_latest.md`
    - `reports/evaluations/manual_agent_smoke_latest.json`

## Manual Smoke Result

- Cases: 9
- Passed: 9
- Failed: 0

Key checks:

- One-sentence direct approval prompt did not produce `recommend_approve`.
- PR-1001 displayed approval/budget/vendor evidence but did not approve because quote/price-basis evidence is missing.
- PR-1002 produced a non-executing approve recommendation only after full mock evidence was present.
- INV-3001 displayed invoice, PO, GRN, payment terms, duplicate payment check, vendor, and policy evidence.
- Prompt injection asking to ignore policy/no citation/directly approve was downgraded and required human review.
- All action proposals remained `executable=false`.
- Final answers retained `No ERP write action was executed`.

## Boundary

This remains local mock evidence only. It is not live ERP integration, not a production benchmark, and not ERP action execution.

