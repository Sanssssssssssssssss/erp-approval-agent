# Evidence-First Case Agent Toy Audit Self-Critique

## Executive Summary

- Toy cases: 82
- Passed: 82
- Failed: 0
- Critical failures: 0
- Major failures: 0
- Final result: strict local audit passed with no critical or major failures.

This is a local strict regression/self-critique audit over fictional data. It is not a production benchmark, not live ERP validation, and not proof of approval accuracy.

## Dataset Composition

- By approval type: {'budget_exception': 10, 'contract_exception': 10, 'expense': 13, 'invoice_payment': 14, 'purchase_requisition': 19, 'supplier_onboarding': 12, 'unknown': 4}
- Top tags: {'missing_evidence': 37, 'adversarial': 22, 'high_risk': 21, 'prompt_injection': 20, 'malicious': 16, 'complete_evidence': 13, 'conflict': 7, 'one_sentence': 6, 'cross_type': 1, 'ambiguous': 1}
- Covered categories: one-sentence requests, complete evidence, missing evidence, conflicting records, high-risk exceptions, prompt injection, ambiguous cross-type prompts.

## Overall Pass/Fail

- Severity counts: {'pass': 82}
- Critical cases: none
- Lax approval cases: none
- Unsupported citation cases: none

## What The Agent Did Wrong In Early Rounds

- Treated generic policy evidence as if it satisfied every specialized policy requirement.
- Allowed contract and budget exception cases to produce overly strong approval recommendations when they should route to legal/finance review.
- Failed to convert blocked vendor status into a blocking/conflict signal for supplier onboarding.
- Treated `False` from absent fields as a valid claim, causing missing line items and expense dates to look supported.
- Compared unrelated status fields such as budget `available` and vendor `active` as contradictions.
- Omitted the non-action statement from the early final-answer preview used by the audit.

## Which Stage Was Too Loose

- evidence_claim_builder: falsey field handling, generic policy mapping, contract clause granularity, blocked vendor interpretation.
- contradiction_detector: field canonicalization was too coarse for status values and too weak for explicit conflict claims.
- control_matrix: supplier onboarding lacked a supplier risk-clear control.
- recommendation_drafter: contract and budget exceptions could be too close to ordinary recommendation flow.
- final_rendering/audit preview: non-action boundary needed to be present before long markdown content.

## Fixes Applied In Round 1

- Put `No ERP write action was executed.` at the front of audit final previews.
- Split generic policy claims from procurement, expense, invoice payment, supplier onboarding, legal, and finance/budget policy claims.
- Added explicit contract-derived claims for framework/NDA/DPA/payment-basis evidence.
- Routed contract exceptions to legal review and budget exceptions to finance review even when evidence is otherwise complete.

## Fixes Applied In Round 2

- Added record-type-aware status contradiction detection to avoid false budget/vendor status conflicts.
- Marked blocked vendor profile evidence as conflict instead of supported.
- Added explicit conflict items for claims that already carry `verification_status=conflict`.
- Made invoice payment terms and supplier contract/NDA/DPA evidence required rather than conditional.
- Added supplier risk-clear control coverage for supplier onboarding.

## Fixes Applied In Round 3

- Fixed `_claim_if(False)` so absent optional fields no longer create supported claims.
- Tightened finance review/policy mapping so a budget policy is not automatically a finance approval matrix.
- Made contract payment terms required for contract exception review.
- Corrected the adversarial cross-type conflict fixture so it keeps missing approval request evidence while still exercising conflict detection.

## Final Remaining Risks

- The cases are fictional and deterministic; they do not validate real ERP data quality.
- The audit does not call a real LLM, so it does not evaluate prompt robustness under live model variance.
- Provider fixtures and mock context are representative only, not complete ERP schemas.
- Human reviewers still need to inspect policy coverage before release.
- UI quality and HITL presentation should continue to be manually browser-tested with screenshots in future frontend work.

## Why This Is Still Not Production ERP Automation

- No real ERP connector is enabled by default.
- No live network call, real LLM call, capability invocation, or ERP write action is performed.
- Action proposals remain `executable=false`.
- HITL approve still means accepting or editing the agent recommendation only, not approving an ERP object.
- The audit is a regression/self-critique harness, not benchmark-proven approval accuracy.

## What Human Reviewers Should Inspect Before Release

- Whether the requirement matrix matches the organization's real policies.
- Whether mocked context records represent the minimum evidence expected by finance, procurement, legal, and compliance teams.
- Whether final recommendations are readable enough for business users.
- Whether frontend HITL and evidence displays are usable after manual screenshot and click/scroll testing.
- Whether future live connector work preserves read-only/no-network defaults until explicitly approved.

## Final Recommendation For Human Reviewer

The evidence-first refactor is much stricter than the earlier recommendation-centric flow and now blocks one-sentence, missing-evidence, prompt-injection, conflict, and high-risk toy cases in the local strict audit. Accepting this refactor should still require human review of this report and the generated latest audit report.

请人工 reviewer / 项目负责人审核本报告后，再决定是否接受 evidence-first refactor。
