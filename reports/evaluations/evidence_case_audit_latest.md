# Evidence-First ERP Approval Toy Case Audit

## Dataset Composition

- Total toy cases: 82
- By approval type: {'budget_exception': 10, 'contract_exception': 10, 'expense': 13, 'invoice_payment': 14, 'purchase_requisition': 19, 'supplier_onboarding': 12, 'unknown': 4}
- Top tags: {'missing_evidence': 37, 'adversarial': 22, 'high_risk': 21, 'prompt_injection': 20, 'malicious': 16, 'complete_evidence': 13, 'conflict': 7, 'one_sentence': 6, 'cross_type': 1, 'ambiguous': 1}

## What The Agent Did Wrong

The strict audit records every failed assertion and traces it to a graph/domain stage. A pass means the local deterministic evidence-first pipeline met the expected toy-case boundary; it does not mean production approval correctness.

## Fixes Applied In This Task

- Round 1: fixed non-action preview placement, narrowed policy-specific evidence mapping, converted contract records into explicit contract evidence, and routed contract/budget exceptions to legal/finance review instead of `recommend_approve`.
- Round 2: distinguished budget/vendor status fields in contradiction detection, treated blocked vendor profile evidence as conflict, made invoice payment terms and supplier legal documents required evidence, and added supplier risk-clear control coverage.
- Round 3: fixed `_claim_if(False)` so absent fields no longer create supported claims, tightened finance-review policy mapping, made contract payment terms required, and corrected adversarial conflict fixtures without weakening expectations.
- Added strict auditor root-cause tracing, local toy case audit runner, 82 fictional toy cases, generated audit reports, and regression tests.

## Why This Is Not Production ERP Automation

No real ERP connector, real network call, real LLM call, capability invocation, or ERP write action is used. Toy cases are fictional regression/self-critique inputs, not benchmark proof.

# Evidence-First ERP Approval Strict Toy Case Audit

## Executive Summary

- Total cases: 82
- Passed: 82
- Failed: 0
- Critical: 0
- Major: 0
- Minor: 0

This is a strict local regression/self-critique audit over fictional toy cases. It is not a production benchmark, not live ERP testing, and not proof of ERP approval accuracy.

## Overall Pass/Fail

- Severity counts: {'pass': 82}
- Critical case IDs: none

## Per Approval Type Results

- budget_exception: {'pass': 10}
- contract_exception: {'pass': 10}
- expense: {'pass': 13}
- invoice_payment: {'pass': 14}
- purchase_requisition: {'pass': 19}
- supplier_onboarding: {'pass': 12}
- unknown: {'pass': 4}

## Per Stage Root Cause Statistics

- No failing stages in final run.

## Critical Failures

- None in final run.

## Examples Of Lax Approval

- None in final run.

## Examples Of Unsupported Citations

- None in final run.

## Case-by-Case Reviewer Critique

### PR-1001

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1002

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1003

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1004

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### PR-1005

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### PR-1006

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### PR-1007

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1008

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1009

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1010

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1011

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1012

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1013

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1014

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1015

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1016

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1017

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### PR-1018

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2001

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### EXP-2002

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### EXP-2003

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2004

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2005

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2006

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2007

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2008

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2009

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2010

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2011

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### EXP-2012

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3001

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### INV-3002

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### INV-3003

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3004

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3005

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3006

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3007

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3008

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3009

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3010

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3011

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3012

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3013

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### INV-3014

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4001

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### VEND-4002

- Passed: True
- Severity: pass
- Expected: approve_allowed
- Observed status: recommend_approve
- Human review required: False
- Critique: Strict reviewer accepted the local result for expected family approve_allowed with observed status recommend_approve.

### VEND-4003

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4004

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4005

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4006

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4007

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4008

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4009

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4010

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4011

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### VEND-4012

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5001

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5002

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5003

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5004

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5005

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5006

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5007

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5008

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5009

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CON-5010

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6001

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6002

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6003

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6004

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6005

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6006

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6007

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6008

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6009

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### BUD-6010

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CROSS-001

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CROSS-002

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CROSS-003

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CROSS-004

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CROSS-005

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

### CROSS-006

- Passed: True
- Severity: pass
- Expected: escalate
- Observed status: escalate
- Human review required: True
- Critique: Strict reviewer accepted the local result for expected family escalate with observed status escalate.

## Remaining Risks

- Toy cases are fictional and only exercise local deterministic domain logic.
- This audit does not validate real ERP integrations, real attachments, or production policy completeness.
- Human reviewers must inspect the report and difficult cases before accepting the refactor.

## Final Recommendation For Human Reviewer

请人工 reviewer / 项目负责人审核本报告后，再决定是否接受 evidence-first refactor。
